import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        val = await conn.fetchval("SELECT count(id) FROM ibge_boundaries WHERE id = 'sao_paulo_sp'")
        print(f'SP str exists: {val}')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()
asyncio.run(test())
