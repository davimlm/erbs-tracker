import os
import requests
import zipfile

url = "https://www.telecocare.com.br/mapaerbs/ERBs_Mar26.zip"
zip_path = "ERBs_Mar26.zip"
data_dir = "data"

print("Fazendo o download...")
response = requests.get(url)
with open(zip_path, 'wb') as f:
    f.write(response.content)

print("Extraindo...")
os.makedirs(data_dir, exist_ok=True)
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(data_dir)

print("Download e extração completos!")
