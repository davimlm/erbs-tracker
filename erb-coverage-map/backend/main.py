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

class CoverageRequest(BaseModel):
    locationId: str
    viewMode: str
    operadora: str
    frequencia: str
    mostrarPopulacao: bool
    mostrarVegetacao: bool = False

@app.get("/api/tiles/{z}/{x}/{y}.pbf")
async def get_mvt_tile(z: int, x: int, y: int, operadora: str = 'all', frequencia: str = 'all'):
    raio_metros = CONFIG_PROPAGACAO.get(frequencia, 1200)
    
    # Query otimizada para Vector Tiles via PostGIS
    query = """
    WITH 
    bounds AS (
        SELECT ST_Transform(ST_TileEnvelope($1, $2, $3), 4326) AS geom,
               ST_TileEnvelope($1, $2, $3) AS geom_3857
    ),
    cobertura AS (
        SELECT ST_Union(ST_Buffer(geometry::geography, $4)::geometry) AS uniao
        FROM erbs_ativas
        WHERE ($5 = 'all' OR operadora = $5) 
          AND ($6 = 'all' OR frequencia = $6)
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
            CASE 
                WHEN (SELECT uniao FROM cobertura) IS NULL THEN TRUE
                ELSE NOT ST_Intersects(c.geom_4326, (SELECT uniao FROM cobertura))
            END as na_sombra
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
    
    # Obter ERBs para retornar ao front (ainda enviaremos via JSON os pontos das antenas para desenhar os marcadores)
    query_erbs = """
        SELECT id, ST_Y(geometry) as lat, ST_X(geometry) as lng, operadora, frequencia
        FROM erbs_ativas
        WHERE ($1 = 'all' OR operadora = $1) 
          AND ($2 = 'all' OR frequencia = $2)
    """
    
    # Obter métricas globais para a UI (Soma total)
    query_stats = """
        WITH cobertura AS (
            SELECT ST_Union(ST_Buffer(geometry::geography, $1)::geometry) AS uniao
            FROM erbs_ativas
            WHERE ($2 = 'all' OR operadora = $2) 
              AND ($3 = 'all' OR frequencia = $3)
        )
        SELECT 
            COALESCE(SUM(populacao_estimada), 0) as pop_total,
            COALESCE(SUM(CASE 
                WHEN (SELECT uniao FROM cobertura) IS NULL THEN populacao_estimada 
                ELSE (CASE WHEN NOT ST_Intersects(geometry, (SELECT uniao FROM cobertura)) THEN populacao_estimada ELSE 0 END) 
            END), 0) as pop_sombra,
            
            COALESCE(SUM(ST_Area(geometry::geography)), 0) / 1000000.0 as area_total_km2,
            COALESCE(SUM(CASE 
                WHEN (SELECT uniao FROM cobertura) IS NULL THEN ST_Area(geometry::geography) 
                ELSE (CASE WHEN NOT ST_Intersects(geometry, (SELECT uniao FROM cobertura)) THEN ST_Area(geometry::geography) ELSE 0 END) 
            END), 0) / 1000000.0 as area_sombra_km2
        FROM h3_grid_precalc;
    """
    
    async with db_pool.acquire() as conn:
        erbs_records = await conn.fetch(query_erbs, req.operadora, req.frequencia)
        stats = await conn.fetchrow(query_stats, raio_metros, req.operadora, req.frequencia)
        
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
