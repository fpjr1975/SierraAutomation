-- ============================================
-- Views e Índices para o Gastón
-- Sierra Seguros — PostgreSQL
-- ============================================

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_corp_cd_cliente ON corp_clientes_docs(cliente);
CREATE INDEX IF NOT EXISTS idx_corp_cd_seguradora ON corp_clientes_docs(seguradora);
CREATE INDEX IF NOT EXISTS idx_corp_cd_ramo ON corp_clientes_docs(ramo);
CREATE INDEX IF NOT EXISTS idx_corp_cd_vigencia ON corp_clientes_docs(inicio_vigencia, fim_vigencia);
CREATE INDEX IF NOT EXISTS idx_corp_cd_status ON corp_clientes_docs(status);
CREATE INDEX IF NOT EXISTS idx_corp_cd_apolice ON corp_clientes_docs(apolice);
CREATE INDEX IF NOT EXISTS idx_corp_cd_cpf ON corp_clientes_docs(cpf_cnpj);
CREATE INDEX IF NOT EXISTS idx_corp_rel_periodo ON corp_relatorios(ano, mes, aba);

-- ============================================
-- VIEW: Carteira ativa (apólices vigentes hoje)
-- ============================================
CREATE OR REPLACE VIEW v_carteira_ativa AS
SELECT 
    cliente, cpf_cnpj, seguradora, ramo, apolice,
    inicio_vigencia, fim_vigencia, premio, comissao, produtor, status,
    fim_vigencia - CURRENT_DATE AS dias_restantes
FROM corp_clientes_docs
WHERE fim_vigencia >= CURRENT_DATE
  AND (status IS NULL OR status NOT IN ('Cancelado', 'CANCELADO', 'Devolvido'))
ORDER BY fim_vigencia;

-- ============================================
-- VIEW: Renovações pendentes (vencendo em 30/60/90 dias)
-- ============================================
CREATE OR REPLACE VIEW v_renovacoes_pendentes AS
SELECT 
    cliente, cpf_cnpj, seguradora, ramo, apolice,
    inicio_vigencia, fim_vigencia, premio, comissao, produtor,
    fim_vigencia - CURRENT_DATE AS dias_para_vencer,
    CASE 
        WHEN fim_vigencia - CURRENT_DATE <= 30 THEN '🔴 URGENTE (30 dias)'
        WHEN fim_vigencia - CURRENT_DATE <= 60 THEN '🟡 ATENÇÃO (60 dias)'
        WHEN fim_vigencia - CURRENT_DATE <= 90 THEN '🟢 PLANEJAMENTO (90 dias)'
    END AS prioridade
FROM corp_clientes_docs
WHERE fim_vigencia BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '90 days'
  AND (status IS NULL OR status NOT IN ('Cancelado', 'CANCELADO', 'Devolvido'))
ORDER BY fim_vigencia;

-- ============================================
-- VIEW: Produção mensal por seguradora
-- ============================================
CREATE OR REPLACE VIEW v_producao_seguradora AS
SELECT 
    seguradora,
    COUNT(*) AS total_docs,
    COUNT(*) FILTER (WHERE fim_vigencia >= CURRENT_DATE) AS docs_vigentes,
    SUM(premio) AS premio_total,
    SUM(comissao) AS comissao_total,
    ROUND(AVG(premio), 2) AS ticket_medio,
    ROUND(SUM(comissao) * 100.0 / NULLIF(SUM(premio), 0), 1) AS perc_comissao
FROM corp_clientes_docs
WHERE seguradora IS NOT NULL
GROUP BY seguradora
ORDER BY premio_total DESC NULLS LAST;

