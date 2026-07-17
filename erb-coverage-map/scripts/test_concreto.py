import asyncio
import asyncpg

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    print("Criando função ITU_P2040_LOSS...")
    await conn.execute("""
    CREATE OR REPLACE FUNCTION ITU_P2040_LOSS(
        f_mhz NUMERIC,       -- Frequência em MHz
        thickness_m NUMERIC, -- Espessura da parede em metros
        eps_prime NUMERIC,   -- Permissividade real (Epsilon')
        sigma NUMERIC        -- Condutividade (S/m)
    ) RETURNS NUMERIC AS $$
    DECLARE
        c NUMERIC := 299792458.0; 
        f_ghz NUMERIC := f_mhz / 1000.0;
        k0 NUMERIC := (2.0 * pi() * f_mhz * 1000000.0) / c; -- Número de onda no vácuo
        eps_double_prime NUMERIC;
        eps_mag NUMERIC;
        n NUMERIC;
        k_e NUMERIC;
        alpha_np NUMERIC;
        loss_mat_db NUMERIC;
        r_mag NUMERIC;
        loss_ref_db NUMERIC;
    BEGIN
        -- Epsilon'' (Parte imaginária da permissividade via aproximação ITU-R)
        eps_double_prime := (17.98 * sigma) / f_ghz;
        
        -- Magnitude complexa |Eps|
        eps_mag := sqrt(power(eps_prime, 2) + power(eps_double_prime, 2));

        -- Índice de refração (n) e Coeficiente de extinção (k_e)
        n := sqrt((eps_mag + eps_prime) / 2.0);
        k_e := sqrt((eps_mag - eps_prime) / 2.0);

        -- 1. Perda por Absorção no Material (dB)
        alpha_np := k0 * k_e; -- Constante de atenuação em Nepers/m
        loss_mat_db := alpha_np * 8.6858896 * thickness_m; -- 1 Np = 8.686 dB

        -- 2. Perda por Reflexão nas Fronteiras (Incidência Normal Simplificada)
        -- Magnitude do Coeficiente de Reflexão ao quadrado |R|^2
        r_mag := (power(1.0 - n, 2) + power(k_e, 2)) / (power(1.0 + n, 2) + power(k_e, 2));
        
        -- Transmissão pelas 2 interfaces (Ar->Concreto e Concreto->Ar)
        loss_ref_db := -10.0 * log((power(1.0 - r_mag, 2))::numeric);

        RETURN round((loss_mat_db + loss_ref_db)::numeric, 4);
    END;
    $$ LANGUAGE plpgsql IMMUTABLE;
    """)

    print("Rodando Ray-Tracing 3D na Berrini (Isso pode demorar um pouco)...")
    
    query = """
    WITH erb AS (
        SELECT
            ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857) AS geom_3857,
            ST_SetSRID(ST_MakePoint(
                ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857)),
                ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857)),
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
    colisoes_predios AS (
        SELECT 
            r.hex_geom,
            r.erb_3d_3857,
            r.receptor_3d_3857,
            r.eirp_dbm,
            r.freq_mhz,
            COUNT(b.ed_id) AS qtd_predios_cruzados
        FROM ray_tracing r
        LEFT JOIN geosampa_buildings_3d b
            ON r.los_3d_geom && b.geometry
            AND ST_3DIntersects(r.los_3d_geom, b.geometry)
        GROUP BY r.hex_geom, r.erb_3d_3857, r.receptor_3d_3857, r.eirp_dbm, r.freq_mhz
    )
    SELECT
        ST_AsText(ST_Transform(hex_geom, 4326)) AS geom,
        ST_3DDistance(erb_3d_3857, receptor_3d_3857) AS dist_3d_m,
        qtd_predios_cruzados,
        
        (qtd_predios_cruzados * 2 * ITU_P2040_LOSS(freq_mhz, 0.20, 5.31, 0.0326)) AS loss_concreto_db,
        
        ((20 * log((NULLIF(ST_3DDistance(erb_3d_3857, receptor_3d_3857), 0) / 1000.0)::numeric)) + (20 * log(freq_mhz::numeric)) + 32.44) AS fspl_db,
        
        (eirp_dbm 
         - ((20 * log((NULLIF(ST_3DDistance(erb_3d_3857, receptor_3d_3857), 0) / 1000.0)::numeric)) + (20 * log(freq_mhz::numeric)) + 32.44) 
         - (qtd_predios_cruzados * 2 * ITU_P2040_LOSS(freq_mhz, 0.20, 5.31, 0.0326))
        ) AS rx_signal_dbm
    
    FROM colisoes_predios;
    """
    
    import time
    start = time.time()
    rows = await conn.fetch(query)
    elapsed = time.time() - start
    
    print(f"Consulta finalizada em {elapsed:.2f} segundos. Processando dados...")
    
    total = len(rows)
    los_hex = 0
    nlos_hex = 0
    
    max_buildings = 0
    max_building_dist = 0
    max_building_signal = 0
    
    worst_signal = float('inf')
    
    for r in rows:
        qtd = r['qtd_predios_cruzados']
        sig = float(r['rx_signal_dbm'])
        
        if qtd == 0:
            los_hex += 1
        else:
            nlos_hex += 1
            
        if qtd > max_buildings:
            max_buildings = qtd
            max_building_dist = r['dist_3d_m']
            max_building_signal = sig
            
        if sig < worst_signal:
            worst_signal = sig

    print(f"Hexágonos LoS (Limpos): {los_hex}")
    print(f"Hexágonos NLoS (Sombreados): {nlos_hex}")
    print(f"Pior sinal registrado (Escuridão RF): {worst_signal:.2f} dBm")
    if max_buildings > 0:
        print(f"O raio que atravessou mais prédios perfurou {max_buildings} edifícios (distância: {max_building_dist:.2f}m) resultando em {max_building_signal:.2f} dBm")
    
    await conn.close()

asyncio.run(run())
