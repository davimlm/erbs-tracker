-- 1. Criar a Tabela da Matriz
CREATE TABLE IF NOT EXISTS rf_matriz_vegetacao (
    id_perfil SERIAL PRIMARY KEY,
    nivel_descricao TEXT,
    nome_ibge_like TEXT,
    perda_700_dbm NUMERIC(5,3),
    perda_3500_dbm NUMERIC(5,3),
    ordem_prioridade INTEGER
);

-- Limpar se já existir para rodar idempotente
TRUNCATE TABLE rf_matriz_vegetacao;

-- 2. Inserir Regras Físicas
-- Nível 5: Atenuação Nula (Transparente)
INSERT INTO rf_matriz_vegetacao (nivel_descricao, nome_ibge_like, perda_700_dbm, perda_3500_dbm, ordem_prioridade)
VALUES ('Atenuação Nula', '%Estepe%', 0.00, 0.00, 50),
       ('Atenuação Nula', '%Parque%', 0.00, 0.00, 51),
       ('Atenuação Nula', '%Herb_cea%', 0.00, 0.00, 52),
       ('Atenuação Nula', '%Agricultura%', 0.00, 0.00, 53),
       ('Atenuação Nula', '%Agropecu_ria%', 0.00, 0.00, 54),
       ('Atenuação Nula', '%Pecu_ria%', 0.00, 0.00, 55);

-- Nível 4: Atenuação Média-Baixa (Filtro Vazado)
INSERT INTO rf_matriz_vegetacao (nivel_descricao, nome_ibge_like, perda_700_dbm, perda_3500_dbm, ordem_prioridade)
VALUES ('Atenuação Média-Baixa', '%Savana%', 0.03, 0.35, 40),
       ('Atenuação Média-Baixa', '%Savana-Est_pica%', 0.03, 0.35, 41);

-- Nível 3: Atenuação Média-Alta (Umidade e Galhos)
INSERT INTO rf_matriz_vegetacao (nivel_descricao, nome_ibge_like, perda_700_dbm, perda_3500_dbm, ordem_prioridade)
VALUES ('Atenuação Média-Alta', '%Campinarana%', 0.08, 0.80, 30),
       ('Atenuação Média-Alta', '%Contato%', 0.08, 0.80, 31),
       ('Atenuação Média-Alta', '%Pioneira%arb_rea%', 0.08, 0.80, 32);

-- Nível 2: Atenuação Alta (Florestas Sazonais)
INSERT INTO rf_matriz_vegetacao (nivel_descricao, nome_ibge_like, perda_700_dbm, perda_3500_dbm, ordem_prioridade)
VALUES ('Atenuação Alta', '%Estacional%', 0.12, 1.20, 20),
       ('Atenuação Alta', '%Mista%', 0.12, 1.20, 21),
       ('Atenuação Alta', '%Sempre Verde%', 0.12, 1.20, 22);

-- Nível 1: Atenuação Extrema (Muro Verde)
INSERT INTO rf_matriz_vegetacao (nivel_descricao, nome_ibge_like, perda_700_dbm, perda_3500_dbm, ordem_prioridade)
VALUES ('Atenuação Extrema', '%Ombr_fila%', 0.18, 1.65, 10);

-- 3. Adicionar Colunas em h3_grid_precalc
ALTER TABLE h3_grid_precalc ADD COLUMN IF NOT EXISTS perda_700_dbm NUMERIC(5,3);
ALTER TABLE h3_grid_precalc ADD COLUMN IF NOT EXISTS perda_3500_dbm NUMERIC(5,3);

-- 4. Criar Índices (Só serão úteis após o povoamento)
CREATE INDEX IF NOT EXISTS idx_h3_perda_700 ON h3_grid_precalc(perda_700_dbm);
CREATE INDEX IF NOT EXISTS idx_h3_perda_3500 ON h3_grid_precalc(perda_3500_dbm);
