import geopandas as gpd
from sqlalchemy import create_engine, text
import zipfile
import os

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
ZIP_PATH = "data/ibge_areas_urbanizadas/AreasUrbanizadas2019_Brasil.zip"
EXTRACT_DIR = "data/ibge_areas_urbanizadas/extracted"

def main():
    print(f"Extraindo {ZIP_PATH}...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        zip_ref.extractall(EXTRACT_DIR)
    
    # Encontrar o .shp
    shp_file = None
    for root, dirs, files in os.walk(EXTRACT_DIR):
        for file in files:
            if file.endswith('.shp'):
                shp_file = os.path.join(root, file)
                break
    
    if not shp_file:
        print("Erro: Shapefile não encontrado após extração.")
        return

    print(f"Lendo Shapefile: {shp_file}")
    gdf = gpd.read_file(shp_file)
    
    print("Reprojetando para WGS84 (EPSG:4326)...")
    gdf = gdf.to_crs(epsg=4326)
    
    print("Conectando ao banco de dados...")
    engine = create_engine(DB_URI)
    
    print("Salvando no PostGIS na tabela 'ibge_urban_areas'...")
    gdf.to_postgis('ibge_urban_areas', engine, if_exists='replace', index=False)
    
    # Adicionar index espacial
    with engine.connect() as con:
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_ibge_urban_geom ON ibge_urban_areas USING GIST (geometry);"))
        
    print("Sucesso! Áreas urbanizadas inseridas como máscara.")

if __name__ == "__main__":
    main()
