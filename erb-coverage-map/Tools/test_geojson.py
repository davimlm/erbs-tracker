import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    try:
        val = await conn.fetchval("SELECT ST_AsText(ST_GeomFromGeoJSON('{\"type\": \"FeatureCollection\", \"features\": [{\"type\": \"Feature\", \"geometry\": {\"type\": \"Point\", \"coordinates\": [0, 0]}}]}'))")
        print(f'Result: {val}')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await conn.close()
asyncio.run(test())
