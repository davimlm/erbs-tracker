import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    await conn.execute("SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE query ILIKE '%ray_tracing%' AND pid != pg_backend_pid()")
    print("Cancelled slow queries")
    await conn.close()

asyncio.run(run())
