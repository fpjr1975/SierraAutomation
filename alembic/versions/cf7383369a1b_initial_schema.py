"""initial_schema

Revision ID: cf7383369a1b
Revises: 
Create Date: 2026-03-09

Schema inicial do Sierra SaaS — captura o estado atual do banco.
Tabelas: agent_messages, agent_sessions, apolices, audit_log,
         clientes, comissoes, corp_clientes_docs, corp_export_raw,
         corp_relatorios, corretoras, cotacao_resultados, cotacoes,
         documentos, login_attempts, parcelas, usuarios, veiculos
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cf7383369a1b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Schema inicial já existente no banco.
    Esta migration serve como baseline — aplicada via 'alembic stamp head'.
    
    Se executada em banco vazio, cria toda a estrutura.
    """
    # Corretoras
    op.create_table('corretoras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(200), nullable=False),
        sa.Column('cnpj', sa.String(20), nullable=True),
        sa.Column('telefone', sa.String(30), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cnpj'),
    )

    # Usuarios
    op.create_table('usuarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('corretora_id', sa.Integer(), nullable=True),
        sa.Column('nome', sa.String(200), nullable=False),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('senha_hash', sa.Text(), nullable=True),
        sa.Column('role', sa.String(20), server_default='corretor', nullable=True),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True),
        sa.Column('active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['corretora_id'], ['corretoras.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('telegram_id'),
    )

    # Clientes
    op.create_table('clientes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('corretora_id', sa.Integer(), nullable=True),
        sa.Column('nome', sa.String(200), nullable=False),
        sa.Column('cpf_cnpj', sa.String(20), nullable=True),
        sa.Column('nascimento', sa.Date(), nullable=True),
        sa.Column('telefone', sa.String(30), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('cep', sa.String(10), nullable=True),
        sa.Column('endereco', sa.Text(), nullable=True),
        sa.Column('cidade', sa.String(100), nullable=True),
        sa.Column('uf', sa.String(2), nullable=True),
        sa.Column('status', sa.String(10), server_default='ativo', nullable=True),
        sa.Column('drive_pasta', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['corretora_id'], ['corretoras.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('corretora_id', 'cpf_cnpj', name='clientes_corretora_id_cpf_cnpj_key'),
    )

    # Veiculos
    op.create_table('veiculos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('placa', sa.String(10), nullable=True),
        sa.Column('chassi', sa.String(30), nullable=True),
        sa.Column('marca_modelo', sa.String(200), nullable=True),
        sa.Column('ano_fabricacao', sa.String(4), nullable=True),
        sa.Column('ano_modelo', sa.String(4), nullable=True),
        sa.Column('cor', sa.String(30), nullable=True),
        sa.Column('combustivel', sa.String(30), nullable=True),
        sa.Column('cep_pernoite', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Documentos
    op.create_table('documentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(50), nullable=True),
        sa.Column('arquivo_path', sa.Text(), nullable=True),
        sa.Column('dados_extraidos', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Cotacoes
    op.create_table('cotacoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('corretora_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('veiculo_id', sa.Integer(), nullable=True),
        sa.Column('tipo', sa.String(50), nullable=True),
        sa.Column('cnh_data', sa.JSON(), nullable=True),
        sa.Column('crvl_data', sa.JSON(), nullable=True),
        sa.Column('condutor_data', sa.JSON(), nullable=True),
        sa.Column('cep_pernoite', sa.String(10), nullable=True),
        sa.Column('status', sa.String(20), server_default='calculada', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.ForeignKeyConstraint(['corretora_id'], ['corretoras.id'], ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['veiculo_id'], ['veiculos.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Cotacao resultados
    op.create_table('cotacao_resultados',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cotacao_id', sa.Integer(), nullable=True),
        sa.Column('seguradora', sa.String(100), nullable=True),
        sa.Column('premio', sa.Numeric(12, 2), nullable=True),
        sa.Column('franquia', sa.Numeric(12, 2), nullable=True),
        sa.Column('parcelas', sa.String(100), nullable=True),
        sa.Column('numero_cotacao', sa.String(50), nullable=True),
        sa.Column('mensagem', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('pdf_path', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['cotacao_id'], ['cotacoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Apolices
    op.create_table('apolices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('corretora_id', sa.Integer(), nullable=True),
        sa.Column('cliente_id', sa.Integer(), nullable=True),
        sa.Column('veiculo_id', sa.Integer(), nullable=True),
        sa.Column('cotacao_id', sa.Integer(), nullable=True),
        sa.Column('seguradora', sa.String(100), nullable=True),
        sa.Column('numero_apolice', sa.String(50), nullable=True),
        sa.Column('vigencia_inicio', sa.Date(), nullable=True),
        sa.Column('vigencia_fim', sa.Date(), nullable=True),
        sa.Column('premio', sa.Numeric(12, 2), nullable=True),
        sa.Column('franquia', sa.Numeric(12, 2), nullable=True),
        sa.Column('comissao_percentual', sa.Numeric(5, 2), nullable=True),
        sa.Column('comissao_valor', sa.Numeric(12, 2), nullable=True),
        sa.Column('status', sa.String(20), server_default='vigente', nullable=True),
        sa.Column('ramo', sa.String(20), nullable=True),
        sa.Column('nosso_numero', sa.String(30), nullable=True),
        sa.Column('emissao', sa.Date(), nullable=True),
        sa.Column('proposta', sa.String(50), nullable=True),
        sa.Column('produtor', sa.String(100), nullable=True),
        sa.Column('renovacao_status', sa.String(20), server_default='pendente', nullable=True),
        sa.Column('renovacao_obs', sa.Text(), nullable=True),
        sa.Column('renovacao_updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['cliente_id'], ['clientes.id'], ),
        sa.ForeignKeyConstraint(['corretora_id'], ['corretoras.id'], ),
        sa.ForeignKeyConstraint(['cotacao_id'], ['cotacoes.id'], ),
        sa.ForeignKeyConstraint(['veiculo_id'], ['veiculos.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Comissoes
    op.create_table('comissoes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('corretora_id', sa.Integer(), nullable=True),
        sa.Column('apolice_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('seguradora', sa.String(100), nullable=True),
        sa.Column('valor', sa.Numeric(12, 2), nullable=True),
        sa.Column('percentual', sa.Numeric(5, 2), nullable=True),
        sa.Column('parcela', sa.Integer(), nullable=True),
        sa.Column('total_parcelas', sa.Integer(), nullable=True),
        sa.Column('data_pagamento', sa.Date(), nullable=True),
        sa.Column('status', sa.String(20), server_default='pendente', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['apolice_id'], ['apolices.id'], ),
        sa.ForeignKeyConstraint(['corretora_id'], ['corretoras.id'], ),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Agent sessions
    op.create_table('agent_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('estado', sa.String(50), server_default='ativo', nullable=True),
        sa.Column('contexto', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('intent', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # Agent messages
    op.create_table('agent_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Audit log
    op.create_table('audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_nome', sa.String(100), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Login attempts
    op.create_table('login_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Remove todas as tabelas (usar com cuidado!)."""
    op.drop_table('login_attempts')
    op.drop_table('audit_log')
    op.drop_table('agent_messages')
    op.drop_table('agent_sessions')
    op.drop_table('comissoes')
    op.drop_table('apolices')
    op.drop_table('cotacao_resultados')
    op.drop_table('cotacoes')
    op.drop_table('documentos')
    op.drop_table('veiculos')
    op.drop_table('clientes')
    op.drop_table('usuarios')
    op.drop_table('corretoras')
