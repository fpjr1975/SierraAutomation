"""
agent_tools.py — Ferramentas disponíveis para a Sofia (agente IA da Sierra Seguros)

Cada função aqui é um wrapper das capacidades já existentes no sistema:
  - OCR de CNH/CRVL (via ocr_docs.py)
  - Cálculo de cotação (via agilizador.py)
  - Download de PDF cotação (via agilizador.py)
  - Busca de CEP (via ViaCEP)
  - Consulta de clientes/apólices (via PostgreSQL)
  - Notificação pro corretor (via Telegram)

Todas as funções são assíncronas pra não bloquear o bot.
"""

import os
import sys
import logging
import asyncio
import httpx
import json
from typing import Optional

# Adiciona o diretório pai (/root/sierra/) ao path pra importar módulos existentes
_SIERRA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SIERRA_ROOT not in sys.path:
    sys.path.insert(0, _SIERRA_ROOT)

logger = logging.getLogger(__name__)

# Chat_id do Eduardo (corretor responsável) — recebe handoffs e notificações
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
                        "cotacao_nova",      # quer cotar um seguro novo
                        "transferencia",     # transferência de seguro/veículo
                        "renovacao",         # renovar apólice existente
                        "endosso",           # alterar apólice vigente
                        "sinistro",          # acidente, colisão, furto
                        "documentos",        # pedir documentos, apólice, boleto
                        "duvidas",           # perguntas gerais sobre seguro
                        "assistencia",       # guincho, socorro, carro reserva
                        "status",            # verificar status de cotação/proposta
                        "indicacao",         # indicar a Sierra pra outra pessoa
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
            "Processa uma imagem de CNH (Carteira Nacional de Habilitação) usando OCR com IA. "
            "Extrai: nome, CPF, data de nascimento, categoria, validade, etc. "
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
            "Processa uma imagem do CRLV (Certificado de Registro e Licenciamento de Veículo) usando OCR com IA. "
            "Extrai: placa, marca/modelo, ano, chassi, proprietário, etc. "
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
            "Retorna: logradouro, bairro, cidade, UF. "
            "Use para validar e completar o endereço de pernoite do veículo."
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
            "Preenche o formulário automaticamente e retorna os resultados das seguradoras. "
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
                    "description": "ID do chat do cliente (para manter sessão do browser)"
                }
            },
            "required": ["session_data", "chat_id"]
        }
    },
    {
        "name": "gerar_pdf_sierra",
        "description": (
            "Baixa e gera o PDF de cotação de uma seguradora específica no layout Sierra. "
            "Use após calcular_cotacao, quando o cliente escolher uma seguradora. "
            "Retorna o caminho do PDF gerado."
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
        "name": "notificar_corretor",
        "description": (
            "Envia uma notificação para o corretor Eduardo via Telegram. "
            "Use quando: confiança < 0.95, cliente pede falar com humano, "
            "situação complexa (sinistro, endosso, reclamação), ou ao concluir cotação."
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
    """
    OCR de CNH usando o módulo ocr_docs existente.
    Retorna dados estruturados da CNH.
    """
    try:
        from ocr_docs import extract_document_data
        data = extract_document_data(foto_path)
        if not data:
            return {"erro": "Não foi possível ler a CNH. Peça uma foto mais nítida."}
        if data.get("tipo", "").upper() != "CNH":
            # Tenta com prompt específico de CNH
            return {"erro": f"Documento identificado como '{data.get('tipo', 'Desconhecido')}', não como CNH."}
        return {"sucesso": True, "dados": data}
    except Exception as e:
        logger.error(f"Erro ao processar CNH: {e}", exc_info=True)
        return {"erro": f"Erro interno ao processar CNH: {str(e)}"}


async def processar_crlv(foto_path: str) -> dict:
    """
    OCR de CRLV usando o módulo ocr_docs existente.
    Retorna dados estruturados do CRLV.
    """
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
    """
    Busca endereço via ViaCEP.
    Retorna dados do endereço ou erro.
    """
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
    """
    Calcula cotação no Agilizador.
    Wrapper da função calcular_cotacao do agilizador.py.
    """
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
    """
    Gera PDF Sierra de uma seguradora.
    Wrapper da função baixar_pdf_cotacao do agilizador.py.
    """
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
    """
    Busca cliente por CPF ou nome no PostgreSQL.
    """
    import re
    try:
        import asyncpg
        conn = await asyncpg.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        try:
            # Verifica se parece um CPF (só números ou com pontuação)
            cpf_limpo = re.sub(r"\D", "", busca)
            if len(cpf_limpo) == 11:
                rows = await conn.fetch(
                    "SELECT id, nome, cpf_cnpj, telefone, email, cidade, uf "
                    "FROM clientes WHERE cpf_cnpj LIKE $1 LIMIT 5",
                    f"%{cpf_limpo}%"
                )
            else:
                # Busca por nome (case insensitive)
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
        # Fallback com psycopg2
        return await _buscar_cliente_psycopg2(busca)
    except Exception as e:
        logger.error(f"Erro ao buscar cliente: {e}", exc_info=True)
        return {"encontrado": False, "erro": str(e)}


async def _buscar_cliente_psycopg2(busca: str) -> dict:
    """Fallback com psycopg2 síncrono."""
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
    """
    Consulta apólices vigentes de um cliente.
    """
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
            # Formata datas
            for campo in ["vigencia_inicio", "vigencia_fim"]:
                if ap.get(campo):
                    ap[campo] = ap[campo].strftime("%d/%m/%Y")
            # Formata prêmio
            if ap.get("premio"):
                ap["premio_fmt"] = f"R$ {float(ap['premio']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            apolices.append(ap)

        return {"encontrado": True, "apolices": apolices, "total": len(apolices)}
    except Exception as e:
        logger.error(f"Erro ao consultar apólices: {e}", exc_info=True)
        return {"encontrado": False, "erro": str(e)}


async def notificar_corretor(resumo: str, tipo: str = "info", urgente: bool = False,
                              bot=None, cliente_nome: str = None) -> dict:
    """
    Envia notificação pro Eduardo via Telegram.
    Precisa do objeto bot do python-telegram-bot.
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
        titulo = "Handoff solicitado"
        instrucao = "\n\n_O cliente está aguardando seu contato!_"
    elif tipo == "cotacao_completa":
        titulo = "Cotação finalizada"
        instrucao = "\n\n_Verifique os resultados e entre em contato._"
    elif tipo == "sinistro":
        titulo = "Acionamento de sinistro"
        instrucao = "\n\n_Contato prioritário com o cliente._"
    else:
        titulo = "Notificação do agente"
        instrucao = ""

    cliente_tag = f"\n👤 *Cliente:* {cliente_nome}" if cliente_nome else ""
    msg = (
        f"{urgente_tag}{emoji} *Sofia — {titulo}*{cliente_tag}\n\n"
        f"{resumo}{instrucao}"
    )

    try:
        await bot.send_message(
            chat_id=CORRETOR_CHAT_ID,
            text=msg,
            parse_mode="Markdown"
        )
        return {"sucesso": True, "msg": "Corretor notificado com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao notificar corretor: {e}")
        return {"sucesso": False, "msg": f"Erro ao notificar: {str(e)}"}


# ─────────────────────────────────────────────────────────────
#  DISPATCHER: executa a ferramenta pelo nome
# ─────────────────────────────────────────────────────────────

async def executar_ferramenta(nome: str, parametros: dict,
                               bot=None, on_progress=None,
                               cliente_nome: str = None) -> dict:
    """
    Despacha a chamada de ferramenta pelo nome.
    Chamado pelo agent_engine quando o Claude retorna um tool_use.
    """
    logger.info(f"[tool] Executando: {nome} | params={list(parametros.keys())}")

    if nome == "classificar_intencao":
        # Esta ferramenta é "virtual" — o resultado é retornado pelo próprio Claude
        # Apenas repassa os parâmetros como resultado
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

    elif nome == "notificar_corretor":
        return await notificar_corretor(
            resumo=parametros["resumo"],
            tipo=parametros.get("tipo", "info"),
            urgente=parametros.get("urgente", False),
            bot=bot,
            cliente_nome=cliente_nome
        )

    else:
        return {"erro": f"Ferramenta desconhecida: {nome}"}
