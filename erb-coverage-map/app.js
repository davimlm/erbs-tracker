// Configurações de propagação teórica por frequência (ambiente urbano denso)
const CONFIG_PROPAGACAO = {
    '700': { raioMetros: 1200, corCobertura: '#30d158' },  // Alto alcance/penetração
    '2600': { raioMetros: 600, corCobertura: '#0a84ff' },  // Médio alcance
    '3500': { raioMetros: 300, corCobertura: '#bf5af2' }   // Curto alcance (5G Puro)
};

// Inicialização do Estado da Aplicação
let mapa;
let camadaEstudoGroup;
let camadaDadosGroup;
let basePointsERB = []; // Armazena a infraestrutura fixa para evitar mutações de posição
// CONFIG_CIDADES_GERADO já vêm carregados via tag <script> no HTML (config.js)
let erbsDataCache = {}; // Cache de macrorregiões
let malhasIbgeCache = {}; // Cache de contornos IBGE
let malhaPoligonoAtual = null; // Guarda o GeoJSON da malha atual

let viewMode = 'cidades'; // 'cidades', 'estados', 'regioes'

document.addEventListener('DOMContentLoaded', async () => {
    inicializarMapa();
    configurarAbasModoVisualizacao();
    await popularDropdownLocation(); // Popula o dropdown e engatilha mudarCidade()
    configurarEventosUI();
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
    const citySelect = document.getElementById('city-select');
    citySelect.innerHTML = ''; 
    
    let configData;
    if (viewMode === 'cidades') configData = CONFIG_CIDADES_GERADO;
    else if (viewMode === 'estados') configData = CONFIG_ESTADOS_GERADO;
    else if (viewMode === 'regioes') configData = CONFIG_REGIOES_GERADO;
    
    const locations = Object.entries(configData);
    if (locations.length === 0) return;
    
    let defaultId = locations[0][0];
    
    for (const [id, config] of locations) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = config.nome;
        citySelect.appendChild(option);
    }
    
    // Força selecao da capital SP caso exista na lista de cidades
    if (viewMode === 'cidades' && configData['sao_paulo_sp']) {
        defaultId = 'sao_paulo_sp';
    }
    
    citySelect.value = defaultId;
    await mudarCidade();
}

function inicializarMapa() {
    mapa = L.map('map', {
        zoom: 14,
        zoomControl: false
    });

    L.control.zoom({
        position: 'topright'
    }).addTo(mapa);

    // Substituição do mapa base clássico por CartoDB Dark Matter (Essencial para destacar o mapa de calor/vetores)
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(mapa);

    camadaEstudoGroup = L.layerGroup().addTo(mapa);
    camadaDadosGroup = L.layerGroup().addTo(mapa);
}

// Carrega a base de ERBs para a região selecionada (Cidade, Estado ou Região)
function gerarMalhaInfraestrutura(locationId, erbsDataLocal) {
    basePointsERB = []; // Limpa a base
    
    if (viewMode === 'cidades') {
        if (erbsDataLocal[locationId]) {
            basePointsERB = erbsDataLocal[locationId];
        }
    } else if (viewMode === 'estados') {
        // locationId é a UF (ex: 'SP')
        for (const [cid, erbsArray] of Object.entries(erbsDataLocal)) {
            if (erbsArray.length > 0 && erbsArray[0].uf === locationId) {
                basePointsERB = basePointsERB.concat(erbsArray);
            }
        }
    } else if (viewMode === 'regioes') {
        // locationId é a Regiao (ex: 'Sudeste')
        // O erbsDataLocal inteiro já é filtrado pela macrorregião selecionada
        for (const [cid, erbsArray] of Object.entries(erbsDataLocal)) {
            basePointsERB = basePointsERB.concat(erbsArray);
        }
    }
}

