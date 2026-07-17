import re
with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Substring 1 to remove
start_str = '<div id="unified-legends" class="legends-container">'
end_str = '<!-- Botão HUD Telemetria -->'
start_idx = content.find(start_str)
end_idx = content.find(end_str)
if start_idx != -1 and end_idx != -1:
    content = content[:start_idx] + content[end_idx:]

# Substring 2 to remove
start_str2 = '<!-- Botão HUD Telemetria -->'
end_str2 = '<script charset="utf-8" src="data/config.js'
start_idx2 = content.find(start_str2)
end_idx2 = content.find(end_str2)
if start_idx2 != -1 and end_idx2 != -1:
    content = content[:start_idx2] + content[end_idx2:]

# Insert the new content
insert_idx = content.find('<script charset="utf-8" src="data/config.js')
new_html = """
<!-- 1. BOTÃO E PAINEL DE TELEMETRIA + LIMPEZA DE CACHE -->
<div id="hud-admin-container" style="position: fixed; top: 16px; left: 16px; z-index: 99999; font-family: monospace;">
    <button id="btn-admin-hud" style="background: #ffd60a; color: #000; font-weight: bold; padding: 8px 14px; border-radius: 6px; border: none; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
        ⚡ TELEMETRIA & CACHE
    </button>
    
    <div id="telemetry-hud" style="display: none; margin-top: 8px; background: rgba(18, 18, 20, 0.95); border: 1px solid #333; border-radius: 8px; padding: 14px; width: 260px; color: #fff; backdrop-filter: blur(8px);">
        <div style="font-size: 11px; color: #aaa; margin-bottom: 8px;">MONITORAMENTO POSTGIS</div>
        <div style="margin-bottom: 6px;">CPU: <span id="hud-cpu" style="color: #00ff00;">0%</span></div>
        <div style="width: 100%; background: #222; height: 4px; border-radius: 2px; margin-bottom: 10px;">
            <div id="hud-cpu-bar" style="width: 0%; background: #00ff00; height: 100%;"></div>
        </div>
        <div style="margin-bottom: 6px;">RAM: <span id="hud-ram" style="color: #00ff00;">0 GB (0%)</span></div>
        <div style="width: 100%; background: #222; height: 4px; border-radius: 2px; margin-bottom: 10px;">
            <div id="hud-ram-bar" style="width: 0%; background: #00ff00; height: 100%;"></div>
        </div>
        <div style="margin-bottom: 12px;">Conexões DB: <span id="hud-db-conns" style="color: #0a84ff;">0 / 0</span></div>
        
        <hr style="border: 0; border-top: 1px solid #333; margin: 10px 0;">
        <button id="btn-clear-cache" style="width: 100%; background: #ff3b30; color: #fff; font-weight: bold; padding: 8px; border-radius: 4px; border: none; cursor: pointer;">
            [!] LIMPAR CACHE LOCAL (PBF)
        </button>
    </div>
</div>

<!-- 2. CONTAINER UNIFICADO DE LEGENDAS EM GRADIENTE -->
<div id="unified-legends" style="position: fixed; bottom: 24px; right: 24px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; pointer-events: none; font-family: sans-serif;">
    <!-- Sombra Exata (Fixo) -->
    <div class="legend-card" style="background: rgba(18, 18, 20, 0.9); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 10px 14px; pointer-events: auto; color: #fff;">
        <div style="font-size: 12px; font-weight: bold; margin-bottom: 4px;">Sombra de RF (Falha Geodésica)</div>
        <div style="display: flex; align-items: center; gap: 8px; font-size: 11px; color: #ccc;">
            <span style="width: 14px; height: 14px; background: #ff3b30; border-radius: 2px; display: inline-block;"></span>
            <span>Área sem Cobertura Calculada</span>
        </div>
    </div>

    <!-- Relevo Termal (Gradiente Contínuo) -->
    <div id="leg-thermal" class="legend-card hidden" style="display: none; background: rgba(18, 18, 20, 0.9); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 10px 14px; pointer-events: auto; color: #fff;">
        <div style="font-size: 12px; font-weight: bold;">Altimetria (Topodata MDE)</div>
        <div style="height: 8px; border-radius: 4px; margin: 6px 0; width: 180px; background: linear-gradient(90deg, #30123b, #28bceb, #a5fb38, #f86012, #7a0403);"></div>
        <div style="display: flex; justify-content: space-between; font-size: 10px; color: #aaa;"><span>0m</span><span>600m</span><span>1200m+</span></div>
    </div>

    <!-- Vegetação (Degraus Discretos de Atenuação RF) -->
    <div id="leg-veg" class="legend-card hidden" style="display: none; background: rgba(18, 18, 20, 0.9); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 10px 14px; pointer-events: auto; color: #fff;">
        <div style="font-size: 12px; font-weight: bold;">Atenuação Vegetativa (700MHz)</div>
        <div style="height: 8px; border-radius: 4px; margin: 6px 0; width: 180px; background: linear-gradient(90deg, #a5d6a7 0% 25%, #66bb6a 25% 50%, #388e3c 50% 75%, #004d00 75% 100%);"></div>
        <div style="display: flex; justify-content: space-between; font-size: 10px; color: #aaa;"><span>0.0</span><span>0.08</span><span>0.18 dBm/m</span></div>
    </div>

    <!-- População H3 (Gradiente de Densidade) -->
    <div id="leg-pop" class="legend-card hidden" style="display: none; background: rgba(18, 18, 20, 0.9); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 6px; padding: 10px 14px; pointer-events: auto; color: #fff;">
        <div style="font-size: 12px; font-weight: bold;">Densidade Populacional H3</div>
        <div style="height: 8px; border-radius: 4px; margin: 6px 0; width: 180px; background: linear-gradient(90deg, rgba(144,238,144,0.4), rgba(255,165,0,0.8), rgba(255,0,0,0.9));"></div>
        <div style="display: flex; justify-content: space-between; font-size: 10px; color: #aaa;"><span>10</span><span>500</span><span>2500+ hab/km²</span></div>
    </div>
</div>

"""
if insert_idx != -1:
    content = content[:insert_idx] + new_html + content[insert_idx:]

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
