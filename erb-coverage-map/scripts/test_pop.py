import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    res = await conn.fetchval("SELECT SUM(populacao_estimada) FROM h3_grid_precalc")
    print('Total pop h3:', res)
    
    res2 = await conn.fetchval("SELECT SUM(v0001) FROM ibge_setores_raw")
    print('Total pop raw:', res2)
    
    # Check SP specifically
    sp_pop_h3 = await conn.fetchval("""
        SELECT SUM(p.populacao_estimada) 
        FROM h3_grid_precalc p
        JOIN ibge_boundaries b ON b.id = 'sao_paulo_sp'
        WHERE p.geom && b.geom AND ST_Intersects(p.geom, b.geom)
    """)
    print('SP pop h3 (from boundary intersection):', sp_pop_h3)
    
    await conn.close()

asyncio.run(check())
