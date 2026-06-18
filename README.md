# Mapeamento de ERBs e Identificação de Gargalos de Cobertura no Brasil

Aplicação web para análise geográfica de infraestrutura de telecomunicações, cruzando a localização das Estações Rádio Base (ERBs) com dados populacionais do IBGE para identificar regiões com cobertura de rede desproporcional à população residente.

## Contexto

A cobertura de telefonia móvel no Brasil é garantida por uma rede de ERBs distribuída de forma desigual pelo território. Em regiões densamente povoadas, a falta de ERBs próximas pode gerar sobrecarga de rede, sinal fraco e baixa qualidade de serviço — mesmo em áreas urbanas. Este projeto busca identificar esses "gargalos": regiões com população significativa, mas cobertura insuficiente de ERBs.

## Objetivo

Desenvolver uma aplicação web que permita visualizar a densidade de ERBs por região do Brasil e identificar municípios/áreas onde a relação ERBs x população indica carência de infraestrutura.

## Base de Dados

Cadastro nacional de ERBs (ANATEL, referência mar/2026):

| Métrica | Valor |
|---|---|
| Total de ERBs no Brasil | 110.045 |
| Municípios com ERB cadastrada | 5.296 |
| ERBs no estado de SP | 24.449 |
| Operadoras | 7 (Vivo, Tim, Claro, etc.) |

**Colunas:** Número da Estação, Operadora, UF, Município, Bairro, Logradouro, Latitude, Longitude, Código IBGE, Classe de Infraestrutura Física, Tecnologias (2G/3G/4G/5G) e Faixas de Frequência.

## Metodologia

1. **Tratamento da base de ERBs** — limpeza e padronização das coordenadas e atributos técnicos (tecnologia, faixa de frequência).
2. **Obtenção de dados do IBGE** — população por município/setor censitário e malha geográfica para visualização em mapa.
3. **Cálculo de densidade** — número de ERBs por área e por população em cada região.
4. **Cruzamento e classificação** — definição de um índice de gargalo (ex: habitantes por ERB), considerando também o alcance estimado de cada estação a partir da tecnologia/faixa de frequência (frequências baixas, como 700/900 MHz, indicam maior alcance; frequências altas, como 3500 MHz, indicam menor alcance).
5. **Visualização** — exibição dos resultados em mapa interativo.

## Funcionalidades Propostas

- **Mapa interativo** com ERBs e malha municipal, com camadas de população e densidade de cobertura.
- **Indicador de gargalo** — classificação visual (ex: verde/amarelo/vermelho) das regiões.
- **Filtros** por UF, município, operadora e tecnologia.
- **Ranking de regiões** com maior carência relativa de cobertura.

## Fontes de Dados

- Base de ERBs — ANATEL
- População por município — IBGE (Censo/estimativas populacionais)
- Malha geográfica municipal — IBGE (shapefiles)

## Tecnologias Previstas

- Python (pandas, geopandas) — tratamento e análise dos dados
- Leaflet.js — mapa interativo
- HTML/CSS/JS — interface web

## Resultado Esperado

Identificação visual das regiões do Brasil que concentram população significativa, mas possuem baixa densidade de ERBs, servindo como apoio a discussões sobre priorização de investimentos em infraestrutura de telecomunicações.

