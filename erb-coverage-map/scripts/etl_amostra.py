import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine
import h3
from shapely.geometry import Polygon
import random

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def gerar_amostra_sbc():
    print("Iniciando ETL para amostra controlada (São Bernardo do Campo)...")
    
    # Coordenadas base de SBC
    lat_sbc = -23.6938
    lng_sbc = -46.5656
    
    # 1. Gerar ERBs de amostra
    print("Gerando ERBs...")
    erbs = []
    operadoras = ["vivo", "claro", "tim"]
    for i in range(15):
        erbs.append({
            "id": f"erb_sbc_{i}",
            "lat": lat_sbc + random.gauss(0, 0.05),
            "lng": lng_sbc + random.gauss(0, 0.05),
            "operadora": random.choice(operadoras),
            "frequencia": random.choice(["700", "2600", "3500"])
        })
    df_erbs = pd.DataFrame(erbs)
    gdf_erbs = gpd.GeoDataFrame(df_erbs, geometry=gpd.points_from_xy(df_erbs.lng, df_erbs.lat), crs="EPSG:4326")
    
    # 2. Gerar Malha H3 pré-calculada (População e Vegetação)
    print("Gerando Malha H3 (Resolução 9)...")
    res = 9
    # Bounding box aproximada de SBC
    min_lat, max_lat = -24.0, -23.6
    min_lng, max_lng = -46.7, -46.4
    
    poly_geo = {
        "type": "Polygon",
        "coordinates": [[[min_lng, min_lat], [min_lng, max_lat], [max_lng, max_lat], [max_lng, min_lat], [min_lng, min_lat]]]
    }
    poly_coords = [(lat, lng) for lng, lat in poly_geo["coordinates"][0]]
    poly_h3 = h3.LatLngPoly(poly_coords)
    hexagons = h3.polygon_to_cells(poly_h3, res)
    
    grid_data = []
    for h in hexagons:
        # Pega o centro do hexágono para calcular distâncias e criar gradientes
        lat, lng = h3.cell_to_latlng(h)
        
        # Simular densidade populacional (mais alta ao norte de SBC, mais baixa ao sul/represa)
        # O norte fica perto de -23.69, o sul perto de -23.9
        dist_norte = abs(lat - (-23.69))
        populacao = max(0, int(1000 - (dist_norte * 20000) + random.randint(-100, 100)))
        if populacao < 50:
            populacao = 0
            
        # Simular vegetação (mananciais/Billings ficam ao sul, logo tem mais vegetação)
        percent_vegetacao = min(100, max(0, int(dist_norte * 400 + random.randint(-10, 10))))
        if populacao > 500:
            percent_vegetacao = 0 # Áreas densas não tem mata
            
        # H3 v4.0 retorna (lat, lng), mas Polygon requer (lng, lat)
        boundary_lat_lng = h3.cell_to_boundary(h)
        boundary = [(lng, lat) for lat, lng in boundary_lat_lng]
        poly = Polygon(boundary)
        
        grid_data.append({
            "h3_index": h,
            "populacao_estimada": populacao,
            "percent_vegetacao": percent_vegetacao,
            "geometry": poly
        })
        
    gdf_grid = gpd.GeoDataFrame(grid_data, crs="EPSG:4326")
    
    # 3. Inserir no PostGIS
    print("Conectando ao PostGIS e inserindo dados via SQLAlchemy/GeoAlchemy2...")
    engine = create_engine(DB_URI)
    
    print(f"Inserindo {len(gdf_erbs)} ERBs...")
    gdf_erbs.to_postgis("erbs_ativas", engine, if_exists="replace", index=False)
    
    print(f"Inserindo {len(gdf_grid)} células H3...")
    gdf_grid.to_postgis("h3_grid_precalc", engine, if_exists="replace", index=False)
    
    print("ETL Concluído com sucesso! Banco populado.")

if __name__ == "__main__":
    gerar_amostra_sbc()
