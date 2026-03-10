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
    },
    # ── 2.5.6 ──────────────────────────────────────────────
    {
        "name": "processar_endosso",
        "description": (
            "Prepara um endosso (alteração de apólice vigente) para o cliente. "
            "Use quando o cliente quiser trocar de carro, mudar de CEP, incluir condutor ou fazer outra alteração. "
            "NÃO executa o endosso — apenas prepara o resumo, calcula pro-rata estimado e notifica o corretor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_apolice": {
                    "type": "string",
                    "description": "Número da apólice a ser alterada"
                },
                "tipo_endosso": {
                    "type": "string",
                    "enum": ["troca_veiculo", "mudanca_cep", "inclusao_condutor", "outros"],
                    "description": "Tipo de alteração solicitada"
                },
                "dados_novos": {
                    "type": "object",
                    "description": (
                        "Dados novos a serem incluídos. Ex.: "
                        "{'veiculo': 'Honda Civic 2024', 'placa': 'ABC1D23'} ou "
                        "{'cep': '01310-100'} ou "
                        "{'condutor_nome': 'Maria Silva', 'condutor_cpf': '000.000.000-00'}"
                    )
                }
            },
            "required": ["numero_apolice", "tipo_endosso", "dados_novos"]
        }
    },
    # ── 2.5.7 ──────────────────────────────────────────────
    {
        "name": "abrir_sinistro",
        "description": (
            "Abre um registro de sinistro para o cliente. "
            "Use quando o cliente relatar acidente, colisão, roubo, furto, incêndio ou alagamento. "
            "Busca cobertura na apólice, retorna checklist de documentos necessários, "
            "valor da franquia e telefones de assistência 24h. Notifica o corretor como URGENTE."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_apolice": {
                    "type": "string",
                    "description": "Número da apólice do cliente"
                },
                "tipo_sinistro": {
                    "type": "string",
                    "enum": ["colisao", "roubo", "furto", "incendio", "alagamento", "outros"],
                    "description": "Tipo do sinistro ocorrido"
                },
                "descricao": {
                    "type": "string",
                    "description": "Descrição do ocorrido conforme relatado pelo cliente"
                },
                "data_ocorrencia": {
                    "type": "string",
                    "description": "Data do ocorrido (formato DD/MM/AAAA ou texto livre)"
                }
            },
            "required": ["numero_apolice", "tipo_sinistro", "descricao", "data_ocorrencia"]
        }
    },
    # ── 2.5.8 ──────────────────────────────────────────────
    {
        "name": "buscar_documento",
        "description": (
            "Busca documentos do cliente na base de dados: apólice, boleto ou proposta. "
            "Use quando o cliente pedir uma segunda via de documento, apólice ou boleto. "
            "Retorna o caminho do arquivo ou informa que vai verificar com o corretor."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["apolice", "boleto", "proposta"],
                    "description": "Tipo de documento solicitado"
                },
                "numero_apolice": {
                    "type": "string",
                    "description": "Número da apólice (opcional se informar cliente_nome)"
                },
                "cliente_nome": {
                    "type": "string",
                    "description": "Nome do cliente para busca (opcional se informar numero_apolice)"
                }
            },
            "required": ["tipo"]
        }
    },
    # ── 2.5.9 ──────────────────────────────────────────────
    {
        "name": "consultar_assistencia",
        "description": (
            "Retorna o telefone de assistência 24h de uma seguradora. "
            "Use quando o cliente precisar de socorro, guincho ou assistência emergencial. "
            "Suporta: Porto Seguro, HDI, Tokio Marine, Bradesco, Allianz, Azul, Mapfre, "
            "Zurich, Liberty/Yelum, Suhai, Itaú."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seguradora": {
                    "type": "string",
                    "description": "Nome da seguradora (ex: 'Porto Seguro', 'HDI', 'Tokio Marine')"
                }
            },
            "required": ["seguradora"]
        }
    },
    # ── 2.5.10 ─────────────────────────────────────────────
    {
        "name": "consultar_status_sinistro",
        "description": (
            "Consulta o status de um sinistro em aberto pelo número da apólice ou nome do cliente. "
            "Busca registros na base de dados. Se não houver tabela de sinistros, "
            "informa que vai verificar com o corretor e notifica."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "numero_apolice": {
                    "type": "string",
                    "description": "Número da apólice associada ao sinistro (opcional)"
                },
                "nome_cliente": {
                    "type": "string",
                    "description": "Nome do cliente (opcional se informar numero_apolice)"
                }
            }
        }
    },
    # ── 2.5.11 ─────────────────────────────────────────────
    {
        "name": "registrar_indicacao",
        "description": (
            "Registra uma indicação feita pelo cliente para um amigo ou familiar. "
            "Notifica o corretor com os dados da pessoa indicada para que ele entre em contato. "
            "Retorna agradecimento ao cliente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome_indicado": {
                    "type": "string",
                    "description": "Nome da pessoa indicada"
                },
                "telefone_indicado": {
                    "type": "string",
                    "description": "Telefone/WhatsApp da pessoa indicada"
                },
                "ramo_interesse": {
                    "type": "string",
                    "description": "Ramo de seguro de interesse (auto, residencial, vida, empresarial, etc.)"
                },
                "cliente_indicador": {
                    "type": "string",
                    "description": "Nome do cliente que fez a indicação"
                }
            },
            "required": ["nome_indicado", "telefone_indicado", "cliente_indicador"]
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
#  TELEFONES DE ASSISTÊNCIA 24H (hardcoded)
# ─────────────────────────────────────────────────────────────

ASSISTENCIA_24H = {
    "porto seguro":   "0800-727-0800",
    "porto":          "0800-727-0800",
    "hdi":            "0800-770-1608",
    "tokio marine":   "0800-625-9000",
    "tokio":          "0800-625-9000",
    "bradesco":       "0800-701-7000",
    "allianz":        "0800-130-000",
    "azul":           "0800-703-0203",
    "mapfre":         "0800-775-4545",
    "zurich":         "0800-284-4848",
    "liberty":        "0800-709-6464",
    "yelum":          "0800-709-6464",
    "liberty/yelum":  "0800-709-6464",
    "suhai":          "0800-882-1882",
    "itaú":           "0800-722-1722",
    "itau":           "0800-722-1722",
}

# ─────────────────────────────────────────────────────────────
#  HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────

def _fmt_brl(valor) -> str:
    """Formata valor float/Decimal como R$ X.XXX,XX."""
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor)


