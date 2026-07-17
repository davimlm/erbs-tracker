import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    query = """
    WITH 
    um_setor AS (
        SELECT 
            cd_setor AS id_setor,
            COALESCE(v0001, 0) AS populacao,
            ST_Transform(geom, 4326) AS geom_4326,
            ST_Area(ST_Transform(geom, 4326)::geography) AS area_total_setor
        FROM ibge_setores_raw
        WHERE geom IS NOT NULL AND v0001 > 0
        LIMIT 1
    ),
    h3_setores AS (
        SELECT 
            id_setor,
            populacao,
            area_total_setor,
            h3_polygon_to_cells(geom_4326, 9) AS h3_index,
            geom_4326 AS geom_setor
        FROM um_setor
    ),
    h3_populacao_fracionada AS (
        SELECT 
            h3_index,
            h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326) AS geom_hex,
            SUM(
                populacao * (
                    ST_Area(ST_Intersection(geom_setor, h3_cell_to_boundary(h3_index)::geometry(Polygon, 4326))::geography) 
                    / NULLIF(area_total_setor, 0)
                )
            ) AS pop_no_hexagono
        FROM h3_setores
        GROUP BY h3_index
    ),
    h3_com_vegetacao AS (
        SELECT 
            p.h3_index,
            p.pop_no_hexagono,
            (
                SELECT v.legenda
                FROM ibge_vegetacao_raw v
                WHERE ST_Intersects(p.geom_hex, ST_Transform(v.geom, 4326))
                ORDER BY ST_Area(ST_Intersection(p.geom_hex, ST_Transform(v.geom, 4326))::geography) DESC
                LIMIT 1
            ) as tipo_veg
        FROM h3_populacao_fracionada p
    )
    SELECT
        h3_index,
        pop_no_hexagono as populacao_estimada,
        tipo_veg as tipo_vegetacao_predominante,
        CASE 
            WHEN tipo_veg ILIKE '%Floresta Ombrófila%' 
              OR tipo_veg ILIKE '%Floresta Estacional%'
              OR tipo_veg ILIKE '%Reflorestamento com%' THEN 0.35
            WHEN tipo_veg ILIKE '%Savana%' 
              OR tipo_veg ILIKE '%Cerrado%'
              OR tipo_veg ILIKE '%Secundária%' 
              OR tipo_veg ILIKE '%Caatinga%' THEN 0.20
            WHEN tipo_veg ILIKE '%Pastagem%' 
              OR tipo_veg ILIKE '%Agricultura%' 
              OR tipo_veg ILIKE '%Agropecuária%' THEN 0.00
            ELSE 0.00
        END AS fator_atenuacao_veg
    FROM h3_com_vegetacao
    LIMIT 5;
    """
    
    print("--- SIMULAÇÃO DE COMO FICARÃO OS DADOS DA TABELA ---")
    print("Calculando um exemplo na hora para mostrar...")
    
    rows = await conn.fetch(query)
    
    if rows:
        for r in rows:
            print(f"H3 Index (Hexágono): {r['h3_index']}")
            print(f"  População Estimada.: {r['populacao_estimada']:.2f} hab.")
            print(f"  Vegetação..........: {r['tipo_vegetacao_predominante'] or 'Área Urbana / Sem Veg.'}")
            print(f"  Atenuação Gravada..: {r['fator_atenuacao_veg']} (Tira {r['fator_atenuacao_veg']*100}% da onda)")
            print("-" * 50)
            
    await conn.close()

asyncio.run(run())
