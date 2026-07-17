// Configurações de propagação teórica por frequência (ambiente urbano denso)
const CONFIG_PROPAGACAO = {
    'all': { raioMetros: 1200, corCobertura: '#8e8e93' },  
    '700': { raioMetros: 1200, corCobertura: '#30d158' },  
    '2600': { raioMetros: 600, corCobertura: '#0a84ff' },  
    '3500': { raioMetros: 300, corCobertura: '#bf5af2' }   
};

// Inicialização do Estado da Aplicação
let mapa;
let viewMode = 'cidades';
let currentLocationId = 'all';
let mvtCacheVersion = 3; 

// Sem mensagens aleatórias, focando no carregamento real dos blocos MVT

let apiCallCounter = 0; // DEBUG: Contador de requisições /api/coverage
let isMapLoaded = false;
let tilesRequested = 0;
let tilesLoaded = 0;
let isFetching = false;

document.addEventListener('DOMContentLoaded', async () => {
    try {
        inicializarMapa();
        configurarAbasModoVisualizacao();
        await popularDropdownLocation(); 
        configurarEventosUI();
        
        
        // Loop de status do banco
        setInterval(async () => {
            try {
                const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
                const res = await fetch(`${baseUrl}/api/status?location_id=${currentLocationId}`);
                if (res.ok) {
                    const data = await res.json();
                    let cacheInfo = `<span style='color:${data.location_cached ? '#00ff00' : '#ff9d00'}'>Disco: ${data.cache_size_mb !== undefined ? data.cache_size_mb : 0} MB<br>Situação: ${data.location_cached ? 'HIT' : 'MISS'}</span>`;

                    const cachePanel = document.getElementById('hud-cache-dados');
                    if(cachePanel) {
                        cachePanel.innerHTML = cacheInfo;
                    }

                    const btnClearCache = document.getElementById('btn-clear-cache');
                    if (btnClearCache) {
                        const cacheSizeMb = data.cache_size_mb || 0;
                        let cacheLabel = '';
                        if (cacheSizeMb < 1024) {
                            cacheLabel = `${cacheSizeMb.toFixed(2)} MB`;
                        } else {
                            cacheLabel = `${(cacheSizeMb / 1024).toFixed(2)} GB`;
                        }
                        btnClearCache.innerText = `[!] LIMPAR CACHE LOCAL (${cacheLabel})`;
                    }
                }
            } catch(e) {}
        }, 3000);

    } catch (err) {
        document.body.innerHTML += `<div style="position:fixed; top:0; left:0; width:100%; background:red; color:white; z-index:9999; padding:20px; font-size:20px;">CRITICAL JS ERROR: ${err.message}<br>${err.stack}</div>`;
        console.error(err);
    }
});

function atualizarPainelDebug() {}

function configurarAbasModoVisualizacao() {
    const botoes = document.querySelectorAll('.segment-btn');
    botoes.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            botoes.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            viewMode = e.target.getAttribute('data-mode');
            await popularDropdownLocation();
        });
    });
}

async function popularDropdownLocation() {
    const cityDatalist = document.getElementById('city-datalist');
    const searchInput = document.getElementById('search-input');
    cityDatalist.innerHTML = ''; 
    
    let configData;
    if (viewMode === 'cidades') { configData = CONFIG_CIDADES_GERADO; searchInput.placeholder = 'Digite para pesquisar...'; searchInput.disabled = false; }
    else if (viewMode === 'estados') { configData = CONFIG_ESTADOS_GERADO; searchInput.placeholder = 'Digite para pesquisar...'; searchInput.disabled = false; }
    else if (viewMode === 'regioes') { configData = CONFIG_REGIOES_GERADO; searchInput.placeholder = 'Digite para pesquisar...'; searchInput.disabled = false; }
    else if (viewMode === 'drivetest') {
        searchInput.placeholder = 'Digite um endereço para simular...';
        searchInput.value = '';
        searchInput.disabled = false;
        return; // Don't populate datalist
    }
    
    if (!configData) return;
    
    const locations = Object.entries(configData);
    if (locations.length === 0) return;
    
    locations.forEach(([id, data]) => {
        const option = document.createElement('option');
        option.value = data.nome;
        option.dataset.id = id;
        cityDatalist.appendChild(option);
    });
    
    let defaultId = locations[0][0];
    if (viewMode === 'cidades' && configData['sao_paulo_sp']) {
        defaultId = 'sao_paulo_sp';
    }
    
    searchInput.value = configData[defaultId].nome;
    searchInput.dataset.currentId = defaultId;
    if (isMapLoaded) {
        await mudarCidade(defaultId);
    } else {
        mapa.once('load', () => mudarCidade(defaultId));
    }
}

