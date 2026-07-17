import asyncio
import asyncpg
import time

async def test_query():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
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
    
    # Z:17 X:48544 Y:74385
    start = time.time()
    res = await conn.fetchval(query, 17, 48544, 74385)
    print(f"Time taken: {time.time() - start:.3f} seconds")
    if res:
        print(f"Tile size: {len(res)} bytes")
    else:
        print("Tile is empty")
        
    await conn.close()

asyncio.run(test_query())
