import requests
import time
from concurrent.futures import ThreadPoolExecutor

# Configurações do seu backend
BASE_URL = "http://127.0.0.1:8000/api/geosampa_tiles"
ZOOM = 14  # Nível de zoom onde os prédios começam a ser gerados

# Coordenadas X e Y dos Ladrilhos (Tiles) que cobrem a Grande São Paulo no Zoom 14
X_RANGE = range(6040, 6100) # De Osasco à Zona Leste
Y_RANGE = range(9260, 9320) # De Guarulhos a Interlagos/Parelheiros

def fetch_tile(x, y):
    url = f"{BASE_URL}/{ZOOM}/{x}/{y}.pbf"
    try:
        # Pede o tile. O FastAPI vai rodar o SQL e salvar no HD (pasta cache)
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            if len(response.content) > 100: # Se for maior que 100 bytes, tem prédio!
                return f"[SUCESSO] Tile {ZOOM}/{x}/{y} gerado e cacheado! ({len(response.content)} bytes)"
            else:
                return f"[VAZIO] Tile {ZOOM}/{x}/{y} - Sem prédios aqui."
        else:
            return f"[ERRO] Tile {ZOOM}/{x}/{y} - Status {response.status_code}"
    except Exception as e:
        return f"[FALHA] Tile {ZOOM}/{x}/{y} - {e}"

def run_seeder():
    print("INICIANDO O TRATOR DE CACHE (PRE-WARMING)...")
    print("Isso vai forçar o PostGIS a calcular São Paulo inteira e salvar os PBFs.")
    start_time = time.time()
    
    tasks = []
    # Usando 4 threads para não derreter a CPU do seu banco de dados
    with ThreadPoolExecutor(max_workers=4) as executor:
        for x in X_RANGE:
            for y in Y_RANGE:
                tasks.append(executor.submit(fetch_tile, x, y))
                
        for future in tasks:
            print(future.result())

    elapsed = time.time() - start_time
    print(f"CACHE CONCLUÍDO EM {elapsed:.2f} SEGUNDOS!")
    print("Agora abra o frontend. São Paulo inteira vai carregar instantaneamente.")

if __name__ == "__main__":
    run_seeder()
