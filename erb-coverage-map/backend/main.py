import os
import json
import logging
import psutil
import time
import asyncio
import warnings
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
from contextlib import asynccontextmanager

import math

# Suppress Rasterio and GDAL warnings
logging.getLogger("rasterio").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="rasterio")

def num2deg(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return (lat_deg, lon_deg)

logging.basicConfig(level=logging.INFO)

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logging.info("Conectando ao banco de dados...")
    db_pool = await asyncpg.create_pool(DB_URI, min_size=10, max_size=50)
    yield
    logging.info("Fechando conexões...")
    await db_pool.close()

app = FastAPI(title="ERB Coverage API - PostGIS MVT", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

CONFIG_PROPAGACAO = {
    'all': 1200,
    '700': 1200,
    '2600': 600,
    '3500': 300
}

from typing import Optional

class BBox(BaseModel):
    minLat: float
    minLng: float
    maxLat: float
    maxLng: float

class CoverageRequest(BaseModel):
    locationId: str
    viewMode: str
    operadora: str
    frequencia: str
    mostrarPopulacao: bool
    mostrarVegetacao: bool = False
    lat: Optional[float] = None
    lng: Optional[float] = None
    bbox: Optional[BBox] = None
    geojson: Optional[dict] = None

# Caches em memória para evitar recálculos no mesmo local
tile_cache = {}
coverage_cache = {}

CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

@app.delete("/api/admin/cache")
async def clear_cache():
    count = 0
    try:
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".pbf"):
                os.remove(os.path.join(CACHE_DIR, f))
                count += 1
    except Exception as e:
        return {"status": "error", "message": str(e)}
    return {"status": "success", "cleared_files": count}

@app.get("/api/status")
async def get_status(location_id: str = None):
    try:
        cache_size_bytes = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in os.listdir(CACHE_DIR) if os.path.isfile(os.path.join(CACHE_DIR, f)))
        cache_size_mb = round(cache_size_bytes / (1024 * 1024), 2)
        location_cached = False
        if location_id:
            location_cached = any(location_id in f for f in os.listdir(CACHE_DIR))
            
        async with db_pool.acquire() as conn:
            # Pega o total inserido até agora de forma aproximada e rápida
            count = await conn.fetchval("SELECT reltuples::bigint FROM pg_class WHERE relname = 'h3_grid_precalc'")
            # Tenta pegar se há subdivisão rodando (simples checagem no PID)
            subdivide = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE query LIKE '%ST_Subdivide%' AND state = 'active' AND pid != pg_backend_pid())")
        return {"status": "ok", "rows": count, "is_subdividing": subdivide, "cache_size_mb": cache_size_mb, "location_cached": location_cached}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/check_h3")
async def check_h3_status():
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT reltuples::bigint FROM pg_class WHERE relname = 'h3_grid_precalc'")
        return {"count": count}

@app.get("/api/admin/telemetry")
async def get_telemetry():
    procs = []
    for p in psutil.process_iter(['name', 'memory_info']):
        try:
            if p.info['name'] and 'postgres' in p.info['name'].lower():
                p.cpu_percent(interval=None)
                procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    await asyncio.sleep(0.1)
    
    postgres_cpu = 0.0
    postgres_ram = 0.0
    for p in procs:
        try:
            postgres_cpu += p.cpu_percent(interval=None)
            postgres_ram += p.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    ram_gb = round(postgres_ram / (1024**3), 2)
    total_ram = psutil.virtual_memory().total
    ram_percent = round((postgres_ram / total_ram) * 100, 1) if total_ram else 0
    
    db_conns = 0
    db_total = 100
    try:
        async with db_pool.acquire() as conn:
            db_conns = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
            db_total = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
    except Exception:
        pass

    return {
        "cpu_percent": round(postgres_cpu, 1),
        "ram_percent": ram_percent,
        "ram_used_gb": ram_gb,
        "db_active_connections": db_conns,
        "db_total_connections": db_total
    }

