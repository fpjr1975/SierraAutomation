"""
agent_tools.py — Ferramentas disponíveis para a Sofia (agente IA da Sierra Seguros)

Cada função aqui é um wrapper das capacidades já existentes no sistema:
  - OCR de CNH/CRLV (via ocr_docs.py)
  - Cálculo de cotação (via agilizador.py)
  - Download de PDF cotação (via agilizador.py)
  - Busca de CEP (via ViaCEP)
  - Consulta de clientes/apólices (via PostgreSQL)
  - Notificação pro corretor (via Telegram)
  - Renovações pendentes e iniciar renovação

Todas as funções são assíncronas pra não bloquear o bot.
"""

import os
import sys
import logging
import asyncio
import httpx
import json
from typing import Optional

_SIERRA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIERRA_ROOT not in sys.path:
    sys.path.insert(0, _SIERRA_ROOT)

logger = logging.getLogger(__name__)

CORRETOR_CHAT_ID = 2104676074

# ─────────────────────────────────────────────────────────────
#  DEFINIÇÕES DAS FERRAMENTAS (formato Claude tool_use)
# ─────────────────────────────────────────────────────────────

TOOLS_DEFINITIONS = [
    {
        "name": "classificar_intencao",
        "description": (
            "Classifica a intenção do cliente com base na mensagem recebida. "
            "Use esta ferramenta SEMPRE ao início de uma conversa ou quando o assunto mudar. "
            "Retorna o cenário identificado e a confiança (0-1)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "intencao": {
                    "type": "string",
                    "enum": [
                        "cotacao_nova",
                        "transferencia",
                        "renovacao",
                        "endosso",
                        "sinistro",
                        "documentos",
                        "duvidas",
                        "assistencia",
                        "status",
                        "indicacao",
                    ],
                    "description": "Cenário identificado na mensagem do cliente"
                },
                "confianca": {
                    "type": "number",
                    "description": "Confiança na classificação, entre 0.0 e 1.0"
                },
                "resumo": {
                    "type": "string",
                    "description": "Resumo em 1 frase do que o cliente quer"
                }
            },
            "required": ["intencao", "confianca", "resumo"]
        }
    },
    {
        "name": "processar_cnh",
        "description": (
            "Processa uma imagem de CNH usando OCR com IA. "
            "Extrai: nome, CPF, data de nascimento, categoria, validade. "
            "Use quando o cliente enviar foto da CNH."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "foto_path": {
                    "type": "string",
                    "description": "Caminho local do arquivo de imagem ou PDF da CNH"
                }
            },
            "required": ["foto_path"]
        }
    },
    {
        "name": "processar_crlv",
        "description": (
            "Processa uma imagem do CRLV usando OCR com IA. "
            "Extrai: placa, marca/modelo, ano, chassi, proprietário. "
            "Use quando o cliente enviar foto do CRLV."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "foto_path": {
                    "type": "string",
                    "description": "Caminho local do arquivo de imagem ou PDF do CRLV"
                }
            },
            "required": ["foto_path"]
        }
    },
    {
        "name": "buscar_cep",
        "description": (
            "Busca informações de endereço a partir de um CEP brasileiro via ViaCEP. "
            "Retorna: logradouro, bairro, cidade, UF."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cep": {
                    "type": "string",
                    "description": "CEP com 8 dígitos (com ou sem hífen)"
                }
            },
            "required": ["cep"]
        }
    },
    {
        "name": "calcular_cotacao",
        "description": (
            "Calcula cotação de seguro auto no Agilizador usando dados da CNH, CRLV e CEP. "
            "IMPORTANTE: só use após confirmar todos os dados com o cliente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_data": {
                    "type": "object",
                    "description": "Dados completos: {cnh: {...}, crvl: {...}, cep: '00000000', endereco: {...}, cnh_condutor: {...}}"
                },
                "chat_id": {
                    "type": "integer",
                    "description": "ID do chat do cliente"
                }
            },
            "required": ["session_data", "chat_id"]
        }
    },
    {
        "name": "gerar_pdf_sierra",
        "description": (
            "Baixa e gera o PDF de cotação de uma seguradora específica no layout Sierra. "
            "Use após calcular_cotacao, quando o cliente escolher uma seguradora."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seguradora": {
                    "type": "string",
                    "description": "Nome da seguradora (ex: 'Porto Seguro', 'Bradesco', 'HDI')"
                },
                "chat_id": {
                    "type": "integer",
                    "description": "ID do chat do cliente"
                },
                "premio_esperado": {
                    "type": "number",
                    "description": "Valor esperado do prêmio (opcional, para validação)"
                }
            },
            "required": ["seguradora", "chat_id"]
        }
    },
    {
        "name": "buscar_cliente",
        "description": (
            "Busca um cliente na base de dados da Sierra pelo CPF ou nome. "
            "Retorna dados do cliente se encontrado: id, nome, telefone, email, apólices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "busca": {
                    "type": "string",
                    "description": "CPF (formato 000.000.000-00 ou apenas números) ou nome do cliente"
                }
            },
            "required": ["busca"]
        }
    },
    {
        "name": "consultar_apolices",
        "description": (
            "Consulta as apólices vigentes de um cliente específico. "
            "Retorna lista de apólices com: seguradora, número, vigência, veículo, prêmio, status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {
                    "type": "integer",
                    "description": "ID do cliente no banco de dados"
                }
            },
            "required": ["cliente_id"]
        }
    },
    {
        "name": "consultar_renovacoes_pendentes",
        "description": (
            "Busca apólices do cliente com vencimento nos próximos 30, 60 ou 90 dias. "
            "Use no fluxo de renovação para identificar quais apólices precisam ser renovadas. "
            "Retorna lista com detalhes das apólices próximas do vencimento."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cliente_id": {
                    "type": "integer",
                    "description": "ID do cliente no banco de dados"
                },
                "dias": {
                    "type": "integer",
                    "enum": [30, 60, 90],
                    "description": "Janela de dias para verificar vencimentos (padrão: 60)"
                }
            },
            "required": ["cliente_id"]
        }
    },
    {
        "name": "iniciar_renovacao",
        "description": (
            "Marca uma apólice para renovação e inicia o processo de cotação com os dados existentes. "
            "Use após consultar_renovacoes_pendentes quando o cliente confirmar que quer renovar. "
            "Retorna confirmação e dados para a nova cotação."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "apolice_id": {
                    "type": "integer",
                    "description": "ID da apólice a ser renovada"
                },
                "cliente_id": {
                    "type": "integer",
                    "description": "ID do cliente"
                }
            },
            "required": ["apolice_id", "cliente_id"]
        }
    },
    {
        "name": "notificar_corretor",
        "description": (
            "Envia uma notificação para o corretor Eduardo via Telegram. "
            "Use quando: confiança < 0.95, cliente pede falar com humano, "
            "situação complexa (sinistro, endosso, reclamação, cancelamento), ou ao concluir cotação."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "resumo": {
                    "type": "string",
                    "description": "Resumo completo do atendimento para o corretor"
                },
                "urgente": {
                    "type": "boolean",
                    "description": "Se True, marca como urgente"
                },
                "tipo": {
                    "type": "string",
                    "enum": ["handoff", "cotacao_completa", "sinistro", "info"],
                    "description": "Tipo da notificação"
                },
                "historico_resumo": {
                    "type": "string",
                    "description": "Resumo do histórico da conversa (preenchido automaticamente em handoffs)"
                }
            },
            "required": ["resumo", "tipo"]
        }
    }
]


