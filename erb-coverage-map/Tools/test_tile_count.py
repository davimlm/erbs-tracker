import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    query = """
        WITH bounds AS (
            SELECT ST_TileEnvelope(9, 189, 292) AS geom_3857
        ),
        tile_clip AS (
            SELECT ST_Transform(geom_3857, 4326) as geom_4326 FROM bounds
        ),
        celulas_h3 AS (
            SELECT g.populacao_estimada as pop_absoluta, 
                   ST_Centroid(g.geom) AS geom
            FROM h3_grid_precalc g, tile_clip
            WHERE g.geom && tile_clip.geom_4326
              AND g.populacao_estimada > 50
        )
        SELECT count(*) FROM celulas_h3;
    """
    try:
        count = await conn.fetchval(query)
        print(f"celulas_h3 count: {count}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
