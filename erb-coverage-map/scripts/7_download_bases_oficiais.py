import os
import requests
import zipfile
import logging
from pathlib import Path

# Configuração de Logs para acompanhamento
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista oficial de UFs do Brasil
UFS = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", 
    "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", 
    "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"
]

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CENSO_DIR = DATA_DIR / "ibge_censo"
USO_TERRA_DIR = DATA_DIR / "ibge_uso_terra"

def garantir_diretorios():
    """Cria a estrutura de pastas caso não exista."""
    for pasta in [DATA_DIR, CENSO_DIR, USO_TERRA_DIR]:
        pasta.mkdir(parents=True, exist_ok=True)
    for uf in UFS:
        (CENSO_DIR / uf).mkdir(exist_ok=True)
        (USO_TERRA_DIR / uf).mkdir(exist_ok=True)

def download_em_chunks(url, destino, chunk_size=8192):
    """
    Faz o download em streaming direto para o disco rígido.
    Garante que a RAM não seja sobrecarregada com arquivos de múltiplos GBs.
    """
    if destino.exists():
        logging.info(f"⏭️ Pulo: Arquivo já existe -> {destino.name}")
        return True

    logging.info(f"⬇️ Iniciando download: {url}")
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(destino, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
        logging.info(f"✅ Download concluído: {destino.name}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Erro ao baixar {url}: {e}")
        # Remove o arquivo corrompido caso tenha falhado no meio
        if destino.exists():
            destino.unlink()
        return False

def extrair_zip(caminho_zip, diretorio_extracao):
    """Extrai o arquivo e remove o ZIP para poupar SSD."""
    try:
        logging.info(f"📦 Extraindo: {caminho_zip.name}")
        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(diretorio_extracao)
        # Limpeza do ZIP original para economizar espaço
        caminho_zip.unlink()
        logging.info(f"🧹 ZIP removido, dados extraídos em: {diretorio_extracao}")
    except zipfile.BadZipFile:
        logging.error(f"❌ Arquivo ZIP corrompido: {caminho_zip.name}")
        caminho_zip.unlink()

def baixar_malha_censo():
    """
    Orquestra o download da Malha de Setores Censitários 2022 do IBGE por UF.
    *Nota: Os links do GeoFTP do IBGE são case-sensitive.
    """
    logging.info("--- INICIANDO PIPELINE: MALHA CENSITÁRIA 2022 ---")
    base_url = "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/2022/Malha_de_setores_censitarios_-_arquivo_por_UF/"
    
    for uf in UFS:
        # Padrão de nomenclatura IBGE 2022 (ex: AC_Malha_Preliminar_2022.zip)
        # É importante conferir no GeoFTP se o padrão exato de nomenclatura mudou.
        nome_arquivo = f"{uf}_Malha_Preliminar_2022.zip"
        url = f"{base_url}{uf}/{nome_arquivo}"
        
        destino_zip = CENSO_DIR / uf / nome_arquivo
        
        # O arquivo SHP principal para checar a idempotência da extração
        shp_esperado = CENSO_DIR / uf / f"{uf}_Setores_2022.shp"
        
        if shp_esperado.exists():
            logging.info(f"⏭️ Pulo: Dados extraídos já existem para {uf}")
            continue
            
        sucesso = download_em_chunks(url, destino_zip)
        if sucesso and destino_zip.exists():
            extrair_zip(destino_zip, CENSO_DIR / uf)

def baixar_uso_terra():
    """
    Orquestra o download dos vetores de Uso e Cobertura da Terra do IBGE.
    *Nota: Diferente do Censo, a base ambiental do IBGE geralmente 
    é distribuída por recortes estaduais ou malha nacional na escala 1:250.000.
    """
    logging.info("--- INICIANDO PIPELINE: USO DA TERRA ---")
    # Link de exemplo do FTP de geociências do IBGE para a cobertura vetorial.
    base_url = "https://geoftp.ibge.gov.br/cartas_e_mapas/mapas_ambientais/uso_de_cobertura_da_terra/shapefile/estado/"
    
    for uf in UFS:
        nome_arquivo = f"Uso_Terra_{uf}.zip"
        url = f"{base_url}{uf}/{nome_arquivo}"
        
        destino_zip = USO_TERRA_DIR / uf / nome_arquivo
        shp_esperado = USO_TERRA_DIR / uf / f"Uso_Terra_{uf}.shp"
        
        if shp_esperado.exists():
            logging.info(f"⏭️ Pulo: Dados ambientais já existem para {uf}")
            continue
            
        # Para fins de PoC, se um estado falhar, tentamos o próximo
        sucesso = download_em_chunks(url, destino_zip)
        if sucesso and destino_zip.exists():
            extrair_zip(destino_zip, USO_TERRA_DIR / uf)

if __name__ == "__main__":
    logging.info("🚀 Iniciando Motor de Ingestão de Dados Oficiais (IBGE)")
    garantir_diretorios()
    baixar_malha_censo()
    baixar_uso_terra()
    logging.info("🏁 Pipeline de Download Finalizado!")
