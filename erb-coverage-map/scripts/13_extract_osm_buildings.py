from pyrosm import OSM
from sqlalchemy import create_engine, text
import geopandas as gpd
import pandas as pd
import gc
import os

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def main():
    print("Conectando ao banco para obter áreas urbanas...")
    engine = create_engine(DB_URI)
    
    pbf_path = "data/osm/brazil-latest.osm.pbf"
    if not os.path.exists(pbf_path):
        print(f"Erro: Arquivo {pbf_path} não encontrado.")
        return

    print("Buscando envelopes das áreas urbanas do IBGE...")
    query = """
    SELECT ST_XMin(geometry) as min_lon, ST_YMin(geometry) as min_lat, 
           ST_XMax(geometry) as max_lon, ST_YMax(geometry) as max_lat
    FROM ibge_urban_areas
    """
    bboxes = pd.read_sql(query, engine)
    print(f"Encontradas {len(bboxes)} manchas urbanas para processar.")
    
    # Recria a tabela vazia para limpar execuções anteriores ou a tabela dummy
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS osm_buildings_3d_raw;"))
        conn.execute(text("CREATE TABLE osm_buildings_3d_raw (id bigint, building text, \"building:levels\" text, height text, geometry geometry(MultiPolygon, 4326));"))
    
    for idx, row in bboxes.iterrows():
        minx, miny, maxx, maxy = row['min_lon'], row['min_lat'], row['max_lon'], row['max_lat']
        # Expande levemente o bbox para não cortar prédios na borda exata da geometria urbana
        bbox = [minx - 0.01, miny - 0.01, maxx + 0.01, maxy + 0.01]
        
        print(f"Processando mancha {idx+1}/{len(bboxes)}...")
        try:
            osm = OSM(pbf_path, bounding_box=bbox)
            buildings = osm.get_buildings()
            if buildings is not None and not buildings.empty:
                cols_to_keep = ['id', 'building', 'building:levels', 'height', 'geometry']
                existing_cols = [c for c in cols_to_keep if c in buildings.columns]
                buildings = buildings[existing_cols]
                
                # Assegura que todas as geometrias sejam convertidas para MultiPolygon
                from shapely.geometry.multipolygon import MultiPolygon
                def to_multi(geom):
                    if geom.geom_type == 'Polygon':
                        return MultiPolygon([geom])
                    return geom
                
                buildings['geometry'] = buildings['geometry'].apply(to_multi)
                
                buildings.to_postgis('osm_buildings_3d_raw', engine, if_exists='append', index=False)
                print(f"   -> Salvos {len(buildings)} prédios no banco.")
            else:
                print("   -> Nenhum prédio encontrado.")
                
            del osm
            del buildings
        except Exception as e:
            print(f"   -> Erro ao processar mancha: {e}")
        
        # Limpa memória ativamente
        gc.collect()

    print("Criando índice espacial...")
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_osm_bldg_geom ON osm_buildings_3d_raw USING GIST (geometry);"))

    print("Extração concluída com sucesso!")

if __name__ == "__main__":
    main()
