import os
import json
import logging
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    logging.info("Conectando ao banco de dados...")
    db_pool = await asyncpg.create_pool(DB_URI, min_size=1, max_size=10)
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

@app.get("/api/tiles/{z}/{x}/{y}.pbf")
async def get_mvt_tile(z: int, x: int, y: int, operadora: str = 'all', frequencia: str = 'all', locationId: str = 'none'):
    raio_metros = CONFIG_PROPAGACAO.get(frequencia, 1200)
    
    # Se houver um locationId válido, vamos cruzar a malha H3 apenas com a fronteira desse local
    intersect_clause = "bounds.geom_4326"
    if locationId and locationId != 'none':
        intersect_clause = f"(SELECT geom FROM ibge_boundaries WHERE id = '{locationId}')"

    # Query otimizada para Vector Tiles via PostGIS gerando 2 layers
    query = f"""
    WITH 
    bounds AS (
        SELECT ST_Transform(ST_TileEnvelope({z}, {x}, {y}), 4326) AS geom_4326,
               ST_TileEnvelope({z}, {x}, {y}) AS geom_3857
    ),
    tile_clip AS (
        SELECT 
            CASE 
                WHEN '{locationId}' != 'none' THEN 
                    ST_Intersection(bounds.geom_4326, {intersect_clause})
                ELSE bounds.geom_4326
            END as geom_4326
        FROM bounds
    ),
    -- 1. Sombra Geométrica Exata (Cobre a cidade inteira, mesmo onde não tem dado H3)
    erbs_buffers AS (
        SELECT ST_Union(ST_Buffer(e.geometry, {raio_metros} / 111320.0, 'quad_segs=4')) as geom
        FROM erbs_ativas e, tile_clip
        WHERE ('{operadora}' = 'all' OR e.operadora = '{operadora}') 
          AND ('{frequencia}' = 'all' OR e.frequencia = '{frequencia}')
          AND ST_DWithin(e.geometry, tile_clip.geom_4326, {raio_metros} / 111320.0)
    ),
    sombra_geom AS (
        SELECT 
            ST_Difference(tile_clip.geom_4326, COALESCE((SELECT geom FROM erbs_buffers), ST_GeomFromText('POLYGON EMPTY', 4326))) as geom_4326
        FROM tile_clip
        WHERE NOT ST_IsEmpty(tile_clip.geom_4326)
    ),
    mvt_sombra AS (
        SELECT ST_AsMVTGeom(ST_Transform(s.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom
        FROM sombra_geom s
        WHERE NOT ST_IsEmpty(s.geom_4326)
    ),
    -- 2. H3 Cobertura (Apenas dados de população e vegetação, para onde o H3 existe)
    celulas_cobertura AS (
        SELECT h.h3_index, h.populacao_estimada, h.percent_vegetacao, h.geometry AS geom_4326
        FROM h3_grid_precalc h, tile_clip
        WHERE ST_Intersects(h.geometry, tile_clip.geom_4326)
    ),
    mvt_cobertura AS (
        SELECT 
            ST_AsMVTGeom(ST_Transform(c.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
            c.populacao_estimada,
            c.percent_vegetacao,
            NOT EXISTS (
                SELECT 1 FROM erbs_ativas e
                WHERE ('{operadora}' = 'all' OR e.operadora = '{operadora}') 
                  AND ('{frequencia}' = 'all' OR e.frequencia = '{frequencia}')
                  AND ST_DWithin(c.geom_4326, e.geometry, {raio_metros} / 111320.0)
            ) as na_sombra
        FROM celulas_cobertura c
    )
    SELECT (
        COALESCE((SELECT ST_AsMVT(mvt_sombra, 'sombra_exata') FROM mvt_sombra), '\\x'::bytea) || 
        COALESCE((SELECT ST_AsMVT(mvt_cobertura, 'cobertura') FROM mvt_cobertura), '\\x'::bytea)
    ) AS mvt;
    """
    
    async with db_pool.acquire() as conn:
        tile = await conn.fetchval(query)
        
    if not tile:
        return Response(content=b"", media_type="application/x-protobuf")
        
    return Response(content=tile, media_type="application/x-protobuf")

