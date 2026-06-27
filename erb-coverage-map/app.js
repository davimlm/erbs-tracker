// Configurações de propagação teórica por frequência (ambiente urbano denso)
const CONFIG_PROPAGACAO = {
    'all': { raioMetros: 1200, corCobertura: '#8e8e93' },  
    '700': { raioMetros: 1200, corCobertura: '#30d158' },  
    '2600': { raioMetros: 600, corCobertura: '#0a84ff' },  
    '3500': { raioMetros: 300, corCobertura: '#bf5af2' }   
};

// Inicialização do Estado da Aplicação
let mapa;
let camadaEstudoGroup;
let camadaDadosGroup;
let camadaPopulacaoGroup; 
let viewMode = 'cidades'; 

document.addEventListener('DOMContentLoaded', async () => {
    try {
        inicializarMapa();
        configurarAbasModoVisualizacao();
        await popularDropdownLocation(); 
        configurarEventosUI();
    } catch (err) {
        document.body.innerHTML += `<div style="position:fixed; top:0; left:0; width:100%; background:red; color:white; z-index:9999; padding:20px; font-size:20px;">CRITICAL JS ERROR: ${err.message}<br>${err.stack}</div>`;
        console.error(err);
    }
});

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
    if (viewMode === 'cidades') configData = CONFIG_CIDADES_GERADO;
    else if (viewMode === 'estados') configData = CONFIG_ESTADOS_GERADO;
    else if (viewMode === 'regioes') configData = CONFIG_REGIOES_GERADO;
    
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
    await mudarCidade(defaultId);
}

function inicializarMapa() {
    mapa = L.map('map', {
        center: [-15.7801, -47.9292], 
        zoom: 14,
        zoomControl: false
    });

    L.control.zoom({ position: 'topright' }).addTo(mapa);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(mapa);

    camadaEstudoGroup = L.layerGroup().addTo(mapa);
    camadaDadosGroup = L.layerGroup().addTo(mapa);
    camadaPopulacaoGroup = L.layerGroup().addTo(mapa);
}

