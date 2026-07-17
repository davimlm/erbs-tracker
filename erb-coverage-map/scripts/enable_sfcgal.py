import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    await conn.execute("CREATE EXTENSION IF NOT EXISTS postgis_sfcgal")
    print("SFCGAL enabled.")
    await conn.close()

asyncio.run(run())
