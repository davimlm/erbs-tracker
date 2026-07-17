import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    # Let's test the z>=10 query for SP city tile!
    # SP city center at z=11:
    # lon = -46.63 -> x = (lon + 180)/360 * 2^11 = 133.37 / 360 * 2048 = 758.7 -> 758
    # lat = -23.55 -> y = 1161.4 -> 1161
    
    query = """
        WITH bounds AS (
            SELECT ST_TileEnvelope(11, 758, 1161) AS geom_3857
        ),
        tile_clip AS (
            SELECT ST_Transform(geom_3857, 4326) as geom_4326 FROM bounds
        ),
        boundary AS (
            SELECT geom FROM ibge_boundaries WHERE id = 'sao_paulo_sp'
        ),
        celulas_pop AS (
            SELECT ST_Centroid(ST_Transform(p.geom, 4326)) AS geom_4326, p.v0001::float as pop_absoluta, p.area_km2
            FROM ibge_setores_raw p, tile_clip
            WHERE p.geom && ST_Transform(tile_clip.geom_4326, 4674)
              AND ST_Intersects(ST_Transform(p.geom, 4326), COALESCE((SELECT geom FROM boundary), tile_clip.geom_4326))
        ),
        mvt_populacao AS (
            SELECT ST_AsMVTGeom(ST_Transform(c.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
                   c.pop_absoluta,
                   CASE WHEN c.area_km2 > 0 THEN c.pop_absoluta / c.area_km2 ELSE 0 END as densidade,
                   false as na_sombra
            FROM celulas_pop c
        )
        SELECT length(COALESCE((SELECT ST_AsMVT(mvt_populacao, 'populacao') FROM mvt_populacao), '\\x'::bytea)) AS tile_len;
    """
    try:
        val = await conn.fetchval(query)
        print(f'MVT pop length: {val}')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()
asyncio.run(test())
