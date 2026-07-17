import sys

with open('app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out_lines = []

update_legends = '''
function updateLegends() {
    const topoToggle = document.getElementById('topo-toggle');
    const thermalToggle = document.getElementById('thermal-toggle');
    const erbToggle = document.getElementById('erb-toggle');
    const vegToggle = document.getElementById('veg-toggle');
    const prediosToggle = document.getElementById('predios-toggle');

    const setDisplay = (id, show) => {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? 'block' : 'none';
    };

    setDisplay('legend-thermal', thermalToggle && thermalToggle.checked);
    setDisplay('legend-sombra', erbToggle && erbToggle.checked);
    setDisplay('legend-vegetacao', vegToggle && vegToggle.checked);
    setDisplay('legend-predios', prediosToggle && prediosToggle.checked);
}
'''

zoom_logic = '''        mapa.on('zoom', () => {
            const z = mapa.getZoom();
            const topoToggle = document.getElementById('topo-toggle');
            if (topoToggle && topoToggle.checked) {
                if (z < 5) {
                    mapa.setTerrain(null);
                } else {
                    mapa.setTerrain({ source: 'terrain-source', exaggeration: 3.0 });
                }
            }
        });
'''

toggles_logic = '''
    const prediosToggle = document.getElementById('predios-toggle');
    if (prediosToggle) prediosToggle.addEventListener('change', (e) => {
        const showPredios = e.target.checked;
        updateLegends();
        
        if (mapa.getLayer('predios-layer')) {
            mapa.setLayoutProperty('predios-layer', 'visibility', showPredios ? 'visible' : 'none');
        }

        if (showPredios) {
            if (!mapa.getSource('geosampa-mvt')) {
                const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
                mapa.addSource('geosampa-mvt', {
                    type: 'vector',
                    tiles: [`${baseUrl}/api/geosampa_tiles/{z}/{x}/{y}.pbf`]
                });
                let beforeId = undefined;
                if (mapa.getLayer('predios-layer')) beforeId = 'predios-layer';
                
                mapa.addLayer({
                    'id': 'geosampa-layer',
                    'type': 'fill-extrusion',
                    'source': 'geosampa-mvt',
                    'source-layer': 'geosampa',
                    'paint': {
                        'fill-extrusion-color': '#ffd60a',
                        'fill-extrusion-height': ['get', 'height'],
                        'fill-extrusion-opacity': 0.95
                    }
                }, beforeId);
            } else {
                mapa.setLayoutProperty('geosampa-layer', 'visibility', 'visible');
            }
        } else {
            if (mapa.getLayer('geosampa-layer')) {
                mapa.setLayoutProperty('geosampa-layer', 'visibility', 'none');
            }
        }
    });

    const topoToggle = document.getElementById('topo-toggle');
    if (topoToggle) topoToggle.addEventListener('change', (e) => {
        const showTopo = e.target.checked;
        updateLegends();
        if (showTopo) {
            if (!mapa.getSource('terrain-source')) {
                mapa.addSource('terrain-source', {
                    type: 'raster-dem',
                    url: 'https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=QG1m5y50D7uN7h4cXXnU',
                    tileSize: 256,
                    minzoom: 5,
                    maxzoom: 14
                });
            }
            if (mapa.getZoom() >= 5) {
                mapa.setTerrain({ source: 'terrain-source', exaggeration: 3.0 });
            }
        } else {
            mapa.setTerrain(null);
        }
    });

    const thermalToggle = document.getElementById('thermal-toggle');
    if (thermalToggle) thermalToggle.addEventListener('change', (e) => {
        const showThermal = e.target.checked;
        const baseUrl = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
        updateLegends();

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
'''

for line in lines:
    # 1. Update Zoom listener
    if "mapa.on('zoom', atualizarFisicaDados);" in line:
        out_lines.append(line)
        out_lines.append(zoom_logic)
        continue
    
    # 2. Add updateLegends() calls to existing toggles
    if "if (popToggle) popToggle.addEventListener('change', (e) => {" in line:
        out_lines.append(line)
        out_lines.append("        updateLegends();\n")
        continue
    if "if (vegToggle) vegToggle.addEventListener('change', (e) => {" in line:
        out_lines.append(line)
        out_lines.append("        updateLegends();\n")
        continue
    if "if (erbToggle) erbToggle.addEventListener('change', (e) => {" in line:
        out_lines.append(line)
        out_lines.append("        updateLegends();\n")
        continue

    # 3. Insert new toggles after erb-toggle
    if "const btnClearCache = document.getElementById('btn-clear-cache');" in line:
        out_lines.append(toggles_logic)
        out_lines.append(line)
        continue

    out_lines.append(line)

# Add updateLegends at the end
out_lines.append("\n" + update_legends)

with open('app.js', 'w', encoding='utf-8') as f:
    f.writelines(out_lines)

print("Recover script completed.")
