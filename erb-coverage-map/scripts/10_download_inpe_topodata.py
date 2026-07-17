import os
import re
import urllib.request
import asyncio
import aiohttp
from tqdm.asyncio import tqdm

# URL base do diretório do INPE Topodata
BASE_URL = "http://www.dsr.inpe.br/topodata/data/geotiff/"
# Diretório onde os arquivos brutos serão salvos
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "topodata_mde_raw")

async def download_file(session, url, dest_path, sem):
    """Faz o download de um único arquivo zip, se ainda não existir."""
    if os.path.exists(dest_path):
        return  # Já baixado

    async with sem:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    with open(dest_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(1024 * 64):
                            f.write(chunk)
                else:
                    print(f"Erro {response.status} ao baixar {url}")
        except Exception as e:
            print(f"Falha ao baixar {url}: {e}")

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Buscando lista de arquivos em {BASE_URL}...")
    
    # Faz o scrape da página HTML do diretório
    req = urllib.request.urlopen(BASE_URL)
    html = req.read().decode('utf-8')
    
    # Procura por todos os arquivos que terminam com ZN.zip (Altitude/MDE)
    filenames = re.findall(r'href="([^"]*ZN\.zip)"', html)
    
    # Remove duplicatas, se houver
    filenames = list(set(filenames))
    print(f"Encontrados {len(filenames)} arquivos MDE (Altitude ZN) para o Brasil inteiro.")
    
    if not filenames:
        print("Nenhum arquivo encontrado. Verifique a conexão com o INPE.")
        return

    # Limita o número de downloads paralelos para não sobrecarregar/ser bloqueado pelo INPE
    MAX_CONCURRENT_DOWNLOADS = 8
    sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    
    print(f"Iniciando download para: {OUTPUT_DIR}")
    
    # Prepara as tarefas de download
    tasks = []
    # Definindo um timeout customizado para o client
    timeout = aiohttp.ClientTimeout(total=600)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for filename in filenames:
            file_url = BASE_URL + filename
            dest_path = os.path.join(OUTPUT_DIR, filename)
            tasks.append(download_file(session, file_url, dest_path, sem))
            
        # Executa com barra de progresso visual
        await tqdm.gather(*tasks, desc="Baixando MDE Topodata")
        
    print("Download do INPE concluído!")

if __name__ == "__main__":
    asyncio.run(main())
