from pyrosm import OSM
from sqlalchemy import create_engine, text
import pandas as pd
import gc
import os

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def main():
    print("Conectando ao banco...")
    engine = create_engine(DB_URI)
    
    pbf_path = "data/osm/sudeste-latest.osm.pbf"
    if not os.path.exists(pbf_path):
        print(f"Erro: Arquivo {pbf_path} não encontrado.")
        return

    # SP bbox + buffer
    minx, miny, maxx, maxy = -46.8262, -24.0084, -46.3651, -23.3564
    bbox = [minx - 0.01, miny - 0.01, maxx + 0.01, maxy + 0.01]
    
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS osm_buildings_3d_raw (id bigint, building text, \"building:levels\" text, height text, geometry geometry(MultiPolygon, 4326));"))
    
    print("Iniciando pyrosm com bbox...")
    try:
        osm = OSM(pbf_path, bounding_box=bbox)
        print("Lendo predios...")
        buildings = osm.get_buildings()
        if buildings is not None and not buildings.empty:
            cols_to_keep = ['id', 'building', 'building:levels', 'height', 'geometry']
            existing_cols = [c for c in cols_to_keep if c in buildings.columns]
            buildings = buildings[existing_cols]
            
            buildings = buildings[buildings.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])].copy()
            
            from shapely.geometry.multipolygon import MultiPolygon
            def to_multi(geom):
                if geom.geom_type == 'Polygon':
                    return MultiPolygon([geom])
                return geom
            
            buildings['geometry'] = buildings['geometry'].apply(to_multi)
            
            print(f"Salvando {len(buildings)} predios no banco...")
            buildings.to_postgis('osm_buildings_3d_raw', engine, if_exists='append', index=False)
            print("Prédios salvos com sucesso.")
        else:
            print("Nenhum prédio encontrado no bbox.")
            
    except Exception as e:
        print(f"Erro: {e}")
        
    print("Criando índice espacial...")
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_osm_bldg_geom ON osm_buildings_3d_raw USING GIST (geometry);"))
        
if __name__ == "__main__":
    main()
