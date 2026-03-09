"""
Importador de CSV exportado do Corp (Clientes e Documentos).
Lê o CSV, parseia e insere no PostgreSQL.
Roda quando o Fafá mandar o arquivo.
"""

import csv
import psycopg2
import json
import os
import sys
from datetime import datetime

DB_CONFIG = {
    'host': 'localhost',
    'database': 'sierra_db',
    'user': 'sierra',
    'password': 'SierraDB2026!!'
}

def detect_delimiter(filepath):
    """Detecta o delimitador do CSV (;, , ou tab)."""
    with open(filepath, 'r', encoding='latin-1') as f:
        first_line = f.readline()
    
    for delim in [';', ',', '\t', '|']:
        if delim in first_line:
            count = first_line.count(delim)
            if count >= 3:
                return delim
    return ';'  # padrão brasileiro

def parse_date(date_str):
    """Parseia data em formato BR (dd/mm/yyyy) ou ISO."""
    if not date_str or date_str.strip() == '':
        return None
    date_str = date_str.strip()
    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y']:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None

def parse_decimal(val):
    """Parseia valor decimal BR (ponto milhar, vírgula decimal)."""
    if not val or val.strip() == '':
        return None
    val = val.strip().replace('R$', '').replace(' ', '')
    # Formato BR: 1.234,56
    if ',' in val:
        val = val.replace('.', '').replace(',', '.')
    try:
        return float(val)
    except:
        return None

def import_clientes_csv(filepath):
    """Importa CSV de Clientes e Documentos do Corp."""
    delim = detect_delimiter(filepath)
    print(f"Delimitador detectado: '{delim}'")
    
    # Lê CSV
    with open(filepath, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f, delimiter=delim)
        rows = list(reader)
    
    print(f"Total de linhas: {len(rows)}")
    if rows:
        print(f"Colunas: {list(rows[0].keys())}")
        print(f"Primeira linha: {dict(list(rows[0].items())[:5])}")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Cria tabela de staging pra dados brutos do Corp
    cur.execute("""
        CREATE TABLE IF NOT EXISTS corp_export_raw (
            id SERIAL PRIMARY KEY,
            corretora_id INTEGER DEFAULT 1,
            dados JSONB NOT NULL,
            tipo VARCHAR(50) DEFAULT 'clientes_docs',
            imported_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Cria tabela específica se conseguir mapear colunas
    cur.execute("""
        CREATE TABLE IF NOT EXISTS corp_clientes_docs (
            id SERIAL PRIMARY KEY,
            corretora_id INTEGER DEFAULT 1,
            filial VARCHAR(20),
            nosso_numero VARCHAR(50),
            cliente VARCHAR(200),
            cpf_cnpj VARCHAR(20),
            seguradora VARCHAR(100),
            ramo VARCHAR(100),
            apolice VARCHAR(50),
            inicio_vigencia DATE,
            fim_vigencia DATE,
            premio DECIMAL(12,2),
            comissao DECIMAL(12,2),
            produtor VARCHAR(200),
            status VARCHAR(50),
            dados_extras JSONB,
            imported_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # Insere dados brutos
    raw_count = 0
    for row in rows:
        cur.execute(
            "INSERT INTO corp_export_raw (dados, tipo) VALUES (%s, %s)",
            (json.dumps(dict(row), ensure_ascii=False), 'clientes_docs')
        )
        raw_count += 1
    
    # Tenta mapear pra tabela estruturada
    # Nomes possíveis de colunas (Corp pode usar diferentes labels)
    col_map = {
        'filial': ['Filial', 'FILIAL', 'filial'],
        'nosso_numero': ['Nosso Nº', 'Nosso No', 'NOSSO_NUMERO', 'NossoNumero', 'Nosso N'],
        'cliente': ['Cliente', 'CLIENTE', 'Nome Cliente', 'NOME_CLIENTE', 'Nome'],
        'cpf_cnpj': ['CPF/CNPJ', 'CPF', 'CNPJ', 'CPF_CNPJ', 'Documento'],
        'seguradora': ['Seg', 'Seguradora', 'SEGURADORA', 'Cia'],
        'ramo': ['Ramo', 'RAMO'],
        'apolice': ['Apólice', 'Apolice', 'APOLICE', 'Nr Apolice'],
        'inicio_vigencia': ['Início Vig.', 'Inicio Vig', 'INICIO_VIGENCIA', 'Dt Início'],
        'fim_vigencia': ['Final Vig.', 'Fim Vig', 'FIM_VIGENCIA', 'Dt Final'],
        'premio': ['Prêmio', 'Premio', 'PREMIO', 'Valor Prêmio'],
        'comissao': ['Comissão', 'Comissao', 'COMISSAO'],
        'produtor': ['Produtor', 'PRODUTOR'],
        'status': ['Status', 'STATUS', 'Situação', 'Situacao'],
    }
    
    def find_col(row, names):
        for name in names:
            if name in row:
                return row[name]
        return None
    
    struct_count = 0
    if rows:
        for row in rows:
            filial = find_col(row, col_map['filial'])
            nosso_num = find_col(row, col_map['nosso_numero'])
            cliente = find_col(row, col_map['cliente'])
            cpf = find_col(row, col_map['cpf_cnpj'])
            seg = find_col(row, col_map['seguradora'])
            ramo = find_col(row, col_map['ramo'])
            apolice = find_col(row, col_map['apolice'])
            inicio = parse_date(find_col(row, col_map['inicio_vigencia']) or '')
            fim = parse_date(find_col(row, col_map['fim_vigencia']) or '')
            premio = parse_decimal(find_col(row, col_map['premio']) or '')
            comissao = parse_decimal(find_col(row, col_map['comissao']) or '')
            produtor = find_col(row, col_map['produtor'])
            status = find_col(row, col_map['status'])
            
            # Dados extras: tudo que não foi mapeado
            mapped_keys = set()
            for names in col_map.values():
                for n in names:
                    mapped_keys.add(n)
            extras = {k: v for k, v in row.items() if k not in mapped_keys and v}
            
            cur.execute("""
                INSERT INTO corp_clientes_docs (
                    filial, nosso_numero, cliente, cpf_cnpj, seguradora, ramo,
                    apolice, inicio_vigencia, fim_vigencia, premio, comissao,
                    produtor, status, dados_extras
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                filial, nosso_num, cliente, cpf, seg, ramo, apolice,
                inicio, fim, premio, comissao, produtor, status,
                json.dumps(extras, ensure_ascii=False) if extras else None
            ))
            struct_count += 1
    
    conn.commit()
    
    print(f"\n✅ Importação concluída!")
    print(f"   Registros brutos (JSON): {raw_count}")
    print(f"   Registros estruturados: {struct_count}")
    
    # Mostra resumo
    cur.execute("SELECT COUNT(*) FROM corp_clientes_docs")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT cliente) FROM corp_clientes_docs WHERE cliente IS NOT NULL")
    clientes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT seguradora) FROM corp_clientes_docs WHERE seguradora IS NOT NULL")
    segs = cur.fetchone()[0]
    
    print(f"\n📊 Resumo no banco:")
    print(f"   Total registros: {total}")
    print(f"   Clientes únicos: {clientes}")
    print(f"   Seguradoras: {segs}")
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python import_csv_corp.py <arquivo.csv>")
        print("Aguardando arquivo do Fafá...")
    else:
        import_clientes_csv(sys.argv[1])
