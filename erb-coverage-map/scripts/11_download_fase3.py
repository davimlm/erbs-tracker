import os
import urllib.request
from tqdm import tqdm

class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)

def download_file(url, dest_path):
    if os.path.exists(dest_path):
        print(f"O arquivo {dest_path} já existe. Pulando download.")
        return
        
    print(f"\nIniciando download de: {url}")
    print(f"Salvando em: {dest_path}")
    
    try:
        with DownloadProgressBar(unit='B', unit_scale=True, miniters=1, desc=os.path.basename(dest_path)) as t:
            urllib.request.urlretrieve(url, filename=dest_path, reporthook=t.update_to)
        print("Download concluído com sucesso!")
    except Exception as e:
        print(f"Erro ao baixar {url}: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)

def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    
    # 1. Download OSM Brasil
    osm_dir = os.path.join(base_dir, "osm")
    osm_url = "https://download.geofabrik.de/south-america/brazil-latest.osm.pbf"
    osm_dest = os.path.join(osm_dir, "brazil-latest.osm.pbf")
    
    # 2. Download IBGE Áreas Urbanizadas 2019
    ibge_dir = os.path.join(base_dir, "ibge_areas_urbanizadas")
    ibge_url = "https://geoftp.ibge.gov.br/organizacao_do_territorio/tipologias_do_territorio/areas_urbanizadas_do_brasil/2019/Shapefile/AreasUrbanizadas2019_Brasil.zip"
    ibge_dest = os.path.join(ibge_dir, "AreasUrbanizadas2019_Brasil.zip")

    # Garante que os diretórios existem
    os.makedirs(osm_dir, exist_ok=True)
    os.makedirs(ibge_dir, exist_ok=True)
    
    print("--- INICIANDO DOWNLOADS DA FASE 3 ---")
    download_file(osm_url, osm_dest)
    download_file(ibge_url, ibge_dest)
    print("\nProcesso de download finalizado.")

if __name__ == "__main__":
    main()
