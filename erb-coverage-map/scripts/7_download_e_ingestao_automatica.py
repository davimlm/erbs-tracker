import os
import requests
import zipfile
import logging
import subprocess
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
import urllib.parse

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", 
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", 
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"
]

# URLs Raiz
CENSO_URL = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_dos_Resultados_do_Universo/Malha_de_Setores_Censitarios/"
USO_TERRA_URL = "https://geoftp.ibge.gov.br/cartas_e_mapas/mapas_ambientais/uso_de_cobertura_da_terra/shapefile/estado/"

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CENSO_DIR = DATA_DIR / "ibge_censo"
USO_TERRA_DIR = DATA_DIR / "ibge_uso_terra"

# Caminhos do PostgreSQL (Ajuste conforme necessário)
PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
SHP2PGSQL = os.path.join(PG_BIN, "shp2pgsql.exe")
PSQL = os.path.join(PG_BIN, "psql.exe")
DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def garantir_diretorios():
    for pasta in [DATA_DIR, CENSO_DIR, USO_TERRA_DIR]:
        pasta.mkdir(parents=True, exist_ok=True)
    for uf in UFS:
        (CENSO_DIR / uf).mkdir(exist_ok=True)
        (USO_TERRA_DIR / uf).mkdir(exist_ok=True)

def obter_links_ibge(url_raiz):
    """Varre o diretório do IBGE e retorna uma lista de links para arquivos .zip."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        r = requests.get(url_raiz, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            # O IBGE pode ter subpastas ou o ZIP direto.
            # Aqui filtramos apenas links para arquivos .zip ou diretórios das UFs.
            links.append(urllib.parse.urljoin(url_raiz, href))
        return links
    except Exception as e:
        logging.error(f"Erro ao acessar {url_raiz}: {e}")
        return []

def baixar_aria2c(url, destino_pasta, nome_arquivo):
    """Invoca o aria2c para baixar o arquivo super rápido e com resiliência."""
    destino_completo = destino_pasta / nome_arquivo
    if destino_completo.exists():
        logging.info(f"⏭️ Pulo: Arquivo já existe -> {destino_completo}")
        return True

    logging.info(f"⬇️ Iniciando aria2c para: {url}")
    cmd = [
        "aria2c", 
        "-x", "4",          # 4 conexões por servidor
        "-s", "4",          # Dividir o arquivo em 4
        "-d", str(destino_pasta), 
        "-o", nome_arquivo,
        "--auto-file-renaming=false",
        "--allow-overwrite=true",
        url
    ]
    try:
        # shell=True on Windows is sometimes needed for aria2c if it's not in PATH of python's os.environ directly
        # but since we restarted or winget added to path, we try normal first. If fail, shell=True.
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"❌ Falha no aria2c: {result.stderr}")
            if destino_completo.exists():
                destino_completo.unlink()
            return False
        return True
    except Exception as e:
        logging.error(f"Erro ao rodar aria2c: {e}")
        return False

def ingerir_shapefile_unico(pasta_uf, prefixo_shp, tabela_destino, primeiro_estado):
    """Ingere um único shapefile usando shp2pgsql."""
    import glob
    shps = glob.glob(str(pasta_uf / f"*{prefixo_shp}*.shp"))
    if not shps:
        logging.warning(f"Shapefile não encontrado para {pasta_uf.name} na pasta {pasta_uf}")
        return False
        
    shp_path = shps[0]
    modo = "-c" if primeiro_estado else "-a"
    temp_sql = pasta_uf / "temp_ingestao.sql"
    
    logging.info(f"[{pasta_uf.name}] Gerando SQL para {Path(shp_path).name}...")
    cmd_shp2pgsql = f'"{SHP2PGSQL}" {modo} -s 4674 -W "LATIN1" -I "{shp_path}" public.{tabela_destino} > "{temp_sql}"'
    if subprocess.run(cmd_shp2pgsql, shell=True).returncode != 0:
        logging.error(f"Erro no shp2pgsql para {pasta_uf.name}")
        return False
        
    logging.info(f"[{pasta_uf.name}] Injetando no PostgreSQL...")
    cmd_psql = f'"{PSQL}" "{DB_URI}" -q -f "{temp_sql}"'
    if subprocess.run(cmd_psql, shell=True).returncode != 0:
        logging.error(f"Erro no psql para {pasta_uf.name}")
        return False
        
    temp_sql.unlink(missing_ok=True)
    return True

def orquestrar_pipeline(uf, base_url, diretorio, prefixo_shp, tabela_destino, primeiro_estado):
    """Pipeline completo: Pega links dinâmicos -> Baixa -> Extrai -> Ingere -> Limpa."""
    # Como as UFs têm subpastas no IBGE na maioria das vezes, vamos resolver o link dinamicamente.
    # Ex: no censo a URL é .../Malha_de_Setores_Censitarios/AC/AC_Malha_2022.zip
    url_uf = f"{base_url}{uf}/"
    links = obter_links_ibge(url_uf)
    
    zip_url = next((link for link in links if link.lower().endswith(".zip")), None)
    if not zip_url:
        logging.error(f"Nenhum ZIP encontrado para {uf} em {url_uf}")
        return False
        
    nome_zip = zip_url.split('/')[-1]
    pasta_uf = diretorio / uf
    caminho_zip = pasta_uf / nome_zip
    
    # 1. Download (aria2c)
    if not baixar_aria2c(zip_url, pasta_uf, nome_zip):
        return False
        
    # 2. Extract
    try:
        logging.info(f"📦 Extraindo: {caminho_zip.name}")
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta_uf)
        # 3. Clean ZIP
        caminho_zip.unlink()
    except Exception as e:
        logging.error(f"Erro ao extrair {caminho_zip}: {e}")
        return False
        
    # 4. Ingest (shp2pgsql -> PostgreSQL)
    sucesso_ingestao = ingerir_shapefile_unico(pasta_uf, prefixo_shp, tabela_destino, primeiro_estado)
    
    # 5. Clean SHPs
    if sucesso_ingestao:
        logging.info(f"🧹 Limpando dados brutos da pasta {pasta_uf}...")
        for item in pasta_uf.iterdir():
            if item.is_file():
                item.unlink()
                
    return sucesso_ingestao

def main():
    logging.info("🚀 Iniciando Motor de Ingestão de Dados Oficiais (IBGE) via aria2c + shp2pgsql")
    garantir_diretorios()
    
    primeiro_censo = True
    primeiro_uso = True
    
    for uf in UFS:
        logging.info(f"=== PROCESSANDO {uf} ===")
        # Censo
        if orquestrar_pipeline(uf, CENSO_URL, CENSO_DIR, "Setores", "ibge_setores_raw", primeiro_censo):
            primeiro_censo = False
            
        # Uso da Terra
        if orquestrar_pipeline(uf, USO_TERRA_URL, USO_TERRA_DIR, "Uso_Terra", "ibge_vegetacao_raw", primeiro_uso):
            primeiro_uso = False
            
    logging.info("🏁 Pipeline de Download e Ingestão Automática Finalizado com Sucesso!")

if __name__ == "__main__":
    main()
