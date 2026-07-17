import asyncio
import asyncpg
import json
async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
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
        )
        SELECT count(*), ST_AsText(geom_4326) as geom FROM celulas_pop GROUP BY geom_4326 LIMIT 1;
    """
    try:
        row = await conn.fetchrow(query)
        print(f'Count: {row[0]}, Geom: {row[1]}')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()
asyncio.run(test())
