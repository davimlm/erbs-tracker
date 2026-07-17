import geopandas as gpd
import warnings
warnings.filterwarnings('ignore')

# 1. COLOQUE O CAMINHO DO SEU ARQUIVO ZIP AQUI
caminho_zip = r"C:\Users\User\Downloads\SPE\vege_area.zip"

try:
    print(f"Lendo o arquivo: {caminho_zip} (Isso pode levar alguns segundos...)")
    
    # O Geopandas consegue ler o shapefile diretamente de dentro do ZIP
    gdf = gpd.read_file(f"zip://{caminho_zip}")

    print("\n========================================")
    print("✅ COLUNAS DISPONÍVEIS NO ARQUIVO:")
    print("========================================")
    for col in gdf.columns:
        print(f"  - {col}")

    # Pega as colunas de texto (ignorando a geometria e números)
    colunas_texto = [c for c in gdf.select_dtypes(include=['object']).columns if c != 'geometry']
    
    if len(colunas_texto) > 0:
        # Geralmente a primeira coluna de texto é a legenda principal
        alvo = colunas_texto[0] 
        
        print("\n========================================")
        print(f"🔍 CATEGORIAS ENCONTRADAS NA COLUNA '{alvo}':")
        print("========================================")
        
        categorias = gdf[alvo].dropna().unique()
        for cat in categorias[:20]: # Mostra as 20 primeiras categorias
            print(f"  - {cat}")
            
except Exception as e:
    print(f"❌ Erro ao ler o arquivo: {e}")