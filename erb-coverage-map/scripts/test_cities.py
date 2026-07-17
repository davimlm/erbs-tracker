import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'ibge_setores_raw'")
    col_names = [r[0] for r in cols]
    
    city_col = None
    if 'nm_mun' in col_names:
        city_col = 'nm_mun'
    elif 'nm_municip' in col_names:
        city_col = 'nm_municip'
    elif 'nome_municipio' in col_names:
        city_col = 'nome_municipio'
    elif 'nm_mng' in col_names: # Sometimes it's something weird
        city_col = 'nm_mng'
        
    if not city_col:
        # Check if there is anything that looks like municipality
        for c in col_names:
            if 'mun' in c.lower():
                city_col = c
                break
                
    if not city_col:
        print("Não foi possível encontrar a coluna de município. Colunas:", col_names)
        await conn.close()
        return

    print(f"Usando coluna de cidade: {city_col}")
    
    # Vamos pegar 3 cidades conhecidas grandes/médias para ter certeza que têm dados, e 2 aleatórias
    test_cities = ['SÃO PAULO', 'ALTAMIRA', 'CURITIBA']
    
    import random
    all_cities = await conn.fetch(f"SELECT DISTINCT {city_col} FROM ibge_setores_raw WHERE {city_col} IS NOT NULL")
    city_list = [c[0] for c in all_cities]
    
    random_cities = random.sample(city_list, 3)
    for c in random_cities:
        if c not in test_cities:
            test_cities.append(c)
            
    for city in test_cities:
        pop_raw = await conn.fetchval(f"SELECT SUM(v0001) FROM ibge_setores_raw WHERE {city_col} = $1", city)
        
        # Para evitar query demorada com ST_Union, vamos apenas somar a população H3 cruzando com os setores raw dessa cidade
        # Já que h3_grid_precalc é rápida com índices.
        # Mas ST_Intersects dupla contagem se um hex cruza 2 setores? 
        # A forma 100% segura sem dupla contagem: pegar o ST_Union da cidade e cruzar com centróides dos hexágonos H3.
        pop_h3 = await conn.fetchval(f"""
            WITH city_geom AS (
                SELECT ST_Transform(ST_Union(geom), 4326) as geom 
                FROM ibge_setores_raw 
                WHERE {city_col} = $1
            )
            SELECT SUM(p.populacao_estimada)
            FROM h3_grid_precalc p, city_geom c
            WHERE p.geom && c.geom 
              AND ST_Intersects(ST_Centroid(p.geom), c.geom)
        """, city)
        
        print(f"Cidade: {city}")
        print(f"  População IBGE: {pop_raw}")
        print(f"  População H3:   {pop_h3:.2f}" if pop_h3 else "  População H3:   0.00")
        if pop_raw is not None and pop_h3 is not None:
            pop_raw_f = float(pop_raw)
            pop_h3_f = float(pop_h3)
            print(f"  Diferença: {abs(pop_raw_f - pop_h3_f):.2f} (Precisão: {(pop_h3_f/pop_raw_f if pop_raw_f > 0 else 0)*100:.2f}%)")
        print("-" * 50)
        
    await conn.close()

asyncio.run(check())
