import asyncio
import asyncpg

async def run():
    try:
        conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
        await conn.execute("""
            SELECT pg_terminate_backend(pid) 
            FROM pg_stat_activity 
            WHERE state = 'active' AND pid != pg_backend_pid() AND datname = 'cobertura_db'
        """)
        print("All other queries terminated.")
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(run())
