import asyncio
import asyncpg
import requests

async def test():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    z, x, y = 10, 393, 584 # Just an arbitrary tile in Sao Paulo
    query = """
        WITH bounds AS (
            SELECT ST_TileEnvelope(10, 393, 584) AS geom_3857
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
        celulas_veg AS (
            SELECT ST_Transform(v.geom, 3857) AS geom_3857
            FROM ibge_vegetacao_subdividida v, tile_clip
            WHERE v.geom && ST_Transform(tile_clip.geom_4326, 4674)
        ),
        mvt_vegetacao AS (
            SELECT ST_AsMVTGeom(c.geom_3857, (SELECT geom_3857 FROM bounds)) AS geom
            FROM celulas_veg c
        ),
        celulas_pop AS (
            SELECT ST_Centroid(ST_Transform(p.geom, 4326)) AS geom_4326, p.v0001::float as pop_absoluta, p.area_km2
            FROM ibge_setores_raw p, tile_clip
            WHERE p.geom && ST_Transform(tile_clip.geom_4326, 4674)
        ),
        mvt_populacao AS (
            SELECT ST_AsMVTGeom(ST_Transform(c.geom_4326, 3857), (SELECT geom_3857 FROM bounds)) AS geom,
                   c.pop_absoluta
            FROM celulas_pop c
        )
        SELECT (
            COALESCE((SELECT ST_AsMVT(mvt_sombra, 'sombra_exata') FROM mvt_sombra), '\\x'::bytea) || 
            COALESCE((SELECT ST_AsMVT(mvt_vegetacao, 'vegetacao') FROM mvt_vegetacao), '\\x'::bytea) ||
            COALESCE((SELECT ST_AsMVT(mvt_populacao, 'populacao') FROM mvt_populacao), '\\x'::bytea)
        ) AS tile;
    """
    try:
        val = await conn.fetchval(query)
        print(f"Tile Length: {len(val) if val else 0}")
        with open('test_tile.pbf', 'wb') as f:
            f.write(val)
    except Exception as e:
        print(f"Query error: {e}")
    finally:
        await conn.close()

asyncio.run(test())
