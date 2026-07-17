import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    res = await conn.fetch("SELECT proname, pg_get_function_identity_arguments(oid) FROM pg_proc WHERE proname LIKE 'h3_%to_h3' OR proname LIKE 'h3_%to_cell%'")
    print([(r[0], r[1]) for r in res])
    await conn.close()

asyncio.run(check())
