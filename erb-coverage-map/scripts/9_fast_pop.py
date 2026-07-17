import asyncpg
import asyncio
import math
from tqdm import tqdm

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

async def main():
    conn = await asyncpg.connect(DB_URI)
    
    print("Recriando tabela de populacao sem vegetacao (RÁPIDO)...")
    await conn.execute("""
        DROP TABLE IF EXISTS h3_grid_precalc;
        CREATE TABLE h3_grid_precalc (
            h3_index h3index PRIMARY KEY,
            geom geometry(Polygon, 4326),
            populacao_estimada double precision,
            tipo_vegetacao_predominante varchar(255),
            fator_atenuacao_veg double precision DEFAULT 0.0
        );
    """)
    
    total_setores = await conn.fetchval("SELECT COUNT(*) FROM ibge_setores_raw WHERE geom IS NOT NULL")
    chunk_size = 5000
    total_chunks = math.ceil(total_setores / chunk_size)
    print(f"Processando {total_setores} setores...")
    
    query = """
    WITH 
    setores_chunk AS (
        SELECT cd_setor AS id_setor, COALESCE(v0001, 0) AS populacao, ST_Transform(geom, 4326) AS geom_4326, ST_Area(ST_Transform(geom, 4326)::geography) AS area_total_setor
        FROM ibge_setores_raw WHERE geom IS NOT NULL ORDER BY gid LIMIT $1 OFFSET $2
    ),
    h3_setores AS (
        SELECT id_setor, populacao, area_total_setor, h3_polygon_to_cells(geom_4326, 9) AS h3_index, geom_4326 AS geom_setor
        FROM setores_chunk
    ),
    h3_populacao_fracionada AS (
        SELECT 
            h3_index,
            h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex,
            SUM(populacao * (ST_Area(ST_Intersection(geom_setor, h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326))::geography) / NULLIF(area_total_setor, 0))) AS pop_no_hexagono
        FROM h3_setores
        GROUP BY h3_index
    )
    INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada)
    SELECT h3_index, geom_hex, pop_no_hexagono
    FROM h3_populacao_fracionada
    ON CONFLICT (h3_index) DO UPDATE 
    SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
    """

    for i in tqdm(range(total_chunks), desc="Processando Malha H3"):
        offset = i * chunk_size
        await conn.execute(query, chunk_size, offset)
        
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_h3_grid_precalc_geom ON h3_grid_precalc USING GIST (geom);")
    await conn.close()
    print("Concluido!")

if __name__ == '__main__':
    asyncio.run(main())
