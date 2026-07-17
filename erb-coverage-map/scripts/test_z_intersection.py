import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    rows = await conn.fetch("SELECT ST_AsText(ST_Intersection(ST_MakeLine(ST_MakePoint(0,0,35), ST_MakePoint(100,0,0)), ST_GeomFromText('POLYGON((50 -10, 50 10, 100 10, 100 -10, 50 -10))')))")
    print(rows)
    await conn.close()

asyncio.run(run())
