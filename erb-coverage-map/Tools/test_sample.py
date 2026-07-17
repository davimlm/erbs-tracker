import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        row = await conn.fetchrow("""
            SELECT ST_X(ST_Centroid(geom)) as lon, ST_Y(ST_Centroid(geom)) as lat, populacao_estimada
            FROM h3_grid_precalc
            WHERE populacao_estimada > 50
            LIMIT 1
        """)
        print(f"Sample H3 cell with pop > 50: {row['lon']}, {row['lat']} (pop: {row['populacao_estimada']})")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
