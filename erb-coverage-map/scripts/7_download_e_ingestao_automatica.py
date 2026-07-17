import os
import requests
import zipfile
import logging
import subprocess
import re
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

# --- URLs Exatas e Definitivas ---
# Censo 2022: O IBGE agora consolida o Brasil num único ficheiro (BR)
CENSO_URL_BR = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/malha_com_atributos/setores/shp/UF/"
ZIP_CENSO_NOME = "BR_setores_CD2022.zip"
CENSO_ZIP_URL = f"{CENSO_URL_BR}{ZIP_CENSO_NOME}"

# Uso da Terra: Mantém-se a divisão por Unidade da Federação (UF)
USO_TERRA_URL = "https://geoftp.ibge.gov.br/informacoes_ambientais/cobertura_e_uso_da_terra/uso_250mil/vetores/unidades_da_federacao/"

# Diretorias base
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CENSO_DIR = DATA_DIR / "ibge_censo"
USO_TERRA_DIR = DATA_DIR / "ibge_uso_terra"

# IMPORTANTE: Confirme se a diretoria do PostgreSQL corresponde à sua versão (ex: \15\bin)
PG_BIN = r"C:\Program Files\PostgreSQL\15\bin" 
SHP2PGSQL = os.path.join(PG_BIN, "shp2pgsql.exe")
PSQL = os.path.join(PG_BIN, "psql.exe")
DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def garantir_diretorios():
    for pasta in [DATA_DIR, CENSO_DIR, USO_TERRA_DIR]:
        pasta.mkdir(parents=True, exist_ok=True)
    for uf in UFS:
        (USO_TERRA_DIR / uf).mkdir(exist_ok=True)

def obter_links_ibge(url_raiz):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        logging.info(f"🔍 A mapear diretoria IBGE: {url_raiz}")
        r = requests.get(url_raiz, headers=headers, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        # Filtra estritamente ficheiros ZIP
        return [urllib.parse.urljoin(url_raiz, a['href']) for a in soup.find_all('a', href=True) if a['href'].lower().endswith('.zip')]
    except Exception as e:
        logging.error(f"❌ Erro ao aceder a {url_raiz}: {e}")
        return []

def baixar_aria2c(url, destino_pasta, nome_arquivo):
    destino_completo = destino_pasta / nome_arquivo
    if destino_completo.exists():
        logging.info(f"⏭️ Ignorado: O ficheiro já existe -> {destino_completo}")
        return True

    logging.info(f"⬇️ A descarregar: {url}")
    cmd = [
        "aria2c", "-x", "4", "-s", "4", "-d", str(destino_pasta), 
        "-o", nome_arquivo, "--auto-file-renaming=false", 
        "--allow-overwrite=true", url
    ]
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error(f"❌ Falha no aria2c: {result.stderr}")
        if destino_completo.exists():
            destino_completo.unlink()
        return False
    return True

def ingerir_shapefile(pasta_alvo, prefixo_shp, tabela_destino, modo_append=False):
    import glob
    shps = glob.glob(str(pasta_alvo / f"*{prefixo_shp}*.shp"))
    if not shps:
        shps = glob.glob(str(pasta_alvo / "*.shp"))
        
    if not shps:
        logging.warning(f"⚠️ Nenhum Shapefile encontrado em {pasta_alvo}")
        return False
        
    shp_path = shps[0]
    modo = "-a" if modo_append else "-c"
    temp_sql = pasta_alvo / "temp_ingestao.sql"
    
    logging.info(f"[{pasta_alvo.name}] A gerar SQL para {Path(shp_path).name}...")
    cmd_shp2pgsql = f'"{SHP2PGSQL}" {modo} -s 4674 -W "LATIN1" -I "{shp_path}" public.{tabela_destino} > "{temp_sql}"'
    
    if subprocess.run(cmd_shp2pgsql, shell=True).returncode != 0:
        logging.error("Erro interno no utilitário shp2pgsql.")
        return False
        
    logging.info(f"[{pasta_alvo.name}] A injetar no PostgreSQL...")
    cmd_psql = f'"{PSQL}" "{DB_URI}" -q -f "{temp_sql}"'
    
    if subprocess.run(cmd_psql, shell=True).returncode != 0:
        logging.error("Erro na injeção via psql.")
        return False
        
    temp_sql.unlink(missing_ok=True)
    return True

def main():
    logging.info("🚀 A iniciar Motor Automático IBGE")
    garantir_diretorios()
    
    # ---------------------------------------------------------
    # PIPELINE 1: CENSO 2022 (Ficheiro Único Nacional)
    # ---------------------------------------------------------
    logging.info("=== PROCESSAR MALHA NACIONAL DO CENSO (BR) ===")
    if baixar_aria2c(CENSO_ZIP_URL, CENSO_DIR, ZIP_CENSO_NOME):
        zip_path = CENSO_DIR / ZIP_CENSO_NOME
        try:
            logging.info(f"📦 A extrair {ZIP_CENSO_NOME}...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(CENSO_DIR)
            zip_path.unlink() # Limpa o zip gigante imediatamente para poupar espaço
            
            # Injeta criando a tabela nova (modo_append=False)
            if ingerir_shapefile(CENSO_DIR, "BR_setores", "ibge_setores_raw", modo_append=False):
                logging.info("🧹 A limpar ficheiros brutos do Censo...")
                for item in CENSO_DIR.iterdir():
                    if item.is_file():
                        try: item.unlink()
                        except: pass
        except Exception as e:
            logging.error(f"Erro no pipeline do Censo: {e}")

   # ---------------------------------------------------------
    # PIPELINE 2: USO DA TERRA (Iteração por UF)
    # ---------------------------------------------------------
    logging.info("=== PROCESSAR USO DA TERRA POR UF ===")
    primeiro_uso = True
    
    for uf in UFS:
        logging.info(f"--- UF: {uf} ---")
        # O IBGE colocou os dados dentro de subpastas em minúsculas para cada estado
        url_uf = f"{USO_TERRA_URL}{uf.lower()}/"
        
        # Acedemos à pasta específica do estado e procuramos qualquer ficheiro ZIP
        links_uf = obter_links_ibge(url_uf)
        url_zip_uso = next((l for l in links_uf if l.lower().endswith('.zip')), None)
        
        if not url_zip_uso:
            logging.error(f"Ficheiro ZIP de Uso da Terra não encontrado na pasta {url_uf}")
            continue
            
        nome_zip = url_zip_uso.split('/')[-1]
        pasta_uf = USO_TERRA_DIR / uf
        
        if baixar_aria2c(url_zip_uso, pasta_uf, nome_zip):
            caminho_zip = pasta_uf / nome_zip
            try:
                logging.info(f"📦 A extrair {nome_zip}...")
                with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
                    zip_ref.extractall(pasta_uf)
                caminho_zip.unlink()
                
                # Deixamos o prefixo vazio para o fallback apanhar o .shp independentemente do nome
                if ingerir_shapefile(pasta_uf, "", "ibge_vegetacao_raw", modo_append=not primeiro_uso):
                    primeiro_uso = False
                    logging.info(f"🧹 A limpar ficheiros brutos de {uf}...")
                    for item in pasta_uf.iterdir():
                        if item.is_file():
                            try: item.unlink()
                            except: pass
            except Exception as e:
                logging.error(f"Erro a extrair dados do estado {uf}: {e}")

    logging.info("🏁 Pipeline Finalizado e dados guardados na base de dados!")

if __name__ == "__main__":
    main()