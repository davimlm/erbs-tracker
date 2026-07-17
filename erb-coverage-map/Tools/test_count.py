import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        val1 = await conn.fetchval("SELECT count(*) FROM h3_grid_precalc")
        val2 = await conn.fetchval("SELECT count(*) FROM ibge_vegetacao_subdividida")
        val3 = await conn.fetchval("SELECT count(*) FROM ibge_setores_raw")
        print(f"h3_grid_precalc: {val1}")
        print(f"ibge_vegetacao_subdividida: {val2}")
        print(f"ibge_setores_raw: {val3}")
    except Exception as e:
        print(f"Query error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