async function executarAnaliseEspacial() {
    const spinner = document.getElementById('loading-spinner');
    if (spinner) spinner.style.display = 'flex';
    
    camadaEstudoGroup.clearLayers();
    camadaDadosGroup.clearLayers();
    camadaPopulacaoGroup.clearLayers();

    const operadoraSelecionada = document.getElementById('operator-select').value;
    const frequenciaSelecionada = document.querySelector('input[name="frequency"]:checked').value;
    const popToggleEl = document.getElementById('pop-toggle');
    const mostrarPopulacao = popToggleEl ? popToggleEl.checked : false;
    
    const vegToggleEl = document.getElementById('veg-toggle');
    const mostrarVegetacao = vegToggleEl ? vegToggleEl.checked : false;

    const locationId = document.getElementById('search-input').dataset.currentId;

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
                const ibgeLayer = L.geoJSON(malhaGeojson, {
                    style: {
                        color: '#ffffff',
                        weight: 2,
                        dashArray: '5, 5',
                        fillOpacity: 0
                    },
                    interactive: false
                }).addTo(camadaEstudoGroup);
                
                const bounds = ibgeLayer.getBounds();
                mapa.flyToBounds(bounds, { duration: 1.5 });
                
                bbox = {
                    minLat: bounds.getSouth(),
                    minLng: bounds.getWest(),
                    maxLat: bounds.getNorth(),
                    maxLng: bounds.getEast()
                };
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
        
        // Renderizar H3 via MVT (Sombra, População e Vegetação)
        if (window.currentMvtLayer) {
            mapa.removeLayer(window.currentMvtLayer);
        }
        
        const tileUrl = `${baseUrl}/api/tiles/{z}/{x}/{y}.pbf?operadora=${operadoraSelecionada}&frequencia=${frequenciaSelecionada}&locationId=${locationId}`;
        window.currentMvtLayer = L.vectorGrid.protobuf(tileUrl, {
            vectorTileLayerStyles: {
                'cobertura': function(properties, zoom) {
                    // Lógica de prioridade de renderização H3
                    // Parsing seguro de propriedades do MVT (evita bugs de serialização)
                    const naSombra = properties.na_sombra === true || properties.na_sombra === 'true' || properties.na_sombra === 't' || properties.na_sombra === 1;
                    const popEstimada = Number(properties.populacao_estimada) || 0;
                    const percVegetacao = Number(properties.percent_vegetacao) || 0;
                    
                    if (mostrarVegetacao && percVegetacao > 0) {
                        return {
                            fillColor: '#30d158',
                            fillOpacity: Math.max(0.2, percVegetacao / 100),
                            color: '#30d158',
                            weight: 0,
                            fill: true
                        };
                    }
                    
                    if (naSombra) {
                        if (mostrarPopulacao && popEstimada > 0) {
                            return {
                                fillColor: '#ff453a',
                                fillOpacity: Math.min(1.0, popEstimada / 500),
                                color: '#ff453a',
                                weight: 0,
                                fill: true
                            };
                        } else if (!mostrarPopulacao) {
                            return {
                                fillColor: '#ff3b30',
                                fillOpacity: 0.35,
                                color: '#ff3b30',
                                weight: 0,
                                fill: true
                            };
                        }
                    } else {
                        // Área Coberta
                        if (mostrarPopulacao && popEstimada > 0) {
                            return {
                                fillColor: '#86868b',
                                fillOpacity: Math.min(0.8, popEstimada / 500),
                                color: '#86868b',
                                weight: 0,
                                fill: true
                            };
                        }
                    }
                    
                    // Hexágonos sem relevância (cobertos e sem highlight de popup/veg)
                    return { weight: 0, fillOpacity: 0, color: 'transparent' };
                }
            },
            interactive: false // Não precisa clicar nas células H3 por enquanto
        }).addTo(mapa);
        
        // O zoom agora é controlado pelo flyToBounds do polígono IBGE

        // Renderizar ERBs
        const configFrequencia = CONFIG_PROPAGACAO[frequenciaSelecionada] || {raioMetros: 1200};
        const raioMetros = configFrequencia.raioMetros;
        const colorCoverage = frequenciaSelecionada === '700' ? '#0a84ff' : 
                              frequenciaSelecionada === '2600' ? '#ff9f0a' : '#bf5af2';

        data.erbsAtivas.forEach(erb => {
            L.circle([erb.lat, erb.lng], {
                color: colorCoverage,
                fillColor: colorCoverage,
                fillOpacity: 0.1,
                radius: raioMetros,
                weight: 1
            }).addTo(camadaEstudoGroup);

            if (viewMode === 'cidades') {
                L.circleMarker([erb.lat, erb.lng], {
                    radius: 4,
                    fillColor: '#ffffff',
                    color: '#000000',
                    weight: 1,
                    fillOpacity: 1
                }).bindPopup(`<b>Operadora:</b> ${(erb.operadora || 'Desconhecida').toUpperCase()}`).addTo(camadaDadosGroup);
            }
        });

        // Atualizar Métricas
        const percentSombraCalculado = data.popTotal > 0 ? ((data.popSombra / data.popTotal) * 100) : 0;
        const percentualSombra = viewMode === 'cidades' && data.popTotal > 0 ? percentSombraCalculado.toFixed(1) : 'N/A';

        document.getElementById('stat-erb-count').innerText = data.erbsAtivas.length.toLocaleString('pt-BR');
        document.getElementById('stat-total-pop').innerText = viewMode === 'cidades' ? data.popTotal.toLocaleString('pt-BR') + ' hab.' : '--';
        document.getElementById('stat-shadow-pop').innerText = viewMode === 'cidades' ? `${data.popSombra.toLocaleString('pt-BR')} hab. (${percentualSombra}%)` : '--';
        
        if (viewMode === 'cidades' && data.areaTotalKm2 > 0) {
            document.getElementById('stat-shadow-area').innerText = `${data.areaSombraKm2.toFixed(1)} km² (${data.areaSombraPercent.toFixed(1)}%)`;
            
            if (data.areaSombraHabitadaKm2 > 0 || data.areaSombraVegetativaKm2 > 0) {
                document.getElementById('stat-shadow-area-hab').innerText = `${data.areaSombraHabitadaKm2.toFixed(1)} km²`;
                document.getElementById('stat-shadow-area-veg').innerText = `${data.areaSombraVegetativaKm2.toFixed(1)} km²`;
            } else {
                document.getElementById('stat-shadow-area-hab').innerText = `N/D`;
                document.getElementById('stat-shadow-area-veg').innerText = `N/D`;
            }
        } else if (viewMode === 'estados' || viewMode === 'regioes') {
            if (data.areaTotalKm2 > 0) {
                document.getElementById('stat-shadow-area').innerText = `${data.areaSombraKm2.toFixed(1)} km² (${data.areaSombraPercent.toFixed(1)}%)`;
            } else {
                document.getElementById('stat-shadow-area').innerText = '--';
            }
            document.getElementById('stat-shadow-area-hab').innerText = '--';
            document.getElementById('stat-shadow-area-veg').innerText = '--';
        } else {
            document.getElementById('stat-shadow-area').innerText = '--';
            document.getElementById('stat-shadow-area-hab').innerText = '--';
            document.getElementById('stat-shadow-area-veg').innerText = '--';
        }
        
        const shadowProgressEl = document.getElementById('shadow-progress');
        if (shadowProgressEl) {
            shadowProgressEl.style.width = viewMode === 'cidades' ? `${percentualSombra}%` : '0%';
        }
        
    } catch (e) {
        console.error("Erro na chamada de API:", e);
    } finally {
        if (spinner) spinner.style.display = 'none';
    }
}

