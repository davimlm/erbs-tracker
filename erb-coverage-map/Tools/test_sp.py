import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        # Check if there are any points in h3_grid_precalc for SP
        count = await conn.fetchval("""
            SELECT count(*) FROM h3_grid_precalc g
            WHERE g.geom && ST_MakeEnvelope(-47.0, -24.0, -46.0, -23.0, 4326)
            AND g.populacao_estimada > 0
        """)
        print(f"SP H3 count: {count}")
        
        # Check vegetation
        count_veg = await conn.fetchval("""
            SELECT count(*) FROM ibge_vegetacao_subdividida v
            WHERE v.geom && ST_Transform(ST_MakeEnvelope(-47.0, -24.0, -46.0, -23.0, 4326), 4674)
        """)
        print(f"SP Veg count: {count_veg}")
    except Exception as e:
        print(f"Query error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
