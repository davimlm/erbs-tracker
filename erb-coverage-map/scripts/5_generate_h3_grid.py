import json
import glob
import os
import math
import h3

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0 # km
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    a = math.sin(dLat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dLon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c * 1000 # returns meters

def process_city(file_path):
    cidade_id = os.path.basename(file_path).replace('populacao_real_', '').replace('.json', '')
    print(f"Processando malha H3 para {cidade_id}...")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        pontos = json.load(f)
        
    h3_grid = {}
    
    # Parâmetros de Decaimento
    LAMBDA = 0.01 # Cai rápido após ~200m
    K_RING_SIZE = 2 # Raio de 2 hexágonos (~350m)
    
    for p in pontos:
        lat = p.get('lat')
        lng = p.get('lng')
        pop = p.get('populacao', 0)
        
        if pop <= 0:
            continue
            
        center_cell = h3.latlng_to_cell(lat, lng, 9)
        # Obter os vizinhos até K_RING_SIZE de distância
        neighbors = h3.grid_disk(center_cell, K_RING_SIZE)
        
        weights = {}
        total_weight = 0
        
        for cell in neighbors:
            cell_lat, cell_lng = h3.cell_to_latlng(cell)
            d = haversine(lat, lng, cell_lat, cell_lng)
            
            # Função de Decaimento Contínuo: e^(-lambda * d)
            w = math.exp(-LAMBDA * d)
            weights[cell] = w
            total_weight += w
            
        # Distribuir a população
        for cell, w in weights.items():
            norm_w = w / total_weight
            distributed_pop = pop * norm_w
            
            if cell not in h3_grid:
                h3_grid[cell] = 0
            h3_grid[cell] += distributed_pop
            
    # Salvar grid da cidade
    output_path = os.path.join(os.path.dirname(file_path), f'h3_grid_{cidade_id}.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(h3_grid, f)
        
    print(f"[{cidade_id}] Grid H3 gerado com {len(h3_grid)} hexágonos únicos.")

def main():
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    pop_files = glob.glob(os.path.join(data_dir, 'populacao_real_*.json'))
    
    for pf in pop_files:
        process_city(pf)

if __name__ == '__main__':
    main()
