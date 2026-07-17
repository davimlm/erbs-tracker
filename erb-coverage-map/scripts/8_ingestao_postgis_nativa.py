import os
import subprocess
import logging
from pathlib import Path
import glob

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Cuidado 1: Caminho dos binários do PostgreSQL no Windows
PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
SHP2PGSQL = os.path.join(PG_BIN, "shp2pgsql.exe")
PSQL = os.path.join(PG_BIN, "psql.exe")

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

UFS = ["AC"]

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CENSO_DIR = DATA_DIR / "ibge_censo"
USO_TERRA_DIR = DATA_DIR / "ibge_uso_terra"

def run_subprocess(command, shell=True):
    """Executa um comando no sistema operacional e captura a saída."""
    result = subprocess.run(command, shell=shell, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error(f"Erro no comando: {command}")
        logging.error(result.stderr)
        return False
    return True

def ingerir_shapefiles(diretorio_base, tabela_destino, prefixo_shp):
    """
    Varre os estados e faz a ingestão do shapefile principal de cada UF no PostGIS.
    """
    primeiro_estado = True
    
    for uf in UFS:
        pasta_uf = diretorio_base / uf
        if not pasta_uf.exists():
            continue
            
        # Pega o primeiro shapefile que bate com o prefixo
        shps = glob.glob(str(pasta_uf / f"*{prefixo_shp}*.shp"))
        if not shps:
            logging.warning(f"Shapefile não encontrado para {uf} na pasta {pasta_uf}")
            continue
            
        shp_path = shps[0]
        
        # Cuidado 4: A Lógica da Esteira (Criar na primeira UF, Apensar nas seguintes)
        modo = "-c" if primeiro_estado else "-a"
        
        # Cuidado 2 e 3: O Terror do Encoding (-W "LATIN1") e Projeção Geográfica (-s 4674)
        # Além disso, usamos -I para criar índices espaciais (GIST) automaticamente
        temp_sql = pasta_uf / "temp_ingestao.sql"
        
        logging.info(f"[{uf}] Gerando SQL para {Path(shp_path).name}...")
        
        # Fase 1: SHP para SQL
        cmd_shp2pgsql = f'"{SHP2PGSQL}" {modo} -s 4674 -W "LATIN1" -I "{shp_path}" public.{tabela_destino} > "{temp_sql}"'
        if not run_subprocess(cmd_shp2pgsql):
            continue
            
        logging.info(f"[{uf}] Injetando no PostgreSQL...")
        
        # Fase 2: SQL para Banco
        cmd_psql = f'"{PSQL}" "{DB_URI}" -q -f "{temp_sql}"'
        if not run_subprocess(cmd_psql):
            continue
            
        # Limpeza do arquivo SQL temporário
        temp_sql.unlink(missing_ok=True)
        
        primeiro_estado = False
        logging.info(f"[{uf}] ✅ Sucesso!")

def main():
    logging.info("🚀 Iniciando Ingestão Nativa no PostGIS")
    
    logging.info("--- 1. INGERINDO MALHA CENSITÁRIA ---")
    # Tabela temporária para os setores do censo com os dados populacionais
    ingerir_shapefiles(CENSO_DIR, "ibge_setores_raw", "Setores")
    
    logging.info("--- 2. INGERINDO USO DA TERRA ---")
    # Tabela temporária para a vegetação
    ingerir_shapefiles(USO_TERRA_DIR, "ibge_vegetacao_raw", "Uso_Terra")
    
    logging.info("🏁 Ingestão Finalizada! Os dados brutos já estão no banco.")

if __name__ == "__main__":
    main()