@app.get("/api/geosampa_tiles/{z}/{x}/{y}.pbf")
async def get_geosampa_mvt(z: int, x: int, y: int, response: Response, v: str = '1'):
    print(f"\n[MAPA] => Solicitando GEOSAMPA (Predios 3D): Z:{z} X:{x} Y:{y} (v={v})")
    cache_key = f"geosampa_{z}_{x}_{y}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pbf")
    
    headers = {
        "Cache-Control": "public, max-age=86400, immutable"
    }

    if z < 14:
        return Response(content=b"", media_type="application/x-protobuf", headers=headers)

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return Response(content=f.read(), media_type="application/x-protobuf", headers=headers)

    # CORREÇÃO: Aplica ST_Transform para 3857 e converte ed_altura explicitamente para Float
    query = '''
    WITH bounds AS (
        SELECT ST_TileEnvelope($1, $2, $3) AS geom_3857
    ),
    -- 1. Captura GeoSampa (AGORA RETORNANDO TUDO, COM ALTURA SINTÉTICA SE PRECISO)
    geo_bldgs AS (
        SELECT geometry AS geom,
               -- Se não tiver altura no banco da prefeitura, força a média real de SP (5.19m)
               COALESCE(
                   NULLIF(REGEXP_REPLACE(ed_altura::text, '[^0-9.]', '', 'g'), '')::float,
                   5.19
               ) AS height,
               'geosampa' AS source
        FROM geosampa_buildings_3d
        WHERE geometry && (SELECT geom_3857 FROM bounds)
    ),
    -- 2. Captura OSM (O Fallback para áreas onde NÃO HÁ geometria governamental)
    osm_bldgs AS (
        SELECT ST_Transform(geometry, 3857) AS geom,
               COALESCE(
                   NULLIF(REGEXP_REPLACE(height, '[^0-9.]', '', 'g'), '')::float,
                   NULLIF(REGEXP_REPLACE("building:levels", '[^0-9.]', '', 'g'), '')::float * 3.0,
                   5.19 
               ) AS height,
               'osm' AS source
        FROM osm_buildings_3d_raw
        WHERE geometry && ST_Transform((SELECT geom_3857 FROM bounds), 4326)
    ),
    -- 3. Mesclagem Espacial Mestra
    merged AS (
        SELECT geom, height, source FROM geo_bldgs
        
        UNION ALL
        
        SELECT o.geom, o.height, o.source
        FROM osm_bldgs o
        WHERE NOT EXISTS (
            SELECT 1 
            FROM geosampa_buildings_3d g
            WHERE g.geometry && (SELECT geom_3857 FROM bounds)
              AND ST_Intersects(o.geom, g.geometry)
            -- Removido o filtro que exigia altura > 0 do GeoSampa. 
            -- Se o GeoSampa tem o terreno, o OSM recua.
        )
    ),
    mvt_data AS (
        SELECT ST_AsMVTGeom(geom, (SELECT geom_3857 FROM bounds)) AS geom_mvt,
               GREATEST(height, 3.0) as height,
               source
        FROM merged
    )
    SELECT ST_AsMVT(mvt_data, 'geosampa') AS tile 
    FROM mvt_data 
    WHERE geom_mvt IS NOT NULL;
    '''
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(query, z, x, y)
            if row and row['tile']:
                with open(cache_path, "wb") as f:
                    f.write(row['tile'])
                return Response(content=row['tile'], media_type="application/x-protobuf", headers=headers)
    except Exception as e:
        logging.error(f"MVT GeoSampa Error: {e}")
        
    return Response(content=b"", media_type="application/x-protobuf", headers=headers)

