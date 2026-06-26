import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
import h3
import json
from shapely.geometry import Polygon
import os
import glob
import re

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def load_real_data():
    print("Iniciando carga de dados REAIS para o PostGIS...")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    
    # 1. Carregar ERBs reais a partir dos JSONs divididos por região
    print("Processando ERBs reais...")
    erbs = []
    erbs_files = glob.glob(os.path.join(data_dir, 'erbs_*.json'))
    for file_path in erbs_files:
        if 'cidades' in file_path: continue
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                for cid, erb_list in data.items():
                    for idx, erb in enumerate(erb_list):
                        erbs.append({
                            "id": f"erb_{cid}_{idx}",
                            "lat": erb['lat'],
                            "lng": erb['lng'],
                            "operadora": erb['operadora'],
                            "frequencia": erb['frequencias'][0] if erb['frequencias'] else "700"
                        })
                        if len(erb['frequencias']) > 1:
                            for extra_freq in erb['frequencias'][1:]:
                                erbs.append({
                                    "id": f"erb_{cid}_{idx}_{extra_freq}",
                                    "lat": erb['lat'],
                                    "lng": erb['lng'],
                                    "operadora": erb['operadora'],
                                    "frequencia": extra_freq
                                })
            except Exception as e:
                print(f"Erro lendo {file_path}: {e}")

    df_erbs = pd.DataFrame(erbs)
    print(f"Total de antenas extraídas: {len(df_erbs)}")
    gdf_erbs = gpd.GeoDataFrame(df_erbs, geometry=gpd.points_from_xy(df_erbs.lng, df_erbs.lat), crs="EPSG:4326")
    
    # 2. Carregar Malhas H3 Reais
    print("Processando malhas H3 reais...")
    h3_files = glob.glob(os.path.join(data_dir, 'h3_grid_*.json'))
    
    grid_data = []
    
    for file_path in h3_files:
        cidade_id = os.path.basename(file_path).replace('h3_grid_', '').replace('.json', '')
        print(f"Lendo malha de {cidade_id}...")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            h3_dict = json.load(f)
            
        for h, pop in h3_dict.items():
            boundary_lat_lng = h3.cell_to_boundary(h)
            boundary = [(lng, lat) for lat, lng in boundary_lat_lng]
            poly = Polygon(boundary)
            
            # Simular percentagem vegetativa para áreas com pop < 50
            percent_vegetacao = 0
            if pop < 50:
                percent_vegetacao = 80
            
            grid_data.append({
                "h3_index": h,
                "populacao_estimada": int(pop),
                "percent_vegetacao": percent_vegetacao,
                "geometry": poly
            })
            
    df_grid = pd.DataFrame(grid_data)
    print(f"Total de hexágonos H3 extraídos: {len(df_grid)}")
    
    gdf_grid = gpd.GeoDataFrame(df_grid, geometry='geometry', crs="EPSG:4326")
    
    # 3. Inserir no PostGIS
    print("Conectando ao PostGIS...")
    engine = create_engine(DB_URI)
    
    print("Inserindo ERBs (isso pode levar alguns segundos)...")
    gdf_erbs.to_postgis("erbs_ativas", engine, if_exists="replace", index=False)
    
    # Criar índice espacial nas ERBs
    with engine.connect() as con:
        con.execute(text("CREATE INDEX IF NOT EXISTS idx_erbs_geom ON erbs_ativas USING GIST (geometry)"))
    
    if len(gdf_grid) > 0:
        print("Inserindo Malha H3 (isso pode levar de segundos a minutos, dependendo do tamanho)...")
        # Inserção em chunks para não estourar a memória
        gdf_grid.to_postgis("h3_grid_precalc", engine, if_exists="replace", index=False, chunksize=10000)
        
        with engine.connect() as con:
            con.execute(text("CREATE INDEX IF NOT EXISTS idx_h3_geom ON h3_grid_precalc USING GIST (geometry)"))
    
    print("Carga concluída com sucesso! Os dados reais agora estão no PostGIS.")

if __name__ == "__main__":
    load_real_data()
