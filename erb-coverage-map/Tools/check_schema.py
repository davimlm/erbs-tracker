import asyncio
import asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    print("Checking ibge_setores_raw.area_km2:")
    res_pop = await conn.fetchval("SELECT count(*) FROM ibge_setores_raw WHERE area_km2 IS NULL OR area_km2 = 0")
    print(f"Setores com area_km2 nula/zero: {res_pop}")
    
    print("\nChecking ibge_vegetacao_raw.nm_uantr:")
    res_veg = await conn.fetch("SELECT DISTINCT nm_uantr FROM ibge_vegetacao_raw LIMIT 20")
    print([r['nm_uantr'] for r in res_veg])
    
    await conn.close()
if __name__ == '__main__':
    asyncio.run(main())
