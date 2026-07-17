import re

with open('app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. minzoom: 5 to terrain-source
content = content.replace(
    'tileSize: 256,\n            maxzoom: 14',
    'tileSize: 256,\n            minzoom: 5,\n            maxzoom: 14'
)

# 2. zoom listener
zoom_listener = '''
        mapa.on('zoom', () => {
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
if "mapa.on('zoom', atualizarFisicaDados);" in content:
    content = content.replace("mapa.on('zoom', atualizarFisicaDados);", "mapa.on('zoom', atualizarFisicaDados);" + zoom_listener)

# 3. GeoSampa layer on prediosToggle
predios_target = '''
        if (mapa.getLayer('predios-layer')) {
            mapa.setLayoutProperty('predios-layer', 'visibility', showPredios ? 'visible' : 'none');
        }
'''
predios_replacement = predios_target + '''
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
'''
if predios_target.strip() in content:
    content = content.replace(predios_target.strip(), predios_replacement.strip())

# 4. Opacity thermal map
content = content.replace("'raster-opacity': 0.7", "'raster-opacity': 0.65")
content = content.replace("'raster-opacity': 0.8", "'raster-opacity': 0.65")

# 5. Legends logic
update_legends_func = '''
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
if 'function updateLegends()' not in content:
    content += '\n' + update_legends_func

content = content.replace('const showPredios = e.target.checked;', 'const showPredios = e.target.checked;\n        updateLegends();')
content = content.replace('const showThermal = e.target.checked;', 'const showThermal = e.target.checked;\n        updateLegends();')
content = content.replace('const showTopo = e.target.checked;', 'const showTopo = e.target.checked;\n        updateLegends();')

content = content.replace("document.getElementById('veg-toggle').addEventListener('change', (e) => {", "document.getElementById('veg-toggle').addEventListener('change', (e) => {\n        updateLegends();")
content = content.replace("document.getElementById('erb-toggle').addEventListener('change', (e) => {", "document.getElementById('erb-toggle').addEventListener('change', (e) => {\n        updateLegends();")

# Remove old thermalLegend DOM updates safely
content = re.sub(r'const thermalLegend = document\.getElementById\(\'thermal-legend\'\);', '', content)
content = re.sub(r'if\s*\(thermalLegend\)\s*thermalLegend\.style\.display\s*=\s*.*?(\'block\'\s*:\s*\'none\'|\'none\');', '', content)

with open('app.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done modifying app.js')
