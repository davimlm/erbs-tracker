import asyncio
import asyncpg

async def tune_postgres():
    DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
    conn = await asyncpg.connect(DB_URI)
    
    settings = [
        "ALTER SYSTEM SET shared_buffers = '4GB'",
        "ALTER SYSTEM SET effective_cache_size = '12GB'",
        "ALTER SYSTEM SET work_mem = '256MB'",
        "ALTER SYSTEM SET maintenance_work_mem = '1GB'",
        "ALTER SYSTEM SET max_worker_processes = '12'",
        "ALTER SYSTEM SET max_parallel_workers = '12'",
        "ALTER SYSTEM SET max_parallel_workers_per_gather = '6'",
        "ALTER SYSTEM SET random_page_cost = '1.1'"
    ]
    
    for sql in settings:
        print(f"Executando: {sql}")
        await conn.execute(sql)
        
    print("Recarregando configurações (pg_reload_conf)...")
    await conn.execute("SELECT pg_reload_conf();")
    print("PostgreSQL otimizado!")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(tune_postgres())
