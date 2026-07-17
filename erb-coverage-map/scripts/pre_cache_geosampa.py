import asyncio
import aiohttp
import math
import argparse
import sys
import os

# Bounding Box de Sao Paulo Capital (aproximada)
SP_MIN_LNG = -46.8255
SP_MIN_LAT = -24.0082
SP_MAX_LNG = -46.3650
SP_MAX_LAT = -23.3567

ZOOM_LEVELS = [13, 14, 15]

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

async def fetch_tile(session, z, x, y, semaphore):
    async with semaphore:
        url = f"http://127.0.0.1:8000/api/geosampa_tiles/{z}/{x}/{y}.pbf"
        try:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    return True
                else:
                    return False
        except Exception as e:
            print(f"Erro em {z}/{x}/{y}: {e}")
            return False

async def main():
    tiles_to_fetch = []
    for z in ZOOM_LEVELS:
        min_x, max_y = deg2num(SP_MIN_LAT, SP_MIN_LNG, z)
        max_x, min_y = deg2num(SP_MAX_LAT, SP_MAX_LNG, z)
        
        # Adjust for inverted Y
        min_y, max_y = min(min_y, max_y), max(min_y, max_y)
        min_x, max_x = min(min_x, max_x), max(min_x, max_x)
        
        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                tiles_to_fetch.append((z, x, y))

    total = len(tiles_to_fetch)
    print(f"Iniciando pre-cache do GeoSampa (SP) para {total} tiles (zooms: {ZOOM_LEVELS})...")
    
    semaphore = asyncio.Semaphore(15) # Concurrency control to not overload DB
    
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_tile(session, z, x, y, semaphore) for (z, x, y) in tiles_to_fetch]
        
        completed = 0
        for f in asyncio.as_completed(tasks):
            res = await f
            completed += 1
            if completed % 50 == 0 or completed == total:
                print(f"Progresso: {completed}/{total} ({(completed/total)*100:.1f}%)")

if __name__ == "__main__":
    # check disk space before starting
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (2**30)
    print(f"Espaço livre em disco: {free_gb} GB")
    if free_gb < 1:
        print("CUIDADO: Menos de 1GB de espaço livre. O cache pode falhar.")
        
    asyncio.run(main())
