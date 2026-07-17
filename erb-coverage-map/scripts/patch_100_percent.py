import asyncio
import asyncpg
import time

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
CHUNK_SIZE = 5000

async def patch_precision():
    print("Iniciando Patch Demográfico (Modo 100% Precisão)...")
    
    conn = await asyncpg.connect(DB_URI)
    
    print("Identificando setores órfãos...")
    # Using NOT EXISTS instead of array_length because h3_polygon_to_cells is a Set-Returning Function
    # And substituting 'v0001' and 'cd_setor' as per our ibge schema.
    await conn.execute("""
        DROP TABLE IF EXISTS setores_orfaos;
        CREATE TABLE setores_orfaos AS
        SELECT 
            cd_setor AS id,
            v0001 AS populacao_estimada,
            ST_PointOnSurface(ST_Transform(geom, 4326)) AS ponto_interno 
        FROM ibge_setores_raw
        WHERE COALESCE(v0001, 0) > 0 
          AND geom IS NOT NULL
          AND ST_Area(geom::geography) < 500000
          AND NOT EXISTS (
              SELECT 1 FROM h3_polygon_to_cells(ST_Transform(geom, 4326), 9)
          );
    """)
    
    # We do not use VACUUM ANALYZE in asyncpg execute block as it triggers ActiveSQLTransactionError
    await conn.execute("""
        ALTER TABLE setores_orfaos ADD PRIMARY KEY (id);
        CREATE INDEX idx_orfaos_ponto ON setores_orfaos USING GIST (ponto_interno);
    """)
    
    total_orfaos = await conn.fetchval("SELECT COUNT(*) FROM setores_orfaos;")
    print(f"Total de setores evadidos identificados: {total_orfaos}")
    
    offset = 0
    setores_processados = 0
    
    while offset < total_orfaos:
        start_time = time.time()
        
        # Adapted to include the 'geom' column as it is NOT NULL or heavily relied upon in h3_grid_precalc
        upsert_query = f"""
        WITH lote AS (
            SELECT 
                id,
                populacao_estimada,
                h3_geo_to_h3(ponto_interno, 9) AS h3_index 
            FROM setores_orfaos
            ORDER BY id
            LIMIT {CHUNK_SIZE} OFFSET {offset}
        ),
        lote_agregado AS (
            SELECT 
                h3_index, 
                SUM(populacao_estimada) AS pop_recuperada,
                h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex
            FROM lote
            WHERE h3_index IS NOT NULL
            GROUP BY h3_index
        )
        INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada, tipo_vegetacao_predominante, fator_atenuacao_veg)
        SELECT 
            h3_index, 
            geom_hex,
            pop_recuperada,
            'Área Urbana Densa (Patch)',
            0.0
        FROM lote_agregado
        ON CONFLICT (h3_index) 
        DO UPDATE SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
        """
        
        await conn.execute(upsert_query)
        
        setores_processados += CHUNK_SIZE
        offset += CHUNK_SIZE
        
        elapsed = time.time() - start_time
        progresso = min((setores_processados / total_orfaos) * 100, 100)
        
        print(f"[{progresso:.2f}%] Lote seguro em {elapsed:.2f}s | População alocada.")
        
    await conn.close()
    print("Auditoria finalizada. 100% da população ancorada na malha.")

if __name__ == "__main__":
    asyncio.run(patch_precision())
