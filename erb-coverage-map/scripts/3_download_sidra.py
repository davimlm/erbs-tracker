import urllib.request
import json
import os

def download_sidra_populacao():
    print("Iniciando download dos dados populacionais do IBGE SIDRA (Censo 2022)...")
    
    # URL da API de Agregados do IBGE (Tabela 4709 - População residente Censo 2022)
    # N6[all] = Todos os municípios do Brasil
    url = "https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93?localidades=N6[all]"
    
    try:
        import requests
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        data = r.json()
    except Exception as e:
        print(f"Erro ao acessar a API do IBGE: {e}")
        return

    # A API retorna uma lista. O primeiro item contém os 'resultados'
    series = data[0]['resultados'][0]['series']
    
    # Estrutura de organização: Estado -> Município -> Dados
    populacao_estruturada = {
        "metadata": {
            "fonte": "IBGE - SIDRA",
            "tabela": "4709",
            "variavel": "População residente (Censo 2022)",
            "unidade": "Pessoas"
        },
        "estados": {}
    }
    
    print(f"Processando {len(series)} municípios...")
    
    for item in series:
        # Ex: "Alta Floresta D'Oeste - RO"
        nome_completo = item['localidade']['nome']
        codigo_ibge = item['localidade']['id'] # Código IBGE de 7 dígitos
        
        # A série do ano 2022
        pop_str = item['serie'].get('2022', '0')
        populacao = int(pop_str) if pop_str and pop_str.isdigit() else 0
        
        if " - " in nome_completo:
            municipio, uf = nome_completo.split(" - ", 1)
        else:
            municipio = nome_completo
            uf = "Desconhecido"
            
        if uf not in populacao_estruturada['estados']:
            populacao_estruturada['estados'][uf] = []
            
        populacao_estruturada['estados'][uf].append({
            "codigo_ibge": codigo_ibge,
            "municipio": municipio,
            "populacao": populacao
        })

    # Ordenar os estados alfabeticamente e as cidades dentro de cada estado
    estados_ordenados = {}
    for uf in sorted(populacao_estruturada['estados'].keys()):
        cidades = populacao_estruturada['estados'][uf]
        cidades_ordenadas = sorted(cidades, key=lambda x: x['municipio'])
        estados_ordenados[uf] = cidades_ordenadas
        
    populacao_estruturada['estados'] = estados_ordenados

    # Determinar caminho de saída (pasta data do projeto)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, '..', 'data', 'sidra_populacao.json')
    
    # Salvar o arquivo
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(populacao_estruturada, f, ensure_ascii=False, indent=4)
        
    print(f"Sucesso! Dados organizados e salvos em: {output_path}")

if __name__ == "__main__":
    download_sidra_populacao()
