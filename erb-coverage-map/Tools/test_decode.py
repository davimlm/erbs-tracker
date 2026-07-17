import urllib.request
try:
    import mapbox_vector_tile
except ImportError:
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mapbox-vector-tile"])
    import mapbox_vector_tile

url = 'http://127.0.0.1:8000/api/tiles/11/758/1161.pbf?operadora=all&frequencia=all&locationId=sao_paulo_sp&viewMode=cidades'
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req) as f:
        data = f.read()
        decoded = mapbox_vector_tile.decode(data)
        print('Layers:', list(decoded.keys()))
        for layer_name, layer_data in decoded.items():
            print(f"Layer {layer_name}: {len(layer_data['features'])} features")
            if len(layer_data['features']) > 0:
                print(f"  First feature geom type: {layer_data['features'][0]['geometry']['type']}")
except Exception as e:
    print('Error:', e)
