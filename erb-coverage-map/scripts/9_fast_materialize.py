import asyncpg
import asyncio
from tqdm import tqdm

DB_URI = 'postgresql://postgres:UFABC@localhost:5432/cobertura_db'

async def main():
    conn = await asyncpg.connect(DB_URI)
    
    print('1. Tabela veg_4326 já foi subdividida com sucesso. Pulando etapa de criação...')
    
    print('2. Limpando h3_grid_precalc sem travar o banco...')
    await conn.execute('''
        DELETE FROM h3_grid_precalc;
    ''')

    print('3. Contando setores censitários...')
    total = await conn.fetchval('SELECT COUNT(*) FROM ibge_setores_raw WHERE geom IS NOT NULL;')
    
    chunk_size = 5000
    print(f'Total de setores: {total} | Chunks: {total//chunk_size + 1}')
    
    query = '''
    WITH 
    setores_chunk AS (
        SELECT cd_setor AS id_setor, COALESCE(v0001, 0) AS populacao, ST_Transform(geom, 4326) AS geom_4326,
               ST_Centroid(ST_Transform(geom, 4326)) as pt_centro
        FROM ibge_setores_raw
        WHERE geom IS NOT NULL
        ORDER BY gid
        LIMIT $1 OFFSET $2
    ),
    setores_veg AS (
        SELECT DISTINCT ON (s.id_setor)
               s.id_setor, s.populacao, s.geom_4326, v.tipo_veg
        FROM setores_chunk s
        LEFT JOIN veg_4326 v ON ST_Intersects(s.pt_centro, v.geom)
    ),
    h3_setores AS (
        SELECT id_setor, populacao, tipo_veg, h3_polygon_to_cells(geom_4326, 9) AS h3_index
        FROM setores_veg
    ),
    h3_pontos AS (
        SELECT h3_index, 
               (populacao::float / count(*) OVER (PARTITION BY id_setor)) AS pop_no_hexagono,
               tipo_veg
        FROM h3_setores
    )
    INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada, tipo_vegetacao_predominante)
    SELECT h3_index, h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326), 
           SUM(pop_no_hexagono), 
           MAX(tipo_veg)
    FROM h3_pontos
    GROUP BY h3_index
    ON CONFLICT (h3_index) DO UPDATE 
    SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
    '''
    
    for offset in tqdm(range(0, total, chunk_size)):
        await conn.execute(query, chunk_size, offset)
        
    print('Gerando índice espacial final...')
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_h3_grid_precalc_geom ON h3_grid_precalc USING GIST(geom);")
    
    await conn.close()
    print('Concluído!')

asyncio.run(main())