@app.get("/api/tiles/{z}/{x}/{y}.pbf")
async def get_mvt_tile(z: int, x: int, y: int, response: Response, operadora: str = 'all', frequencia: str = 'all', locationId: str = 'none', viewMode: str = 'cidades'):
    print(f"\n[MAPA] => Solicitando MVT Predios/Pop: Z:{z} X:{x} Y:{y} (Local: {locationId})")
    cache_key = f"{z}_{x}_{y}_{locationId}_{operadora}_{frequencia}_{viewMode}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.pbf")
    
    headers = {
        "Cache-Control": "public, max-age=86400, immutable"
    }

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return Response(content=f.read(), media_type="application/x-protobuf", headers=headers)

    start_time = time.time()
    
    try:
        import rf_models
        raio_urbano, raio_rural = rf_models.obter_raios_frequencia(frequencia)
    except Exception:
        raio_urbano = 1200.0
        raio_rural = 1200.0
    
    max_raio = max(raio_urbano, raio_rural)

    # Física de Dados: Determinar a tolerância dinâmica
    lat_deg, lon_deg = num2deg(x, y, z)
    is_amazonia = (-15 <= lat_deg <= 5) and (-75 <= lon_deg <= -45)
    
    debug_tag = "Exata"
    
    if viewMode in ['estados', 'regioes']:
        if z < 8:
            # Visão nacional/macro
            tolerance = 0.02 if is_amazonia else 0.01
            debug_tag = f"Agressiva (z={z}, Amz: {is_amazonia})"
        else:
            # Visão regional
            tolerance = 0.005 if is_amazonia else 0.001
            debug_tag = f"Moderada (z={z}, Amz: {is_amazonia})"
            
        simplify_clause = f"ST_SimplifyPreserveTopology(v.geom, {tolerance})"
    else:
        # Visão de cidades: Geometria exata, sem simplificação na borda
        simplify_clause = "v.geom"
        debug_tag = f"Exata (Cidades, z={z})"
        
    query = f'''
    WITH bounds AS (
        SELECT ST_TileEnvelope({z}, {x}, {y}) AS geom_3857
    ),
    tile_clip AS (
        SELECT ST_Transform(geom_3857, 4326) as geom_4326 FROM bounds
    ),
    boundary AS (
        SELECT geom FROM ibge_boundaries WHERE id = '{locationId}'
    ),
    boundary_clip AS (
        SELECT ST_Intersection(tile_clip.geom_4326, COALESCE((SELECT geom FROM boundary), tile_clip.geom_4326)) as geom_4326
        FROM tile_clip
    ),
    erbs_buffers AS (
        SELECT ST_Union(ST_Buffer(e.geometry, 
            (CASE WHEN COALESCE(e.is_urbano, false) THEN {raio_urbano} ELSE {raio_rural} END) / 111320.0, 'quad_segs=4')) as geom
        FROM erbs_ativas e, tile_clip
        WHERE ('{operadora}' = 'all' OR e.operadora = '{operadora}') 
          AND ('{frequencia}' = 'all' OR e.frequencia = '{frequencia}')
          AND ST_DWithin(e.geometry, tile_clip.geom_4326, GREATEST({raio_urbano}, {raio_rural}) / 111320.0)
    ),
    sombra_geom AS (
        SELECT ST_CollectionExtract(
            ST_Difference(
                (SELECT geom_4326 FROM boundary_clip),
                COALESCE((SELECT geom FROM erbs_buffers), ST_GeomFromText('POLYGON EMPTY', 4326))
            ), 3
        ) as geom_4326
    ),
    mvt_sombra AS (
        SELECT ST_AsMVTGeom(ST_Transform(s.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom
        FROM sombra_geom s
        WHERE NOT ST_IsEmpty(s.geom_4326)
    ),
    celulas_veg AS (
        SELECT ST_Transform(
            CASE WHEN '{viewMode}' = 'cidades' THEN 
                ST_CollectionExtract(
                    ST_Intersection(v.geom, ST_Transform((SELECT geom_4326 FROM boundary_clip), 4674)), 3
                )
            ELSE
                {simplify_clause}
            END, 3857) as geom_3857,
            v.legenda,
            v.perda_700_dbm
        FROM ibge_vegetacao_subdividida v, tile_clip
        WHERE v.geom && ST_Transform(tile_clip.geom_4326, 4674)
          AND ST_Intersects(v.geom, ST_Transform(COALESCE((SELECT geom FROM boundary), tile_clip.geom_4326), 4674))
          AND v.legenda NOT ILIKE '%antrópic%'
          AND v.legenda NOT ILIKE '%urban%'
          AND v.legenda NOT ILIKE '%agro%'
          AND v.legenda NOT ILIKE '%pecuária%'
          AND v.legenda NOT ILIKE '%água%'
          AND v.legenda NOT ILIKE '%agua%'
          AND v.legenda NOT ILIKE '%rio%'
          AND v.legenda NOT ILIKE '%corpo d%'        
    ),
    mvt_vegetacao AS (
        SELECT 
            ST_AsMVTGeom(c.geom_3857, (SELECT geom_3857 FROM bounds)) AS geom,
            c.legenda,
            c.perda_700_dbm
        FROM celulas_veg c
        WHERE NOT ST_IsEmpty(c.geom_3857)
    ),
    celulas_pop AS (
        SELECT g.geom AS geom_4326,
               g.populacao_estimada as pop_absoluta,
               (ST_Area(g.geom::geography) / 1000000.0) as area_km2
        FROM h3_grid_precalc g, tile_clip
        WHERE g.geom && tile_clip.geom_4326
          AND ST_Intersects(g.geom, COALESCE((SELECT geom FROM boundary), tile_clip.geom_4326))
    ),
    mvt_populacao AS (
        SELECT ST_AsMVTGeom(ST_Transform(c.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
               c.pop_absoluta,
               CASE WHEN c.area_km2 > 0 THEN c.pop_absoluta / c.area_km2 ELSE 0 END as densidade,
               NOT EXISTS (
                   SELECT 1 FROM erbs_ativas e
                   WHERE ('{operadora}' = 'all' OR e.operadora = '{operadora}') 
                     AND ('{frequencia}' = 'all' OR e.frequencia = '{frequencia}')
                     AND ST_DWithin(c.geom_4326, e.geometry, {max_raio} / 111320.0)
                     AND ST_Distance(c.geom_4326, e.geometry) <= (CASE WHEN COALESCE(e.is_urbano, false) THEN {raio_urbano} ELSE {raio_rural} END) / 111320.0
               ) as na_sombra
        FROM celulas_pop c
        WHERE c.pop_absoluta > 0
    )
    SELECT (
        COALESCE((SELECT ST_AsMVT(mvt_sombra, 'sombra_exata') FROM mvt_sombra), '\\x'::bytea) || 
        COALESCE((SELECT ST_AsMVT(mvt_vegetacao, 'vegetacao') FROM mvt_vegetacao), '\\x'::bytea) ||
        COALESCE((SELECT ST_AsMVT(mvt_populacao, 'populacao') FROM mvt_populacao), '\\x'::bytea)
    ) AS tile;
    '''
    
    try:
        async with db_pool.acquire() as conn:
            tile = await conn.fetchval(query)
            
        duration_ms = int((time.time() - start_time) * 1000)
        logging.info(f"MVT Tile z:{z} x:{x} y:{y} calculado em {duration_ms}ms")
        response.headers["Server-Timing"] = f'db;desc="PostGIS MVT";dur={duration_ms}'
        response.headers["Cache-Control"] = "public, max-age=86400, immutable"
            
        if tile is None:
            tile = b""

        with open(cache_path, "wb") as f:
            f.write(tile)

        return Response(content=tile, media_type="application/x-protobuf", headers=response.headers)
    except Exception as e:
        logging.error(f"Erro fatal gerando Tile z:{z} x:{x} y:{y} -> {str(e)}")
        # Retorna um arquivo em branco em vez de Crashar o MapLibre
        return Response(content=b"", media_type="application/x-protobuf", headers=response.headers)

