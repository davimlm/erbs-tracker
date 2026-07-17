import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    print([r[0] for r in rows])
    await conn.close()

asyncio.run(run())
