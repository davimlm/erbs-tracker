import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT pg_get_function_arguments(p.oid) FROM pg_proc p WHERE proname = 'st_extrude'")
    print([r[0] for r in rows])
    await conn.close()

asyncio.run(run())
