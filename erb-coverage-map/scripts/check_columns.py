import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'geosampa_buildings_3d'")
    print([r[0] for r in rows])
    await conn.close()

asyncio.run(run())
