import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT name, installed_version FROM pg_available_extensions WHERE name LIKE '%sfcgal%'")
    print(rows)
    await conn.close()

asyncio.run(run())
