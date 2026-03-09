"""add_rls_multitenancy

Revision ID: be65170d7027
Revises: cf7383369a1b
Create Date: 2026-03-09

Fase 1.2 — Multi-tenancy com Row Level Security (RLS):
- Adiciona corretora_id a: veiculos, documentos, cotacao_resultados, agent_sessions
- Popula corretora_id de tabelas relacionadas
- Ativa RLS nas tabelas principais
- Cria policies para filtrar por corretora_id via current_setting()
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'be65170d7027'
down_revision = 'cf7383369a1b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Adicionar corretora_id onde falta ──────────────────────────────

    # veiculos: deriva de clientes.corretora_id via cliente_id
    op.add_column('veiculos', sa.Column('corretora_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE veiculos v
        SET corretora_id = c.corretora_id
        FROM clientes c
        WHERE v.cliente_id = c.id
          AND v.corretora_id IS NULL
    """)
    op.create_index('idx_veiculos_corretora', 'veiculos', ['corretora_id'])
    op.create_foreign_key(
        'veiculos_corretora_id_fkey', 'veiculos',
        'corretoras', ['corretora_id'], ['id']
    )

    # documentos: deriva de clientes.corretora_id via cliente_id
    op.add_column('documentos', sa.Column('corretora_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE documentos d
        SET corretora_id = c.corretora_id
        FROM clientes c
        WHERE d.cliente_id = c.id
          AND d.corretora_id IS NULL
    """)
    op.create_index('idx_documentos_corretora', 'documentos', ['corretora_id'])
    op.create_foreign_key(
        'documentos_corretora_id_fkey', 'documentos',
        'corretoras', ['corretora_id'], ['id']
    )

    # cotacao_resultados: deriva de cotacoes.corretora_id via cotacao_id
    op.add_column('cotacao_resultados', sa.Column('corretora_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE cotacao_resultados cr
        SET corretora_id = cot.corretora_id
        FROM cotacoes cot
        WHERE cr.cotacao_id = cot.id
          AND cr.corretora_id IS NULL
    """)
    op.create_index('idx_cotacao_resultados_corretora', 'cotacao_resultados', ['corretora_id'])
    op.create_foreign_key(
        'cotacao_resultados_corretora_id_fkey', 'cotacao_resultados',
        'corretoras', ['corretora_id'], ['id']
    )

    # agent_sessions: adiciona corretora_id (vinculado via chat_id → usuarios.telegram_id)
    op.add_column('agent_sessions', sa.Column('corretora_id', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE agent_sessions ags
        SET corretora_id = u.corretora_id
        FROM usuarios u
        WHERE ags.chat_id = u.telegram_id
          AND ags.corretora_id IS NULL
    """)
    op.create_index('idx_agent_sessions_corretora', 'agent_sessions', ['corretora_id'])

    # ── 2. Ativar RLS nas tabelas com dados por corretora ─────────────────

    tables_with_rls = [
        'clientes',
        'apolices',
        'cotacoes',
        'cotacao_resultados',
        'veiculos',
        'documentos',
        'comissoes',
        'agent_sessions',
    ]

    for table in tables_with_rls:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # NOTA: Não usar FORCE ROW LEVEL SECURITY pois quebra pg_dump
        # O usuário sierra (owner) contorna RLS automaticamente
        # Para produção: criar usuário sierra_app (não-owner) para queries da aplicação

    # ── 3. Criar policies de acesso por corretora ─────────────────────────

    # Policy: sierra app user pode ver/modificar todos (bypass para a app)
    # Corretor autenticado vê apenas sua corretora via current_setting
    # O app define: SET app.corretora_id = <id> antes de queries

    for table in tables_with_rls:
        # Drop policy se já existir (idempotente)
        op.execute(f"DROP POLICY IF EXISTS policy_corretora ON {table}")

    # clientes
    op.execute("""
        CREATE POLICY policy_corretora ON clientes
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # apolices
    op.execute("""
        CREATE POLICY policy_corretora ON apolices
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # cotacoes
    op.execute("""
        CREATE POLICY policy_corretora ON cotacoes
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # cotacao_resultados (via corretora_id adicionado)
    op.execute("""
        CREATE POLICY policy_corretora ON cotacao_resultados
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # veiculos (via corretora_id adicionado)
    op.execute("""
        CREATE POLICY policy_corretora ON veiculos
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # documentos (via corretora_id adicionado)
    op.execute("""
        CREATE POLICY policy_corretora ON documentos
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # comissoes
    op.execute("""
        CREATE POLICY policy_corretora ON comissoes
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)

    # agent_sessions
    op.execute("""
        CREATE POLICY policy_corretora ON agent_sessions
        USING (
            corretora_id = NULLIF(current_setting('app.corretora_id', TRUE), '')::integer
            OR current_user IN ('postgres', 'sierra')
        )
    """)


def downgrade() -> None:
    tables_with_rls = [
        'clientes',
        'apolices',
        'cotacoes',
        'cotacao_resultados',
        'veiculos',
        'documentos',
        'comissoes',
        'agent_sessions',
    ]

    # Remove policies
    for table in tables_with_rls:
        op.execute(f"DROP POLICY IF EXISTS policy_corretora ON {table}")

    # Desativa RLS
    for table in tables_with_rls:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Remove colunas adicionadas
    op.drop_constraint('cotacao_resultados_corretora_id_fkey', 'cotacao_resultados', type_='foreignkey')
    op.drop_index('idx_cotacao_resultados_corretora', table_name='cotacao_resultados')
    op.drop_column('cotacao_resultados', 'corretora_id')

    op.drop_constraint('documentos_corretora_id_fkey', 'documentos', type_='foreignkey')
    op.drop_index('idx_documentos_corretora', table_name='documentos')
    op.drop_column('documentos', 'corretora_id')

    op.drop_constraint('veiculos_corretora_id_fkey', 'veiculos', type_='foreignkey')
    op.drop_index('idx_veiculos_corretora', table_name='veiculos')
    op.drop_column('veiculos', 'corretora_id')

    op.drop_index('idx_agent_sessions_corretora', table_name='agent_sessions')
    op.drop_column('agent_sessions', 'corretora_id')