@app.post("/api/coverage")
async def analyze_coverage(req: CoverageRequest):
    raio_metros = CONFIG_PROPAGACAO.get(req.frequencia, 1200)
    
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
            SELECT populacao_estimada, geometry as geom, ST_Area(geometry::geography) as area_geog
            FROM h3_grid_precalc
            WHERE ($3::float IS NULL AND $7::float IS NULL AND $11::text IS NULL) OR ST_Intersects(geometry, (SELECT bbox FROM bounding_box))
        )
        SELECT 
            COALESCE(SUM(populacao_estimada), 0) as pop_total,
            COALESCE(SUM(CASE 
                WHEN NOT EXISTS (
                    SELECT 1 FROM erbs_ativas e 
                    WHERE ($2 = 'all' OR e.operadora = $2) 
                      AND ($6 = 'all' OR e.frequencia = $6)
                      AND ST_DWithin(g.geom, e.geometry, $1 / 111320.0)
                ) THEN populacao_estimada ELSE 0 END
            ), 0) as pop_sombra,
            
            COALESCE(SUM(area_geog), 0) / 1000000.0 as area_total_km2,
            COALESCE(SUM(CASE 
                WHEN NOT EXISTS (
                    SELECT 1 FROM erbs_ativas e 
                    WHERE ($2 = 'all' OR e.operadora = $2) 
                      AND ($6 = 'all' OR e.frequencia = $6)
                      AND ST_DWithin(g.geom, e.geometry, $1 / 111320.0)
                ) THEN area_geog ELSE 0 END
            ), 0) / 1000000.0 as area_sombra_km2
        FROM grid_filtrado g;
    """
    
    bbox = req.bbox
    minLat = bbox.minLat if bbox else None
    minLng = bbox.minLng if bbox else None
    maxLat = bbox.maxLat if bbox else None
    maxLng = bbox.maxLng if bbox else None
    
    geom_json = None
    if req.geojson and "features" in req.geojson and len(req.geojson["features"]) > 0:
        geom_json = json.dumps(req.geojson["features"][0]["geometry"])

    async with db_pool.acquire() as conn:
        if geom_json:
            # Salvar no banco para ser usado pela query do MVT (cache da fronteira do município)
            await conn.execute("""
                INSERT INTO ibge_boundaries (id, geom) 
                VALUES ($1, ST_SetSRID(ST_GeomFromGeoJSON($2), 4326))
                ON CONFLICT (id) DO UPDATE SET geom = EXCLUDED.geom
            """, req.locationId, geom_json)
            
        erbs_records = await conn.fetch(query_erbs, req.operadora, req.frequencia, req.lat, req.lng, r_deg, geom_json, minLat, minLng, maxLat, maxLng)
        stats = await conn.fetchrow(query_stats, raio_metros, req.operadora, req.lat, req.lng, r_deg, req.frequencia, minLat, minLng, maxLat, maxLng, geom_json)
        
    erbs_ativas = [{"id": r["id"], "lat": r["lat"], "lng": r["lng"], "operadora": r["operadora"], "frequencia": r["frequencia"]} for r in erbs_records]
    
    areaTotalKm2 = float(stats["area_total_km2"])
    areaSombraKm2 = float(stats["area_sombra_km2"])
    areaSombraPercent = (areaSombraKm2 / areaTotalKm2 * 100) if areaTotalKm2 > 0 else 0
    
    return {
        "poligonoSombra": None, # MVT cuidará disso
        "poligonoVegetativo": None, # MVT cuidará disso
        "popTotal": int(stats["pop_total"]),
        "popSombra": int(stats["pop_sombra"]),
        "erbsAtivas": erbs_ativas,
        "populacao_pontos": [], # MVT cuidará disso
        "areaTotalKm2": areaTotalKm2,
        "areaSombraKm2": areaSombraKm2,
        "areaSombraPercent": areaSombraPercent,
        "areaSombraHabitadaKm2": areaSombraKm2 * 0.8, # Aproximação para PoC, poderia ser query
        "areaSombraVegetativaKm2": areaSombraKm2 * 0.2, # Aproximação para PoC
        "aviso_area_verde": None
    }

app.mount("/", StaticFiles(directory=BASE_DIR, html=True), name="static")
