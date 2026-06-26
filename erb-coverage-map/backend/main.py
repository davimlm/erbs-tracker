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

class CoverageRequest(BaseModel):
    locationId: str
    viewMode: str
    operadora: str
    frequencia: str
    mostrarPopulacao: bool
    mostrarVegetacao: bool = False
    lat: Optional[float] = None
    lng: Optional[float] = None

@app.get("/api/tiles/{z}/{x}/{y}.pbf")
async def get_mvt_tile(z: int, x: int, y: int, operadora: str = 'all', frequencia: str = 'all'):
    raio_metros = CONFIG_PROPAGACAO.get(frequencia, 1200)
    
    # Query otimizada para Vector Tiles via PostGIS usando EXISTS
    query = """
    WITH 
    bounds AS (
        SELECT ST_Transform(ST_TileEnvelope($1, $2, $3), 4326) AS geom,
               ST_TileEnvelope($1, $2, $3) AS geom_3857
    ),
    celulas_sombra AS (
        SELECT h.h3_index, h.populacao_estimada, h.percent_vegetacao, h.geometry AS geom_4326
        FROM h3_grid_precalc h, bounds
        WHERE ST_Intersects(h.geometry, bounds.geom)
    ),
    celulas_classificadas AS (
        SELECT 
            c.h3_index,
            c.populacao_estimada,
            c.percent_vegetacao,
            c.geom_4326,
            NOT EXISTS (
                SELECT 1 FROM erbs_ativas e
                WHERE ($5 = 'all' OR e.operadora = $5) 
                  AND ($6 = 'all' OR e.frequencia = $6)
                  AND ST_DWithin(c.geom_4326, e.geometry, $4 / 111320.0)
            ) as na_sombra
        FROM celulas_sombra c
    ),
    mvtgeom AS (
        SELECT 
            ST_AsMVTGeom(ST_Transform(c.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
            c.populacao_estimada,
            c.percent_vegetacao,
            c.na_sombra
        FROM celulas_classificadas c
    )
    SELECT ST_AsMVT(mvtgeom, 'cobertura') FROM mvtgeom;
    """
    
    async with db_pool.acquire() as conn:
        tile = await conn.fetchval(query, z, x, y, raio_metros, operadora, frequencia)
        
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
          AND ($3::float IS NULL OR ST_DWithin(geometry, ST_SetSRID(ST_MakePoint($4, $3), 4326), $5))
    """
    
    query_stats = """
        WITH bounding_box AS (
            SELECT ST_MakeEnvelope($4::float - $5::float, $3::float - $5::float, $4::float + $5::float, $3::float + $5::float, 4326) AS bbox
        ),
        grid_filtrado AS (
            SELECT populacao_estimada, geometry as geom, ST_Area(geometry::geography) as area_geog
            FROM h3_grid_precalc
            WHERE ($3::float IS NULL OR ST_Intersects(geometry, (SELECT bbox FROM bounding_box)))
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
    
    async with db_pool.acquire() as conn:
        erbs_records = await conn.fetch(query_erbs, req.operadora, req.frequencia, req.lat, req.lng, r_deg)
        stats = await conn.fetchrow(query_stats, raio_metros, req.operadora, req.lat, req.lng, r_deg, req.frequencia)
        
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
