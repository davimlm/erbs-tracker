import pandas as pd
import json
import os
import re
import unicodedata

# Corrige problema de caminhos relativos independente de onde o script seja rodado
script_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(script_dir, '..', 'data', 'ERBs Mar26.xlsx')
out_path = os.path.join(script_dir, '..', 'data', 'erbs_cidades.js')

df = pd.read_excel(data_path)

# 1. Limpeza de coordenadas (Vetorizado e extremamente rápido)
df['Latitude'] = pd.to_numeric(df['Latitude'].astype(str).str.replace(',', '.'), errors='coerce')
df['Longitude'] = pd.to_numeric(df['Longitude'].astype(str).str.replace(',', '.'), errors='coerce')
df = df.dropna(subset=['Latitude', 'Longitude'])

# 2. Mapeamento de Operadoras (Função aplicada à coluna)
df['Operadora'] = df['Operadora'].astype(str).str.lower()
df['op_clean'] = df['Operadora'].apply(lambda op: next((o for o in ['vivo', 'claro', 'tim', 'algar'] if o in op), 'outra'))

# 3. Extração de Frequências (Toggles: 700, 2600, 3500)
df['Faixa'] = df['Faixa'].astype(str).str.lower()
df['Tecs'] = df['Tecs'].astype(str).str.lower()

def extrair_freqs(row):
    f = []
    if '700' in row['Faixa']: f.append('700')
    if '2600' in row['Faixa']: f.append('2600')
    if '3500' in row['Faixa'] or '3,5' in row['Faixa'] or '5g' in row['Tecs']: f.append('3500')
    return f if f else ['700'] # Default para torres sem info

df['freqs'] = df.apply(extrair_freqs, axis=1)

# 4. Formatação de Cidades, Estados e Regiões
df['MUN'] = df['MUN'].astype(str).str.strip().str.title()
df['SiglaUf'] = df['SiglaUf'].astype(str).str.strip().str.upper()

regioes_map = {
    'AC': 'Norte', 'AP': 'Norte', 'AM': 'Norte', 'PA': 'Norte', 'RO': 'Norte', 'RR': 'Norte', 'TO': 'Norte',
    'AL': 'Nordeste', 'BA': 'Nordeste', 'CE': 'Nordeste', 'MA': 'Nordeste', 'PB': 'Nordeste', 'PE': 'Nordeste', 'PI': 'Nordeste', 'RN': 'Nordeste', 'SE': 'Nordeste',
    'DF': 'Centro-Oeste', 'GO': 'Centro-Oeste', 'MT': 'Centro-Oeste', 'MS': 'Centro-Oeste',
    'ES': 'Sudeste', 'MG': 'Sudeste', 'RJ': 'Sudeste', 'SP': 'Sudeste',
    'PR': 'Sul', 'RS': 'Sul', 'SC': 'Sul'
}
df['Regiao'] = df['SiglaUf'].map(regioes_map)

import requests

def to_id(text):
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'[^a-z0-9]', '_', text.lower())

df['cidade_id'] = df['MUN'].apply(to_id) + '_' + df['SiglaUf'].str.lower()

ibge_cache_path = os.path.join(script_dir, '..', 'data', 'ibge_pop.json')
ibge_pop_map = {}
if os.path.exists(ibge_cache_path):
    with open(ibge_cache_path, 'r', encoding='utf-8') as f:
        ibge_pop_map = json.load(f)
else:
    try:
        url_ibge = "https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[all]"
        r = requests.get(url_ibge, timeout=30)
        data = r.json()[0]['resultados'][0]['series']
        for item in data:
            nome_full = item['localidade']['nome'] # "Alta Floresta D'Oeste - RO"
            pop = int(item['serie']['2022']) if item['serie']['2022'] else 0
            if " - " in nome_full:
                mun, uf = nome_full.split(" - ")
                cid_id = to_id(mun) + "_" + uf.lower()
                ibge_pop_map[cid_id] = pop
        with open(ibge_cache_path, 'w', encoding='utf-8') as f:
            json.dump(ibge_pop_map, f, ensure_ascii=False)
    except Exception as e:
        print("Erro ao buscar dados do IBGE:", e)

# Adicionando populao aos estados e regies
pop_estados_map = {}
pop_regioes_map = {}
for cid, pop in ibge_pop_map.items():
    uf = cid.split('_')[-1].upper()
    pop_estados_map[uf] = pop_estados_map.get(uf, 0) + pop
    regiao = regioes_map.get(uf, 'Desconhecida')
    pop_regioes_map[regiao] = pop_regioes_map.get(regiao, 0) + pop

city_centers = df.groupby(['cidade_id', 'MUN', 'SiglaUf', 'Regiao'])[['Latitude', 'Longitude']].mean().reset_index()
city_centers = city_centers.sort_values('MUN')

config_cidades = {}
for _, row in city_centers.iterrows():
    cid_id = row['cidade_id']
    pop = ibge_pop_map.get(cid_id, 0)
    config_cidades[cid_id] = {
        'lat': row['Latitude'],
        'lng': row['Longitude'],
        'nome': f"{row['MUN']} - {row['SiglaUf']}",
        'uf': row['SiglaUf'],
        'regiao': row['Regiao'],
        'populacao': pop
    }

# --- CONFIGURAÇÕES: ESTADOS ---
state_centers = df.groupby('SiglaUf')[['Latitude', 'Longitude']].mean().reset_index()
state_centers = state_centers.sort_values('SiglaUf')

config_estados = {}
for _, row in state_centers.iterrows():
    uf = row['SiglaUf']
    config_estados[uf] = {
        'lat': row['Latitude'],
        'lng': row['Longitude'],
        'nome': uf,
        'uf': uf,
        'regiao': regioes_map.get(uf, 'Desconhecida'),
        'populacao': pop_estados_map.get(uf, 0)
    }

# --- CONFIGURAÇÕES: REGIÕES ---
region_centers = df.groupby('Regiao')[['Latitude', 'Longitude']].mean().reset_index()
region_centers = region_centers.sort_values('Regiao')

config_regioes = {}
for _, row in region_centers.iterrows():
    reg = row['Regiao']
    config_regioes[reg] = {
        'lat': row['Latitude'],
        'lng': row['Longitude'],
        'nome': reg,
        'regiao': reg,
        'populacao': pop_regioes_map.get(reg, 0)
    }

# Estruturando os dados finais das ERBs
erbsData = {}
view = df[['cidade_id', 'Latitude', 'Longitude', 'op_clean', 'freqs', 'SiglaUf', 'Regiao']]

for cid, group in view.groupby('cidade_id'):
    erbsData[cid] = [
        {
            'lat': row['Latitude'],
            'lng': row['Longitude'],
            'operadora': row['op_clean'],
            'frequencias': row['freqs'],
            'uf': row['SiglaUf'],
            'regiao': row['Regiao']
        }
        for _, row in group.iterrows()
    ]

os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('const CONFIG_CIDADES_GERADO = ')
    json.dump(config_cidades, f, ensure_ascii=False)
    f.write(';\nconst CONFIG_ESTADOS_GERADO = ')
    json.dump(config_estados, f, ensure_ascii=False)
    f.write(';\nconst CONFIG_REGIOES_GERADO = ')
    json.dump(config_regioes, f, ensure_ascii=False)
    f.write(';\nconst erbsData = ')
    json.dump(erbsData, f, ensure_ascii=False)
    f.write(';\n')

print(f"Banco atualizado")
