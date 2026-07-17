import os
import zipfile
import subprocess
import time
import shutil

DATA_DIR = r"C:\Users\User\Downloads\SPE\erb-coverage-map\data\geosampa"
EXTRACT_DIR = os.path.join(DATA_DIR, "extracted")

if not os.path.exists(EXTRACT_DIR):
    os.makedirs(EXTRACT_DIR)

print("Iniciando processo de ingestão de distritos GeoSampa...")

# 1. Extrair os arquivos zip se necessário
zip_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.zip')]
print(f"Encontrados {len(zip_files)} arquivos ZIP.")

for zf in zip_files:
    zip_path = os.path.join(DATA_DIR, zf)
    district_name = zf.replace('.zip', '')
    district_extract_path = os.path.join(EXTRACT_DIR, district_name)
    
    if not os.path.exists(district_extract_path):
        print(f"Extraindo {zf}...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(district_extract_path)
        except Exception as e:
            print(f"Erro ao extrair {zf}: {e}")

print("Extração concluída. Buscando shapefiles SIRGAS...")

# 2. Localizar os shapefiles SIRGAS
shapefiles = []
for root, dirs, files in os.walk(EXTRACT_DIR):
    for f in files:
        if f.endswith('.shp') and f.upper().startswith('SIRGAS'):
            shapefiles.append(os.path.join(root, f))

print(f"Encontrados {len(shapefiles)} shapefiles para ingestão.")

# 3. Rodar shp2pgsql e psql
# O caminho para psql no Windows geralmente não está no PATH a menos que configurado, 
# mas o usuário deve ter, vamos tentar. O postgres no powershell original usa `psql -U postgres -d cobertura_db -q`
# Porém no teste anterior o `psql` não foi encontrado no PATH.
# Vamos assumir que a variável de ambiente do PostgreSQL bin directory existe ou usar o caminho padrão.

PSQL_PATH = "psql"
SHP2PGSQL_PATH = "shp2pgsql"

# Tentar encontrar o path do PostgreSQL se psql não estiver global
pg_paths = [
    r"C:\Program Files\PostgreSQL\18\bin",
    r"C:\Program Files\PostgreSQL\16\bin",
    r"C:\Program Files\PostgreSQL\15\bin",
    r"C:\Program Files\PostgreSQL\14\bin",
    r"C:\Program Files\PostgreSQL\13\bin",
    r"C:\Program Files\PostGIS 3\bin"
]

def find_bin(name):
    for p in pg_paths:
        if os.path.exists(os.path.join(p, name + ".exe")):
            return os.path.join(p, name + ".exe")
    return name

psql_exe = find_bin("psql")
shp2pgsql_exe = find_bin("shp2pgsql")

print(f"Usando psql: {psql_exe}")
print(f"Usando shp2pgsql: {shp2pgsql_exe}")

os.environ["PGPASSWORD"] = "UFABC" # The password from test_mvt.py postgresql://postgres:UFABC@localhost

success_count = 0
for idx, shp in enumerate(shapefiles):
    name = os.path.basename(shp)
    print(f"[{idx+1}/{len(shapefiles)}] Injetando {name}...")
    
    # -a (append), -W LATIN1 (encoding), -s 31983:3857 (reproject), -S (simple geometry)
    cmd_shp = [shp2pgsql_exe, "-a", "-W", "LATIN1", "-s", "31983:3857", "-S", shp, "public.geosampa_buildings_3d"]
    cmd_psql = [psql_exe, "-U", "postgres", "-d", "cobertura_db", "-q"]
    
    try:
        p1 = subprocess.Popen(cmd_shp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p2 = subprocess.Popen(cmd_psql, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p1.stdout.close() 
        out, err = p2.communicate()
        
        if p2.returncode == 0:
            success_count += 1
            print(f"  -> SUCESSO: {name}")
        else:
            print(f"  -> ERRO: {err.decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"  -> EXCEPTION: {e}")

print(f"Ingestão concluída. {success_count}/{len(shapefiles)} shapefiles inseridos.")

print("Limpando cache do mapa...")
cache_dir = r"C:\Users\User\Downloads\SPE\erb-coverage-map\backend\cache"
if os.path.exists(cache_dir):
    for f in os.listdir(cache_dir):
        if f.endswith('.pbf'):
            os.remove(os.path.join(cache_dir, f))
print("Cache removido.")

print("Rodando VACUUM ANALYZE...")
try:
    subprocess.run([psql_exe, "-U", "postgres", "-d", "cobertura_db", "-c", "VACUUM ANALYZE geosampa_buildings_3d;"], check=True)
    print("VACUUM concluído.")
except Exception as e:
    print(f"Erro no VACUUM: {e}")

print("Tudo pronto!")
