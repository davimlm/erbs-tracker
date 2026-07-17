import psycopg2
import time

def main():
    conn = psycopg2.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    conn.autocommit = True
    cur = conn.cursor()

    print("--- INICIANDO MAPEAMENTO ITU-R P.833 NO H3 ---")

    # Contar total de registros
    cur.execute("SELECT COUNT(*) FROM h3_grid_precalc;")
    total = cur.fetchone()[0]
    print(f"Total de hexágonos para atualizar: {total}")

    # Processamento em lotes para evitar lock gigante
    batch_size = 50000
    processed = 0

    # Query mágica que atualiza baseada no JOIN LATERAL com a matriz
    # Vamos usar o ctid ou uma janela, mas como temos id na h3_grid_precalc, usaremos o id.
    # Assumindo que h3_grid_precalc tem um identificador único (se não tiver, usaremos h3_index).
    
    update_sql = """
        WITH cte AS (
            SELECT 
                h.h3_index,
                m.perda_700_dbm,
                m.perda_3500_dbm
            FROM (
                SELECT h3_index, vegetacao_legenda 
                FROM h3_grid_precalc 
                WHERE perda_700_dbm IS NULL 
                LIMIT %s
            ) h
            LEFT JOIN LATERAL (
                SELECT perda_700_dbm, perda_3500_dbm 
                FROM rf_matriz_vegetacao 
                WHERE h.vegetacao_legenda ILIKE nome_ibge_like
                ORDER BY ordem_prioridade ASC
                LIMIT 1
            ) m ON true
        )
        UPDATE h3_grid_precalc dest
        SET perda_700_dbm = COALESCE(cte.perda_700_dbm, 0.0),
            perda_3500_dbm = COALESCE(cte.perda_3500_dbm, 0.0)
        FROM cte
        WHERE dest.h3_index = cte.h3_index;
    """

    while processed < total:
        start_time = time.time()
        cur.execute(update_sql, (batch_size,))
        rows_updated = cur.rowcount
        
        if rows_updated == 0:
            break
            
        processed += rows_updated
        elapsed = time.time() - start_time
        print(f"Lote processado: {processed}/{total} ({(processed/total)*100:.1f}%) - {elapsed:.2f}s")
    
    print("Atualização concluída. As colunas de perda física foram injetadas no grid H3!")

if __name__ == "__main__":
    main()