function executarAnaliseEspacial() {
    // Limpar camadas anteriores
    camadaEstudoGroup.clearLayers();
    camadaDadosGroup.clearLayers();

    // 1. Obter parâmetros da UI
    const operadoraSelecionada = document.getElementById('operator-select').value;
    const frequenciaSelecionada = document.querySelector('input[name="frequency"]:checked').value;
    const configFrequencia = CONFIG_PROPAGACAO[frequenciaSelecionada];
    const raioMetros = configFrequencia.raioMetros;

    // 2. Filtrar e Processar ERBs Ativas
    const erbsAtivas = basePointsERB.filter(erb => {
        const matchOp = operadoraSelecionada === 'all' || erb.operadora === operadoraSelecionada;
        const matchFreq = erb.frequencias && erb.frequencias.includes(frequenciaSelecionada);
        return matchOp && matchFreq;
    });

    // 3. Definir Polígono da Área de Estudo
    const locationId = document.getElementById('city-select').value;
    let configLocal;
    if (viewMode === 'cidades') configLocal = CONFIG_CIDADES_GERADO[locationId];
    else if (viewMode === 'estados') configLocal = CONFIG_ESTADOS_GERADO[locationId];
    else if (viewMode === 'regioes') configLocal = CONFIG_REGIOES_GERADO[locationId];
    
    let poligonoEstudo;

    if (malhaPoligonoAtual) {
        // Usa o geojson exato baixado do IBGE
        // A API do IBGE retorna um FeatureCollection, o turf.difference precisa da geometria (Polygon/MultiPolygon)
        poligonoEstudo = malhaPoligonoAtual.features[0];
        
        L.geoJSON(malhaPoligonoAtual, {
            style: { color: '#ffffff', weight: 2, dashArray: '4, 4', fillOpacity: 0.05 }
        }).addTo(camadaEstudoGroup);
    } else {
        // Fallback: calcula bounding box
        if (viewMode === 'cidades' && erbsAtivas.length > 0) {
            const margemKm = (raioMetros / 1000) + 0.5;
            if (erbsAtivas.length === 1) {
                const pt = turf.point([erbsAtivas[0].lng, erbsAtivas[0].lat]);
                const bboxEstudo = turf.bbox(turf.circle(pt, margemKm, {units: 'kilometers'}));
                poligonoEstudo = turf.bboxPolygon(bboxEstudo);
            } else {
                const pts = erbsAtivas.map(erb => turf.point([erb.lng, erb.lat]));
                const fc = turf.featureCollection(pts);
                const envelop = turf.envelope(fc);
                const bboxBuffer = turf.buffer(envelop, margemKm, {units: 'kilometers'});
                poligonoEstudo = turf.bboxPolygon(turf.bbox(bboxBuffer));
            }
        } else {
            const centroDireto = [configLocal.lng, configLocal.lat];
            let bboxSizeKm = 2.2;
            if (viewMode === 'estados') bboxSizeKm = 200;
            if (viewMode === 'regioes') bboxSizeKm = 800;
            const bboxEstudo = turf.bbox(turf.circle(centroDireto, bboxSizeKm, {units: 'kilometers'}));
            poligonoEstudo = turf.bboxPolygon(bboxEstudo);
        }

        if (viewMode === 'cidades') {
            L.geoJSON(poligonoEstudo, {
                style: { color: '#ffffff', weight: 1, dashArray: '5, 5', fillOpacity: 0 }
            }).addTo(camadaEstudoGroup);
        }
    }

    let buffersCobertura = [];
    const colorCoverage = frequenciaSelecionada === '700' ? '#0a84ff' : 
                          frequenciaSelecionada === '2600' ? '#ff9f0a' : '#bf5af2';

    // Para qualquer volume, desenhamos os círculos normais das antenas com Leaflet nativo
    erbsAtivas.forEach(erb => {
        L.circle([erb.lat, erb.lng], {
            color: colorCoverage,
            fillColor: colorCoverage,
            fillOpacity: 0.1,
            radius: raioMetros,
            weight: 1
        }).addTo(camadaEstudoGroup);

        // Marcadores físicos (pontos brancos) apenas se for visão Cidade, senão o mapa fica poluído
        if (viewMode === 'cidades') {
            L.circleMarker([erb.lat, erb.lng], {
                radius: 4,
                fillColor: '#ffffff',
                color: '#000000',
                weight: 1,
                fillOpacity: 1
            }).bindPopup(`<b>Operadora:</b> ${erb.operadora.toUpperCase()}`).addTo(camadaDadosGroup);
        }
    });

    let poligonoZonaSombra = null;

    // Trava de segurança para Turf.js
    const LIMIT_TURF = 1500;
    
    if (erbsAtivas.length <= LIMIT_TURF && viewMode === 'cidades') {
        erbsAtivas.forEach(erb => {
            const pt = turf.point([erb.lng, erb.lat]);
            const buffered = turf.buffer(pt, raioMetros, {units: 'meters'});
            buffersCobertura.push(buffered);
        });

        if (buffersCobertura.length > 0) {
            let uniaoCobertura = buffersCobertura[0];
            for (let i = 1; i < buffersCobertura.length; i++) {
                uniaoCobertura = turf.union(uniaoCobertura, buffersCobertura[i]);
            }
            
            poligonoZonaSombra = turf.difference(poligonoEstudo, uniaoCobertura);
            
            if (poligonoZonaSombra) {
                L.geoJSON(poligonoZonaSombra, {
                    style: {
                        color: 'transparent',
                        fillColor: '#ff3b30',
                        fillOpacity: 0.35 // Vermelho indicando buraco de sombra
                    }
                }).addTo(camadaEstudoGroup);
            }
        } else {
            poligonoZonaSombra = poligonoEstudo;
        }
    } else {
        if (erbsAtivas.length > LIMIT_TURF) {
            console.warn(`[Segurança] ${erbsAtivas.length} antenas na tela. O cálculo matemático de sombra (Turf.js) foi desligado para não travar o navegador.`);
        }
    }

    // 6. Atualização de Métricas
    const areaTotalKm2 = turf.area(poligonoEstudo) / 1000000;
    const areaSombraKm2 = poligonoZonaSombra ? (turf.area(poligonoZonaSombra) / 1000000) : 0;
    const percentualSombra = viewMode === 'cidades' ? ((areaSombraKm2 / areaTotalKm2) * 100).toFixed(1) : 'N/A';

    // População e Habitantes por ERB
    const pop = configLocal.populacao || 0;
    let habPorErb = '--';
    if (erbsAtivas.length > 0 && pop > 0) {
        habPorErb = Math.round(pop / erbsAtivas.length).toLocaleString('pt-BR');
    }

    document.getElementById('stat-erb-count').innerText = erbsAtivas.length.toLocaleString('pt-BR');
    document.getElementById('stat-total-area').innerText = viewMode === 'cidades' ? `${areaTotalKm2.toFixed(2)} km²` : 'Visão Macro';
    document.getElementById('stat-population').innerText = pop > 0 ? pop.toLocaleString('pt-BR') : 'N/D';
    document.getElementById('stat-hab-erb').innerText = habPorErb;
    document.getElementById('stat-shadow-percent').innerText = viewMode === 'cidades' ? `${percentualSombra}%` : '--';
    document.getElementById('shadow-progress').style.width = viewMode === 'cidades' ? `${percentualSombra}%` : '0%';
}

