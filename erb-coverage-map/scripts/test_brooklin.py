import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    query = """
    WITH ponto_teste AS (
        SELECT ST_Transform(ST_SetSRID(ST_MakePoint(-46.685, -23.620), 4326), 3857) as geom
    )
    SELECT 'GeoSampa' as origem, COUNT(*) as qtd_predios 
    FROM geosampa_buildings_3d, ponto_teste 
    WHERE ST_DWithin(geometry, ponto_teste.geom, 500)
    UNION ALL
    SELECT 'OSM' as origem, COUNT(*) as qtd_predios 
    FROM osm_buildings_3d_raw, ponto_teste 
    WHERE ST_DWithin(ST_Transform(geometry, 3857), ponto_teste.geom, 500);
    """
    
    res = await conn.fetch(query)
    print("Resultados no Brooklin (Av. Santo Amaro x Roberto Marinho):")
    for r in res:
        print(f" - {r['origem']}: {r['qtd_predios']} prédios")
        
    await conn.close()

asyncio.run(check())
