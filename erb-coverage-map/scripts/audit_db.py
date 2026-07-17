import asyncpg
import asyncio

async def main():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')

    print("=== TABELAS EM cobertura_db ===")
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)
    for t in tables:
        name = t['table_name']
        count = await conn.fetchval(f'SELECT COUNT(*) FROM public."{name}"')
        size = await conn.fetchval(f"SELECT pg_size_pretty(pg_total_relation_size('public.\"{name}\"'))")
        print(f"  {name}: {count:,} linhas ({size})")

    print("\n=== COLUNAS de h3_grid_precalc ===")
    cols = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'h3_grid_precalc' 
        ORDER BY ordinal_position;
    """)
    for c in cols:
        print(f"  {c['column_name']}: {c['data_type']}")

    print("\n=== EXTENSOES INSTALADAS ===")
    exts = await conn.fetch("SELECT extname, extversion FROM pg_extension ORDER BY extname;")
    for e in exts:
        print(f"  {e['extname']} v{e['extversion']}")

    await conn.close()

asyncio.run(main())