-- ============================================
-- VIEW: Produção por ramo
-- ============================================
CREATE OR REPLACE VIEW v_producao_ramo AS
SELECT 
    ramo,
    COUNT(*) AS total_docs,
    COUNT(*) FILTER (WHERE fim_vigencia >= CURRENT_DATE) AS docs_vigentes,
    SUM(premio) AS premio_total,
    SUM(comissao) AS comissao_total,
    ROUND(AVG(premio), 2) AS ticket_medio,
    ROUND(COUNT(*)::numeric * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 1) AS perc_carteira
FROM corp_clientes_docs
WHERE ramo IS NOT NULL
GROUP BY ramo
ORDER BY total_docs DESC;

-- ============================================
-- VIEW: Ranking de clientes (top por prêmio)
-- ============================================
CREATE OR REPLACE VIEW v_ranking_clientes AS
SELECT 
    cliente, cpf_cnpj,
    COUNT(*) AS total_apolices,
    COUNT(*) FILTER (WHERE fim_vigencia >= CURRENT_DATE) AS apolices_ativas,
    SUM(premio) AS premio_total,
    SUM(comissao) AS comissao_total,
    MIN(inicio_vigencia) AS cliente_desde,
    ARRAY_AGG(DISTINCT ramo) AS ramos,
    ARRAY_AGG(DISTINCT seguradora) AS seguradoras
FROM corp_clientes_docs
WHERE cliente IS NOT NULL
GROUP BY cliente, cpf_cnpj
ORDER BY premio_total DESC NULLS LAST;

-- ============================================
-- VIEW: Produção mensal (série temporal)
-- ============================================
CREATE OR REPLACE VIEW v_producao_mensal AS
SELECT 
    DATE_TRUNC('month', inicio_vigencia)::date AS mes,
    COUNT(*) AS novos_docs,
    SUM(premio) AS premio_novos,
    SUM(comissao) AS comissao_novos
FROM corp_clientes_docs
WHERE inicio_vigencia IS NOT NULL
GROUP BY DATE_TRUNC('month', inicio_vigencia)
ORDER BY mes DESC;

-- ============================================
-- VIEW: Resumo geral (dashboard)
-- ============================================
CREATE OR REPLACE VIEW v_resumo_geral AS
SELECT
    (SELECT COUNT(*) FROM corp_clientes_docs) AS total_registros,
    (SELECT COUNT(DISTINCT cliente) FROM corp_clientes_docs WHERE cliente IS NOT NULL) AS total_clientes,
    (SELECT COUNT(*) FROM corp_clientes_docs WHERE fim_vigencia >= CURRENT_DATE) AS apolices_vigentes,
    (SELECT COUNT(*) FROM corp_clientes_docs WHERE fim_vigencia BETWEEN CURRENT_DATE AND CURRENT_DATE + 30) AS vencem_30_dias,
    (SELECT COUNT(*) FROM corp_clientes_docs WHERE fim_vigencia BETWEEN CURRENT_DATE AND CURRENT_DATE + 60) AS vencem_60_dias,
    (SELECT COUNT(*) FROM corp_clientes_docs WHERE fim_vigencia BETWEEN CURRENT_DATE AND CURRENT_DATE + 90) AS vencem_90_dias,
    (SELECT SUM(premio) FROM corp_clientes_docs WHERE fim_vigencia >= CURRENT_DATE) AS premio_carteira_ativa,
    (SELECT SUM(comissao) FROM corp_clientes_docs WHERE fim_vigencia >= CURRENT_DATE) AS comissao_carteira_ativa,
    (SELECT COUNT(DISTINCT seguradora) FROM corp_clientes_docs) AS total_seguradoras,
    (SELECT COUNT(DISTINCT ramo) FROM corp_clientes_docs) AS total_ramos;

-- ============================================
-- Dados do Gerenciador de Relatórios (já importados)
-- ============================================
CREATE OR REPLACE VIEW v_historico_producao AS
SELECT 
    periodo, mes, ano, aba,
    producao_total, producao_variacao,
    novos, renovacoes, faturas, endossos,
    seguradoras, ramos
FROM corp_relatorios
ORDER BY ano, mes, aba;
