import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost/cobertura_db')
    val = await conn.fetchrow("SELECT ST_XMin(geom), ST_YMin(geom), ST_XMax(geom), ST_YMax(geom) FROM ibge_boundaries WHERE id = 'sao_paulo_sp'")
    print(val)
    await conn.close()
asyncio.run(main())