async def _buscar_apolice_por_numero(numero_apolice: str) -> dict | None:
    """Busca apólice completa pelo número. Retorna dict ou None."""
    import psycopg2
    import psycopg2.extras
    try:
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT
                a.id, a.numero_apolice, a.seguradora, a.status, a.ramo,
                a.vigencia_inicio, a.vigencia_fim, a.premio, a.franquia,
                a.comissao_percentual, a.comissao_valor,
                c.nome AS cliente_nome, c.telefone AS cliente_telefone,
                c.cpf_cnpj, c.cidade, c.uf,
                v.marca_modelo, v.placa, v.ano_fabricacao
            FROM apolices a
            LEFT JOIN clientes c ON a.cliente_id = c.id
            LEFT JOIN veiculos v ON a.veiculo_id = v.id
            WHERE UPPER(a.numero_apolice) = UPPER(%s)
            LIMIT 1
        """, (numero_apolice.strip(),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.error(f"Erro ao buscar apólice {numero_apolice}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
#  IMPLEMENTAÇÕES — NOVAS FERRAMENTAS (2.5.6 a 2.5.11)
# ─────────────────────────────────────────────────────────────

async def processar_endosso(numero_apolice: str, tipo_endosso: str,
                             dados_novos: dict, bot=None,
                             cliente_nome: str = None) -> dict:
    """
    Prepara resumo de endosso, calcula pro-rata estimado e notifica o corretor.
    NÃO grava nem executa o endosso.
    """
    from datetime import date

    apolice = await _buscar_apolice_por_numero(numero_apolice)
    if not apolice:
        return {
            "sucesso": False,
            "msg": (
                f"Não encontrei nenhuma apólice com o número *{numero_apolice}*. "
                "Verifique o número e tente novamente, ou fale com o corretor."
            )
        }

    status = (apolice.get("status") or "").lower()
    if status not in ("vigente", "ativa", "active"):
        return {
            "sucesso": False,
            "msg": (
                f"A apólice *{numero_apolice}* está com status *{status}* "
                "e não pode ser alterada por aqui. Fale com o corretor."
            )
        }

    hoje = date.today()
    vigencia_fim = apolice.get("vigencia_fim")
    premio = float(apolice.get("premio") or 0)

    if vigencia_fim and premio > 0:
        dias_restantes = max((vigencia_fim - hoje).days, 0)
        pro_rata_base = round(dias_restantes / 365 * premio, 2)
        pro_rata_msg = (
            f"Pro-rata estimado: {_fmt_brl(pro_rata_base)} "
            f"({dias_restantes} dias restantes de vigência)"
        )
    else:
        pro_rata_base = None
        pro_rata_msg = "Pro-rata não calculado (dados de vigência/prêmio incompletos)"

    tipo_labels = {
        "troca_veiculo":     "Troca de veículo",
        "mudanca_cep":       "Mudança de CEP/endereço de pernoite",
        "inclusao_condutor": "Inclusão de condutor",
        "outros":            "Outro tipo de alteração",
    }
    tipo_label = tipo_labels.get(tipo_endosso, tipo_endosso)
    dados_str = "\n".join(f"  • {k}: {v}" for k, v in dados_novos.items())

    resumo_endosso = (
        f"📋 *Solicitação de Endosso*\n"
        f"Apólice: {numero_apolice} — {apolice.get('seguradora', '?')}\n"
        f"Cliente: {apolice.get('cliente_nome', cliente_nome or '?')}\n"
        f"Tipo: {tipo_label}\n"
        f"Dados novos:\n{dados_str}\n"
        f"{pro_rata_msg}\n"
        f"Veículo atual: {apolice.get('marca_modelo', '?')} | Placa: {apolice.get('placa', '?')}\n"
        f"Vigência fim: {apolice.get('vigencia_fim', '?')}"
    )

    if bot:
        await notificar_corretor(
            resumo=resumo_endosso,
            tipo="info",
            urgente=False,
            bot=bot,
            cliente_nome=apolice.get("cliente_nome", cliente_nome)
        )

    return {
        "sucesso": True,
        "numero_apolice": numero_apolice,
        "seguradora": apolice.get("seguradora"),
        "tipo_endosso": tipo_label,
        "pro_rata_estimado": pro_rata_base,
        "pro_rata_msg": pro_rata_msg,
        "msg": (
            f"Solicitação de endosso registrada! O corretor Eduardo foi notificado "
            f"e entrará em contato para finalizar a alteração.\n{pro_rata_msg}."
        )
    }


async def abrir_sinistro(numero_apolice: str, tipo_sinistro: str,
                          descricao: str, data_ocorrencia: str,
                          bot=None, cliente_nome: str = None) -> dict:
    """
    Registra abertura de sinistro: verifica cobertura, retorna checklist,
    franquia e telefone de assistência. Notifica corretor como URGENTE.
    """
    apolice = await _buscar_apolice_por_numero(numero_apolice)
    if not apolice:
        return {
            "sucesso": False,
            "msg": (
                f"Não encontrei a apólice *{numero_apolice}*. "
                "Vou notificar o corretor para verificar. Confirme o número da apólice."
            )
        }

    seguradora = apolice.get("seguradora", "Seguradora")
    franquia = apolice.get("franquia")
    franquia_fmt = _fmt_brl(franquia) if franquia else "verificar com corretor"

    tipo_labels = {
        "colisao":    "Colisão",
        "roubo":      "Roubo",
        "furto":      "Furto",
        "incendio":   "Incêndio",
        "alagamento": "Alagamento",
        "outros":     "Sinistro",
    }
    tipo_label = tipo_labels.get(tipo_sinistro, tipo_sinistro)

    CHECKLISTS = {
        "colisao": [
            "📸 Fotos do local (veículos, placas, danos visíveis)",
            "📋 Boletim de Ocorrência (BO) — obrigatório se houver terceiros",
            "🪪 CNH do condutor",
            "📄 CRLV do veículo",
            "📝 Dados do terceiro (se houver): nome, CPF, placa, seguradora",
        ],
        "roubo": [
            "📋 Boletim de Ocorrência (BO) — OBRIGATÓRIO",
            "🪪 CNH do condutor",
            "📄 CRLV do veículo",
            "🔑 Chaves do veículo (original + cópia)",
            "📝 Declaração de roubo assinada",
        ],
        "furto": [
            "📋 Boletim de Ocorrência (BO) — OBRIGATÓRIO",
            "🪪 CNH do proprietário",
            "📄 CRLV do veículo",
            "🔑 Chaves do veículo (original + cópia)",
        ],
        "incendio": [
            "📋 Boletim de Ocorrência (BO)",
            "📸 Fotos do veículo (antes de remover, se possível)",
            "🪪 CNH do condutor",
            "📄 CRLV do veículo",
            "🚒 Relatório do Corpo de Bombeiros (se houver)",
        ],
        "alagamento": [
            "📸 Fotos do veículo e do local (antes de mover)",
            "🪪 CNH do proprietário",
            "📄 CRLV do veículo",
            "📋 Boletim de Ocorrência (BO) — recomendado",
            "📍 Endereço onde o veículo estava",
        ],
        "outros": [
            "📸 Fotos do ocorrido",
            "🪪 CNH do condutor",
            "📄 CRLV do veículo",
            "📋 Boletim de Ocorrência (BO) — se aplicável",
            "📝 Descrição detalhada do ocorrido",
        ],
    }
    checklist = CHECKLISTS.get(tipo_sinistro, CHECKLISTS["outros"])
    checklist_str = "\n".join(checklist)

    seg_key = seguradora.lower()
    tel_assistencia = ASSISTENCIA_24H.get(seg_key)
    if not tel_assistencia:
        for key, tel in ASSISTENCIA_24H.items():
            if key in seg_key or seg_key in key:
                tel_assistencia = tel
                break
    tel_assistencia = tel_assistencia or "Consulte o dorso da apólice"

    resumo_corretor = (
        f"🚨 *SINISTRO — {tipo_label.upper()}*\n"
        f"Apólice: {numero_apolice} | {seguradora}\n"
        f"Cliente: {apolice.get('cliente_nome', cliente_nome or '?')}\n"
        f"Tel: {apolice.get('cliente_telefone', '?')}\n"
        f"Veículo: {apolice.get('marca_modelo', '?')} | {apolice.get('placa', '?')}\n"
        f"Data do ocorrido: {data_ocorrencia}\n"
        f"Descrição: {descricao}\n"
        f"Franquia: {franquia_fmt}"
    )

    if bot:
        await notificar_corretor(
            resumo=resumo_corretor,
            tipo="sinistro",
            urgente=True,
            bot=bot,
            cliente_nome=apolice.get("cliente_nome", cliente_nome)
        )

    return {
        "sucesso": True,
        "numero_apolice": numero_apolice,
        "seguradora": seguradora,
        "tipo_sinistro": tipo_label,
        "franquia": franquia_fmt,
        "assistencia_24h": tel_assistencia,
        "checklist": checklist,
        "msg": (
            f"Sinistro de *{tipo_label}* registrado! O corretor Eduardo foi notificado com URGÊNCIA.\n\n"
            f"📞 Assistência 24h {seguradora}: *{tel_assistencia}*\n\n"
            f"💰 Franquia: *{franquia_fmt}*\n\n"
            f"📋 *Documentos necessários:*\n{checklist_str}"
        )
    }


async def buscar_documento(tipo: str, numero_apolice: str = None,
                            cliente_nome: str = None) -> dict:
    """
    Busca documentos na tabela documentos/apolices/cotacao_resultados.
    """
    import psycopg2
    import psycopg2.extras

    tipo_labels = {"apolice": "Apólice", "boleto": "Boleto", "proposta": "Proposta"}
    tipo_label = tipo_labels.get(tipo, tipo)

    if not numero_apolice and not cliente_nome:
        return {
            "encontrado": False,
            "msg": "Informe o número da apólice ou o nome do cliente para buscar o documento."
        }

    try:
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Busca na tabela documentos
        if numero_apolice:
            cur.execute("""
                SELECT d.id, d.tipo, d.arquivo_path, d.created_at, c.nome AS cliente_nome
                FROM documentos d
                LEFT JOIN clientes c ON d.cliente_id = c.id
                LEFT JOIN apolices a ON a.cliente_id = d.cliente_id
                WHERE d.tipo ILIKE %s
                  AND (a.numero_apolice = %s OR d.dados_extraidos::text ILIKE %s)
                ORDER BY d.created_at DESC LIMIT 1
            """, (f"%{tipo}%", numero_apolice, f"%{numero_apolice}%"))
        else:
            cur.execute("""
                SELECT d.id, d.tipo, d.arquivo_path, d.created_at, c.nome AS cliente_nome
                FROM documentos d
                LEFT JOIN clientes c ON d.cliente_id = c.id
                WHERE d.tipo ILIKE %s
                  AND unaccent(lower(c.nome)) ILIKE unaccent(lower(%s))
                ORDER BY d.created_at DESC LIMIT 1
            """, (f"%{tipo}%", f"%{cliente_nome}%"))

        row = cur.fetchone()
        if row and row.get("arquivo_path"):
            cur.close(); conn.close()
            return {
                "encontrado": True,
                "tipo": tipo_label,
                "arquivo_path": row["arquivo_path"],
                "cliente_nome": row.get("cliente_nome"),
                "msg": f"Encontrei o documento! Caminho: {row['arquivo_path']}"
            }

        # 2. Busca pdf_path em cotacao_resultados
        if numero_apolice:
            cur.execute("""
                SELECT cr.pdf_path, cr.seguradora, cr.created_at, c.nome AS cliente_nome
                FROM cotacao_resultados cr
                JOIN cotacoes co ON cr.cotacao_id = co.id
                LEFT JOIN apolices a ON a.cotacao_id = co.id
                LEFT JOIN clientes c ON co.cliente_id = c.id
                WHERE cr.pdf_path IS NOT NULL
                  AND (a.numero_apolice = %s OR cr.numero_cotacao = %s)
                ORDER BY cr.created_at DESC LIMIT 1
            """, (numero_apolice, numero_apolice))
        else:
            cur.execute("""
                SELECT cr.pdf_path, cr.seguradora, cr.created_at, c.nome AS cliente_nome
                FROM cotacao_resultados cr
                JOIN cotacoes co ON cr.cotacao_id = co.id
                LEFT JOIN clientes c ON co.cliente_id = c.id
                WHERE cr.pdf_path IS NOT NULL
                  AND unaccent(lower(c.nome)) ILIKE unaccent(lower(%s))
                ORDER BY cr.created_at DESC LIMIT 1
            """, (f"%{cliente_nome}%",))

        row2 = cur.fetchone()
        cur.close(); conn.close()

        if row2 and row2.get("pdf_path"):
            return {
                "encontrado": True,
                "tipo": tipo_label,
                "arquivo_path": row2["pdf_path"],
                "seguradora": row2.get("seguradora"),
                "cliente_nome": row2.get("cliente_nome"),
                "msg": f"Encontrei o PDF da cotação. Caminho: {row2['pdf_path']}"
            }

        busca_ref = numero_apolice or cliente_nome
        return {
            "encontrado": False,
            "msg": (
                f"Não encontrei o documento ({tipo_label}) para '{busca_ref}'. "
                "Vou verificar com o corretor e ele entrará em contato com você."
            )
        }

    except Exception as e:
        logger.error(f"Erro ao buscar documento: {e}", exc_info=True)
        return {
            "encontrado": False,
            "msg": "Erro ao consultar documentos. Vou verificar com o corretor."
        }


async def consultar_assistencia(seguradora: str) -> dict:
    """Retorna telefone de assistência 24h da seguradora."""
    seg_lower = seguradora.lower().strip()

    telefone = ASSISTENCIA_24H.get(seg_lower)
    if not telefone:
        for key, tel in ASSISTENCIA_24H.items():
            if key in seg_lower or seg_lower in key:
                telefone = tel
                break

    if telefone:
        return {
            "sucesso": True,
            "seguradora": seguradora,
            "telefone_assistencia": telefone,
            "msg": f"Assistência 24h {seguradora}: *{telefone}*"
        }

    lista = (
        "• Porto Seguro: 0800-727-0800\n"
        "• HDI: 0800-770-1608\n"
        "• Tokio Marine: 0800-625-9000\n"
        "• Bradesco: 0800-701-7000\n"
        "• Allianz: 0800-130-000\n"
        "• Azul: 0800-703-0203\n"
        "• Mapfre: 0800-775-4545\n"
        "• Zurich: 0800-284-4848\n"
        "• Liberty/Yelum: 0800-709-6464\n"
        "• Suhai: 0800-882-1882\n"
        "• Itaú: 0800-722-1722"
    )
    return {
        "sucesso": False,
        "seguradora": seguradora,
        "msg": (
            f"Não encontrei o telefone específico para '{seguradora}'. "
            f"Principais contatos de assistência 24h:\n{lista}"
        )
    }


async def consultar_status_sinistro(numero_apolice: str = None,
                                     nome_cliente: str = None,
                                     bot=None) -> dict:
    """
    Consulta status de sinistro. Se não há tabela sinistros,
    notifica o corretor e informa o cliente.
    """
    import psycopg2
    import psycopg2.extras

    if not numero_apolice and not nome_cliente:
        return {"encontrado": False, "msg": "Informe o número da apólice ou o seu nome."}

    try:
        conn = psycopg2.connect("postgresql://sierra:SierraDB2026!!@localhost/sierra_db")
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'sinistros'
            )
        """)
        tem_tabela = cur.fetchone()["exists"]

        if tem_tabela:
            if numero_apolice:
                cur.execute("""
                    SELECT s.*, a.seguradora, c.nome AS cliente_nome
                    FROM sinistros s
                    JOIN apolices a ON s.apolice_id = a.id
                    JOIN clientes c ON a.cliente_id = c.id
                    WHERE a.numero_apolice = %s
                    ORDER BY s.created_at DESC LIMIT 5
                """, (numero_apolice,))
            else:
                cur.execute("""
                    SELECT s.*, a.seguradora, c.nome AS cliente_nome
                    FROM sinistros s
                    JOIN apolices a ON s.apolice_id = a.id
                    JOIN clientes c ON a.cliente_id = c.id
                    WHERE unaccent(lower(c.nome)) ILIKE unaccent(lower(%s))
                    ORDER BY s.created_at DESC LIMIT 5
                """, (f"%{nome_cliente}%",))

            rows = cur.fetchall()
            cur.close(); conn.close()

            if rows:
                return {
                    "encontrado": True,
                    "sinistros": [dict(r) for r in rows],
                    "msg": f"Encontrei {len(rows)} sinistro(s) registrado(s)."
                }
            return {
                "encontrado": False,
                "msg": "Nenhum sinistro encontrado. Se é recente, pode ainda estar sendo registrado."
            }

        cur.close(); conn.close()

        ref = numero_apolice or nome_cliente
        if bot:
            await notificar_corretor(
                resumo=(
                    f"📋 Consulta de status de sinistro\n"
                    f"Referência: {ref}\n"
                    f"Cliente solicitou via chatbot."
                ),
                tipo="info",
                urgente=False,
                bot=bot,
                cliente_nome=nome_cliente
            )

        return {
            "encontrado": False,
            "msg": (
                "Ainda não tenho acesso ao histórico de sinistros pelo chat. "
                "O corretor Eduardo foi notificado e entrará em contato com o status em breve!"
            )
        }

    except Exception as e:
        logger.error(f"Erro ao consultar sinistro: {e}", exc_info=True)
        return {
            "encontrado": False,
            "msg": "Erro ao consultar sinistro. Vou verificar com o corretor."
        }


