import asyncio
import asyncpg
import json

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

async def main():
    conn = await asyncpg.connect(DB_URI)
    
    print("\n--- GEOSAMPA ALTURAS ---")
    rows = await conn.fetch("""
        SELECT count(*) FROM geosampa_buildings_3d WHERE ed_altura = 0 OR ed_altura::text = '0';
    """)
    print("Predios com altura 0:", rows)

    rows2 = await conn.fetch("""
        SELECT count(*) FROM geosampa_buildings_3d;
    """)
    print("Total de Predios:", rows2)

    await conn.close()

asyncio.run(main())