# ─────────────────────────────────────────────────────────────
#  IMPLEMENTAÇÕES DAS FERRAMENTAS
# ─────────────────────────────────────────────────────────────

async def processar_cnh(foto_path: str) -> dict:
    try:
        from ocr_docs import extract_document_data
        data = extract_document_data(foto_path)
        if not data:
            return {"erro": "Não foi possível ler a CNH. Peça uma foto mais nítida."}
        if data.get("tipo", "").upper() != "CNH":
            return {"erro": f"Documento identificado como '{data.get('tipo', 'Desconhecido')}', não como CNH."}
        return {"sucesso": True, "dados": data}
    except Exception as e:
        logger.error(f"Erro ao processar CNH: {e}", exc_info=True)
        return {"erro": f"Erro interno ao processar CNH: {str(e)}"}


async def processar_crlv(foto_path: str) -> dict:
    try:
        from ocr_docs import extract_document_data
        data = extract_document_data(foto_path)
        if not data:
            return {"erro": "Não foi possível ler o CRLV. Peça uma foto mais nítida."}
        tipo = data.get("tipo", "").upper()
        if "CRLV" not in tipo and "CRV" not in tipo:
            return {"erro": f"Documento identificado como '{data.get('tipo', 'Desconhecido')}', não como CRLV."}
        return {"sucesso": True, "dados": data}
    except Exception as e:
        logger.error(f"Erro ao processar CRLV: {e}", exc_info=True)
        return {"erro": f"Erro interno ao processar CRLV: {str(e)}"}


