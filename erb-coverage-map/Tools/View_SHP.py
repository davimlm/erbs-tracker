import tempfile
import zipfile
from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd

# 1. CAMINHO EXATO DA SUA PASTA
pasta_zips = Path(r"C:\Users\User\Downloads\SPE\erb-coverage-map\data\geosampa")

arquivos_zip = list(pasta_zips.glob("*.zip"))
print(f"Encontrados {len(arquivos_zip)} arquivo(s) .zip.")

# Padrão oficial do GeoSampa e do Brasil atual: SIRGAS 2000 / UTM Zone 23S
CRS_ALVO = 31983

gdf_list = []

# 2. EXTRAÇÃO TEMPORÁRIA E TRATAMENTO
print("Extraindo, padronizando coordenadas e lendo arquivos temporariamente...")
with tempfile.TemporaryDirectory() as pasta_temp:
    temp_path = Path(pasta_temp)

    for i, zip_path in enumerate(arquivos_zip, 1):
        print(f"[{i}/{len(arquivos_zip)}] Processando: {zip_path.name}...")
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_path)

            shps = list(temp_path.rglob("*.shp"))

            for shp in shps:
                gdf_temp = gpd.read_file(shp, engine="pyogrio")

                # CORREÇÃO DO ERRO: PADRONIZAÇÃO DE CRS
                # Se o arquivo não tiver CRS definido, assumimos o padrão SIRGAS 2000
                if gdf_temp.crs is None:
                    gdf_temp.set_crs(epsg=CRS_ALVO, inplace=True)
                # Se estiver em SAD69 ou qualquer outro CRS diferente, reprojetamos para SIRGAS 2000
                elif gdf_temp.crs.to_epsg() != CRS_ALVO:
                    gdf_temp = gdf_temp.to_crs(epsg=CRS_ALVO)

                # Otimização para Zoom Out: simplifica a geometria (5 metros)
                # Remove vértices desnecessários para economizar RAM
                gdf_temp["geometry"] = gdf_temp.geometry.simplify(
                    tolerance=5.0, preserve_topology=True
                )

                gdf_list.append(gdf_temp)
                shp.unlink()  # Limpa o arquivo temporário

        except Exception as e:
            print(f"  [Erro ao processar {zip_path.name}]: {e}")

if not gdf_list:
    raise RuntimeError(
        "Falha crítica: Nenhum shapefile pôde ser lido dos arquivos ZIP."
    )

print("\nUnificando todas as 95 bases de edificações...")
gdf = pd.concat(gdf_list, ignore_index=True)

print(f"Sucesso! Total de edificações carregadas: {len(gdf):,}")

# ==============================================================================
# 3. PLOTAGEM RÁPIDA (OTIMIZADA PARA ZOOM OUT)
# ==============================================================================
print("Gerando visualização...")
fig, ax = plt.subplots(figsize=(14, 12))

# Como há milhões de polígonos em zoom out, pintar sem borda (edgecolor='none')
# evita que a tela fique preta pelo excesso de linhas de contorno.
gdf.plot(
    ax=ax,
    facecolor="#2b5c8f",
    edgecolor="none",
    alpha=0.6,
)

ax.set_title(
    f"GeoSampa - Malha de Edificações ({len(gdf):,} polígonos padronizados)",
    fontsize=16,
)
ax.set_xlabel("UTM Leste (m) - EPSG:31983")
ax.set_ylabel("UTM Norte (m) - EPSG:31983")
ax.grid(True, linestyle="--", alpha=0.3)
ax.set_aspect("equal")

plt.tight_layout()
plt.show()