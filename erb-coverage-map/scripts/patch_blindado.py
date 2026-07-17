import asyncio
import asyncpg
import time

DB_URI = "postgresql://postgres:UFABC@localhost:5432/cobertura_db"
CHUNK_SIZE = 5000

async def patch_blindado():
    print("Iniciando Patch Demográfico (Modo Tanque de Guerra - Zero OOM)...")
    
    conn = await asyncpg.connect(DB_URI)
    
    try:
        # Descobre o ID máximo para sabermos quando parar
        max_id = await conn.fetchval("SELECT MAX(gid) FROM ibge_setores_raw;")
        print(f"ID Máximo a processar: {max_id}")
        
        last_id = 0
        setores_processados = 0
        
        while last_id < max_id:
            start_time = time.time()
            
            # Passo A: Pega o limite de IDs deste lote exato (muito leve para o banco)
            current_max_id = await conn.fetchval(f"""
                SELECT MAX(gid) FROM (
                    SELECT gid FROM ibge_setores_raw 
                    WHERE gid > {last_id} 
                    ORDER BY gid ASC 
                    LIMIT {CHUNK_SIZE}
                ) as lote;
            """)
            
            if current_max_id is None:
                break # Acabaram os dados
                
            # Passo B: Executa o filtro pesado e a inserção APENAS nesse intervalo de IDs.
            # O array_length não funciona bem com h3_polygon_to_cells pois ela é um Set-Returning Function (SRF),
            # então usamos NOT EXISTS que é matematicamente equivalente e seguro no PostgreSQL.
            upsert_query = f"""
            WITH lote_cru AS (
                SELECT gid, COALESCE(v0001, 0) AS populacao_estimada, geom
                FROM ibge_setores_raw
                WHERE gid > {last_id} AND gid <= {current_max_id}
                  AND COALESCE(v0001, 0) > 0 
                  AND geom IS NOT NULL
            ),
            orfaos AS (
                SELECT 
                    populacao_estimada,
                    -- ST_PointOnSurface garante 100% de precisão (não cai fora da geometria)
                    h3_lat_lng_to_cell(ST_PointOnSurface(ST_Transform(geom, 4326)), 9) AS h3_index 
                FROM lote_cru
                WHERE ST_Area(geom::geography) < 500000
                  AND NOT EXISTS (
                      SELECT 1 FROM h3_polygon_to_cells(ST_Transform(geom, 4326), 9)
                  )
            ),
            agregados AS (
                SELECT 
                    h3_index, 
                    SUM(populacao_estimada) AS pop_resgatada,
                    h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex
                FROM orfaos
                WHERE h3_index IS NOT NULL
                GROUP BY h3_index
            )
            INSERT INTO h3_grid_precalc (h3_index, geom, populacao_estimada, tipo_vegetacao_predominante, fator_atenuacao_veg)
            SELECT 
                h3_index, 
                geom_hex, 
                pop_resgatada,
                'Área Urbana Densa (Patch Blindado)',
                0.0
            FROM agregados
            ON CONFLICT (h3_index) 
            DO UPDATE SET populacao_estimada = h3_grid_precalc.populacao_estimada + EXCLUDED.populacao_estimada;
            """
            
            await conn.execute(upsert_query)
            
            setores_processados += CHUNK_SIZE
            last_id = current_max_id
            
            elapsed = time.time() - start_time
            progresso = min((last_id / max_id) * 100, 100)
            
            print(f"[{progresso:.2f}%] Lote processado até ID {last_id} em {elapsed:.2f}s | RAM e Disco limpos.")
            
    except Exception as e:
        print(f"Erro Crítico Interceptado (A transação parou, mas os lotes anteriores estão salvos): {e}")
    finally:
        await conn.close()
        print("Operação finalizada. População ancorada com sucesso.")

if __name__ == "__main__":
    asyncio.run(patch_blindado())