# Cache de memoria do indice de elevação
dem_index_cache = None

@app.get("/api/terrain/{z}/{x}/{y}.png")
async def get_terrain_tile(z: int, x: int, y: int, response: Response):
    print(f"\n[MAPA] => Solicitando TERRENO Topodata: Z:{z} X:{x} Y:{y}")
    
    headers = {
        "Cache-Control": "public, max-age=86400, immutable"
    }
    

    cache_key = f"terrain_{z}_{x}_{y}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.png")

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return Response(content=f.read(), media_type="image/png", headers=headers)

    global dem_index_cache
    if not dem_index_cache:
        index_path = os.path.join(DATA_DIR, "topodata_mde_raw", "dem_index.json")
        try:
            with open(index_path, 'r') as f:
                dem_index_cache = json.load(f)
        except Exception:
            dem_index_cache = []

    # Cálculo dos limites (Bounds) EPSG:4326 do tile
    n = 2.0 ** z
    lon_deg_w = x / n * 360.0 - 180.0
    lon_deg_e = (x+1) / n * 360.0 - 180.0
    lat_rad_n = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg_n = math.degrees(lat_rad_n)
    lat_rad_s = math.atan(math.sinh(math.pi * (1 - 2 * (y+1) / n)))
    lat_deg_s = math.degrees(lat_rad_s)
    
    # 1. Acha se algum TIF intersecta esse tile
    lat_deg = (lat_deg_n + lat_deg_s) / 2
    lon_deg = (lon_deg_w + lon_deg_e) / 2
    
    tif_paths = []
    for item in dem_index_cache:
        if not (item["left"] >= lon_deg_e or item["right"] <= lon_deg_w or item["bottom"] >= lat_deg_n or item["top"] <= lat_deg_s):
            tif_path = os.path.join(DATA_DIR, "topodata_mde_raw", item["file"])
            if not os.path.exists(tif_path):
                tif_path = os.path.join(DATA_DIR, "topodata_mde_raw", "extracted", item["file"])
            if os.path.exists(tif_path):
                tif_paths.append(tif_path)
            
    if not tif_paths:
        # Sem dados de relevo = nivel do mar (0m)
        from PIL import Image
        import io
        img = Image.new('RGB', (256, 256), color=(1, 134, 160))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        with open(cache_path, "wb") as f:
            f.write(buf.getvalue())
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)

    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import Resampling
        from rasterio.merge import merge
        import numpy as np
        from PIL import Image
        import io

        datasets = [rasterio.open(p) for p in tif_paths]
        res_x = (lon_deg_e - lon_deg_w) / 256.0
        res_y = (lat_deg_n - lat_deg_s) / 256.0
        bounds = (lon_deg_w, lat_deg_s, lon_deg_e, lat_deg_n)
        
        merged_data, _ = merge(datasets, bounds=bounds, res=(res_x, res_y), resampling=Resampling.bilinear, nodata=0)
        for ds in datasets:
            ds.close()
            
        elevation = merged_data[0]
        # Guarantee 256x256
        if elevation.shape != (256, 256):
            import cv2
            elevation = cv2.resize(elevation, (256, 256), interpolation=cv2.INTER_LINEAR)
            
        # Mapbox Terrain-RGB encoding
        base = np.clip((elevation + 10000) * 10, 0, 16777215).astype(np.int32)
        
        r = (base >> 16) & 255
        g = (base >> 8) & 255
        b = base & 255
        
        rgb = np.dstack((r, g, b)).astype(np.uint8)
        img = Image.fromarray(rgb)
        
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        with open(cache_path, "wb") as f:
            f.write(buf.getvalue())
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)
    except Exception as e:
        logging.error(f"Erro no Terrain-RGB: {e}")
        from PIL import Image
        import io
        img = Image.new('RGB', (256, 256), color=(1, 134, 160))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)