async def buscar_cep(cep: str) -> dict:
    import re
    cep_limpo = re.sub(r"\D", "", cep)
    if len(cep_limpo) != 8:
        return {"erro": "CEP inválido. Use 8 dígitos."}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://viacep.com.br/ws/{cep_limpo}/json/")
            data = resp.json()
        if "erro" in data:
            return {"erro": f"CEP {cep_limpo} não encontrado."}
        return {
            "sucesso": True,
            "cep": cep_limpo,
            "logradouro": data.get("logradouro", ""),
            "bairro": data.get("bairro", ""),
            "cidade": data.get("localidade", ""),
            "uf": data.get("uf", ""),
            "dados_completos": data
        }
    except Exception as e:
        logger.error(f"Erro ViaCEP: {e}")
        return {"erro": f"Erro ao consultar CEP: {str(e)}"}


async def calcular_cotacao_tool(session_data: dict, chat_id: int, on_progress=None) -> dict:
    try:
        from agilizador import calcular_cotacao
        resultado = await calcular_cotacao(
            session_data=session_data,
            on_progress=on_progress,
            chat_id=chat_id
        )
        return resultado
    except Exception as e:
        logger.error(f"Erro ao calcular cotação: {e}", exc_info=True)
        return {"sucesso": False, "msg": f"Erro ao calcular: {str(e)}"}


async def gerar_pdf_sierra_tool(seguradora: str, chat_id: int,
                                 premio_esperado: float = None,
                                 resultado_tela: dict = None,
                                 on_progress=None) -> dict:
    try:
        from agilizador import baixar_pdf_cotacao
        resultado = await baixar_pdf_cotacao(
            chat_id=chat_id,
            seguradora=seguradora,
            on_progress=on_progress,
            premio_esperado=premio_esperado,
            resultado_tela=resultado_tela
        )
        return resultado
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {e}", exc_info=True)
        return {"sucesso": False, "msg": f"Erro ao gerar PDF: {str(e)}"}


async def buscar_cliente(busca: str) -> dict:
    import re
    try:
        import asyncpg
        conn = await asyncpg.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        try:
            cpf_limpo = re.sub(r"\D", "", busca)
            if len(cpf_limpo) == 11:
                rows = await conn.fetch(
                    "SELECT id, nome, cpf_cnpj, telefone, email, cidade, uf "
                    "FROM clientes WHERE cpf_cnpj LIKE $1 LIMIT 5",
                    f"%{cpf_limpo}%"
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, nome, cpf_cnpj, telefone, email, cidade, uf "
                    "FROM clientes WHERE unaccent(lower(nome)) LIKE unaccent(lower($1)) LIMIT 5",
                    f"%{busca}%"
                )
            if not rows:
                return {"encontrado": False, "msg": f"Nenhum cliente encontrado para '{busca}'"}
            clientes = [dict(r) for r in rows]
            return {"encontrado": True, "clientes": clientes, "total": len(clientes)}
        finally:
            await conn.close()
    except ImportError:
        return await _buscar_cliente_psycopg2(busca)
    except Exception as e:
        logger.error(f"Erro ao buscar cliente: {e}", exc_info=True)
        return {"encontrado": False, "erro": str(e)}


