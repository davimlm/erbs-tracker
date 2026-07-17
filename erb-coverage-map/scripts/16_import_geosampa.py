import os
import glob
import zipfile
import geopandas as gpd
from sqlalchemy import create_engine, text

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"

def main():
    print("Iniciando ingestão do GeoSampa...")
    engine = create_engine(DB_URI)
    
    geosampa_dir = "data/geosampa"
    zips = glob.glob(os.path.join(geosampa_dir, "*.zip"))
    print(f"Encontrados {len(zips)} arquivos ZIP do GeoSampa.")
    
    # Recria tabela
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS geosampa_buildings_3d;"))
        
    for i, z in enumerate(zips):
        print(f"[{i+1}/{len(zips)}] Processando {os.path.basename(z)}...")
        try:
            with zipfile.ZipFile(z, 'r') as zf:
                shp_files = [f for f in zf.namelist() if f.endswith('.shp') and 'SIRGAS' in f]
                if not shp_files:
                    print("   -> Shapefile SIRGAS não encontrado no ZIP.")
                    continue
                shp_path = f"zip://{z}!{shp_files[0]}"
                
            gdf = gpd.read_file(shp_path)
            
            if gdf.crs is None or gdf.crs.to_string() != 'EPSG:3857':
                # GeoSampa usually comes in SIRGAS 2000 UTM 23S (EPSG:31983)
                if gdf.crs is None:
                    gdf = gdf.set_crs(epsg=31983)
                gdf = gdf.to_crs(epsg=3857)
                
            cols_to_keep = ['ed_id', 'ed_area', 'ed_altura', 'geometry']
            existing_cols = [c for c in cols_to_keep if c in gdf.columns]
            gdf = gdf[existing_cols]
            
            from shapely.geometry.multipolygon import MultiPolygon
            def to_multi(geom):
                if geom is None: return None
                if geom.geom_type == 'Polygon':
                    return MultiPolygon([geom])
                return geom
            gdf['geometry'] = gdf['geometry'].apply(to_multi)
            
            gdf.to_postgis('geosampa_buildings_3d', engine, if_exists='append', index=False)
            print(f"   -> {len(gdf)} prédios inseridos.")
        except Exception as e:
            print(f"   -> Erro: {e}")
            
    print("Criando índice espacial...")
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_geosampa_geom_3857 ON geosampa_buildings_3d USING GIST (geometry);"))
        print("Realizando CLUSTER para otimização de I/O de disco...")
        conn.execute(text("CLUSTER geosampa_buildings_3d USING idx_geosampa_geom_3857;"))
        
    print("Ingestão do GeoSampa finalizada com sucesso!")

if __name__ == "__main__":
    main()
