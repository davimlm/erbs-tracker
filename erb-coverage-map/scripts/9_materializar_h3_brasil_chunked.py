import asyncpg
import asyncio
import math
from tqdm import tqdm

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

async def main():
    conn = await asyncpg.connect(DB_URI)
    
    print("Preparando tabelas (recriando h3_grid_precalc)...")
    await conn.execute("""
        CREATE EXTENSION IF NOT EXISTS postgis;
        CREATE EXTENSION IF NOT EXISTS h3_postgis CASCADE;
        
        DROP TABLE IF EXISTS h3_grid_precalc;
        CREATE TABLE h3_grid_precalc (
            h3_index h3index PRIMARY KEY,
            geom geometry(Polygon, 4326),
            populacao_estimada double precision,
            tipo_vegetacao_predominante varchar(255),
            fator_atenuacao_veg double precision DEFAULT 0.0
        );
        -- Vamos criar índices nas tabelas brutas para otimizar as queries por chunk
        CREATE INDEX IF NOT EXISTS idx_veg_sub_geom ON ibge_vegetacao_subdividida USING GIST (geom);
        
        -- Criar a tabela subdividida com a área original preservada
        CREATE TABLE IF NOT EXISTS ibge_setores_subdividida AS
        SELECT 
            cd_setor AS id_setor_original,
            v0001 AS populacao,
            ST_Area(geom::geography) AS area_original_m2,
            ST_Subdivide(geom, 256) AS geom_sub
        FROM ibge_setores_raw
        WHERE geom IS NOT NULL;

        -- Adicionar uma chave primária caso não tenha
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'ibge_setores_subdividida' AND constraint_type = 'PRIMARY KEY'
            ) THEN
                ALTER TABLE ibge_setores_subdividida ADD COLUMN id_subdivisao SERIAL PRIMARY KEY;
            END IF;
        END $$;
        
        -- Criar o índice espacial na nova geometria fracionada
        CREATE INDEX IF NOT EXISTS idx_setores_sub_geom ON ibge_setores_subdividida USING GIST (geom_sub);
    """)
    
    print("Contando subdivisões censitárias...")
    total_subdivisoes = await conn.fetchval("SELECT COUNT(*) FROM ibge_setores_subdividida")
    
    chunk_size = 1000
    total_chunks = math.ceil(total_subdivisoes / chunk_size)
    
    print(f"Total de subdivisões: {total_subdivisoes} | Serão processadas em {total_chunks} chunks de {chunk_size}.")
    
    # Cursor paginado
    query = """
    WITH subdivisoes_chunk AS (
        SELECT 
            id_subdivisao,
            COALESCE(populacao, 0) AS populacao,
            area_original_m2,
            ST_Area(geom_sub::geography) AS sub_area_m2,
            ST_Transform(geom_sub, 4326) AS geom_sub_4326
        FROM ibge_setores_subdividida
        ORDER BY id_subdivisao
        LIMIT $1 OFFSET $2
    ),
    h3_setores AS (
        SELECT 
            id_subdivisao,
            populacao,
            area_original_m2,
            sub_area_m2,
            h3_polygon_to_cells(geom_sub_4326, 9) AS h3_index
        FROM subdivisoes_chunk
    ),
    h3_setores_contagem AS (
        SELECT 
            h3_index,
            id_subdivisao,
            populacao,
            area_original_m2,
            sub_area_m2,
            COUNT(*) OVER (PARTITION BY id_subdivisao) as hex_count
        FROM h3_setores
    ),
    h3_populacao_fracionada AS (
        SELECT 
            h3_index,
            SUM(
                (populacao * (sub_area_m2 / NULLIF(area_original_m2, 0))) / 
                NULLIF(hex_count, 0)
            ) AS pop_no_hexagono,
            h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex
        FROM h3_setores_contagem
        GROUP BY h3_index
    ),
    -- Para cada hexagono, pega a vegetacao que tiver a maior interseccao (Limit 1 no select lateral)
    h3_com_vegetacao AS (
        SELECT 
            p.h3_index,
            p.geom_hex,
            p.pop_no_hexagono,
            (
                SELECT v.legenda
                FROM ibge_vegetacao_subdividida v
                WHERE v.geom && ST_Transform(p.geom_hex, 4674)
                  AND ST_Intersects(ST_Transform(p.geom_hex, 4674), v.geom)
                LIMIT 1
            ) as tipo_veg
        FROM h3_populacao_fracionada p
    ),
    h3_com_atenuacao AS (
        SELECT
            h3_index,
            geom_hex,
            pop_no_hexagono,
            tipo_veg,
            CASE 
                -- Mata Fechada (Alta Densidade) - 35% de atenuacao
                WHEN tipo_veg ILIKE '%Floresta Ombrófila%' 
                  OR tipo_veg ILIKE '%Floresta Estacional%'
                  OR tipo_veg ILIKE '%Reflorestamento com%' THEN 0.35
                -- Mata Aberta / Arbustiva (Média Densidade) - 20% de atenuacao
                WHEN tipo_veg ILIKE '%Savana%' 
                  OR tipo_veg ILIKE '%Cerrado%'
                  OR tipo_veg ILIKE '%Secundária%' 
                  OR tipo_veg ILIKE '%Caatinga%' THEN 0.20
                -- Pastagens / Agricultura (Baixa Densidade) - 0% de atenuacao
                WHEN tipo_veg ILIKE '%Pastagem%' 
                  OR tipo_veg ILIKE '%Agricultura%' 
                  OR tipo_veg ILIKE '%Agropecuária%' THEN 0.00
                -- Outros (Água, Rocha, Urbano) - 0% de atenuacao
                ELSE 0.00
            END AS fator_atenuacao
        FROM h3_com_vegetacao
    )
    INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada, tipo_vegetacao_predominante, fator_atenuacao_veg)
    SELECT h3_index, geom_hex, pop_no_hexagono, tipo_veg, fator_atenuacao
    FROM h3_com_atenuacao
    ON CONFLICT (h3_index) DO UPDATE 
    SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
    """

    for i in tqdm(range(total_chunks), desc="Processando Malha H3"):
        offset = i * chunk_size
        await conn.execute(query, chunk_size, offset)
        
    print("Processamento concluído. Criando índice espacial final...")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_h3_grid_precalc_geom ON h3_grid_precalc USING GIST (geom);")
    
    await conn.close()
    print("Tudo pronto!")

if __name__ == '__main__':
    asyncio.run(main())
