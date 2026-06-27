-- SCRIPT 9: MATERIALIZAR H3 BRASIL
-- Este script realiza o cruzamento pesado das geometrias brutas do IBGE para gerar a malha H3 final.

BEGIN;

-- 1. Limpar a tabela final (caso estejamos reprocessando)
-- TRUNCATE TABLE h3_grid_precalc;

-- 2. Materialização Temporária: Censo H3
-- Aqui transformamos os polígonos de setores censitários do IBGE em células H3 (Resolução 9)
-- IMPORTANTE: Verifique o nome da coluna de população na sua base bruta do IBGE (aqui usamos 'v0001' como placeholder padrão de Censo)
CREATE TEMP TABLE temp_censo_h3 AS
WITH censo_cells AS (
    SELECT 
        h3_polygon_to_cells(ST_Transform(geom, 4326), 9) AS h3_index,
        COALESCE(v0001, 0) AS populacao_setor,
        ST_Area(geom) AS area_setor
    FROM ibge_setores_raw
    WHERE geom IS NOT NULL AND ST_IsValid(geom)
)
SELECT 
    h3_index,
    -- Uma simplificação: a população da célula H3 assume a densidade do setor. 
    -- Numa versão hiper-precisa, faríamos a proporção (ST_Area(ST_Intersection) / area_setor)
    SUM(populacao_setor * (ST_Area(h3_cell_to_boundary(h3_index)::geometry) / NULLIF(area_setor, 0))) AS populacao_estimada
FROM censo_cells
GROUP BY h3_index;

CREATE INDEX idx_temp_censo_h3 ON temp_censo_h3 (h3_index);

-- 3. Materialização Temporária: Vegetação H3
-- Transformamos os polígonos de uso da terra em H3 (Resolução 9)
-- IMPORTANTE: Substituir 'nat_veg' pelo nome da coluna/filtro real que indica área verde na base do IBGE
CREATE TEMP TABLE temp_veg_h3 AS
WITH veg_cells AS (
    SELECT 
        h3_polygon_to_cells(ST_Transform(geom, 4326), 9) AS h3_index
    FROM ibge_vegetacao_raw
    WHERE geom IS NOT NULL AND ST_IsValid(geom)
      AND tipo_uso IN ('Floresta', 'Mata Nativa', 'Vegetação') -- Substituir pelos domínios corretos do IBGE!
)
SELECT 
    h3_index,
    100 AS percent_vegetacao -- Células geradas pelos polígonos de vegetação assumem 100% de cobertura
FROM veg_cells
GROUP BY h3_index;

CREATE INDEX idx_temp_veg_h3 ON temp_veg_h3 (h3_index);

-- 4. Fusão (Merge) Final na tabela h3_grid_precalc
INSERT INTO h3_grid_precalc (h3_index, populacao_estimada, percent_vegetacao, geometry)
SELECT 
    COALESCE(c.h3_index, v.h3_index) AS h3_index,
    COALESCE(c.populacao_estimada, 0) AS populacao_estimada,
    COALESCE(v.percent_vegetacao, 0) AS percent_vegetacao,
    h3_cell_to_boundary(COALESCE(c.h3_index, v.h3_index))::geometry AS geometry
FROM temp_censo_h3 c
FULL OUTER JOIN temp_veg_h3 v ON c.h3_index = v.h3_index
ON CONFLICT (h3_index) DO UPDATE SET
    populacao_estimada = EXCLUDED.populacao_estimada,
    percent_vegetacao = EXCLUDED.percent_vegetacao,
    geometry = EXCLUDED.geometry;

-- 5. Limpeza das Tabelas Brutas para salvar espaço (Opcional, pode ser comentado para debug)
-- DROP TABLE ibge_setores_raw;
-- DROP TABLE ibge_vegetacao_raw;

COMMIT;
