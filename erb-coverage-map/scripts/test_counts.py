import asyncio
import asyncpg
import glob
import os

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    geosampa_files = glob.glob("data/geosampa/*.zip")
    print(f"Arquivos na pasta data/geosampa: {len(geosampa_files)}")
    
    try:
        geo_count = await conn.fetchval("SELECT COUNT(*) FROM geosampa_buildings_3d")
        print(f"Total de prédios no geosampa_buildings_3d: {geo_count}")
    except Exception as e:
        print(f"Erro ao acessar geosampa_buildings_3d: {e}")

    try:
        osm_count = await conn.fetchval("SELECT COUNT(*) FROM osm_buildings_3d_raw")
        print(f"Total de prédios no osm_buildings_3d_raw: {osm_count}")
    except Exception as e:
        print(f"Erro ao acessar osm_buildings_3d_raw: {e}")
        
    await conn.close()

asyncio.run(check())
