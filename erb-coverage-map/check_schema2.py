import asyncio, asyncpg
async def main():
    conn = await asyncpg.connect('postgres://postgres:postgres@localhost/postgres')
    rows = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'geosampa_buildings_3d'")
    print(rows)
    await conn.close()
asyncio.run(main())
