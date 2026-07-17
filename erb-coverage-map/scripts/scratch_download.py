import os
import urllib.request
import re
import zipfile
from pathlib import Path

# Fix: PowerShell uses different encoding, let's just use Python standard libs cleanly
CENSO_URL = 'https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_dos_Resultados_do_Universo/Malha_de_Setores_Censitarios/'
USO_URL = 'https://geoftp.ibge.gov.br/cartas_e_mapas/mapas_ambientais/uso_de_cobertura_da_terra/shapefile/estado/AC/'

DATA_DIR = Path(__file__).parent.parent / "data"
CENSO_AC = DATA_DIR / "ibge_censo" / "AC"
USO_AC = DATA_DIR / "ibge_uso_terra" / "AC"
CENSO_AC.mkdir(parents=True, exist_ok=True)
USO_AC.mkdir(parents=True, exist_ok=True)

def download_file(url, dest):
    print(f"Downloading {url} to {dest}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as response, open(dest, 'wb') as out_file:
        out_file.write(response.read())
    print("Download finished.")

def unzip_file(zip_path, extract_to):
    print(f"Unzipping {zip_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    print("Unzip finished.")

def main():
    # 1. Encontrar o ZIP do Censo AC
    print("Buscando malha do Acre...")
    req = urllib.request.Request(CENSO_URL, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    
    # regex to find AC_*.zip
    match = re.search(r'href=[\'"]?(AC[^\'"]+\.zip)[\'"]?', html)
    if not match:
        print("Zip do Censo não encontrado no HTML")
        return
    censo_filename = match.group(1)
    censo_zip_url = CENSO_URL + censo_filename
    censo_zip_dest = CENSO_AC / censo_filename
    
    download_file(censo_zip_url, censo_zip_dest)
    unzip_file(censo_zip_dest, CENSO_AC)
    
    # 2. Uso da Terra AC
    print("Buscando uso da terra do Acre...")
    req = urllib.request.Request(USO_URL, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    match = re.search(r'href=[\'"]?(Uso[^\'"]+\.zip)[\'"]?', html, re.IGNORECASE)
    if not match:
        print("Zip do Uso da Terra não encontrado")
        return
    uso_filename = match.group(1)
    uso_zip_url = USO_URL + uso_filename
    uso_zip_dest = USO_AC / uso_filename
    
    download_file(uso_zip_url, uso_zip_dest)
    unzip_file(uso_zip_dest, USO_AC)
    
    print("TUDO PRONTO PARA AC!")

if __name__ == '__main__':
    main()
