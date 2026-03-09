"""
Importa dados extraídos do Gerenciador de Relatórios do Corp pro PostgreSQL.
Cria tabela corp_relatorios e insere os dados limpos.
"""

import json
import psycopg2
import re

DB_CONFIG = {
    'host': 'localhost',
    'database': 'sierra_db',
    'user': 'sierra',
    'password': 'SierraDB2026!!'
}

def clean_value(val):
    """Converte valor string/float pra float limpo."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Remove R$, espaços, pontos de milhar
        val = val.replace('R$', '').replace(' ', '').strip()
        # Se tem formato brasileiro (ponto = milhar, vírgula = decimal)
        if ',' in val:
            val = val.replace('.', '').replace(',', '.')
        try:
            return float(val)
        except:
            return None
    return None

def main():
    # Lê dados extraídos
    with open('/root/sierra/corp_data/dados_extraidos.json', 'r') as f:
        data = json.load(f)
    
    print(f"Total registros: {len(data)}")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Cria tabela
    cur.execute("""
        CREATE TABLE IF NOT EXISTS corp_relatorios (
            id SERIAL PRIMARY KEY,
            corretora_id INTEGER DEFAULT 1,
            periodo VARCHAR(50),
            mes INTEGER,
            ano INTEGER,
            aba VARCHAR(50),
            producao_total DECIMAL(12,2),
            producao_variacao VARCHAR(20),
            novos DECIMAL(12,2),
            novos_variacao VARCHAR(20),
            renovacoes DECIMAL(12,2),
            renovacoes_variacao VARCHAR(20),
            faturas DECIMAL(12,2),
            endossos DECIMAL(12,2),
            meta_atingida VARCHAR(20),
            seguradoras JSONB,
            ramos JSONB,
            demonstrativo_12m JSONB,
            source_file VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Limpa dados antigos
    cur.execute("DELETE FROM corp_relatorios;")
    
    # Mapeamento de mês
    meses = {
        'JANEIRO': 1, 'FEVEREIRO': 2, 'MARÇO': 3, 'ABRIL': 4,
        'MAIO': 5, 'JUNHO': 6, 'JULHO': 7, 'AGOSTO': 8,
        'SETEMBRO': 9, 'OUTUBRO': 10, 'NOVEMBRO': 11, 'DEZEMBRO': 12
    }
    
    inserted = 0
    skipped = 0
    seen = set()
    
    for record in data:
        if '_error' in record and 'producao_total' not in record:
            skipped += 1
            continue
        
        periodo = record.get('periodo', '')
        aba = record.get('aba', '')
        source = record.get('_source_file', '')
        
        # Extrai mês e ano do período
        mes = None
        ano = None
        for nome_mes, num in meses.items():
            if nome_mes in periodo.upper():
                mes = num
                break
        
        ano_match = re.search(r'(\d{4})', periodo)
        if ano_match:
            ano = int(ano_match.group(1))
        
        # Dedup: periodo + aba
        key = f"{periodo}|{aba}"
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        
        producao = clean_value(record.get('producao_total'))
        novos = clean_value(record.get('novos'))
        renovacoes = clean_value(record.get('renovacoes'))
        faturas = clean_value(record.get('faturas'))
        endossos = clean_value(record.get('endossos'))
        
        # Validação: se producao_total é muito baixo (< 100), pode ser erro de OCR
        # Set/2024 teve 326.33 vs 326330.24 — ignorar valores < 1000 pra Prêmio Base
        if aba == 'Prêmio Base' and producao and producao < 1000:
            skipped += 1
            continue
        
        seguradoras = record.get('seguradoras')
        ramos = record.get('ramos')
        demo = record.get('demonstrativo_12m')
        
        cur.execute("""
            INSERT INTO corp_relatorios (
                periodo, mes, ano, aba, producao_total, producao_variacao,
                novos, novos_variacao, renovacoes, renovacoes_variacao,
                faturas, endossos, meta_atingida, seguradoras, ramos,
                demonstrativo_12m, source_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            periodo, mes, ano, aba, producao,
            record.get('producao_variacao'),
            novos, record.get('novos_variacao'),
            renovacoes, record.get('renovacoes_variacao'),
            faturas, endossos,
            record.get('meta_atingida'),
            json.dumps(seguradoras) if seguradoras else None,
            json.dumps(ramos) if ramos else None,
            json.dumps(demo) if demo else None,
            source
        ))
        inserted += 1
    
    conn.commit()
    
    # Relatório
    print(f"\n✅ Importação concluída!")
    print(f"   Inseridos: {inserted}")
    print(f"   Pulados (duplicados/erros): {skipped}")
    
    # Mostra dados importados
    cur.execute("""
        SELECT periodo, aba, producao_total, novos, renovacoes, endossos
        FROM corp_relatorios
        ORDER BY ano, mes, aba
    """)
    rows = cur.fetchall()
    
    print(f"\n📊 Dados no banco ({len(rows)} registros):")
    print(f"{'Período':<25} {'Aba':<15} {'Produção':>15} {'Novos':>15} {'Renovações':>15} {'Endossos':>12}")
    print("-" * 100)
    for row in rows:
        periodo, aba, prod, novos, renov, endos = row
        prod_str = f"R$ {prod:,.2f}" if prod else "-"
        novos_str = f"R$ {novos:,.2f}" if novos else "-"
        renov_str = f"R$ {renov:,.2f}" if renov else "-"
        endos_str = f"R$ {endos:,.2f}" if endos else "-"
        print(f"{periodo:<25} {aba:<15} {prod_str:>15} {novos_str:>15} {renov_str:>15} {endos_str:>12}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