async def _buscar_cliente_psycopg2(busca: str) -> dict:
    import re
    import psycopg2
    import psycopg2.extras
    try:
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cpf_limpo = re.sub(r"\D", "", busca)
        if len(cpf_limpo) == 11:
            cur.execute(
                "SELECT id, nome, cpf_cnpj, telefone, email, cidade, uf "
                "FROM clientes WHERE cpf_cnpj LIKE %s LIMIT 5",
                (f"%{cpf_limpo}%",)
            )
        else:
            cur.execute(
                "SELECT id, nome, cpf_cnpj, telefone, email, cidade, uf "
                "FROM clientes WHERE lower(nome) LIKE lower(%s) LIMIT 5",
                (f"%{busca}%",)
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return {"encontrado": False, "msg": f"Nenhum cliente encontrado para '{busca}'"}
        return {"encontrado": True, "clientes": [dict(r) for r in rows], "total": len(rows)}
    except Exception as e:
        return {"encontrado": False, "erro": str(e)}


async def consultar_apolices(cliente_id: int) -> dict:
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT 
                a.id, a.seguradora, a.numero_apolice, a.vigencia_inicio, a.vigencia_fim,
                a.premio, a.status, a.ramo,
                v.marca_modelo, v.placa, v.ano_fabricacao
            FROM apolices a
            LEFT JOIN veiculos v ON a.veiculo_id = v.id
            WHERE a.cliente_id = %s
            ORDER BY a.vigencia_fim DESC
            LIMIT 10
        """, (cliente_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {"encontrado": False, "msg": "Nenhuma apólice encontrada para este cliente."}

        apolices = []
        for r in rows:
            ap = dict(r)
            for campo in ["vigencia_inicio", "vigencia_fim"]:
                if ap.get(campo):
                    ap[campo] = ap[campo].strftime("%d/%m/%Y")
            if ap.get("premio"):
                ap["premio_fmt"] = f"R$ {float(ap['premio']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            apolices.append(ap)

        return {"encontrado": True, "apolices": apolices, "total": len(apolices)}
    except Exception as e:
        logger.error(f"Erro ao consultar apólices: {e}", exc_info=True)
        return {"encontrado": False, "erro": str(e)}


async def consultar_renovacoes_pendentes(cliente_id: int, dias: int = 60) -> dict:
    """
    Busca apólices do cliente com vencimento nos próximos N dias (30, 60 ou 90).
    Retorna lista ordenada pelo vencimento mais próximo.
    """
    if dias not in (30, 60, 90):
        dias = 60

    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                a.id,
                a.seguradora,
                a.numero_apolice,
                a.vigencia_inicio,
                a.vigencia_fim,
                a.premio,
                a.status,
                a.renovacao_status,
                a.ramo,
                v.marca_modelo,
                v.placa,
                v.ano_fabricacao,
                (a.vigencia_fim - CURRENT_DATE) AS dias_para_vencer
            FROM apolices a
            LEFT JOIN veiculos v ON a.veiculo_id = v.id
            WHERE a.cliente_id = %s
              AND a.status IN ('vigente', 'ativo')
              AND a.vigencia_fim BETWEEN CURRENT_DATE AND (CURRENT_DATE + INTERVAL '%s days')
            ORDER BY a.vigencia_fim ASC
            LIMIT 10
        """, (cliente_id, dias))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return {
                "encontrado": False,
                "msg": f"Nenhuma apólice com vencimento nos próximos {dias} dias.",
                "cliente_id": cliente_id,
                "janela_dias": dias
            }

        apolices = []
        for r in rows:
            ap = dict(r)
            for campo in ["vigencia_inicio", "vigencia_fim"]:
                if ap.get(campo):
                    ap[campo] = ap[campo].strftime("%d/%m/%Y")
            if ap.get("premio"):
                ap["premio_fmt"] = f"R$ {float(ap['premio']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if ap.get("dias_para_vencer") is not None:
                ap["dias_para_vencer"] = int(ap["dias_para_vencer"].days if hasattr(ap["dias_para_vencer"], "days") else ap["dias_para_vencer"])
            apolices.append(ap)

        return {
            "encontrado": True,
            "apolices": apolices,
            "total": len(apolices),
            "janela_dias": dias
        }
    except Exception as e:
        logger.error(f"Erro ao consultar renovações: {e}", exc_info=True)
        return {"encontrado": False, "erro": str(e)}


