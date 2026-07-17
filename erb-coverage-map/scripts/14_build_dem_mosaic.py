import os
import zipfile
import json
import rasterio
from tqdm import tqdm

INPE_DIR = "data/topodata_mde_raw"
EXTRACT_DIR = os.path.join(INPE_DIR, "extracted")
INDEX_FILE = os.path.join(INPE_DIR, "dem_index.json")

def main():
    if not os.path.exists(EXTRACT_DIR):
        os.makedirs(EXTRACT_DIR)

    zip_files = [f for f in os.listdir(INPE_DIR) if f.endswith('.zip')]
    print(f"Encontrados {len(zip_files)} arquivos ZIP do INPE.")

    # 1. Extrair todos os TIFs
    extracted_tifs = []
    for zf in tqdm(zip_files, desc="Extraindo TIFs"):
        zip_path = os.path.join(INPE_DIR, zf)
        with zipfile.ZipFile(zip_path, 'r') as z:
            for file_info in z.infolist():
                if file_info.filename.endswith('.tif'):
                    # Extrair apenas se não existir
                    out_path = os.path.join(EXTRACT_DIR, file_info.filename)
                    if not os.path.exists(out_path):
                        z.extract(file_info, EXTRACT_DIR)
                    extracted_tifs.append(file_info.filename)

    # 2. Construir o Índice Espacial (VRT caseiro)
    # Vamos abrir cada TIF com rasterio e ler seus limites (bounds)
    print("Construindo índice espacial de elevação...")
    dem_index = []
    for tif_name in tqdm(extracted_tifs, desc="Lendo Bounds"):
        tif_path = os.path.join(EXTRACT_DIR, tif_name)
        try:
            with rasterio.open(tif_path) as src:
                bounds = src.bounds
                dem_index.append({
                    "file": tif_name,
                    "left": bounds.left,
                    "bottom": bounds.bottom,
                    "right": bounds.right,
                    "top": bounds.top
                })
        except Exception as e:
            print(f"Erro ao ler {tif_name}: {e}")

    # Salvar o índice em JSON
    with open(INDEX_FILE, 'w') as f:
        json.dump(dem_index, f, indent=2)

    print(f"Índice salvo em {INDEX_FILE} com {len(dem_index)} tiles MDE.")
    print("O backend usará esse índice para consultar a elevação instantaneamente!")

if __name__ == "__main__":
    main()