function inicializarMapa() {
    maplibregl.addProtocol('cobertura', (params, abortController) => {
        return new Promise((resolve, reject) => {
            tilesRequested++;
            updateRealLoadingPercent();
            
            const urlObj = new URL(params.url);
            const decodedHost = decodeURIComponent(urlObj.host);
            const realUrl = decodedHost + urlObj.pathname + urlObj.search;
            
            fetch(realUrl, { signal: abortController.signal })
                .then(response => {
                    if (!response.ok) throw new Error(response.statusText);
                    return response.arrayBuffer();
                })
                .then(data => {
                    tilesLoaded++;
                    updateRealLoadingPercent();
                    resolve({ data: data });
                })
                .catch(err => {
                    if (err.name !== 'AbortError') {
                        tilesLoaded++;
                        updateRealLoadingPercent();
                        reject(err);
                    }
                });
        });
    });


    mapa = new maplibregl.Map({
        container: 'map',
        style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        center: [-47.9292, -15.7801], // [lng, lat]
        zoom: 13,
        pitch: 60, // Pitch de 60 graus para visualização 3D dos prédios
        bearing: -15, // Leve angulação para melhor perspectiva
        antialias: true
    });
    
    mapa.addControl(new maplibregl.NavigationControl(), 'top-right');

    mapa.on('load', () => {
        isMapLoaded = true;
        
        // Fontes vazias para serem atualizadas
        mapa.addSource('ibge-bounds', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        mapa.addSource('erbs-buffers', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        mapa.addSource('erbs-points', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
        
        // Camada do limite do IBGE
        mapa.addLayer({
            id: 'ibge-bounds-layer',
            type: 'line',
            source: 'ibge-bounds',
            paint: { 'line-color': '#ffffff', 'line-dasharray': [5, 5], 'line-width': 2 }
        });
        
        // Camada dos Buffers ERBs
        mapa.addLayer({
            id: 'erbs-buffers-layer',
            type: 'fill',
            source: 'erbs-buffers',
            paint: {
                'fill-color': ['get', 'color'],
                'fill-opacity': 0.1
            }
        }, 'ibge-bounds-layer');
        
        // Camada dos Pontos ERBs
        mapa.addLayer({
            id: 'erbs-points-layer',
            type: 'circle',
            source: 'erbs-points',
            paint: {
                'circle-radius': 3,
                'circle-color': '#ffffff',
                'circle-stroke-width': 1,
                'circle-stroke-color': 'rgba(255,255,255,0.1)'
            }
        }, 'ibge-bounds-layer');
        
        // O progresso real  gerenciado pelo protocolo customizado "cobertura://"
        // que intercepta os requests de fetch e atualiza a barra de progresso.

        
        mapa.on('idle', () => {
            if (!isFetching) {
                finalizarLoading();
            }
        });
        
        mapa.on('move', atualizarFisicaDados);
        mapa.on('zoom', atualizarFisicaDados);

        // Debugging Tool for GeoSampa Layer
        mapa.on('click', 'geosampa-layer', function (e) {
            const feature = e.features[0];
            console.log("🕵️ DADOS BRUTOS DO TILE CLICADO:");
            console.log("1. Tipo de Geometria:", feature.geometry.type);
            console.log("2. Propriedades:", feature.properties);
        });

        mapa.on('mouseenter', 'geosampa-layer', function () {
            mapa.getCanvas().style.cursor = 'pointer';
        });
        
        mapa.on('mouseleave', 'geosampa-layer', function () {
            mapa.getCanvas().style.cursor = '';
        });
    });
}

function atualizarFisicaDados() {
    const el = document.getElementById('hud-fisica-dados');
    if (!el || !mapa) return;
    
    const z = mapa.getZoom();
    const center = mapa.getCenter();
    const lat = center.lat;
    const lng = center.lng;
    
    const isAmazonia = (lat >= -15 && lat <= 5) && (lng >= -75 && lng <= -45);
    const mode = viewMode; // Usa a variavel global
    
    let text = `Exata (Cidades, z=${z.toFixed(1)})`;
    let color = "#00ff00";
    
    if (mode === 'estados' || mode === 'regioes') {
        if (z < 8) {
            text = `Agressiva (z=${z.toFixed(1)})`;
            color = isAmazonia ? "#ff3b30" : "#ff9d00";
            if (isAmazonia) text += " [Amazônia Detectada]";
        } else {
            text = `Moderada (z=${z.toFixed(1)})`;
            color = "#00e5ff";
            if (isAmazonia) text += " [Amazônia Detectada]";
        }
    }
    
    el.innerText = text;
    el.style.color = color;
}

let currentDisplayPercent = 0;
let targetLoadingPercent = 0;
let loadingAnimationId = null;
let fakeProgressInterval = null; // Controlador da Fase 1 (Banco)

function animateLoading() {
    const percentText = document.getElementById('loading-percent');
    if (percentText && currentDisplayPercent < targetLoadingPercent) {
        currentDisplayPercent += Math.max(1, Math.floor((targetLoadingPercent - currentDisplayPercent) / 4));
        percentText.innerText = currentDisplayPercent + "%";
    }
    if (currentDisplayPercent < 100) {
        loadingAnimationId = requestAnimationFrame(animateLoading);
    }
}

function updateRealLoadingPercent() {
    if (tilesRequested === 0) return;
    // Interrompe a progressão simulada do banco quando os tiles reais começam a chegar
    if (fakeProgressInterval) { clearInterval(fakeProgressInterval); fakeProgressInterval = null; }
    
    // Fase 2: O download dos tiles representa os 50% finais (de 50% a 99%)
    targetLoadingPercent = 50 + Math.floor((tilesLoaded / tilesRequested) * 49);
    if (targetLoadingPercent > 99) targetLoadingPercent = 99;
    
    if (!loadingAnimationId) {
        loadingAnimationId = requestAnimationFrame(animateLoading);
    }
}
function createCirclePolygon(center, radiusInMeters, points = 64) {
    const [lng, lat] = center;
    const coords = [];
    const km = radiusInMeters / 1000;
    const distanceX = km / (111.320 * Math.cos(lat * Math.PI / 180));
    const distanceY = km / 110.574;
    for (let i = 0; i < points; i++) {
        const theta = (i / points) * (2 * Math.PI);
        const x = distanceX * Math.cos(theta);
        const y = distanceY * Math.sin(theta);
        coords.push([lng + x, lat + y]);
    }
    coords.push(coords[0]); 
    return { type: 'Polygon', coordinates: [coords] };
}

function getBBox(geojson) {
    let minLat=90, maxLat=-90, minLng=180, maxLng=-180;
    const processCoord = (coord) => {
        if(coord[0] < minLng) minLng = coord[0];
        if(coord[0] > maxLng) maxLng = coord[0];
        if(coord[1] < minLat) minLat = coord[1];
        if(coord[1] > maxLat) maxLat = coord[1];
    };
    const processGeometry = (geom) => {
        if(geom.type === 'Polygon') geom.coordinates[0].forEach(processCoord);
        if(geom.type === 'MultiPolygon') geom.coordinates.forEach(poly => poly[0].forEach(processCoord));
    };
    if(geojson.type === 'FeatureCollection') geojson.features.forEach(f => processGeometry(f.geometry));
    else if(geojson.type === 'Feature') processGeometry(geojson.geometry);
    else processGeometry(geojson);
    return { minLat, minLng, maxLat, maxLng };
}

async function executarAnaliseEspacial() {
    isFetching = true;
    console.log(`[DEBUG] executarAnaliseEspacial() iniciada.`);
    apiCallCounter++;
    atualizarPainelDebug();

    const spinner = document.getElementById('loading-overlay');
    const spinnerText = spinner ? spinner.querySelector('#loading-phrase') : null;
    const percentText = spinner ? spinner.querySelector('#loading-percent') : null;
    
    if (spinner) {
        spinner.style.transition = 'none';
        spinner.style.opacity = '1';
        spinner.style.display = 'flex';
        if (spinnerText) spinnerText.innerText = "Calculando Malha no PostGIS...";
        
        tilesRequested = 0;
        tilesLoaded = 0;
        currentDisplayPercent = 0;
        targetLoadingPercent = 5;
        if (loadingAnimationId) cancelAnimationFrame(loadingAnimationId);
        
        // Fase 1: Simulação algorítmica de avanço enquanto o PostGIS processa a query
        if (fakeProgressInterval) clearInterval(fakeProgressInterval);
        fakeProgressInterval = setInterval(() => {
            if (targetLoadingPercent < 45) {
                targetLoadingPercent += Math.floor(Math.random() * 6) + 2;
                if (!loadingAnimationId) animateLoading();
            }
        }, 350);
    }
    
    const operadoraSelecionada = document.getElementById('operator-select').value;
    const frequenciaSelecionada = document.querySelector('input[name="frequency"]:checked').value;
    
    const popToggleEl = document.getElementById('pop-toggle');
    const mostrarPopulacao = popToggleEl ? popToggleEl.checked : true;
    
    const vegToggleEl = document.getElementById('veg-toggle');
    const mostrarVegetacao = vegToggleEl ? vegToggleEl.checked : true;
    
    const erbToggleEl = document.getElementById('erb-toggle');
    const mostrarErbs = erbToggleEl ? erbToggleEl.checked : true;

    const locationId = document.getElementById('search-input').dataset.currentId || 'all';
    currentLocationId = locationId;

    let configLocal;
    if (viewMode === 'cidades') configLocal = CONFIG_CIDADES_GERADO[locationId];
    else if (viewMode === 'estados') configLocal = CONFIG_ESTADOS_GERADO[locationId];
    else if (viewMode === 'regioes') configLocal = CONFIG_REGIOES_GERADO[locationId];

    let bbox = null;
    let malhaGeojson = null;
    
    if (configLocal && configLocal.ibge_code) {
        const nivel = viewMode === 'cidades' ? 'municipios' : (viewMode === 'estados' ? 'estados' : 'regioes');
        const ibgeUrl = `https://servicodados.ibge.gov.br/api/v3/malhas/${nivel}/${configLocal.ibge_code}?formato=application/vnd.geo+json`;
        try {
            const malhaResp = await fetch(ibgeUrl);
            if (malhaResp.ok) {
                malhaGeojson = await malhaResp.json();
                
                if (mapa.getSource('ibge-bounds')) {
                    mapa.getSource('ibge-bounds').setData(malhaGeojson);
                }
                
                bbox = getBBox(malhaGeojson);
                
                mapa.fitBounds([
                    [bbox.minLng, bbox.minLat],
                    [bbox.maxLng, bbox.maxLat]
                ], { padding: 50, duration: 1500 });
            }
        } catch (err) {
            console.error("Erro ao buscar malha do IBGE:", err);
        }
    }

    try {
        const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
        const response = await fetch(`${baseUrl}/api/coverage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                locationId: locationId,
                viewMode: viewMode,
                operadora: operadoraSelecionada,
                frequencia: frequenciaSelecionada,
                mostrarPopulacao: mostrarPopulacao,
                mostrarVegetacao: mostrarVegetacao,
                lat: configLocal ? configLocal.lat : null,
                lng: configLocal ? configLocal.lng : null,
                bbox: bbox,
                geojson: malhaGeojson
            })
        });

        if (!response.ok) throw new Error("Erro na API de cobertura");
        
        const data = await response.json();
        
        // Adicionar MVT Source se não existir
        const timestamp = Date.now();
        const encOp = encodeURIComponent(operadoraSelecionada);
        const encFreq = encodeURIComponent(frequenciaSelecionada);
        let encLoc = encodeURIComponent(locationId);
        if (viewMode === 'drivetest') encLoc = 'all';
        const encView = encodeURIComponent(viewMode);
        
        const tileUrl = `cobertura://${encodeURIComponent(baseUrl)}/api/tiles/{z}/{x}/{y}.pbf?operadora=${encOp}&frequencia=${encFreq}&locationId=${encLoc}&viewMode=${encView}&v=${mvtCacheVersion}`;
        
        if (mapa.getLayer('populacao-layer')) mapa.removeLayer('populacao-layer');
        if (mapa.getLayer('vegetacao-layer')) mapa.removeLayer('vegetacao-layer');
        if (mapa.getLayer('sombra-layer')) mapa.removeLayer('sombra-layer');
        
        if (mapa.getSource('cobertura_mvt')) {
            mapa.removeSource('cobertura_mvt');
        }
        
        mapa.addSource('cobertura_mvt', {
            type: 'vector',
            tiles: [tileUrl],
            minzoom: 4,
            maxzoom: 20,
            prefetchZoomDelta: 1
        });

        // Layer: Vegetação
        const vToggleEl = document.getElementById('veg-toggle');
        const showVeg = vToggleEl ? vToggleEl.checked : true;
        mapa.addLayer({
            'id': 'vegetacao-layer',
            'type': 'fill',
            'source': 'cobertura_mvt',
            'source-layer': 'vegetacao',
            'layout': { 'visibility': showVeg ? 'visible' : 'none' },
            'paint': {
                'fill-color': '#2e8b57',
                'fill-opacity': 0.4
            }
        }, 'erbs-buffers-layer');

        // Layer: Sombra Exata
        mapa.addLayer({
            'id': 'sombra-layer',
            'type': 'fill',
            'source': 'cobertura_mvt',
            'source-layer': 'sombra_exata',
            'paint': {
                'fill-color': '#ff3b30',
                'fill-opacity': 0.25
            }
        }, 'erbs-buffers-layer');

        // Layer: População H3
        const popToggleEl = document.getElementById('pop-toggle');
        const showPop = popToggleEl ? popToggleEl.checked : true;
        mapa.addLayer({
            'id': 'populacao-layer',
            'type': 'fill',
            'source': 'cobertura_mvt',
            'source-layer': 'populacao',
            'layout': { 'visibility': showPop ? 'visible' : 'none' },
            'paint': {
                'fill-color': [
                    'step',
                    ['to-number', ['coalesce', ['get', 'densidade'], 0]],
                    'rgba(144, 238, 144, 0.2)', // < 100: Verde claro
                    100, 'rgba(144, 238, 144, 0.4)',
                    500, 'rgba(173, 255, 47, 0.5)',   // ~500: Amarelo/Verde
                    1000, 'rgba(255, 165, 0, 0.6)',   // >1000: Laranja
                    2000, 'rgba(255, 69, 0, 0.7)'     // >2000: Vermelho
                ]
            }
        }, 'erbs-buffers-layer');

        // Renderizar ERBs
        const configFrequencia = CONFIG_PROPAGACAO[frequenciaSelecionada] || {raioMetros: 1200};
        const raioMetros = configFrequencia.raioMetros;
        const colorCoverage = frequenciaSelecionada === '700' ? '#0a84ff' : 
                              frequenciaSelecionada === '2600' ? '#ff9f0a' : '#bf5af2';

        if (mapa.getSource('erbs-points') && mapa.getSource('erbs-buffers')) {
            const pointsGeojson = { type: 'FeatureCollection', features: [] };
            const buffersGeojson = { type: 'FeatureCollection', features: [] };
            
            data.erbsAtivas.forEach(erb => {
                pointsGeojson.features.push({
                    type: 'Feature',
                    geometry: { type: 'Point', coordinates: [erb.lng, erb.lat] },
                    properties: { operadora: erb.operadora }
                });
                
                buffersGeojson.features.push({
                    type: 'Feature',
                    geometry: createCirclePolygon([erb.lng, erb.lat], raioMetros),
                    properties: { color: colorCoverage }
                });
            });
            
            mapa.getSource('erbs-points').setData(viewMode === 'cidades' ? pointsGeojson : {type: 'FeatureCollection', features: []});
            mapa.getSource('erbs-buffers').setData(buffersGeojson);
        } else {
            mapa.getSource('erbs-points').setData({type: 'FeatureCollection', features: []});
            mapa.getSource('erbs-buffers').setData({type: 'FeatureCollection', features: []});
        }

        // Atualizar Métricas
        const percentSombraCalculado = data.popTotal > 0 ? ((data.popSombra / data.popTotal) * 100) : 0;
        const percentualSombra = data.popTotal > 0 ? percentSombraCalculado.toFixed(1) : '0.0';

        document.getElementById('stat-erb-count').innerText = data.erbsAtivas.length.toLocaleString('pt-BR');
        document.getElementById('stat-total-pop').innerText = data.popTotal.toLocaleString('pt-BR') + ' hab.';
        document.getElementById('stat-shadow-pop').innerText = `${data.popSombra.toLocaleString('pt-BR')} hab. (${percentualSombra}%)`;
        
        if (data.areaTotalKm2 > 0) {
            document.getElementById('stat-shadow-area').innerText = `${data.areaSombraKm2.toFixed(1)} km² (${data.areaSombraPercent.toFixed(1)}%)`;
            
            if (data.areaSombraHabitadaKm2 > 0 || data.areaSombraVegetativaKm2 > 0) {
                document.getElementById('stat-shadow-area-hab').innerText = `${data.areaSombraHabitadaKm2.toFixed(1)} km²`;
                document.getElementById('stat-shadow-area-veg').innerText = `${data.areaSombraVegetativaKm2.toFixed(1)} km²`;
            } else {
                document.getElementById('stat-shadow-area-hab').innerText = `N/D`;
                document.getElementById('stat-shadow-area-veg').innerText = `N/D`;
            }
        } else {
            document.getElementById('stat-shadow-area').innerText = '--';
            document.getElementById('stat-shadow-area-hab').innerText = '--';
            document.getElementById('stat-shadow-area-veg').innerText = '--';
        }
        
        const shadowProgressEl = document.getElementById('shadow-progress');
        if (shadowProgressEl) {
            shadowProgressEl.style.width = `${percentualSombra}%`;
        }
    } catch (e) {
        console.error("Erro na chamada de API:", e);
    } finally {
        isFetching = false;
        // Dá um tempo para o MapLibre enfileirar os downloads dos tiles MVT
        // Se a fila ainda estiver vazia depois disso (cache ou erro), finalizamos.
        // Caso contrário, o evento 'idle' do mapa vai finalizar automaticamente quando os tiles chegarem.
        setTimeout(() => {
            if (!isFetching && mapa.loaded() && mapa.areTilesLoaded()) {
                finalizarLoading();
            }
        }, 800);
    }
}

function finalizarLoading() {
    if (fakeProgressInterval) { clearInterval(fakeProgressInterval); fakeProgressInterval = null; }
    targetLoadingPercent = 100;
    currentDisplayPercent = 100;
    const percentText = document.getElementById('loading-percent');
    if (percentText) percentText.innerText = "100%";
    
    const spinner = document.getElementById('loading-overlay');
    if (spinner && spinner.style.display !== 'none') {
        spinner.style.transition = 'opacity 0.5s ease';
        spinner.style.opacity = '0';
        setTimeout(() => { spinner.style.display = 'none'; }, 500);
    }
    // CORREÇÃO: Sincroniza as legendas dinâmicas em gradiente ao finalizar a carga
    sincronizarLegendasDinamicamente();
}

function iniciarCarregamento() {
    const spinner = document.getElementById('loading-overlay');
    if (spinner) {
        spinner.style.display = 'flex';
        spinner.style.opacity = '1';
    }
}

function desenharRadarDriveTest(lon, lat) {
    if (mapa.getSource('drivetest_radar')) {
        mapa.removeLayer('drivetest_radar_layer');
        mapa.removeSource('drivetest_radar');
    }
    if (mapa.getSource('drivetest_point')) {
        mapa.removeLayer('drivetest_point_layer');
        mapa.removeSource('drivetest_point');
    }

    const options = { steps: 64, units: 'meters' };
    const circle = turf.circle([lon, lat], 500, options);

    mapa.addSource('drivetest_radar', {
        type: 'geojson',
        data: circle
    });

    mapa.addLayer({
        id: 'drivetest_radar_layer',
        type: 'fill',
        source: 'drivetest_radar',
        paint: {
            'fill-color': '#0a84ff',
            'fill-opacity': 0.2,
            'fill-outline-color': '#0a84ff'
        }
    });

    mapa.addSource('drivetest_point', {
        type: 'geojson',
        data: {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [lon, lat] }
        }
    });

    mapa.addLayer({
        id: 'drivetest_point_layer',
        type: 'circle',
        source: 'drivetest_point',
        paint: {
            'circle-radius': 6,
            'circle-color': '#ffffff',
            'circle-stroke-width': 2,
            'circle-stroke-color': '#0a84ff'
        }
    });
}

function configurarEventosUI() {
    const operatorSelect = document.getElementById('operator-select');
    if (operatorSelect) {
        operatorSelect.addEventListener('change', () => {
            executarAnaliseEspacial();
        });
    }
    
    const radioButtons = document.querySelectorAll('input[name="frequency"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', executarAnaliseEspacial);
    });

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            if (viewMode !== 'drivetest') return;
            const query = e.target.value;
            if (query.length < 4) return;
            
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}, Brasil&limit=5`, {
                    headers: { 'User-Agent': 'DriveTestApp_RF/1.0' }
                })
                .then(res => res.json())
                .then(data => {
                    const datalist = document.getElementById('city-datalist');
                    datalist.innerHTML = '';
                    if (data && data.length > 0) {
                        data.forEach(item => {
                            const option = document.createElement('option');
                            option.value = item.display_name;
                            datalist.appendChild(option);
                        });
                    }
                }).catch(() => {});
            }, 1000); // 1 sec debounce to respect Nominatim limits
        });

        searchInput.addEventListener('change', (e) => {
            const normalizeText = (str) => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
            const typed = normalizeText(e.target.value);

            if (viewMode === 'drivetest') {
                if (!e.target.value.trim()) return;
                iniciarCarregamento();
                fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(e.target.value)}, Brasil`, {
                    headers: { 'User-Agent': 'DriveTestApp_RF/1.0' }
                })
                .then(res => res.json())
                .then(data => {
                    finalizarLoading();
                    if (data && data.length > 0) {
                        const lat = parseFloat(data[0].lat);
                        const lon = parseFloat(data[0].lon);
                        mapa.flyTo({ center: [lon, lat], zoom: 15, pitch: 45 });
                        desenharRadarDriveTest(lon, lat);
                        executarAnaliseEspacial();
                    } else {
                        alert('Endereço não encontrado.');
                    }
                })
                .catch(() => {
                    finalizarLoading();
                    alert('Erro ao buscar o endereço.');
                });
                return;
            }
            
            let configData;
            if (viewMode === 'cidades') configData = CONFIG_CIDADES_GERADO;
            else if (viewMode === 'estados') configData = CONFIG_ESTADOS_GERADO;
            else if (viewMode === 'regioes') configData = CONFIG_REGIOES_GERADO;
            
            const match = Object.entries(configData).find(([k, v]) => normalizeText(v.nome) === typed);
            if (match) {
                searchInput.dataset.currentId = match[0];
                searchInput.value = match[1].nome;
                mudarCidade(match[0]);
            }
        });
    }

    const popToggle = document.getElementById('pop-toggle');
    if (popToggle) popToggle.addEventListener('change', (e) => {
        sincronizarLegendasDinamicamente();
        if (mapa.getLayer('populacao-layer')) mapa.setLayoutProperty('populacao-layer', 'visibility', e.target.checked ? 'visible' : 'none');
    });
    const vegToggle = document.getElementById('veg-toggle');
    if (vegToggle) vegToggle.addEventListener('change', (e) => {
        sincronizarLegendasDinamicamente();
        if (mapa.getLayer('vegetacao-layer')) mapa.setLayoutProperty('vegetacao-layer', 'visibility', e.target.checked ? 'visible' : 'none');
    });
    const erbToggle = document.getElementById('erb-toggle');
    if (erbToggle) erbToggle.addEventListener('change', (e) => {
        sincronizarLegendasDinamicamente();
        const vis = e.target.checked ? 'visible' : 'none';
        if (mapa.getLayer('erbs-points-layer')) mapa.setLayoutProperty('erbs-points-layer', 'visibility', vis);
        if (mapa.getLayer('erbs-buffers-layer')) mapa.setLayoutProperty('erbs-buffers-layer', 'visibility', vis);
    });


    const prediosToggle = document.getElementById('predios-toggle');
    const topoToggle = document.getElementById('topo-toggle');

    const updateCamera3DState = () => {
        const is3DActive = (topoToggle && topoToggle.checked) || (prediosToggle && prediosToggle.checked);
        if (is3DActive) {
            let options = { duration: 1500 };
            if (mapa.getPitch() < 45) {
                options.pitch = 60;
            }
            if (prediosToggle && prediosToggle.checked && mapa.getZoom() < 15) {
                options.zoom = 15;
            }
            if (Object.keys(options).length > 1) {
                mapa.easeTo(options);
            }
        } else {
            mapa.easeTo({ pitch: 0, bearing: 0, duration: 1500 });
        }
    };

    if (prediosToggle) prediosToggle.addEventListener('change', (e) => {
        const showPredios = e.target.checked;
        sincronizarLegendasDinamicamente();
        updateCamera3DState();
        
        if (mapa.getLayer('predios-layer')) {
            mapa.setLayoutProperty('predios-layer', 'visibility', showPredios ? 'visible' : 'none');
        }

        if (showPredios) {
            const baseUrl = 'http://127.0.0.1:8000';
            const geosampaUrl = `${baseUrl}/api/geosampa_tiles/{z}/{x}/{y}.pbf?v=${mvtCacheVersion}`;

            if (!mapa.getSource('geosampa-mvt')) {
                mapa.addSource('geosampa-mvt', {
                    type: 'vector',
                    tiles: [geosampaUrl],
                    minzoom: 13,
                    maxzoom: 22
                });
                let beforeId = undefined;
                if (mapa.getLayer('predios-layer')) beforeId = 'predios-layer';
                
                mapa.addLayer({
                    'id': 'geosampa-layer',
                    'type': 'fill-extrusion',
                    'source': 'geosampa-mvt',
                    'source-layer': 'geosampa',
                    'minzoom': 13,
                    'paint': {
                        'fill-extrusion-height': [
                            'coalesce', 
                            ['to-number', ['get', 'height']], 
                            5.19
                        ],
                        'fill-extrusion-base': 0,
                        'fill-extrusion-opacity': 0.8,
                        'fill-extrusion-color': '#444444'
                    }
                }, beforeId);
            } else {
                // CORREÇÃO: Força o recarregamento dos blocos se a fonte já existir
                mapa.getSource('geosampa-mvt').setTiles([geosampaUrl]);
                mapa.setLayoutProperty('geosampa-layer', 'visibility', 'visible');
            }
        } else {
            if (mapa.getLayer('geosampa-layer')) {
                mapa.setLayoutProperty('geosampa-layer', 'visibility', 'none');
            }
        }
    });

    if (topoToggle) topoToggle.addEventListener('change', (e) => {
        const showTopo = e.target.checked;
        sincronizarLegendasDinamicamente();
        updateCamera3DState();
        if (showTopo) {
            if (!mapa.getSource('terrain-source')) {
                mapa.addSource('terrain-source', {
                    type: 'raster-dem',
                    url: 'https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=QG1m5y50D7uN7h4cXXnU',
                    tileSize: 256,
                    maxzoom: 14
                });
            }
            mapa.setTerrain({ source: 'terrain-source', exaggeration: 3.0 });
        } else {
            mapa.setTerrain(null);
        }
    });

    const thermalToggle = document.getElementById('thermal-toggle');
    if (thermalToggle) thermalToggle.addEventListener('change', (e) => {
        const showThermal = e.target.checked;
        const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
        sincronizarLegendasDinamicamente();

        if (showThermal) {
            if (!mapa.getSource('thermal-source')) {
                mapa.addSource('thermal-source', {
                    type: 'raster',
                    tiles: [`${baseUrl}/api/thermal/{z}/{x}/{y}.png`],
                    tileSize: 256,
                    maxzoom: 14
                });
                let beforeLayer = undefined;
                if (mapa.getLayer('geosampa-layer')) beforeLayer = 'geosampa-layer';
                else if (mapa.getLayer('predios-layer')) beforeLayer = 'predios-layer';
                else if (mapa.getLayer('populacao-layer')) beforeLayer = 'populacao-layer';
                else if (mapa.getLayer('sombra-layer')) beforeLayer = 'sombra-layer';
                else if (mapa.getLayer('vegetacao-layer')) beforeLayer = 'vegetacao-layer';
                else if (mapa.getLayer('erbs-buffers-layer')) beforeLayer = 'erbs-buffers-layer';
                
                mapa.addLayer({
                    'id': 'thermal-layer',
                    'type': 'raster',
                    'source': 'thermal-source',
                    'layout': { 'visibility': 'visible' },
                    'paint': { 'raster-opacity': 0.65 }
                }, beforeLayer);
            } else {
                mapa.setLayoutProperty('thermal-layer', 'visibility', 'visible');
            }
        } else {
            if (mapa.getLayer('thermal-layer')) {
                mapa.setLayoutProperty('thermal-layer', 'visibility', 'none');
            }
        }
    });
    const btnClearCache = document.getElementById('btn-clear-cache');
    if (btnClearCache) {
        btnClearCache.addEventListener('click', async () => {
            btnClearCache.innerText = 'LIMPANDO...';
            try {
                const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
                await fetch(`${baseUrl}/api/admin/cache`, { method: 'DELETE' });
                btnClearCache.innerText = '[!] LIMPAR CACHE FÍSICO';
                mvtCacheVersion++;
                
                // Força recarregamento instantâneo do GeoSampa se estiver ativo
                if (mapa.getSource('geosampa-mvt')) {
                    mapa.getSource('geosampa-mvt').setTiles([`${baseUrl}/api/geosampa_tiles/{z}/{x}/{y}.pbf?v=${mvtCacheVersion}`]);
                }
                
                await executarAnaliseEspacial();
                alert('Cache Físico apagado. Prédios e coberturas foram recarregados do PostGIS.');
            } catch (e) {
                btnClearCache.innerText = '[!] ERRO';
            }
        });
    }

    const modal = document.getElementById('modal-metodologia');
    const btnMetodologia = document.getElementById('btn-metodologia');
    const btnCloseModal = document.getElementById('btn-close-modal');
    if (modal) {
        if (btnMetodologia) btnMetodologia.addEventListener('click', () => { modal.classList.remove('hidden'); });
        if (btnCloseModal) btnCloseModal.addEventListener('click', () => { modal.classList.add('hidden'); });
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.add('hidden');
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !modal.classList.contains('hidden')) modal.classList.add('hidden');
        });
    }

    // BUSCA BLINDADA POR SELETOR DE ATRIBUTO OU CLASSE
    const telemetryBtn = document.getElementById('btn-admin-hud') || 
                         document.getElementById('btn-telemetry-toggle') ||
                         document.querySelector('[data-target="telemetry"]');
                         
    const hud = document.getElementById('telemetry-hud') || 
                document.getElementById('telemetry-panel') ||
                document.getElementById('telemetry-container');

    if (!telemetryBtn) {
        console.error("ERRO CRÍTICO DE UI: Botão de Telemetria não foi encontrado no index.html! Verifique o atributo ID.");
    } else {
        // Força a exibição ignorando travas de rede ou CSS anterior
        telemetryBtn.style.setProperty('display', 'block', 'important');
        telemetryBtn.style.visibility = 'visible';
        telemetryBtn.style.opacity = '1';

        if (hud) {
            telemetryBtn.addEventListener('click', () => {
                const isHidden = window.getComputedStyle(hud).display === 'none';
                hud.style.display = isHidden ? 'block' : 'none';
                telemetryBtn.classList.toggle('active');
            });
        }
    }

    const updateTelemetry = async () => {
    };
}

