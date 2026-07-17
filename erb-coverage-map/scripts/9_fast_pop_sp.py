import asyncpg
import asyncio

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

async def main():
    conn = await asyncpg.connect(DB_URI)
    
    print("Recriando h3_grid_precalc APENAS PARA SAO PAULO (Capital)...")
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
    
    # 3550308 is the IBGE code for Sao Paulo city
    query = """
    WITH 
    setores_sp AS (
        SELECT cd_setor AS id_setor, COALESCE(v0001, 0) AS populacao, ST_Transform(geom, 4326) AS geom_4326, ST_Area(ST_Transform(geom, 4326)::geography) AS area_total_setor
        FROM ibge_setores_raw 
        WHERE cd_setor LIKE '3550308%' AND geom IS NOT NULL
    ),
    h3_setores AS (
        SELECT 
            id_setor, 
            populacao, 
            area_total_setor, 
            h.h3_index, 
            geom_4326 AS geom_setor
        FROM setores_sp,
        LATERAL (
            SELECT h3_index FROM h3_polygon_to_cells(geom_4326, 9) AS h3_index
            UNION ALL
            SELECT h3_lat_lng_to_cell(ST_Centroid(geom_4326), 9) AS h3_index
            WHERE NOT EXISTS (SELECT 1 FROM h3_polygon_to_cells(geom_4326, 9))
        ) AS h
    ),
    h3_setores_inter AS (
        SELECT 
            id_setor,
            populacao,
            h3_index,
            ST_Area(ST_Intersection(geom_setor, h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326))::geography) AS area_inter
        FROM h3_setores
    ),
    h3_setores_frac AS (
        SELECT 
            id_setor,
            populacao,
            h3_index,
            area_inter / NULLIF(SUM(area_inter) OVER (PARTITION BY id_setor), 0) AS fracao
        FROM h3_setores_inter
    ),
    h3_populacao_fracionada AS (
        SELECT 
            h3_index,
            h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex,
            SUM(populacao * COALESCE(fracao, 0)) AS pop_no_hexagono
        FROM h3_setores_frac
        GROUP BY h3_index
    )
    INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada)
    SELECT h3_index, geom_hex, pop_no_hexagono
    FROM h3_populacao_fracionada
    ON CONFLICT (h3_index) DO UPDATE 
    SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
    """

    print("Executando injecao de setores de SP...")
    await conn.execute(query)
    
    print("Criando indice espacial...")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_h3_grid_precalc_geom ON h3_grid_precalc USING GIST (geom);")
    
    count = await conn.fetchval("SELECT count(*) FROM h3_grid_precalc")
    print(f"Concluido! Celulas em SP: {count}")
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
