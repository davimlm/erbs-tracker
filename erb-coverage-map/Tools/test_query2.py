
import asyncio
import asyncpg

async def main():
    try:
        conn = await asyncpg.connect('postgresql://postgres:postgres@localhost:5432/erb_db')
        val = await conn.fetchval('SELECT 1')
        print('DB ALIVE:', val)
    except Exception as e:
        print('Error:', e)
        
    await conn.close()

asyncio.run(main())