// Telemetria do Servidor
setInterval(async () => {
    try {
        const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
        const res = await fetch(`${baseUrl}/api/admin/telemetry`);
        if (res.ok) {
            const data = await res.json();
            
            const cpuCor = data.cpu_percent > 85 ? 'red' : (data.cpu_percent > 50 ? 'yellow' : '#00ff00');
            const ramCor = data.ram_percent > 85 ? 'red' : '#00ff00';
            
            document.getElementById('hud-cpu').innerText = `${data.cpu_percent}%`;
            document.getElementById('hud-cpu-bar').style.width = `${data.cpu_percent}%`;
            document.getElementById('hud-cpu-bar').style.background = cpuCor;
            
            document.getElementById('hud-ram').innerText = `${data.ram_used_gb} GB (${data.ram_percent}%)`;
            document.getElementById('hud-ram-bar').style.width = `${data.ram_percent}%`;
            document.getElementById('hud-ram-bar').style.background = ramCor;
            
            if (data.db_active_connections !== undefined) {
                document.getElementById('hud-db-conns').innerText = `${data.db_active_connections} / ${data.db_total_connections}`;
            }
        }
    } catch (e) {
    }
}, 2000);

async function mudarCidade(explicitLocationId = null) {
    const locationId = explicitLocationId || document.getElementById('search-input').dataset.currentId;
    await executarAnaliseEspacial();
}


function sincronizarLegendasDinamicamente() {
    const mapeamento = [
        { toggleId: 'thermal-toggle', legendId: 'leg-thermal' },
        { toggleId: 'veg-toggle',     legendId: 'leg-veg' },
        { toggleId: 'pop-toggle',     legendId: 'leg-pop' }
    ];

    mapeamento.forEach(item => {
        const toggle = document.getElementById(item.toggleId);
        const card = document.getElementById(item.legendId);
        if (toggle && card) {
            if (toggle.checked) {
                card.style.display = 'block';
                card.classList.remove('hidden');
            } else {
                card.classList.add('hidden');
                setTimeout(() => {
                    if (!toggle.checked) card.style.display = 'none';
                }, 400); // 400ms is standard css transition duration
            }
        }
    });
}
