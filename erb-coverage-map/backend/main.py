import os
import json
import logging
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import geopandas as gpd
from shapely.geometry import Point, shape, box, mapping, MultiPolygon, Polygon
import requests
import h3
import glob

logging.basicConfig(level=logging.INFO)
# trigger reload

app = FastAPI(title="ERB Coverage API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Caches
ibge_malha_cache = {}
config_cidades = {}
config_estados = {}
config_regioes = {}
erbs_data_cache = {}
h3_grid_cache = {}

def carregar_dados():
    config_path = os.path.join(DATA_DIR, 'config.js')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
            try:
                import re
                cidades_match = re.search(r'const CONFIG_CIDADES_GERADO = (.*?);\n', content)
                estados_match = re.search(r'const CONFIG_ESTADOS_GERADO = (.*?);\n', content)
                regioes_match = re.search(r'const CONFIG_REGIOES_GERADO = (.*?);\n', content)
                
                if cidades_match:
                    global config_cidades
                    config_cidades = json.loads(cidades_match.group(1))
                if estados_match:
                    global config_estados
                    config_estados = json.loads(estados_match.group(1))
                if regioes_match:
                    global config_regioes
                    config_regioes = json.loads(regioes_match.group(1))
                
                logging.info("Dados de config carregados com sucesso!")
            except Exception as e:
                logging.error(f"Erro parseando config.js: {e}")
                
    # Carregar ERBs dos arquivos json
    global erbs_data_cache, h3_grid_cache
    erbs_data_cache = {}
    h3_grid_cache = {}
    
    # Carregar ERBs
    erbs_files = glob.glob(os.path.join(DATA_DIR, 'erbs_*.json'))
    for file_path in erbs_files:
        if 'cidades' in file_path: continue
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                erbs_data_cache.update(data)
        except Exception as e:
            logging.error(f"Erro lendo {file_path}: {e}")
            
    # Carregar Grids H3
    h3_files = glob.glob(os.path.join(DATA_DIR, 'h3_grid_*.json'))
    for file_path in h3_files:
        cidade_id = os.path.basename(file_path).replace('h3_grid_', '').replace('.json', '')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                h3_grid_cache[cidade_id] = data
        except Exception as e:
            logging.error(f"Erro lendo {file_path}: {e}")
            
    logging.info(f"Total de cidades com ERBs: {len(erbs_data_cache)}. Grids H3: {len(h3_grid_cache)}")

@app.on_event("startup")
def startup_event():
    carregar_dados()

class CoverageRequest(BaseModel):
    locationId: str
    viewMode: str
    operadora: str
    frequencia: str
    mostrarPopulacao: bool
    mostrarVegetacao: bool = False

CONFIG_PROPAGACAO = {
    'all': 1200,
    '700': 1200,
    '2600': 600,
    '3500': 300
}

def get_ibge_malha(nivel, ibge_code):
    cache_key = f"{nivel}_{ibge_code}"
    if cache_key in ibge_malha_cache:
        return ibge_malha_cache[cache_key]
        
    url = f"https://servicodados.ibge.gov.br/api/v3/malhas/{nivel}/{ibge_code}?formato=application/vnd.geo+json"
    r = requests.get(url)
    if r.status_code == 200:
        geojson = r.json()
        ibge_malha_cache[cache_key] = geojson
        return geojson
    return None

@app.post("/api/coverage")
async def analyze_coverage(req: CoverageRequest):
    locationId = req.locationId
    viewMode = req.viewMode
    operadora = req.operadora
    frequencia = req.frequencia
    mostrar_populacao = req.mostrarPopulacao
    
    configLocal = None
    if viewMode == 'cidades': configLocal = config_cidades.get(locationId)
    elif viewMode == 'estados': configLocal = config_estados.get(locationId)
    elif viewMode == 'regioes': configLocal = config_regioes.get(locationId)
    
    if not configLocal:
        raise HTTPException(status_code=404, detail="Location not found")
        
    poligonoEstudo = None
    if configLocal.get('ibge_code'):
        nivel = 'municipios' if viewMode == 'cidades' else 'estados' if viewMode == 'estados' else 'regioes'
        malha_geojson = get_ibge_malha(nivel, configLocal['ibge_code'])
        if malha_geojson and malha_geojson.get('features'):
            geom = malha_geojson['features'][0]['geometry']
            poligonoEstudo = shape(geom)
            
    raio_metros = CONFIG_PROPAGACAO.get(frequencia, 1200)
    
    erbs = []
    if viewMode == 'cidades':
        erbs = erbs_data_cache.get(locationId, [])
    elif viewMode == 'estados':
        for cid, arr in erbs_data_cache.items():
            city_config = config_cidades.get(cid)
            if city_config and city_config.get('uf') == locationId:
                erbs.extend(arr)
    elif viewMode == 'regioes':
        for cid, arr in erbs_data_cache.items():
            city_config = config_cidades.get(cid)
            if city_config and city_config.get('regiao') == locationId:
                erbs.extend(arr)
                
    erbs_ativas = []
    for erb in erbs:
        match_op = (operadora == 'all') or (erb.get('operadora') == operadora)
        freqs = erb.get('frequencias', [])
        match_freq = (frequencia == 'all') or (frequencia in freqs)
        if match_op and match_freq:
            erbs_ativas.append(erb)
            
    if not poligonoEstudo:
        if viewMode == 'cidades' and erbs_ativas:
            min_x = min(e['lng'] for e in erbs_ativas)
            max_x = max(e['lng'] for e in erbs_ativas)
            min_y = min(e['lat'] for e in erbs_ativas)
            max_y = max(e['lat'] for e in erbs_ativas)
            margin_deg = (raio_metros / 1000.0) / 111.0 
            poligonoEstudo = box(min_x - margin_deg, min_y - margin_deg, max_x + margin_deg, max_y + margin_deg)
        else:
            lat, lng = configLocal['lat'], configLocal['lng']
            r_deg = 2.2 / 111.0
            if viewMode == 'estados': r_deg = 200 / 111.0
            if viewMode == 'regioes': r_deg = 800 / 111.0
            poligonoEstudo = box(lng - r_deg, lat - r_deg, lng + r_deg, lat + r_deg)

    poligonoSombra_json = None
    poligonoVegetativo_json = None
    uniaoCobertura = None
    aviso_area_verde = None
    
    if erbs_ativas:
        gdf_pts = gpd.GeoDataFrame(
            geometry=[Point(e['lng'], e['lat']) for e in erbs_ativas],
            crs="EPSG:4326"
        )
        gdf_pts_proj = gdf_pts.to_crs("EPSG:3857")
        gdf_pts_proj['geometry'] = gdf_pts_proj.geometry.buffer(raio_metros)
        uniao_proj = gdf_pts_proj.geometry.unary_union
        
        areaTotalKm2 = 0.0
        areaSombraKm2 = 0.0
        areaSombraHabitadaKm2 = 0.0
        areaSombraVegetativaKm2 = 0.0
        areaSombraPercent = 0.0
        
        if uniao_proj:
            uniao_series = gpd.GeoSeries([uniao_proj], crs="EPSG:3857").to_crs("EPSG:4326")
            uniaoCobertura = uniao_series[0]
            
            try:
                sombra = poligonoEstudo.difference(uniaoCobertura)
                poligonoSombra_json = mapping(sombra)
                
                # Calcular área exata via EPSG:6933
                gdf_estudo = gpd.GeoDataFrame(geometry=[poligonoEstudo], crs="EPSG:4326").to_crs("EPSG:6933")
                gdf_sombra = gpd.GeoDataFrame(geometry=[sombra], crs="EPSG:4326").to_crs("EPSG:6933")
                
                areaTotalKm2 = gdf_estudo.geometry.area.iloc[0] / 1e6
                areaSombraKm2 = gdf_sombra.geometry.area.iloc[0] / 1e6
                if areaTotalKm2 > 0:
                    areaSombraPercent = (areaSombraKm2 / areaTotalKm2) * 100
                
                # Isolamento Vegetativo usando H3 para viewMode cidades
                cid_normalized = locationId.replace('_sp', '').replace('_rj', '').replace('_mg', '').replace('_df', '')
                if viewMode == 'cidades' and cid_normalized in h3_grid_cache:
                    sombra_buffered = sombra.buffer(0.0015) # ~170 metros para evitar sumiço de áreas finas (Edge Case H3)
                    
                    def get_h3_cells(poly):
                        exterior = [(lat, lng) for lng, lat in poly.exterior.coords]
                        holes = [[(lat, lng) for lng, lat in interior.coords] for interior in poly.interiors]
                        h3_poly = h3.LatLngPoly(exterior, *holes)
                        return h3.polygon_to_cells(h3_poly, 9)
                        
                    sombra_cells = set()
                    if sombra_buffered.geom_type == 'Polygon':
                        sombra_cells.update(get_h3_cells(sombra_buffered))
                    elif sombra_buffered.geom_type == 'MultiPolygon':
                        for poly in sombra_buffered.geoms:
                            sombra_cells.update(get_h3_cells(poly))
                            
                    city_grid = h3_grid_cache[cid_normalized]
                    habitadas = {cell for cell in sombra_cells if cell in city_grid}
                    vegetativas = sombra_cells - habitadas
                    
                    total_cells = len(sombra_cells)
                    if total_cells > 0:
                        ratio = len(habitadas) / total_cells
                        areaSombraHabitadaKm2 = areaSombraKm2 * ratio
                        areaSombraVegetativaKm2 = areaSombraKm2 * (1 - ratio)
                        
                    if vegetativas:
                            # Gerar GeoJSON das células vegetativas para exibir no mapa
                            # cells_to_geo une as células adjacentes em polígonos otimizados (MultiPolygon)
                            geom_geo = h3.cells_to_geo(list(vegetativas))
                            geom_shape = shape(geom_geo)
                            
                            # Intersectar com a sombra original para cortar as bordas irregulares dos hexágonos
                            # e evitar que a área verde vaze além da cidade ou sobre as ERBs
                            vegetativo_final = geom_shape.intersection(sombra)
                            if not vegetativo_final.is_empty:
                                poligonoVegetativo_json = mapping(vegetativo_final)
                                
                else:
                    poligonoVegetativo_json = None
                    aviso_area_verde = "Sem dados populacionais granulares para calcular a área verde nesta localidade."
                        
            except Exception as e:
                logging.error(f"Erro na difereca: {e}")
                poligonoSombra_json = mapping(poligonoEstudo)
        else:
            poligonoSombra_json = mapping(poligonoEstudo)
    else:
        poligonoSombra_json = mapping(poligonoEstudo)

    popTotal = 0
    popSombra = 0
    populacao_pontos = []
    
    if viewMode == 'cidades':
        cid_normalized = locationId.replace('_sp', '').replace('_rj', '').replace('_mg', '').replace('_df', '')
        pop_file = os.path.join(DATA_DIR, f"populacao_real_{cid_normalized}.json")
        if os.path.exists(pop_file):
            with open(pop_file, 'r', encoding='utf-8') as f:
                dados_pop = json.load(f)
                
            for setor in dados_pop:
                pop = setor.get('populacao', 0)
                popTotal += pop
                pt = Point(setor['lng'], setor['lat'])
                
                na_sombra = True
                if uniaoCobertura:
                    na_sombra = not uniaoCobertura.contains(pt)
                    
                if na_sombra:
                    popSombra += pop
                    
                if mostrar_populacao:
                    populacao_pontos.append({
                        'lat': setor['lat'],
                        'lng': setor['lng'],
                        'na_sombra': na_sombra
                    })

    return {
        "poligonoSombra": poligonoSombra_json,
        "poligonoVegetativo": poligonoVegetativo_json,
        "popTotal": popTotal,
        "popSombra": popSombra,
        "erbsAtivas": erbs_ativas,
        "populacao_pontos": populacao_pontos,
        "areaTotalKm2": areaTotalKm2,
        "areaSombraKm2": areaSombraKm2,
        "areaSombraPercent": areaSombraPercent,
        "areaSombraHabitadaKm2": areaSombraHabitadaKm2,
        "areaSombraVegetativaKm2": areaSombraVegetativaKm2,
        "aviso_area_verde": aviso_area_verde
    }

# Servir static files no final
app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
