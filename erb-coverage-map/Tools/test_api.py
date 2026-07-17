import asyncio
import httpx

async def test_api():
    async with httpx.AsyncClient() as client:
        print("Testing /api/coverage for a Macroregion (e.g. Nordeste bounding box)")
        # Bbox for Nordeste
        req = {
            "bbox": {"minLat": -18.3, "minLng": -48.7, "maxLat": -1.0, "maxLng": -34.8},
            "operadora": "all",
            "frequencia": "all",
            "lat": -10.0, "lng": -40.0,
            "locationId": "none"
        }
        res = await client.post('http://127.0.0.1:8000/api/coverage', json=req, timeout=60.0)
        print("Coverage status:", res.status_code)
        if res.status_code != 200:
            print(res.text)
            
        print("\nTesting /api/tiles/5/11/17.pbf (Zoom 5 tile)")
        res2 = await client.get('http://127.0.0.1:8000/api/tiles/5/11/17.pbf?operadora=all&frequencia=all&locationId=none', timeout=10.0)
        print("Tile status:", res2.status_code)
        if res2.status_code != 200:
            print("Tile Error:", res2.text)

if __name__ == '__main__':
    asyncio.run(test_api())