async def registrar_indicacao(nome_indicado: str, telefone_indicado: str,
                               cliente_indicador: str,
                               ramo_interesse: str = None,
                               bot=None) -> dict:
    """Registra indicação e notifica o corretor."""
    ramo_str = f"\nRamo de interesse: {ramo_interesse}" if ramo_interesse else ""
    resumo = (
        f"🎁 *Nova Indicação*\n"
        f"Indicador: {cliente_indicador}\n"
        f"Indicado: {nome_indicado}\n"
        f"Telefone: {telefone_indicado}{ramo_str}\n\n"
        f"_Entre em contato para aproveitar a indicação!_"
    )

    notif_ok = False
    if bot:
        r = await notificar_corretor(
            resumo=resumo,
            tipo="info",
            urgente=False,
            bot=bot,
            cliente_nome=cliente_indicador
        )
        notif_ok = r.get("sucesso", False)

    return {
        "sucesso": True,
        "nome_indicado": nome_indicado,
        "telefone_indicado": telefone_indicado,
        "ramo_interesse": ramo_interesse,
        "corretor_notificado": notif_ok,
        "msg": (
            f"Obrigado pela indicação, {cliente_indicador}! 🎉\n"
            f"Vamos entrar em contato com {nome_indicado} em breve. "
            "Agradecemos muito pela confiança!"
        )
    }