function configurarEventosUI() {
    document.getElementById('city-select').addEventListener('change', mudarCidade);
    
    document.getElementById('operator-select').addEventListener('change', () => {
        executarAnaliseEspacial();
        atualizarVeracidade();
    });
    
    const radioButtons = document.querySelectorAll('input[name="frequency"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', executarAnaliseEspacial);
    });
}

async function mudarCidade() {
    const locationId = document.getElementById('city-select').value;
    
    let config;
    if (viewMode === 'cidades') config = CONFIG_CIDADES_GERADO[locationId];
    else if (viewMode === 'estados') config = CONFIG_ESTADOS_GERADO[locationId];
    else if (viewMode === 'regioes') config = CONFIG_REGIOES_GERADO[locationId];
    
    let zoomLevel = 14;
    if (viewMode === 'estados') zoomLevel = 6;
    if (viewMode === 'regioes') zoomLevel = 5;
    
    mapa.setView([config.lat, config.lng], zoomLevel);
    
    const regiaoNome = config.regiao;
    const reg_filename = `erbs_${regiaoNome.replace(' ', '')}.json`;
    
    let erbsDataLocal = erbsDataCache[regiaoNome];
    if (!erbsDataLocal) {
        document.getElementById('loading-overlay').style.display = 'flex';
        document.querySelector('#loading-overlay p').innerText = 'Baixando dados da região...';
        try {
            const response = await fetch(`data/${reg_filename}`);
            erbsDataLocal = await response.json();
            erbsDataCache[regiaoNome] = erbsDataLocal;
        } catch (error) {
            console.error("Erro ao carregar dados da região:", error);
            erbsDataLocal = {};
        }
        document.getElementById('loading-overlay').style.display = 'none';
    }
    
    // Download da Malha do IBGE (se existir código)
    malhaPoligonoAtual = null;
    if (config.ibge_code) {
        let nivelIbge = 'municipios';
        if (viewMode === 'estados') nivelIbge = 'estados';
        if (viewMode === 'regioes') nivelIbge = 'regioes';
        
        const cacheKey = `${nivelIbge}_${config.ibge_code}`;
        if (malhasIbgeCache[cacheKey]) {
            malhaPoligonoAtual = malhasIbgeCache[cacheKey];
        } else {
            document.getElementById('loading-overlay').style.display = 'flex';
            document.querySelector('#loading-overlay p').innerText = 'Baixando malha do IBGE...';
            try {
                const res = await fetch(`https://servicodados.ibge.gov.br/api/v3/malhas/${nivelIbge}/${config.ibge_code}?formato=application/vnd.geo+json`);
                if (res.ok) {
                    const geojson = await res.json();
                    malhasIbgeCache[cacheKey] = geojson;
                    malhaPoligonoAtual = geojson;
                }
            } catch (e) {
                console.error("Erro ao buscar malha IBGE:", e);
            }
            document.getElementById('loading-overlay').style.display = 'none';
        }
    }

    gerarMalhaInfraestrutura(locationId, erbsDataLocal);
    executarAnaliseEspacial();
    atualizarVeracidade();
}

function atualizarVeracidade() {
    const operadora = document.getElementById('operator-select').value;
    const ddElement = document.getElementById('veracity-downdetector');
    const telecoElement = document.getElementById('veracity-teleco');
    
    if (operadora === 'claro') {
        ddElement.innerText = 'Picos de Instabilidade';
        ddElement.className = 'stat-value warning-text';
        telecoElement.innerText = '28% Market Share';
    } else if (operadora === 'vivo') {
        ddElement.innerText = 'Estável';
        ddElement.className = 'stat-value success-text';
        telecoElement.innerText = '35% Market Share';
    } else if (operadora === 'tim') {
        ddElement.innerText = 'Normal';
        ddElement.className = 'stat-value success-text';
        telecoElement.innerText = '22% Market Share';
    } else {
        ddElement.innerText = 'Geral Estável';
        ddElement.className = 'stat-value success-text';
        telecoElement.innerText = 'Dados Consolidados';
    }
}
