import asyncio
import asyncpg
from datetime import datetime

async def monitor():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    # Check active queries
    print("--- PROCESSOS ATIVOS NO POSTGRES ---")
    queries = await conn.fetch("""
        SELECT pid, state, duration, query 
        FROM (
            SELECT pid, state, now() - query_start as duration, query 
            FROM pg_stat_activity 
            WHERE state = 'active' AND pid != pg_backend_pid()
        ) q 
        ORDER BY duration DESC
    """)
    if not queries:
        print("Nenhum processo pesado rodando no momento.")
    for q in queries:
        print(f"PID: {q['pid']} | Tempo rodando: {q['duration']} | Status: {q['state']}")
        print(f"Query: {q['query'][:200]}...")
        print("-" * 40)
        
    print("\n--- PROGRESSO DA MATERIALIZAÇÃO H3 ---")
    count = await conn.fetchval("SELECT COUNT(*) FROM h3_grid_precalc")
    pop_total = await conn.fetchval("SELECT COALESCE(SUM(populacao_estimada), 0) FROM h3_grid_precalc")
    print(f"Hexágonos H3 inseridos: {count}")
    print(f"População mapeada até o momento: {pop_total:,.0f} habitantes")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(monitor())