async def iniciar_renovacao(apolice_id: int, cliente_id: int) -> dict:
    """
    Marca a apólice para renovação e prepara os dados para nova cotação.
    Busca dados existentes da apólice e do veículo para pré-preencher a cotação.
    """
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Verifica se apólice pertence ao cliente
        cur.execute("""
            SELECT
                a.id, a.seguradora, a.numero_apolice, a.vigencia_fim,
                a.premio, a.ramo, a.renovacao_status,
                v.id AS veiculo_id, v.marca_modelo, v.placa, v.ano_fabricacao,
                v.chassi, v.cep_pernoite,
                c.nome AS cliente_nome, c.cpf_cnpj, c.telefone
            FROM apolices a
            LEFT JOIN veiculos v ON a.veiculo_id = v.id
            LEFT JOIN clientes c ON a.cliente_id = c.id
            WHERE a.id = %s AND a.cliente_id = %s
        """, (apolice_id, cliente_id))
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            return {
                "sucesso": False,
                "msg": f"Apólice {apolice_id} não encontrada para este cliente."
            }

        dados = dict(row)

        # Marca para renovação no DB
        cur.execute("""
            UPDATE apolices
            SET renovacao_status = 'em_andamento',
                renovacao_updated_at = NOW()
            WHERE id = %s
        """, (apolice_id,))
        conn.commit()
        cur.close()
        conn.close()

        # Formata vigência
        vigencia_fim = dados.get("vigencia_fim")
        if vigencia_fim:
            dados["vigencia_fim"] = vigencia_fim.strftime("%d/%m/%Y")

        # Monta dados pré-preenchidos para cotação
        dados_cotacao = {
            "placa": dados.get("placa", ""),
            "marca_modelo": dados.get("marca_modelo", ""),
            "ano_fabricacao": dados.get("ano_fabricacao"),
            "chassi": dados.get("chassi", ""),
            "cep_pernoite": dados.get("cep_pernoite", ""),
            "cliente_nome": dados.get("cliente_nome", ""),
            "cpf_cnpj": dados.get("cpf_cnpj", ""),
            "telefone": dados.get("telefone", ""),
            "seguradora_atual": dados.get("seguradora", ""),
        }

        logger.info(
            f"[Sofia] Renovação iniciada: apólice {apolice_id} → cliente {cliente_id}"
        )

        return {
            "sucesso": True,
            "msg": f"Renovação da apólice {dados.get('numero_apolice', apolice_id)} iniciada com sucesso.",
            "apolice": dados,
            "dados_cotacao": dados_cotacao,
            "proximo_passo": "Confirme os dados do veículo e do cliente para calcular a nova cotação."
        }
    except Exception as e:
        logger.error(f"Erro ao iniciar renovação: {e}", exc_info=True)
        return {"sucesso": False, "erro": str(e)}


