import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT state, extract(epoch from now() - query_start) as dur FROM pg_stat_activity WHERE query ILIKE '%ray_tracing%' AND pid <> pg_backend_pid()")
    print(rows)
    await conn.close()

asyncio.run(run())
