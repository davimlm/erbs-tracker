import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    avg_geo = await conn.fetchval("SELECT AVG(NULLIF(REGEXP_REPLACE(ed_altura::text, '[^0-9.]', '', 'g'), '')::float) FROM geosampa_buildings_3d WHERE ed_altura IS NOT NULL AND ed_altura::text != '0'")
    print(f"Average GeoSampa height: {avg_geo}")

    osm_sample = await conn.fetch("SELECT height, \"building:levels\" FROM osm_buildings_3d_raw WHERE height IS NOT NULL OR \"building:levels\" IS NOT NULL LIMIT 10")
    print(f"OSM Sample: {osm_sample}")
    
    await conn.close()

asyncio.run(check())
