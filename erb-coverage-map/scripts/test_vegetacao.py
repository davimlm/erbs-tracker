import asyncio
import asyncpg
import time

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    print("Criando função ITU_P833_LOSS...")
    await conn.execute("""
    CREATE OR REPLACE FUNCTION ITU_P833_LOSS(
        freq_mhz NUMERIC,
        distance_m NUMERIC
    ) RETURNS NUMERIC AS $$
    DECLARE
        gamma NUMERIC := 1.5; 
    BEGIN
        RETURN round((gamma * distance_m)::numeric, 4);
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    print("Rodando Ray-Tracing 3D Volumétrico no Ibirapuera (Matemática Otimizada)...")
    
    query = """
    WITH erb AS (
        SELECT
            ST_Transform(ST_SetSRID(ST_MakePoint(-46.6576, -23.5874), 4326), 3857) AS geom_3857,
            ST_SetSRID(ST_MakePoint(
                ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6576, -23.5874), 4326), 3857)),
                ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6576, -23.5874), 4326), 3857)),
                35.0
            ), 3857) AS pt_3d_3857,
            56.0 AS eirp_dbm,
            3500.0 AS freq_mhz
    ),
    hex_grid AS (
        SELECT ST_Centroid(geom) AS centroid_3857, geom AS hex_geom
        FROM ST_HexagonGrid(15.0, (SELECT ST_Buffer(geom_3857, 1500) FROM erb))
    ),
    ray_tracing AS (
        SELECT
            g.hex_geom,
            ST_SetSRID(ST_MakePoint(ST_X(g.centroid_3857), ST_Y(g.centroid_3857), 1.5), 3857) AS receptor_3d_3857,
            e.pt_3d_3857 AS erb_3d_3857,
            e.eirp_dbm, e.freq_mhz,
            ST_SetSRID(ST_MakeLine(e.pt_3d_3857, ST_SetSRID(ST_MakePoint(ST_X(g.centroid_3857), ST_Y(g.centroid_3857), 1.5), 3857)), 3857) AS los_3d_geom
        FROM hex_grid g
        CROSS JOIN erb e
        WHERE ST_Distance(g.centroid_3857, e.geom_3857) <= 1500
    ),
    ray_fractions AS (
        SELECT 
            *,
            -- Fator de conversão 2D -> 3D
            ST_3DLength(los_3d_geom) / NULLIF(ST_Length(los_3d_geom), 0) AS slope_factor,
            -- Fração inicial do raio onde Z=15 (teto da vegetação)
            LEAST(1.0, GREATEST(0.0, (ST_Z(erb_3d_3857) - 15.0) / NULLIF(ST_Z(erb_3d_3857) - ST_Z(receptor_3d_3857), 0))) AS f_start,
            -- Fração final do raio onde Z=0 (chão da vegetação)
            LEAST(1.0, GREATEST(0.0, (ST_Z(erb_3d_3857) - 0.0) / NULLIF(ST_Z(erb_3d_3857) - ST_Z(receptor_3d_3857), 0))) AS f_end
        FROM ray_tracing
    ),
    ray_tree_zones AS (
        SELECT
            *,
            -- Substring do raio que existe APENAS dentro da altitude da vegetação (Z entre 0 e 15)
            CASE 
                WHEN f_start >= f_end THEN NULL 
                ELSE ST_LineSubstring(los_3d_geom, f_start, f_end) 
            END AS ray_in_tree_zone
        FROM ray_fractions
    ),
    colisoes_vegetacao AS (
        SELECT 
            r.hex_geom,
            r.erb_3d_3857,
            r.receptor_3d_3857,
            r.eirp_dbm,
            r.freq_mhz,
            -- Multiplica o comprimento 2D da intersecção pelo fator de inclinação para ter o comprimento 3D exato
            COALESCE(
                SUM(
                    ST_Length(ST_Intersection(r.ray_in_tree_zone, ST_Transform(v.geom, 3857))) * r.slope_factor
                ), 0
            ) AS dist_total_folhagem_m
        FROM ray_tree_zones r
        LEFT JOIN ibge_vegetacao_subdividida v
            ON r.ray_in_tree_zone IS NOT NULL 
            AND ST_Transform(r.ray_in_tree_zone, 4674) && v.geom 
            AND ST_Intersects(r.ray_in_tree_zone, ST_Transform(v.geom, 3857))
        GROUP BY r.hex_geom, r.erb_3d_3857, r.receptor_3d_3857, r.eirp_dbm, r.freq_mhz
    )
    SELECT
        ST_AsText(ST_Transform(hex_geom, 4326)) AS geom,
        ST_3DDistance(erb_3d_3857, receptor_3d_3857) AS dist_3d_m,
        dist_total_folhagem_m,
        
        ITU_P833_LOSS(freq_mhz, dist_total_folhagem_m::numeric) AS loss_veg_db,
        
        ((20 * log((NULLIF(ST_3DDistance(erb_3d_3857, receptor_3d_3857), 0) / 1000.0)::numeric)) + (20 * log(freq_mhz::numeric)) + 32.44) AS fspl_db,
        
        (eirp_dbm 
         - ((20 * log((NULLIF(ST_3DDistance(erb_3d_3857, receptor_3d_3857), 0) / 1000.0)::numeric)) + (20 * log(freq_mhz::numeric)) + 32.44) 
         - ITU_P833_LOSS(freq_mhz, dist_total_folhagem_m::numeric)
        ) AS rx_signal_dbm
    
    FROM colisoes_vegetacao;
    """
    
    start = time.time()
    rows = await conn.fetch(query)
    elapsed = time.time() - start
    
    print(f"Consulta finalizada em {elapsed:.2f} segundos. Processando dados...")
    
    total = len(rows)
    los_hex = 0
    nlos_hex = 0
    
    max_veg_dist = 0
    max_veg_loss = 0
    max_veg_signal = 0
    
    worst_signal = float('inf')
    
    for r in rows:
        dist_veg = float(r['dist_total_folhagem_m'])
        loss_veg = float(r['loss_veg_db'])
        sig = float(r['rx_signal_dbm'])
        
        if dist_veg == 0:
            los_hex += 1
        else:
            nlos_hex += 1
            
        if dist_veg > max_veg_dist:
            max_veg_dist = dist_veg
            max_veg_loss = loss_veg
            max_veg_signal = sig
            
        if sig < worst_signal:
            worst_signal = sig

    print(f"Hexágonos Fora da Folhagem (Limpos): {los_hex}")
    print(f"Hexágonos Atenuados por Vegetação: {nlos_hex}")
    print(f"Pior sinal registrado global: {worst_signal:.2f} dBm")
    if max_veg_dist > 0:
        print(f"O raio que viajou MAIS dentro de árvores percorreu {max_veg_dist:.2f}m de clorofila, resultando numa perda verde de {max_veg_loss:.2f} dB.")
        print(f"Sinal resultante neste caso de selva profunda: {max_veg_signal:.2f} dBm.")
    
    await conn.close()

asyncio.run(run())
