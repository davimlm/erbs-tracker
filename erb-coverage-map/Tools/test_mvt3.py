import asyncio
import asyncpg

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    query = """
        WITH bounds AS (
            SELECT ST_TileEnvelope(9, 189, 292) AS geom_3857
        ),
        tile_clip AS (
            SELECT ST_Transform(geom_3857, 4326) as geom_4326 FROM bounds
        ),
        erbs_buffers AS (
            SELECT ST_Union(ST_Buffer(e.geometry, 1200 / 111320.0, 'quad_segs=4')) as geom
            FROM erbs_ativas e, tile_clip
            WHERE ST_DWithin(e.geometry, tile_clip.geom_4326, 1200 / 111320.0)
        ),
        sombra_geom AS (
            SELECT ST_Difference(tile_clip.geom_4326, COALESCE((SELECT geom FROM erbs_buffers), ST_GeomFromText('POLYGON EMPTY', 4326))) as geom_4326
            FROM tile_clip
            WHERE NOT ST_IsEmpty(tile_clip.geom_4326)
        ),
        mvt_sombra AS (
            SELECT ST_AsMVTGeom(ST_Transform(s.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom
            FROM sombra_geom s
            WHERE NOT ST_IsEmpty(s.geom_4326)
        ),
        celulas_h3 AS (
            SELECT g.populacao_estimada as pop_absoluta, g.tipo_vegetacao_predominante, 
                   ST_Centroid(g.geom) AS geom
            FROM h3_grid_precalc g, tile_clip
            WHERE g.geom && tile_clip.geom_4326
              AND g.populacao_estimada > 50
        ),
        mvt_populacao AS (
            SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
                   c.pop_absoluta,
                   c.pop_absoluta as densidade,
                   false as na_sombra
            FROM celulas_h3 c
            WHERE c.pop_absoluta > 0
        )
        SELECT (
            COALESCE((SELECT ST_AsMVT(mvt_sombra, 'sombra_exata') FROM mvt_sombra), '\\x'::bytea) || 
            COALESCE((SELECT ST_AsMVT(mvt_populacao, 'populacao') FROM mvt_populacao), '\\x'::bytea)
        ) AS tile;
    """
    try:
        val = await conn.fetchval(query)
        print(f"Tile Length: {len(val) if val else 0}")
    except Exception as e:
        print(f"Query error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
