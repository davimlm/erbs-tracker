import urllib.request
import re
try:
    url = 'https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/gpkg/'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    matches = re.findall(r'href=[\'\"]?([^\'\" >]+)', html)
    for m in matches:
        if 'SP' in m:
            print(m)
except Exception as e:
    print('Error:', e)
