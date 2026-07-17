import asyncio
import asyncpg
async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        val = await conn.fetchval("SELECT ST_AsText(ST_TileEnvelope(11, 758, 1161))")
        print(f'Bounds: {val}')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()
asyncio.run(test())