async def notificar_corretor(resumo: str, tipo: str = "info", urgente: bool = False,
                              bot=None, cliente_nome: str = None,
                              historico_resumo: str = None,
                              chat_id: int = None) -> dict:
    """
    Envia notificação pro Eduardo via Telegram.
    Para handoffs, inclui o histórico resumido da conversa.
    """
    if not bot:
        logger.warning("notificar_corretor chamado sem bot object")
        return {"sucesso": False, "msg": "Bot não disponível para notificação"}

    EMOJIS = {
        "handoff": "🤝",
        "cotacao_completa": "✅",
        "sinistro": "🚨",
        "info": "ℹ️"
    }
    emoji = EMOJIS.get(tipo, "📌")
    urgente_tag = "🔴 *URGENTE*\n" if urgente else ""

    if tipo == "handoff":
        titulo = "Handoff — cliente aguarda atendimento humano"
        instrucao = "\n\n_O cliente está aguardando seu contato! Já tem todo o contexto abaixo._"
    elif tipo == "cotacao_completa":
        titulo = "Cotação finalizada"
        instrucao = "\n\n_Verifique os resultados e entre em contato._"
    elif tipo == "sinistro":
        titulo = "🚨 Acionamento de sinistro"
        instrucao = "\n\n_Contato PRIORITÁRIO com o cliente._"
    else:
        titulo = "Notificação do agente"
        instrucao = ""

    cliente_tag = f"\n👤 *Cliente:* {cliente_nome}" if cliente_nome else ""
    chat_tag = f"\n💬 *Chat ID:* `{chat_id}`" if chat_id else ""

    # Corpo principal
    msg = (
        f"{urgente_tag}{emoji} *Sofia — {titulo}*"
        f"{cliente_tag}{chat_tag}\n\n"
        f"*Resumo do atendimento:*\n{resumo}"
        f"{instrucao}"
    )

    # Histórico da conversa (apenas em handoffs)
    if tipo in ("handoff", "sinistro") and historico_resumo:
        # Trunca se muito longo (limite Telegram ~4096 chars)
        hist_trunc = historico_resumo[:1500] if len(historico_resumo) > 1500 else historico_resumo
        msg += f"\n\n*📋 Histórico da conversa:*\n```\n{hist_trunc}\n```"

    try:
        await bot.send_message(
            chat_id=CORRETOR_CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
        logger.info(f"[Sofia] Corretor notificado: tipo={tipo}, urgente={urgente}")
        return {"sucesso": True, "msg": "Corretor notificado com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao notificar corretor: {e}")
        # Tenta sem Markdown como fallback
        try:
            await bot.send_message(
                chat_id=CORRETOR_CHAT_ID,
                text=msg.replace("*", "").replace("_", "").replace("`", "")
            )
            return {"sucesso": True, "msg": "Corretor notificado (sem formatação)."}
        except Exception as e2:
            return {"sucesso": False, "msg": f"Erro ao notificar: {str(e2)}"}


# ─────────────────────────────────────────────────────────────
#  DISPATCHER: executa a ferramenta pelo nome
# ─────────────────────────────────────────────────────────────

async def executar_ferramenta(nome: str, parametros: dict,
                               bot=None, on_progress=None,
                               cliente_nome: str = None) -> dict:
    """
    Despacha a chamada de ferramenta pelo nome.
    """
    logger.info(f"[tool] Executando: {nome} | params={list(parametros.keys())}")

    if nome == "classificar_intencao":
        # Ferramenta "virtual" — repassa os parâmetros como resultado
        return parametros

    elif nome == "processar_cnh":
        return await processar_cnh(parametros["foto_path"])

    elif nome == "processar_crlv":
        return await processar_crlv(parametros["foto_path"])

    elif nome == "buscar_cep":
        return await buscar_cep(parametros["cep"])

    elif nome == "calcular_cotacao":
        return await calcular_cotacao_tool(
            session_data=parametros["session_data"],
            chat_id=parametros["chat_id"],
            on_progress=on_progress
        )

    elif nome == "gerar_pdf_sierra":
        return await gerar_pdf_sierra_tool(
            seguradora=parametros["seguradora"],
            chat_id=parametros["chat_id"],
            premio_esperado=parametros.get("premio_esperado"),
            on_progress=on_progress
        )

    elif nome == "buscar_cliente":
        return await buscar_cliente(parametros["busca"])

    elif nome == "consultar_apolices":
        return await consultar_apolices(parametros["cliente_id"])

    elif nome == "consultar_renovacoes_pendentes":
        return await consultar_renovacoes_pendentes(
            cliente_id=parametros["cliente_id"],
            dias=parametros.get("dias", 60)
        )

    elif nome == "iniciar_renovacao":
        return await iniciar_renovacao(
            apolice_id=parametros["apolice_id"],
            cliente_id=parametros["cliente_id"]
        )

    elif nome == "notificar_corretor":
        return await notificar_corretor(
            resumo=parametros["resumo"],
            tipo=parametros.get("tipo", "info"),
            urgente=parametros.get("urgente", False),
            bot=bot,
            cliente_nome=parametros.get("cliente_nome") or cliente_nome,
            historico_resumo=parametros.get("historico_resumo"),
            chat_id=parametros.get("chat_id")
        )

    # ── 2.5.6 ──────────────────────────────────────────────
    elif nome == "processar_endosso":
        return await processar_endosso(
            numero_apolice=parametros["numero_apolice"],
            tipo_endosso=parametros["tipo_endosso"],
            dados_novos=parametros["dados_novos"],
            bot=bot,
            cliente_nome=cliente_nome
        )

    # ── 2.5.7 ──────────────────────────────────────────────
    elif nome == "abrir_sinistro":
        return await abrir_sinistro(
            numero_apolice=parametros["numero_apolice"],
            tipo_sinistro=parametros["tipo_sinistro"],
            descricao=parametros["descricao"],
            data_ocorrencia=parametros["data_ocorrencia"],
            bot=bot,
            cliente_nome=cliente_nome
        )

    # ── 2.5.8 ──────────────────────────────────────────────
    elif nome == "buscar_documento":
        return await buscar_documento(
            tipo=parametros["tipo"],
            numero_apolice=parametros.get("numero_apolice"),
            cliente_nome=parametros.get("cliente_nome") or cliente_nome
        )

    # ── 2.5.9 ──────────────────────────────────────────────
    elif nome == "consultar_assistencia":
        return await consultar_assistencia(
            seguradora=parametros["seguradora"]
        )

    # ── 2.5.10 ─────────────────────────────────────────────
    elif nome == "consultar_status_sinistro":
        return await consultar_status_sinistro(
            numero_apolice=parametros.get("numero_apolice"),
            nome_cliente=parametros.get("nome_cliente") or cliente_nome,
            bot=bot
        )

    # ── 2.5.11 ─────────────────────────────────────────────
    elif nome == "registrar_indicacao":
        return await registrar_indicacao(
            nome_indicado=parametros["nome_indicado"],
            telefone_indicado=parametros["telefone_indicado"],
            cliente_indicador=parametros["cliente_indicador"],
            ramo_interesse=parametros.get("ramo_interesse"),
            bot=bot
        )

    else:
        return {"erro": f"Ferramenta desconhecida: {nome}"}