function configurarEventosUI() {
    document.getElementById('operator-select').addEventListener('change', () => {
        executarAnaliseEspacial();
    });
    
    const radioButtons = document.querySelectorAll('input[name="frequency"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', executarAnaliseEspacial);
    });

    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.addEventListener('change', (e) => {
            const normalizeText = (str) => str.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
            const val = normalizeText(e.target.value).trim();
            if (!val) return; 
            
            const options = document.querySelectorAll('#city-datalist option');
            let match = null;
            
            for (const option of options) {
                if (normalizeText(option.value) === val) { match = option; break; }
            }
            if (!match) {
                for (const option of options) {
                    if (normalizeText(option.value).includes(val)) { match = option; break; }
                }
            }
            
            if (match) {
                searchInput.value = match.value;
                if (searchInput.dataset.currentId !== match.dataset.id) {
                    searchInput.dataset.currentId = match.dataset.id;
                    mudarCidade(match.dataset.id);
                }
            } else {
                let configLocal;
                const cid = searchInput.dataset.currentId;
                if (viewMode === 'cidades') configLocal = CONFIG_CIDADES_GERADO[cid];
                else if (viewMode === 'estados') configLocal = CONFIG_ESTADOS_GERADO[cid];
                else if (viewMode === 'regioes') configLocal = CONFIG_REGIOES_GERADO[cid];
                if (configLocal) searchInput.value = configLocal.nome;
            }
        });
        
        searchInput.addEventListener('focus', (e) => { e.target.value = ''; });
        searchInput.addEventListener('blur', (e) => {
            if (e.target.value.trim() === '') {
                const cid = searchInput.dataset.currentId;
                let configLocal;
                if (viewMode === 'cidades') configLocal = CONFIG_CIDADES_GERADO[cid];
                else if (viewMode === 'estados') configLocal = CONFIG_ESTADOS_GERADO[cid];
                else if (viewMode === 'regioes') configLocal = CONFIG_REGIOES_GERADO[cid];
                if (configLocal) searchInput.value = configLocal.nome;
            }
        });
    }

    const popToggleEl = document.getElementById('pop-toggle');
    if (popToggleEl) {
        popToggleEl.addEventListener('change', executarAnaliseEspacial);
    }
    
    const vegToggleEl = document.getElementById('veg-toggle');
    if (vegToggleEl) {
        vegToggleEl.addEventListener('change', executarAnaliseEspacial);
    }

    const modal = document.getElementById('modal-metodologia');
    const btnMetodologia = document.getElementById('btn-metodologia');
    const btnCloseModal = document.getElementById('btn-close-modal');
    if (modal && btnMetodologia && btnCloseModal) {
        btnMetodologia.addEventListener('click', () => { modal.classList.remove('hidden'); });
        btnCloseModal.addEventListener('click', () => { modal.classList.add('hidden'); });
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.add('hidden');
        });
    }
}

async function mudarCidade(explicitLocationId = null) {
    const locationId = explicitLocationId || document.getElementById('search-input').dataset.currentId;
    
    let config;
    if (viewMode === 'cidades') config = CONFIG_CIDADES_GERADO[locationId];
    else if (viewMode === 'estados') config = CONFIG_ESTADOS_GERADO[locationId];
    else if (viewMode === 'regioes') config = CONFIG_REGIOES_GERADO[locationId];
    
    // O zoom é agora ajustado dinamicamente pelo fitBounds
    // mapa.flyTo([config.lat, config.lng], zoomLevel, { duration: 1.5 });

    await executarAnaliseEspacial();
}

