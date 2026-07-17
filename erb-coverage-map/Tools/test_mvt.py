import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    query = """
        WITH empty_table AS (SELECT 1 AS a, 2 AS b WHERE false),
             dummy_mvt AS (SELECT ST_AsMVTGeom(ST_MakePoint(0,0), ST_MakeBox2D(ST_MakePoint(-1,-1), ST_MakePoint(1,1))) as geom)
        SELECT (
            COALESCE((SELECT ST_AsMVT(empty_table, 'empty') FROM empty_table), '\\x'::bytea) ||
            COALESCE((SELECT ST_AsMVT(dummy_mvt, 'dummy') FROM dummy_mvt), '\\x'::bytea)
        ) AS tile;
    """
    val = await conn.fetchval(query)
    print(f'Type: {type(val)}, Length: {len(val) if val else 0}')
    await conn.close()

asyncio.run(test())
