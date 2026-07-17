import asyncio
import asyncpg
import json

async def main():
    try:
        conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    except Exception as e:
        print('DB connection failed', e)
        return

    query_stats = """
        WITH bounding_box AS (
            SELECT 
                CASE 
                    WHEN $11::text IS NOT NULL THEN ST_Simplify(ST_SetSRID(ST_GeomFromGeoJSON($11), 4326), 0.05)
                    WHEN $7::float IS NOT NULL THEN ST_MakeEnvelope($8::float, $7::float, $10::float, $9::float, 4326)
                    ELSE ST_MakeEnvelope($4::float - $5::float, $3::float - $5::float, $4::float + $5::float, $3::float + $5::float, 4326)
                END AS bbox
        ),
        grid_filtrado AS (
            SELECT populacao_estimada, geom, ST_Area(geom::geography) as area_geog, tipo_vegetacao_predominante
            FROM h3_grid_precalc
            WHERE ($3::float IS NULL AND $7::float IS NULL AND $11::text IS NULL) OR geom && (SELECT bbox FROM bounding_box)
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
    
    raio_metros = 1200
    operadora = 'all'
    lat = None
    lng = None
    r_deg = 0.5
    frequencia = 'all'
    minLat = -16.0
    minLng = -48.0
    maxLat = -15.0
    maxLng = -47.0
    geom_json = None
    
    try:
        stats = await conn.fetchrow(query_stats, raio_metros, operadora, lat, lng, r_deg, frequencia, minLat, minLng, maxLat, maxLng, geom_json)
        print('STATS:', stats)
    except Exception as e:
        print('Error:', type(e), e)
        
    await conn.close()

asyncio.run(main())