# ─────────────────────────────────────────────────────────────
#  ARBITRAGEM — análise de resultados de cotação
# ─────────────────────────────────────────────────────────────

def analisar_arbitragem(resultados: list) -> dict:
    """
    Analisa resultados de cotação e retorna sweet spot, dispersão e sugestão.

    Args:
        resultados: lista de dicts com 'seguradora', 'premio' e opcionalmente
                    'comissao_percentual'.
    Returns:
        dict com sweet_spot, dispersao, sugestao_cliente, analise_interna
    """
    if not resultados:
        return {}

    validos = [r for r in resultados if r.get("premio") and float(r.get("premio", 0)) > 0]
    if not validos:
        return {}

    premios = [float(r["premio"]) for r in validos]
    menor = min(premios)
    maior = max(premios)
    dispersao_pct = round((maior - menor) / menor * 100, 1) if menor > 0 else 0

    def score_interno(r):
        premio = float(r.get("premio", 9999999))
        comissao = float(r.get("comissao_percentual") or 0)
        normalized_premio = (premio - menor) / (maior - menor + 0.01)
        normalized_comissao = comissao / 100.0
        # Sweet spot: 60% peso no menor prêmio, 40% na maior comissão
        return normalized_comissao * 0.4 + (1 - normalized_premio) * 0.6

    melhor_interno = max(validos, key=score_interno)
    melhor_preco = min(validos, key=lambda r: float(r.get("premio", 9999999)))

    sweet_spot_seg = melhor_interno.get("seguradora", "?")
    sweet_spot_premio = _fmt_brl(melhor_interno.get("premio"))

    return {
        "sweet_spot": sweet_spot_seg,
        "sweet_spot_premio_fmt": sweet_spot_premio,
        "dispersao_percentual": dispersao_pct,
        "dispersao_msg": (
            f"Dispersão de preços: {dispersao_pct}% entre a menor e maior cotação "
            f"({_fmt_brl(menor)} a {_fmt_brl(maior)})."
        ),
        "sugestao_cliente": (
            f"A {sweet_spot_seg} oferece o melhor equilíbrio entre preço e cobertura "
            f"({sweet_spot_premio}/ano)."
        ),
        "analise_interna": {
            "sweet_spot_seguradora": sweet_spot_seg,
            "sweet_spot_comissao_pct": melhor_interno.get("comissao_percentual"),
            "menor_preco_seguradora": melhor_preco.get("seguradora"),
            "menor_preco_valor": melhor_preco.get("premio"),
            "maior_preco_valor": maior,
            "dispersao_percentual": dispersao_pct,
        }
    }


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
        resultado = await calcular_cotacao_tool(
            session_data=parametros["session_data"],
            chat_id=parametros["chat_id"],
            on_progress=on_progress
        )
        # ── arbitragem: sweet spot + dispersão ──────────────
        try:
            resultados_lista = resultado.get("resultados") or resultado.get("seguradoras") or []
            if resultados_lista:
                arb = analisar_arbitragem(resultados_lista)
                if arb:
                    resultado["arbitragem"] = arb
                    resultado["sugestao_cliente"] = arb.get("sugestao_cliente", "")
        except Exception as _arb_err:
            logger.warning(f"Erro ao calcular arbitragem: {_arb_err}")
        return resultado

    elif nome == "gerar_pdf_sierra":
        resultado = await gerar_pdf_sierra_tool(
            seguradora=parametros["seguradora"],
            chat_id=parametros["chat_id"],
            premio_esperado=parametros.get("premio_esperado"),
            on_progress=on_progress
        )
        # ── arbitragem: se o resultado vier com lista de preços ─
        try:
            resultados_lista = resultado.get("resultados") or resultado.get("seguradoras") or []
            if resultados_lista:
                arb = analisar_arbitragem(resultados_lista)
                if arb:
                    resultado["arbitragem"] = arb
                    resultado["sugestao_cliente"] = arb.get("sugestao_cliente", "")
        except Exception as _arb_err:
            logger.warning(f"Erro ao calcular arbitragem (pdf): {_arb_err}")
        return resultado

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
