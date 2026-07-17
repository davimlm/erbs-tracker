with open('backend/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_get_mvt_tile = """@app.get("/api/tiles/{z}/{x}/{y}.pbf")
async def get_mvt_tile(z: int, x: int, y: int, response: Response, operadora: str = 'all', frequencia: str = 'all', locationId: str = 'none', viewMode: str = 'cidades'):
    cache_key = f"{z}_{x}_{y}_{locationId}_{operadora}_{frequencia}_{viewMode}"
    if cache_key in tile_cache:
        return Response(content=tile_cache[cache_key], media_type="application/x-protobuf")

    start_time = time.time()
    raio_metros = CONFIG_PROPAGACAO.get(frequencia, 1200)
    
    # Deixamos o ST_AsMVTGeom fazer o recorte automático e seguro
    simplify_clause = "ST_SimplifyPreserveTopology(v.geom, 0.005)" if viewMode in ['estados', 'regioes'] else "v.geom"
        
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
    erbs_buffers AS (
        SELECT ST_Union(ST_Buffer(e.geometry, {raio_metros} / 111320.0, 'quad_segs=4')) as geom
        FROM erbs_ativas e, tile_clip
        WHERE ('{operadora}' = 'all' OR e.operadora = '{operadora}') 
          AND ('{frequencia}' = 'all' OR e.frequencia = '{frequencia}')
          AND ST_DWithin(e.geometry, tile_clip.geom_4326, {raio_metros} / 111320.0)
    ),
    sombra_geom AS (
        SELECT ST_CollectionExtract(
            ST_Difference(
                ST_Intersection(tile_clip.geom_4326, COALESCE((SELECT geom FROM boundary), tile_clip.geom_4326)),
                COALESCE((SELECT geom FROM erbs_buffers), ST_GeomFromText('POLYGON EMPTY', 4326))
            ), 3
        ) as geom_4326
        FROM tile_clip
    ),
    mvt_sombra AS (
        SELECT ST_AsMVTGeom(ST_Transform(s.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom
        FROM sombra_geom s
        WHERE NOT ST_IsEmpty(s.geom_4326)
    ),
    celulas_veg AS (
        SELECT ST_Transform({simplify_clause}, 3857) AS geom_3857
        FROM ibge_vegetacao_subdividida v, tile_clip
        WHERE v.geom && ST_Transform(tile_clip.geom_4326, 4674)
          AND (v.nm_uantr IS NULL OR v.nm_uantr = '') 
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
        SELECT ST_AsMVTGeom(c.geom_3857, (SELECT geom_3857 FROM bounds)) AS geom
        FROM celulas_veg c
    ),
    celulas_pop AS (
        SELECT ST_Centroid(g.geom) AS geom_4326,
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
                     AND ST_DWithin(c.geom_4326, e.geometry, {raio_metros} / 111320.0)
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
            
        if not tile:
            return Response(content=b"", media_type="application/x-protobuf", headers=response.headers)
            
        tile_cache[cache_key] = tile
        if len(tile_cache) > 2000:
            tile_cache.clear()

        return Response(content=tile, media_type="application/x-protobuf", headers=response.headers)
    except Exception as e:
        logging.error(f"Erro fatal gerando Tile z:{z} x:{x} y:{y} -> {str(e)}")
        # Retorna um arquivo em branco em vez de Crashar o MapLibre
        return Response(content=b"", media_type="application/x-protobuf", headers=response.headers)
"""

new_lines = lines[:133] + [new_get_mvt_tile + '\n'] + lines[315:]

with open('backend/main.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