@app.get("/api/thermal/{z}/{x}/{y}.png")
async def get_thermal_tile(z: int, x: int, y: int, response: Response):
    print(f"\\n[MAPA] => Solicitando THERMAL Topodata: Z:{z} X:{x} Y:{y}")
    
    headers = {
        "Cache-Control": "public, max-age=86400, immutable"
    }
    

    cache_key = f"thermal_{z}_{x}_{y}"
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.png")

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return Response(content=f.read(), media_type="image/png", headers=headers)

    global dem_index_cache
    if not dem_index_cache:
        index_path = os.path.join(DATA_DIR, "topodata_mde_raw", "dem_index.json")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                dem_index_cache = json.load(f)
    
    n = 2.0 ** z
    lon_deg_w = x / n * 360.0 - 180.0
    lon_deg_e = (x+1) / n * 360.0 - 180.0
    lat_rad_n = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg_n = math.degrees(lat_rad_n)
    lat_rad_s = math.atan(math.sinh(math.pi * (1 - 2 * (y+1) / n)))
    lat_deg_s = math.degrees(lat_rad_s)
    
    lat_deg = (lat_deg_n + lat_deg_s) / 2
    lon_deg = (lon_deg_w + lon_deg_e) / 2
    
    tif_paths = []
    for item in dem_index_cache:
        if not (item["left"] >= lon_deg_e or item["right"] <= lon_deg_w or item["bottom"] >= lat_deg_n or item["top"] <= lat_deg_s):
            tif_path = os.path.join(DATA_DIR, "topodata_mde_raw", item["file"])
            if not os.path.exists(tif_path):
                tif_path = os.path.join(DATA_DIR, "topodata_mde_raw", "extracted", item["file"])
            if os.path.exists(tif_path):
                tif_paths.append(tif_path)
            
    if not tif_paths:
        from PIL import Image
        import io
        img = Image.new('RGBA', (256, 256), color=(0, 0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        
        with open(cache_path, "wb") as f:
            f.write(buf.getvalue())
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)

    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.warp import Resampling
        from rasterio.merge import merge
        from rasterio.env import Env
        import numpy as np
        import matplotlib.cm as cm
        from PIL import Image
        import io
        
        with Env(CPL_DEBUG=False, NUM_THREADS='ALL_CPUS', CURL_CA_BUNDLE=None):
            datasets = [rasterio.open(p) for p in tif_paths]
        res_x = (lon_deg_e - lon_deg_w) / 256.0
        res_y = (lat_deg_n - lat_deg_s) / 256.0
        bounds = (lon_deg_w, lat_deg_s, lon_deg_e, lat_deg_n)
        
        merged_data, _ = merge(datasets, bounds=bounds, res=(res_x, res_y), resampling=Resampling.bilinear, nodata=0)
        for ds in datasets:
            ds.close()
            
        elevation = merged_data[0]
        if elevation.shape != (256, 256):
            import cv2
            elevation = cv2.resize(elevation, (256, 256), interpolation=cv2.INTER_LINEAR)
            
        norm_elev = np.clip(elevation / 1200.0, 0, 1)
        colored = cm.turbo(norm_elev)
        rgba = (colored * 255).astype(np.uint8)
        rgba[..., 3] = np.where(elevation <= 1, 0, int(0.6 * 255))
        
        img = Image.fromarray(rgba, 'RGBA')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        
        with open(cache_path, "wb") as f:
            f.write(buf.getvalue())
            
        return Response(content=buf.getvalue(), media_type="image/png", headers=headers)
    except Exception as e:
        logging.error(f"Thermal Tile Error: {e}")
        return Response(status_code=500)

@app.post("/api/coverage")
async def calculate_coverage(req: CoverageRequest):
    bbox_str = str(req.bbox) if not req.geojson else ""
    cache_key = f"{req.locationId}_{req.operadora}_{req.frequencia}_{req.viewMode}_{req.mostrarPopulacao}_{req.mostrarVegetacao}_{bbox_str}"
    if cache_key in coverage_cache:
        return coverage_cache[cache_key]

    if not req.locationId:
        return {"error": "locationId é obrigatório"}
    
    try:
        import rf_models
        raio_urbano, raio_rural = rf_models.obter_raios_frequencia(req.frequencia)
    except Exception:
        raio_urbano = 1200.0
        raio_rural = 1200.0
    
    r_deg = 0.5
    if req.viewMode == 'estados': r_deg = 3.0
    if req.viewMode == 'regioes': r_deg = 8.0
    
    query_erbs = """
        SELECT id, ST_Y(geometry) as lat, ST_X(geometry) as lng, operadora, frequencia
        FROM erbs_ativas
        WHERE ($1 = 'all' OR operadora = $1) 
          AND ($2 = 'all' OR frequencia = $2)
          AND (
              ($6::text IS NOT NULL AND ST_Intersects(geometry, ST_SetSRID(ST_GeomFromGeoJSON($6), 4326)))
            OR ($6::text IS NULL AND $7::float IS NOT NULL AND ST_Intersects(geometry, ST_MakeEnvelope($8::float, $7::float, $10::float, $9::float, 4326)))
            OR ($6::text IS NULL AND $7::float IS NULL AND $3::float IS NOT NULL AND ST_DWithin(geometry, ST_SetSRID(ST_MakePoint($4, $3), 4326), $5))
          )
    """
    
    query_stats = """
        WITH bounding_box AS (
            SELECT 
                CASE 
                    WHEN $11::text IS NOT NULL THEN ST_SetSRID(ST_GeomFromGeoJSON($11), 4326)
                    WHEN $7::float IS NOT NULL THEN ST_MakeEnvelope($8::float, $7::float, $10::float, $9::float, 4326)
                    ELSE ST_MakeEnvelope($4::float - $5::float, $3::float - $5::float, $4::float + $5::float, $3::float + $5::float, 4326)
                END AS bbox
        ),
        grid_filtrado AS (
            SELECT populacao_estimada, geom, ST_Area(geom::geography) as area_geog
            FROM h3_grid_precalc
            WHERE ($3::float IS NULL AND $7::float IS NULL AND $11::text IS NULL) 
               OR (geom && (SELECT bbox FROM bounding_box) AND ST_Intersects(geom, (SELECT bbox FROM bounding_box)))
        ),
        erbs_cobertura AS (
            SELECT ST_Union(ST_Buffer(geometry::geography, CASE WHEN COALESCE(is_urbano, false) THEN $1::float ELSE $13::float END)::geometry) as geom_coberta
            FROM erbs_ativas
            WHERE ($2 = 'all' OR operadora = $2) 
              AND ($6 = 'all' OR frequencia = $6)
              AND geometry && (SELECT bbox FROM bounding_box)
        ),
        sombra_agregada AS (
            SELECT ST_Difference(
                (SELECT bbox FROM bounding_box), 
                COALESCE((SELECT geom_coberta FROM erbs_cobertura), ST_GeomFromText('POLYGON EMPTY'))
            ) as geom
        ),
        vegetacao_sombra AS (
            SELECT COALESCE(SUM(ST_Area(ST_Intersection(s.geom, ST_Transform(v.geom, 4326))::geography)), 0) as area_veg
            FROM sombra_agregada s
            JOIN ibge_vegetacao_subdividida v 
              ON v.geom && ST_Transform((SELECT bbox FROM bounding_box), 4674)
             AND ST_Intersects(s.geom, ST_Transform(v.geom, 4326))
        )
        SELECT 
            COALESCE(SUM(populacao_estimada), 0) as pop_total,
            COALESCE(SUM(CASE 
                WHEN NOT EXISTS (
                    SELECT 1 FROM erbs_ativas e 
                    WHERE ($2 = 'all' OR e.operadora = $2) 
                      AND ($6 = 'all' OR e.frequencia = $6)
                      AND ST_DWithin(g.geom, e.geometry, $13::float / 111320.0)
                      AND ST_Distance(g.geom, e.geometry) <= (CASE WHEN COALESCE(e.is_urbano, false) THEN $1::float ELSE $12::float END) / 111320.0
                ) THEN populacao_estimada ELSE 0 END
            ), 0) as pop_sombra,
            
            COALESCE(SUM(area_geog), 0) / 1000000.0 as area_total_km2,
            COALESCE(SUM(CASE 
                WHEN NOT EXISTS (
                    SELECT 1 FROM erbs_ativas e 
                    WHERE ($2 = 'all' OR e.operadora = $2) 
                      AND ($6 = 'all' OR e.frequencia = $6)
                      AND ST_DWithin(g.geom, e.geometry, $13::float / 111320.0)
                      AND ST_Distance(g.geom, e.geometry) <= (CASE WHEN COALESCE(e.is_urbano, false) THEN $1::float ELSE $12::float END) / 111320.0
                ) THEN area_geog ELSE 0 END
            ), 0) / 1000000.0 as area_sombra_km2,
            
            COALESCE(SUM(CASE 
                WHEN populacao_estimada > 0 AND NOT EXISTS (
                    SELECT 1 FROM erbs_ativas e 
                    WHERE ($2 = 'all' OR e.operadora = $2) 
                      AND ($6 = 'all' OR e.frequencia = $6)
                      AND ST_DWithin(g.geom, e.geometry, $13::float / 111320.0)
                      AND ST_Distance(g.geom, e.geometry) <= (CASE WHEN COALESCE(e.is_urbano, false) THEN $1::float ELSE $12::float END) / 111320.0
                ) THEN area_geog ELSE 0 END
            ), 0) / 1000000.0 as area_sombra_habitada_km2,
            
            (SELECT area_veg FROM vegetacao_sombra) / 1000000.0 as area_sombra_vegetativa_km2
        FROM grid_filtrado g;
    """
    
    bbox = req.bbox
    minLat = bbox.minLat if bbox else None
    minLng = bbox.minLng if bbox else None
    maxLat = bbox.maxLat if bbox else None
    maxLng = bbox.maxLng if bbox else None
    
    geom_json = None
    if req.geojson:
        import json
        geom_dict = req.geojson
        if isinstance(geom_dict, dict) and geom_dict.get('type') == 'FeatureCollection' and geom_dict.get('features'):
            geom_dict = geom_dict['features'][0]['geometry']
        geom_json = json.dumps(geom_dict)

    async with db_pool.acquire() as conn:
        if geom_json:
            # Salvar no banco para ser usado pela query do MVT (cache da fronteira do município)
            await conn.execute("""
                INSERT INTO ibge_boundaries (id, geom) 
                VALUES ($1, ST_SetSRID(ST_GeomFromGeoJSON($2), 4326))
                ON CONFLICT (id) DO UPDATE SET geom = EXCLUDED.geom
            """, req.locationId, geom_json)
            
        erbs = await conn.fetch(query_erbs, req.operadora, req.frequencia, req.lat, req.lng, r_deg, geom_json, minLat, minLng, maxLat, maxLng)
        
        max_raio = max(raio_urbano, raio_rural)
        try:
            stats = await conn.fetchrow(query_stats, raio_urbano, req.operadora, req.lat, req.lng, r_deg, req.frequencia, minLat, minLng, maxLat, maxLng, geom_json, raio_rural, max_raio)
        except Exception as e:
            print('SQL ERROR:', e)
            raise e
        
    erbs_ativas = [{"id": r["id"], "lat": r["lat"], "lng": r["lng"], "operadora": r["operadora"], "frequencia": r["frequencia"]} for r in erbs]
    
    areaTotalKm2 = float(stats["area_total_km2"])
    areaSombraKm2 = float(stats["area_sombra_km2"])
    areaSombraPercent = (areaSombraKm2 / areaTotalKm2 * 100) if areaTotalKm2 > 0 else 0
    
    resp = {
        "poligonoSombra": None, # MVT cuidará disso
        "poligonoVegetativo": None, # MVT cuidará disso
        "popTotal": int(stats["pop_total"]),
        "popSombra": int(stats["pop_sombra"]),
        "erbsAtivas": erbs_ativas,
        "populacao_pontos": [], # MVT cuidará disso
        "areaTotalKm2": areaTotalKm2,
        "areaSombraKm2": areaSombraKm2,
        "areaSombraPercent": areaSombraPercent,
        "areaSombraHabitadaKm2": float(stats["area_sombra_habitada_km2"]),
        "areaSombraVegetativaKm2": float(stats["area_sombra_vegetativa_km2"]),
        "aviso_area_verde": None
    }
    
    coverage_cache[cache_key] = resp
    if len(coverage_cache) > 100:
        coverage_cache.clear()
        
    return resp

@app.get("/api/admin/status")
async def get_admin_status():
    try:
        # Sistema (Apenas o processo Python atual)
        process = psutil.Process(os.getpid())
        cpu_percent = process.cpu_percent(interval=0.1)
        ram_mb = process.memory_info().rss / (1024 * 1024)
        
        # Banco de Dados
        async with db_pool.acquire() as conn:
            db_conns = await conn.fetchval("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
            db_total = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
            
        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_mb": round(ram_mb, 1),
            "db_active_connections": db_conns,
            "db_total_connections": db_total
        }
    except Exception as e:
        return {"error": str(e)}

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
