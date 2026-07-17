import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    res = await conn.fetch('SELECT id, operadora, ST_Y(geometry) as lat, ST_X(geometry) as lng FROM erbs_ativas WHERE ST_X(geometry) < -70')
    for r in res:
        print(dict(r))
    await conn.close()

if __name__ == '__main__':
    asyncio.run(run())
