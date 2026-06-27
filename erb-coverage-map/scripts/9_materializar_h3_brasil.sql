-- ==============================================================================
-- MOTOR H3 POSTGIS: MATERIALIZAÇÃO DA MALHA DO BRASIL
-- Objetivo: Cruzar os Setores Censitários (IBGE) com Uso da Terra (IBGE) 
-- usando Hexágonos H3.
-- ==============================================================================

-- PARÂMETROS A SEREM SUBSTITUÍDOS APÓS A INSPEÇÃO DA TABELA BRUTA:
-- <coluna_populacao> : Ex: v0001, pop_total, num_habitantes
-- <coluna_vegetacao> : Ex: classe_uso, nm_veg, tipo_cobertura
-- <codigo_setor>     : Ex: cd_setor, cd_geo_codigo

BEGIN;

-- 1. Habilitamos o H3 e o PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS h3_postgis CASCADE;

-- 2. Limpamos a tabela final caso estejamos reprocessando
DROP TABLE IF EXISTS h3_grid_precalc;

-- 3. Criamos a estrutura final de alta performance
CREATE TABLE h3_grid_precalc (
    h3_index h3index PRIMARY KEY,
    geom geometry(Polygon, 4326),
    populacao_estimada double precision,
    tipo_vegetacao_predominante varchar(255)
);

-- 4. O Pipeline de Processamento (A Mágica)
-- Usamos CTEs (WITH) para não explodir a memória. 
-- O PostgreSQL vai processar isso como um stream otimizado.
WITH 

-- A) Padronização de Projeção Geográfica
setores_wgs84 AS (
    SELECT 
        <codigo_setor> AS id_setor,
        COALESCE(<coluna_populacao>, 0) AS populacao,
        ST_Transform(geom, 4326) AS geom_4326,
        ST_Area(ST_Transform(geom, 4326)::geography) AS area_total_setor
    FROM ibge_setores_raw
    WHERE geom IS NOT NULL
),

vegetacao_wgs84 AS (
    SELECT 
        <coluna_vegetacao> AS tipo_veg,
        ST_Transform(geom, 4326) AS geom_4326
    FROM ibge_vegetacao_raw
    WHERE geom IS NOT NULL
),

-- B) Geração da Malha H3 usando a Sombra do Setor
-- A resolução 9 (aprox 0.1km²) é ideal para cidades
h3_setores AS (
    SELECT 
        id_setor,
        populacao,
        area_total_setor,
        -- Retorna os IDs dos hexágonos que cobrem a geometria
        h3_polygon_to_cells(geom_4326, 9) AS h3_index,
        geom_4326 AS geom_setor
    FROM setores_wgs84
),

-- C) Fracionamento Populacional de Alta Precisão
h3_populacao_fracionada AS (
    SELECT 
        h3_index,
        h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex,
        SUM(
            populacao * (
                ST_Area(ST_Intersection(geom_setor, h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326))::geography) 
                / NULLIF(area_total_setor, 0)
            )
        ) AS pop_no_hexagono
    FROM h3_setores
    GROUP BY h3_index
),

-- D) Cruzamento Espacial com Uso da Terra (Vegetação)
h3_vegetacao_join AS (
    SELECT 
        p.h3_index,
        p.geom_hex,
        p.pop_no_hexagono,
        v.tipo_veg,
        -- Calculamos o tamanho da interseção para ver qual vegetação domina o hexágono
        ST_Area(ST_Intersection(p.geom_hex, v.geom_4326)::geography) AS area_intersecao
    FROM h3_populacao_fracionada p
    LEFT JOIN vegetacao_wgs84 v 
        ON ST_Intersects(p.geom_hex, v.geom_4326)
),

-- E) Selecionar a vegetação dominante por hexágono (Window Function)
h3_vegetacao_dominante AS (
    SELECT DISTINCT ON (h3_index)
        h3_index,
        geom_hex,
        pop_no_hexagono,
        tipo_veg
    FROM h3_vegetacao_join
    ORDER BY h3_index, area_intersecao DESC
)

-- 5. Inserção Materializada Final
INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada, tipo_vegetacao_predominante)
SELECT 
    h3_index,
    geom_hex,
    pop_no_hexagono,
    tipo_veg
FROM h3_vegetacao_dominante;

-- 6. Criação do Índice Espacial para o MVT da nossa API
CREATE INDEX idx_h3_grid_precalc_geom ON h3_grid_precalc USING GIST (geom);

COMMIT;
