import asyncio
import asyncpg
import math

async def run():
    conn = await asyncpg.connect('postgresql://postgres:UFABC@localhost:5432/cobertura_db')
    
    query = """
    WITH erb AS (
        -- 1. DEFINIÇÃO DA ANTENA (MACRO-CÉLULA 5G)
        SELECT
            ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857) AS geom_3857,
            -- Ponto 3D da Antena (Projetado em 3857 para cálculos métricos exatos + Eixo Z de 35 metros)
            ST_MakePoint(
                ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857)),
                ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(-46.6946, -23.6068), 4326), 3857)),
                35.0
            ) AS pt_3d_3857,
            56.0 AS eirp_dbm,
            3500.0 AS freq_mhz
    ),
    hex_grid AS (
        -- 2. GERAÇÃO DA MALHA HEXAGONAL (Escalabilidade equivalente ao H3 Resolução 11/12)
        -- Lado do hexágono = 15 metros. Cobertura teórica = Raio de 1500m.
        SELECT ST_Centroid(geom) AS centroid_3857, geom AS hex_geom
        FROM ST_HexagonGrid(
            15.0, 
            (SELECT ST_Buffer(geom_3857, 1500) FROM erb)
        )
    ),
    ray_tracing AS (
        -- 3. MOTOR DE MIRA (TARGETING)
        SELECT
            g.hex_geom,
            -- Elevando o Receptor (Celular) a 1.5 metros do chão no centroide do hexágono
            ST_MakePoint(ST_X(g.centroid_3857), ST_Y(g.centroid_3857), 1.5) AS receptor_3d_3857,
            e.pt_3d_3857 AS erb_3d_3857,
            e.eirp_dbm,
            e.freq_mhz
        FROM hex_grid g
        CROSS JOIN erb e
        -- Filtro circular perfeito (corta as rebarbas do bounding box)
        WHERE ST_Distance(g.centroid_3857, e.geom_3857) <= 1500
    ),
    fisica_vacuo AS (
        -- 4. FÍSICA ELETROMAGNÉTICA: ESPAÇO LIVRE (FSPL)
        SELECT
            hex_geom,
            -- A LINHA DE VISADA 3D (Line of Sight - LoS): Da torre de 35m até o celular a 1.5m
            ST_MakeLine(erb_3d_3857, receptor_3d_3857) AS los_3d_geom,
            
            -- Distância real da Hipotenusa (Viagem 3D do sinal em metros)
            ST_3DDistance(erb_3d_3857, receptor_3d_3857) AS dist_3d_m,
            
            eirp_dbm,
            
            -- Equação FSPL ITU-R P.525: 20*log10(d_km) + 20*log10(f_MHz) + 32.44
            (20 * log((NULLIF(ST_3DDistance(erb_3d_3857, receptor_3d_3857), 0) / 1000.0)::numeric)) 
            + (20 * log(freq_mhz::numeric)) 
            + 32.44 AS fspl_db
            
        FROM ray_tracing
    )
    -- 5. ABATE DE SINAL E RETORNO DE DADOS
    SELECT
        ST_AsText(ST_Transform(hex_geom, 4326)) AS geom_wkt, -- Volta para Lat/Lon para renderização WebGL
        dist_3d_m,
        fspl_db,
        (eirp_dbm - fspl_db) AS rx_signal_dbm
    FROM fisica_vacuo;
    """
    
    rows = await conn.fetch(query)
    
    if not rows:
        print("Nenhum resultado.")
        return

    # Analyze results
    min_dist = float('inf')
    max_dist = 0
    max_sig = -float('inf')
    min_sig = float('inf')
    
    center_signal = None
    edge_signal = None
    
    for r in rows:
        d = r['dist_3d_m']
        s = r['rx_signal_dbm']
        
        if d < min_dist:
            min_dist = d
            center_signal = s
        if d > max_dist:
            max_dist = d
            edge_signal = s
            
        if s > max_sig:
            max_sig = s
        if s < min_sig:
            min_sig = s
            
    print(f"Total de hexágonos: {len(rows)}")
    print(f"Menor distância 3D (Zênite): {min_dist:.2f} m | Sinal correspondente: {center_signal:.2f} dBm")
    print(f"Maior distância 3D (Borda): {max_dist:.2f} m | Sinal correspondente: {edge_signal:.2f} dBm")
    print(f"Sinal Máximo global (Anel de fogo): {max_sig:.2f} dBm")
    print(f"Sinal Mínimo global: {min_sig:.2f} dBm")

    await conn.close()

asyncio.run(run())
