import math
import urllib.request
import time
import concurrent.futures

# Bounding box of Brazil
WEST = -74.0
SOUTH = -34.0
EAST = -34.0
NORTH = 5.5

def deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def fetch_url(url):
    try:
        urllib.request.urlopen(url, timeout=120)
        return f"OK: {url}"
    except Exception as e:
        return f"ERROR: {url} -> {e}"

def pre_cache():
    urls_to_fetch = []
    
    # We will cache Zoom levels 4 to 7
    # For zoom 8, it might be too many, but we can do it if needed.
    # Let's do 4, 5, 6, 7
    for z in range(4, 9):
        x_min, y_max = deg2num(SOUTH, WEST, z)
        x_max, y_min = deg2num(NORTH, EAST, z)
        
        # y_min and y_max are inverted because y=0 is at the North Pole
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                terrain_url = f"http://127.0.0.1:8000/api/terrain/{z}/{x}/{y}.png"
                thermal_url = f"http://127.0.0.1:8000/api/thermal/{z}/{x}/{y}.png"
                urls_to_fetch.append(terrain_url)
                urls_to_fetch.append(thermal_url)

    print(f"Total tiles to cache: {len(urls_to_fetch)//2} (Terrain + Thermal = {len(urls_to_fetch)} requests)")
    
    start_time = time.time()
    count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(fetch_url, urls_to_fetch):
            count += 1
            if count % 10 == 0:
                print(f"Progress: {count}/{len(urls_to_fetch)} ({(count/len(urls_to_fetch))*100:.1f}%) in {time.time()-start_time:.1f}s")
                
    print(f"Completed in {time.time()-start_time:.1f}s")

if __name__ == "__main__":
    pre_cache()
