-- 1. Adicionar colunas físicas diretamente na tabela do IBGE (Polígonos verdes)
ALTER TABLE ibge_vegetacao_raw ADD COLUMN IF NOT EXISTS perda_700_dbm NUMERIC(5,3);
ALTER TABLE ibge_vegetacao_raw ADD COLUMN IF NOT EXISTS perda_3500_dbm NUMERIC(5,3);

-- 2. "A Query Mágica" (O Relacionamento e Preenchimento)
-- Encontra as perdas na matriz para cada legenda
UPDATE ibge_vegetacao_raw v
SET 
    perda_700_dbm = m.perda_700,
    perda_3500_dbm = m.perda_3500
FROM (
    SELECT DISTINCT ON (v_in.legenda)
        v_in.legenda,
        COALESCE(mat.perda_700_dbm, 0.00) AS perda_700,
        COALESCE(mat.perda_3500_dbm, 0.00) AS perda_3500
    FROM ibge_vegetacao_raw v_in
    LEFT JOIN rf_matriz_vegetacao mat
      ON v_in.legenda ILIKE mat.nome_ibge_like
    ORDER BY v_in.legenda, mat.ordem_prioridade ASC
) m
WHERE v.legenda = m.legenda;

-- 3. Índices para ajudar no cálculo de alcance depois
CREATE INDEX IF NOT EXISTS idx_ibge_veg_perda_700 ON ibge_vegetacao_raw(perda_700_dbm);
CREATE INDEX IF NOT EXISTS idx_ibge_veg_perda_3500 ON ibge_vegetacao_raw(perda_3500_dbm);
