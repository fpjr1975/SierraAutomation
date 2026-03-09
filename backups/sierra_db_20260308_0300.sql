--
-- PostgreSQL database dump
--

\restrict jw8Pj03AWaYkdxH6bSOQ97B4kjTksKnRxg0W8fe8vKgFrSeMMP95xPEqYqHA3rx

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: apolices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.apolices (
    id integer NOT NULL,
    corretora_id integer,
    cliente_id integer,
    veiculo_id integer,
    cotacao_id integer,
    seguradora character varying(100),
    numero_apolice character varying(50),
    vigencia_inicio date,
    vigencia_fim date,
    premio numeric(12,2),
    franquia numeric(12,2),
    comissao_percentual numeric(5,2),
    comissao_valor numeric(12,2),
    status character varying(20) DEFAULT 'vigente'::character varying,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.apolices OWNER TO postgres;

--
-- Name: apolices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.apolices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.apolices_id_seq OWNER TO postgres;

--
-- Name: apolices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.apolices_id_seq OWNED BY public.apolices.id;


--
-- Name: clientes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.clientes (
    id integer NOT NULL,
    corretora_id integer,
    nome character varying(200) NOT NULL,
    cpf_cnpj character varying(20),
    nascimento date,
    telefone character varying(30),
    email character varying(200),
    cep character varying(10),
    endereco text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.clientes OWNER TO postgres;

--
-- Name: clientes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.clientes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.clientes_id_seq OWNER TO postgres;

--
-- Name: clientes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.clientes_id_seq OWNED BY public.clientes.id;


--
-- Name: comissoes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.comissoes (
    id integer NOT NULL,
    corretora_id integer,
    apolice_id integer,
    usuario_id integer,
    seguradora character varying(100),
    valor numeric(12,2),
    percentual numeric(5,2),
    parcela integer,
    total_parcelas integer,
    data_pagamento date,
    status character varying(20) DEFAULT 'pendente'::character varying,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.comissoes OWNER TO postgres;

--
-- Name: comissoes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.comissoes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.comissoes_id_seq OWNER TO postgres;

--
-- Name: comissoes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.comissoes_id_seq OWNED BY public.comissoes.id;


--
-- Name: corp_clientes_docs; Type: TABLE; Schema: public; Owner: sierra
--

CREATE TABLE public.corp_clientes_docs (
    id integer NOT NULL,
    corretora_id integer DEFAULT 1,
    filial character varying(20),
    nosso_numero character varying(50),
    cliente character varying(200),
    cpf_cnpj character varying(20),
    seguradora character varying(100),
    ramo character varying(100),
    apolice character varying(50),
    inicio_vigencia date,
    fim_vigencia date,
    premio numeric(12,2),
    comissao numeric(12,2),
    produtor character varying(200),
    status character varying(50),
    dados_extras jsonb,
    imported_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.corp_clientes_docs OWNER TO sierra;

--
-- Name: corp_clientes_docs_id_seq; Type: SEQUENCE; Schema: public; Owner: sierra
--

CREATE SEQUENCE public.corp_clientes_docs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.corp_clientes_docs_id_seq OWNER TO sierra;

--
-- Name: corp_clientes_docs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sierra
--

ALTER SEQUENCE public.corp_clientes_docs_id_seq OWNED BY public.corp_clientes_docs.id;


--
-- Name: corp_export_raw; Type: TABLE; Schema: public; Owner: sierra
--

CREATE TABLE public.corp_export_raw (
    id integer NOT NULL,
    corretora_id integer DEFAULT 1,
    dados jsonb NOT NULL,
    tipo character varying(50) DEFAULT 'clientes_docs'::character varying,
    imported_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.corp_export_raw OWNER TO sierra;

--
-- Name: corp_export_raw_id_seq; Type: SEQUENCE; Schema: public; Owner: sierra
--

CREATE SEQUENCE public.corp_export_raw_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.corp_export_raw_id_seq OWNER TO sierra;

--
-- Name: corp_export_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sierra
--

ALTER SEQUENCE public.corp_export_raw_id_seq OWNED BY public.corp_export_raw.id;


--
-- Name: corp_relatorios; Type: TABLE; Schema: public; Owner: sierra
--

CREATE TABLE public.corp_relatorios (
    id integer NOT NULL,
    corretora_id integer DEFAULT 1,
    periodo character varying(50),
    mes integer,
    ano integer,
    aba character varying(50),
    producao_total numeric(12,2),
    producao_variacao character varying(20),
    novos numeric(12,2),
    novos_variacao character varying(20),
    renovacoes numeric(12,2),
    renovacoes_variacao character varying(20),
    faturas numeric(12,2),
    endossos numeric(12,2),
    meta_atingida character varying(20),
    seguradoras jsonb,
    ramos jsonb,
    demonstrativo_12m jsonb,
    source_file character varying(100),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.corp_relatorios OWNER TO sierra;

--
-- Name: corp_relatorios_id_seq; Type: SEQUENCE; Schema: public; Owner: sierra
--

CREATE SEQUENCE public.corp_relatorios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.corp_relatorios_id_seq OWNER TO sierra;

--
-- Name: corp_relatorios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: sierra
--

ALTER SEQUENCE public.corp_relatorios_id_seq OWNED BY public.corp_relatorios.id;


--
-- Name: corretoras; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.corretoras (
    id integer NOT NULL,
    nome character varying(200) NOT NULL,
    cnpj character varying(20),
    regiao character varying(100),
    telefone character varying(30),
    email character varying(200),
    created_at timestamp without time zone DEFAULT now(),
    active boolean DEFAULT true
);


ALTER TABLE public.corretoras OWNER TO postgres;

--
-- Name: corretoras_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.corretoras_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.corretoras_id_seq OWNER TO postgres;

--
-- Name: corretoras_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.corretoras_id_seq OWNED BY public.corretoras.id;


--
-- Name: cotacao_resultados; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cotacao_resultados (
    id integer NOT NULL,
    cotacao_id integer,
    seguradora character varying(100),
    premio numeric(12,2),
    franquia numeric(12,2),
    parcelas character varying(50),
    numero_cotacao character varying(50),
    mensagem text,
    status character varying(20) DEFAULT 'ok'::character varying,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.cotacao_resultados OWNER TO postgres;

--
-- Name: cotacao_resultados_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cotacao_resultados_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cotacao_resultados_id_seq OWNER TO postgres;

--
-- Name: cotacao_resultados_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cotacao_resultados_id_seq OWNED BY public.cotacao_resultados.id;


--
-- Name: cotacoes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.cotacoes (
    id integer NOT NULL,
    corretora_id integer,
    usuario_id integer,
    cliente_id integer,
    veiculo_id integer,
    tipo character varying(20) DEFAULT 'nova'::character varying,
    status character varying(20) DEFAULT 'calculada'::character varying,
    cnh_data jsonb,
    crvl_data jsonb,
    condutor_data jsonb,
    cep_pernoite character varying(10),
    agilizador_url text,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.cotacoes OWNER TO postgres;

--
-- Name: cotacoes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.cotacoes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.cotacoes_id_seq OWNER TO postgres;

--
-- Name: cotacoes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.cotacoes_id_seq OWNED BY public.cotacoes.id;


--
-- Name: documentos; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.documentos (
    id integer NOT NULL,
    cliente_id integer,
    tipo character varying(30),
    arquivo_path text,
    dados_extraidos jsonb,
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.documentos OWNER TO postgres;

--
-- Name: documentos_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.documentos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.documentos_id_seq OWNER TO postgres;

--
-- Name: documentos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.documentos_id_seq OWNED BY public.documentos.id;


--
-- Name: usuarios; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.usuarios (
    id integer NOT NULL,
    corretora_id integer,
    nome character varying(200) NOT NULL,
    email character varying(200),
    senha_hash character varying(200),
    role character varying(20) DEFAULT 'corretor'::character varying NOT NULL,
    telegram_id bigint,
    telefone character varying(30),
    active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    last_login timestamp without time zone
);


ALTER TABLE public.usuarios OWNER TO postgres;

--
-- Name: usuarios_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.usuarios_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.usuarios_id_seq OWNER TO postgres;

--
-- Name: usuarios_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.usuarios_id_seq OWNED BY public.usuarios.id;


--
-- Name: v_carteira_ativa; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_carteira_ativa AS
 SELECT cliente,
    cpf_cnpj,
    seguradora,
    ramo,
    apolice,
    inicio_vigencia,
    fim_vigencia,
    premio,
    comissao,
    produtor,
    status,
    (fim_vigencia - CURRENT_DATE) AS dias_restantes
   FROM public.corp_clientes_docs
  WHERE ((fim_vigencia >= CURRENT_DATE) AND ((status IS NULL) OR ((status)::text <> ALL ((ARRAY['Cancelado'::character varying, 'CANCELADO'::character varying, 'Devolvido'::character varying])::text[]))))
  ORDER BY fim_vigencia;


ALTER VIEW public.v_carteira_ativa OWNER TO sierra;

--
-- Name: v_historico_producao; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_historico_producao AS
 SELECT periodo,
    mes,
    ano,
    aba,
    producao_total,
    producao_variacao,
    novos,
    renovacoes,
    faturas,
    endossos,
    seguradoras,
    ramos
   FROM public.corp_relatorios
  ORDER BY ano, mes, aba;


ALTER VIEW public.v_historico_producao OWNER TO sierra;

--
-- Name: v_producao_mensal; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_producao_mensal AS
 SELECT (date_trunc('month'::text, (inicio_vigencia)::timestamp with time zone))::date AS mes,
    count(*) AS novos_docs,
    sum(premio) AS premio_novos,
    sum(comissao) AS comissao_novos
   FROM public.corp_clientes_docs
  WHERE (inicio_vigencia IS NOT NULL)
  GROUP BY (date_trunc('month'::text, (inicio_vigencia)::timestamp with time zone))
  ORDER BY ((date_trunc('month'::text, (inicio_vigencia)::timestamp with time zone))::date) DESC;


ALTER VIEW public.v_producao_mensal OWNER TO sierra;

--
-- Name: v_producao_ramo; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_producao_ramo AS
 SELECT ramo,
    count(*) AS total_docs,
    count(*) FILTER (WHERE (fim_vigencia >= CURRENT_DATE)) AS docs_vigentes,
    sum(premio) AS premio_total,
    sum(comissao) AS comissao_total,
    round(avg(premio), 2) AS ticket_medio,
    round((((count(*))::numeric * 100.0) / NULLIF(sum(count(*)) OVER (), (0)::numeric)), 1) AS perc_carteira
   FROM public.corp_clientes_docs
  WHERE (ramo IS NOT NULL)
  GROUP BY ramo
  ORDER BY (count(*)) DESC;


ALTER VIEW public.v_producao_ramo OWNER TO sierra;

--
-- Name: v_producao_seguradora; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_producao_seguradora AS
 SELECT seguradora,
    count(*) AS total_docs,
    count(*) FILTER (WHERE (fim_vigencia >= CURRENT_DATE)) AS docs_vigentes,
    sum(premio) AS premio_total,
    sum(comissao) AS comissao_total,
    round(avg(premio), 2) AS ticket_medio,
    round(((sum(comissao) * 100.0) / NULLIF(sum(premio), (0)::numeric)), 1) AS perc_comissao
   FROM public.corp_clientes_docs
  WHERE (seguradora IS NOT NULL)
  GROUP BY seguradora
  ORDER BY (sum(premio)) DESC NULLS LAST;


ALTER VIEW public.v_producao_seguradora OWNER TO sierra;

--
-- Name: v_ranking_clientes; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_ranking_clientes AS
 SELECT cliente,
    cpf_cnpj,
    count(*) AS total_apolices,
    count(*) FILTER (WHERE (fim_vigencia >= CURRENT_DATE)) AS apolices_ativas,
    sum(premio) AS premio_total,
    sum(comissao) AS comissao_total,
    min(inicio_vigencia) AS cliente_desde,
    array_agg(DISTINCT ramo) AS ramos,
    array_agg(DISTINCT seguradora) AS seguradoras
   FROM public.corp_clientes_docs
  WHERE (cliente IS NOT NULL)
  GROUP BY cliente, cpf_cnpj
  ORDER BY (sum(premio)) DESC NULLS LAST;


ALTER VIEW public.v_ranking_clientes OWNER TO sierra;

--
-- Name: v_renovacoes_pendentes; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_renovacoes_pendentes AS
 SELECT cliente,
    cpf_cnpj,
    seguradora,
    ramo,
    apolice,
    inicio_vigencia,
    fim_vigencia,
    premio,
    comissao,
    produtor,
    (fim_vigencia - CURRENT_DATE) AS dias_para_vencer,
        CASE
            WHEN ((fim_vigencia - CURRENT_DATE) <= 30) THEN '🔴 URGENTE (30 dias)'::text
            WHEN ((fim_vigencia - CURRENT_DATE) <= 60) THEN '🟡 ATENÇÃO (60 dias)'::text
            WHEN ((fim_vigencia - CURRENT_DATE) <= 90) THEN '🟢 PLANEJAMENTO (90 dias)'::text
            ELSE NULL::text
        END AS prioridade
   FROM public.corp_clientes_docs
  WHERE (((fim_vigencia >= CURRENT_DATE) AND (fim_vigencia <= (CURRENT_DATE + '90 days'::interval))) AND ((status IS NULL) OR ((status)::text <> ALL ((ARRAY['Cancelado'::character varying, 'CANCELADO'::character varying, 'Devolvido'::character varying])::text[]))))
  ORDER BY fim_vigencia;


ALTER VIEW public.v_renovacoes_pendentes OWNER TO sierra;

--
-- Name: v_resumo_geral; Type: VIEW; Schema: public; Owner: sierra
--

CREATE VIEW public.v_resumo_geral AS
 SELECT ( SELECT count(*) AS count
           FROM public.corp_clientes_docs) AS total_registros,
    ( SELECT count(DISTINCT corp_clientes_docs.cliente) AS count
           FROM public.corp_clientes_docs
          WHERE (corp_clientes_docs.cliente IS NOT NULL)) AS total_clientes,
    ( SELECT count(*) AS count
           FROM public.corp_clientes_docs
          WHERE (corp_clientes_docs.fim_vigencia >= CURRENT_DATE)) AS apolices_vigentes,
    ( SELECT count(*) AS count
           FROM public.corp_clientes_docs
          WHERE ((corp_clientes_docs.fim_vigencia >= CURRENT_DATE) AND (corp_clientes_docs.fim_vigencia <= (CURRENT_DATE + 30)))) AS vencem_30_dias,
    ( SELECT count(*) AS count
           FROM public.corp_clientes_docs
          WHERE ((corp_clientes_docs.fim_vigencia >= CURRENT_DATE) AND (corp_clientes_docs.fim_vigencia <= (CURRENT_DATE + 60)))) AS vencem_60_dias,
    ( SELECT count(*) AS count
           FROM public.corp_clientes_docs
          WHERE ((corp_clientes_docs.fim_vigencia >= CURRENT_DATE) AND (corp_clientes_docs.fim_vigencia <= (CURRENT_DATE + 90)))) AS vencem_90_dias,
    ( SELECT sum(corp_clientes_docs.premio) AS sum
           FROM public.corp_clientes_docs
          WHERE (corp_clientes_docs.fim_vigencia >= CURRENT_DATE)) AS premio_carteira_ativa,
    ( SELECT sum(corp_clientes_docs.comissao) AS sum
           FROM public.corp_clientes_docs
          WHERE (corp_clientes_docs.fim_vigencia >= CURRENT_DATE)) AS comissao_carteira_ativa,
    ( SELECT count(DISTINCT corp_clientes_docs.seguradora) AS count
           FROM public.corp_clientes_docs) AS total_seguradoras,
    ( SELECT count(DISTINCT corp_clientes_docs.ramo) AS count
           FROM public.corp_clientes_docs) AS total_ramos;


ALTER VIEW public.v_resumo_geral OWNER TO sierra;

--
-- Name: veiculos; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.veiculos (
    id integer NOT NULL,
    cliente_id integer,
    placa character varying(10),
    chassi character varying(30),
    marca_modelo character varying(200),
    ano_fabricacao character varying(4),
    ano_modelo character varying(4),
    cor character varying(30),
    combustivel character varying(30),
    cep_pernoite character varying(10),
    created_at timestamp without time zone DEFAULT now()
);


ALTER TABLE public.veiculos OWNER TO postgres;

--
-- Name: veiculos_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.veiculos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.veiculos_id_seq OWNER TO postgres;

--
-- Name: veiculos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.veiculos_id_seq OWNED BY public.veiculos.id;


--
-- Name: apolices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices ALTER COLUMN id SET DEFAULT nextval('public.apolices_id_seq'::regclass);


--
-- Name: clientes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clientes ALTER COLUMN id SET DEFAULT nextval('public.clientes_id_seq'::regclass);


--
-- Name: comissoes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comissoes ALTER COLUMN id SET DEFAULT nextval('public.comissoes_id_seq'::regclass);


--
-- Name: corp_clientes_docs id; Type: DEFAULT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_clientes_docs ALTER COLUMN id SET DEFAULT nextval('public.corp_clientes_docs_id_seq'::regclass);


--
-- Name: corp_export_raw id; Type: DEFAULT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_export_raw ALTER COLUMN id SET DEFAULT nextval('public.corp_export_raw_id_seq'::regclass);


--
-- Name: corp_relatorios id; Type: DEFAULT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_relatorios ALTER COLUMN id SET DEFAULT nextval('public.corp_relatorios_id_seq'::regclass);


--
-- Name: corretoras id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.corretoras ALTER COLUMN id SET DEFAULT nextval('public.corretoras_id_seq'::regclass);


--
-- Name: cotacao_resultados id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacao_resultados ALTER COLUMN id SET DEFAULT nextval('public.cotacao_resultados_id_seq'::regclass);


--
-- Name: cotacoes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes ALTER COLUMN id SET DEFAULT nextval('public.cotacoes_id_seq'::regclass);


--
-- Name: documentos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documentos ALTER COLUMN id SET DEFAULT nextval('public.documentos_id_seq'::regclass);


--
-- Name: usuarios id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuarios ALTER COLUMN id SET DEFAULT nextval('public.usuarios_id_seq'::regclass);


--
-- Name: veiculos id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.veiculos ALTER COLUMN id SET DEFAULT nextval('public.veiculos_id_seq'::regclass);


--
-- Data for Name: apolices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.apolices (id, corretora_id, cliente_id, veiculo_id, cotacao_id, seguradora, numero_apolice, vigencia_inicio, vigencia_fim, premio, franquia, comissao_percentual, comissao_valor, status, created_at) FROM stdin;
\.


--
-- Data for Name: clientes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.clientes (id, corretora_id, nome, cpf_cnpj, nascimento, telefone, email, cep, endereco, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: comissoes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.comissoes (id, corretora_id, apolice_id, usuario_id, seguradora, valor, percentual, parcela, total_parcelas, data_pagamento, status, created_at) FROM stdin;
\.


--
-- Data for Name: corp_clientes_docs; Type: TABLE DATA; Schema: public; Owner: sierra
--

COPY public.corp_clientes_docs (id, corretora_id, filial, nosso_numero, cliente, cpf_cnpj, seguradora, ramo, apolice, inicio_vigencia, fim_vigencia, premio, comissao, produtor, status, dados_extras, imported_at) FROM stdin;
\.


--
-- Data for Name: corp_export_raw; Type: TABLE DATA; Schema: public; Owner: sierra
--

COPY public.corp_export_raw (id, corretora_id, dados, tipo, imported_at) FROM stdin;
\.


--
-- Data for Name: corp_relatorios; Type: TABLE DATA; Schema: public; Owner: sierra
--

COPY public.corp_relatorios (id, corretora_id, periodo, mes, ano, aba, producao_total, producao_variacao, novos, novos_variacao, renovacoes, renovacoes_variacao, faturas, endossos, meta_atingida, seguradoras, ramos, demonstrativo_12m, source_file, created_at) FROM stdin;
1	1	MARÇO/2026	3	2026	Comissão	4750.43	+14,2%	924.22	-91,4%	3778.36	-85,7%	0.00	47.85	0%	\N	\N	[{"mes": "Mar/25", "valor": 40000}]	13_comissao_mar26.jpg	2026-03-07 21:09:32.382358
2	1	MARÇO/2026	3	2026	Qtde de Docs	21.00	-84.8%	6.00	-85%	12.00	-84.4%	0.00	3.00	0%	\N	\N	[{"mes": "Mar/25", "valor": 138}]	14_qtde_docs_mar26.jpg	2026-03-07 21:09:32.382358
3	1	MARÇO/2024	3	2024	Prêmio Base	253615.65	-27.9%	78493.38	-66.8%	167363.18	+46.2%	0.00	7759.09	\N	\N	\N	[{"mes": "Mar/25", "valor": 254000}]	15_premio_2025.jpg	2026-03-07 21:09:32.382358
4	1	JUNHO/2024	6	2024	Prêmio Base	597697.52	+152%	428858.18	+475%	166692.90	+2.8%	0.00	2146.44	\N	\N	\N	[{"mes": "Jun/23", "valor": 237000}, {"mes": "Jul/23", "valor": 246000}, {"mes": "Ago/23", "valor": 243000}, {"mes": "Set/23", "valor": 268000}, {"mes": "Out/23", "valor": 250000}, {"mes": "Nov/23", "valor": 349000}, {"mes": "Dez/23", "valor": 557000}, {"mes": "Jan/24", "valor": 238000}, {"mes": "Fev/24", "valor": 138000}, {"mes": "Mar/24", "valor": 254000}, {"mes": "Abr/24", "valor": 695000}, {"mes": "Mai/24", "valor": 1033000}, {"mes": "Jun/24", "valor": 598000}]	20_premio_Ago25.jpg	2026-03-07 21:09:32.382358
5	1	SETEMBRO/2024	9	2024	Prêmio Base	326330.24	+21,6%	79642.50	-37,2%	241474.64	+71,7%	0.00	5213.10	\N	\N	\N	[{"mes": "Mar/25", "valor": 254000}]	20_premio_Dez25.jpg	2026-03-07 21:09:32.382358
6	1	JANEIRO/2024	1	2024	Prêmio Base	237733.65	+32,6%	94008.36	-0,5%	137021.25	+63,1%	0.00	6704.04	\N	\N	\N	[{"mes": "Jan/23", "valor": 179000}, {"mes": "Fev/23", "valor": 541000}, {"mes": "Mar/23", "valor": 352000}]	20_premio_Fev25.jpg	2026-03-07 21:09:32.382358
7	1	FEVEREIRO/2024	2	2024	Prêmio Base	135958.12	-74.9%	35188.27	-92.4%	98848.36	+24.1%	0.00	1921.49	\N	\N	\N	[{"mes": "Fev/23", "valor": 541000}, {"mes": "Mar/25", "valor": 352000}]	20_premio_Jan25.jpg	2026-03-07 21:09:32.382358
8	1	MAIO/2024	5	2024	Prêmio Base	1032519.65	+313%	848168.26	+783%	183271.77	+19.2%	0.00	1079.62	\N	\N	\N	[{"mes": "Mar/24", "valor": 246000}]	20_premio_Jul25.jpg	2026-03-07 21:09:32.382358
9	1	ABRIL/2024	4	2024	Prêmio Base	694580.45	+250%	531685.23	+680%	161501.81	+26.2%	0.00	1393.41	\N	\N	\N	[{"mes": "Mar/25", "valor": 254000}]	20_premio_Mai25.jpg	2026-03-07 21:09:32.382358
10	1	JULHO/2024	7	2024	Prêmio Base	710415.44	+189%	482886.45	+557%	224628.21	+32.5%	0.00	2900.78	\N	\N	\N	[{"mes": "Jul/23", "valor": 246000}, {"mes": "Ago/23", "valor": 243000}, {"mes": "Set/23", "valor": 268000}, {"mes": "Out/23", "valor": 250000}, {"mes": "Nov/23", "valor": 349000}, {"mes": "Dez/23", "valor": 557000}, {"mes": "Jan/24", "valor": 238000}, {"mes": "Fev/24", "valor": 138000}, {"mes": "Mar/24", "valor": 254000}, {"mes": "Abr/24", "valor": 695000}, {"mes": "Mai/24", "valor": 1033000}, {"mes": "Jun/24", "valor": 598000}, {"mes": "Jul/24", "valor": 710000}]	20_premio_Set25.jpg	2026-03-07 21:09:32.382358
11	1	MARÇO/2024	3	2024	Comissão	43102.27	17%	12413.88	-37.4%	29128.39	62.8%	0.00	1560.00	\N	\N	\N	\N	21_comissao_Abr25.jpg	2026-03-07 21:09:32.382358
12	1	JUNHO/2024	6	2024	Comissão	39410.59	6,6%	13298.22	10,5%	25672.57	3,1%	0.00	439.80	\N	\N	\N	\N	21_comissao_Ago25.jpg	2026-03-07 21:09:32.382358
13	1	SETEMBRO/2024	9	2024	Comissão	52.17	16.0%	11.12	30.4%	40.31	14.0%	0.00	739.89	\N	\N	\N	[{"mes": "Set/23", "valor": 40000}, {"mes": "Out/23", "valor": 39000}, {"mes": "Nov/23", "valor": 58000}, {"mes": "Dez/23", "valor": 47000}, {"mes": "Jan/24", "valor": 35000}, {"mes": "Fev/24", "valor": 24000}, {"mes": "Mar/24", "valor": 43000}, {"mes": "Abr/24", "valor": 42000}, {"mes": "Mai/24", "valor": 46000}, {"mes": "Jun/24", "valor": 39000}, {"mes": "Jul/24", "valor": 56000}, {"mes": "Ago/24", "valor": 47000}, {"mes": "Set/24", "valor": 52000}]	21_comissao_Dez25.jpg	2026-03-07 21:09:32.382358
14	1	JANEIRO/2024	1	2024	Comissão	34645.37	+14.6%	12354.15	-6.5%	21496.56	+15.7%	0.00	794.66	\N	\N	\N	[{"mes": "Jan/23", "valor": 26000}, {"mes": "Fev/23", "valor": 34000}, {"mes": "Mar/23", "valor": 38000}, {"mes": "Abr/23", "valor": 32000}, {"mes": "Mai/23", "valor": 36000}, {"mes": "Jun/23", "valor": 36000}, {"mes": "Jul/23", "valor": 39000}, {"mes": "Ago/23", "valor": 38000}, {"mes": "Set/23", "valor": 40000}, {"mes": "Out/23", "valor": 39000}, {"mes": "Nov/23", "valor": 58000}, {"mes": "Dez/23", "valor": 47000}, {"mes": "Jan/24", "valor": 35000}]	21_comissao_Fev25.jpg	2026-03-07 21:09:32.382358
15	1	AGOSTO/2024	8	2024	Comissão	46.61	+16.2%	13.30	+16.3%	32.53	+16.2%	0.00	785.81	\N	\N	\N	\N	21_comissao_Jan25.jpg	2026-03-07 21:09:32.382358
16	1	MAIO/2024	5	2024	Comissão	46.19	+4,5%	12.94	+1,5%	32.93	+18%	0.00	323.19	\N	\N	\N	\N	21_comissao_Jul25.jpg	2026-03-07 21:09:32.382358
17	1	ABRIL/2024	4	2024	Comissão	41995.84	6%	12139.88	29,3%	29492.46	23,1%	0.00	363.50	\N	\N	\N	[{"mes": "Mar/24", "valor": 43000}]	21_comissao_Mai25.jpg	2026-03-07 21:09:32.382358
18	1	FEVEREIRO/2024	2	2024	Comissão	23491.31	17,3%	6125.38	-72,2%	16531.07	43,3%	0.00	834.86	\N	\N	\N	[{"mes": "Mar/23", "valor": 38000}]	21_comissao_Mar25.jpg	2026-03-07 21:09:32.382358
19	1	JULHO/2024	7	2024	Comissão	55506.11	7,8%	18699.12	3,9%	36114.43	16,1%	0.00	692.56	\N	\N	\N	\N	21_comissao_Set25.jpg	2026-03-07 21:09:32.382358
20	1	MARÇO/2024	3	2024	Qtde de Docs	155.00	+32.5%	44.00	-15.4%	89.00	+50.8%	0.00	22.00	\N	\N	\N	[{"mes": "Mar/23", "valor": 117}]	22_qtde_Abr25.jpg	2026-03-07 21:09:32.382358
21	1	JUNHO/2024	6	2024	Qtde de Docs	123.00	+35.2%	29.00	+45%	81.00	+14.1%	0.00	13.00	\N	\N	\N	\N	22_qtde_Ago25.jpg	2026-03-07 21:09:32.382358
22	1	SETEMBRO/2024	9	2024	Qtde de Docs	138.00	+38%	35.00	+9.4%	85.00	+34.9%	0.00	18.00	\N	\N	\N	[{"mes": "Mar/25", "valor": 155}]	22_qtde_Dez25.jpg	2026-03-07 21:09:32.382358
23	1	JANEIRO/2024	1	2024	Qtde de Docs	115.00	+42%	32.00	+0%	68.00	+41.7%	0.00	15.00	\N	\N	\N	[{"mes": "Mar/23", "valor": 117}]	22_qtde_Fev25.jpg	2026-03-07 21:09:32.382358
24	1	AGOSTO/2024	8	2024	Qtde de Docs	138.00	+22.1%	32.00	-8.6%	90.00	+28.6%	0.00	16.00	\N	\N	\N	\N	22_qtde_Jan25.jpg	2026-03-07 21:09:32.382358
25	1	MAIO/2024	5	2024	Qtde de Docs	125.00	+45.3%	34.00	+61.9%	79.00	+23.4%	0.00	12.00	\N	\N	\N	[{"mes": "Mar/25", "valor": 155}]	22_qtde_Jul25.jpg	2026-03-07 21:09:32.382358
26	1	ABRIL/2024	4	2024	Qtde de Docs	133.00	+33%	40.00	+29%	81.00	+24.6%	0.00	12.00	\N	\N	\N	[{"mes": "Abr/23", "valor": 100}, {"mes": "Mai/23", "valor": 86}, {"mes": "Jun/23", "valor": 91}, {"mes": "Jul/23", "valor": 116}, {"mes": "Ago/23", "valor": 113}, {"mes": "Set/23", "valor": 100}, {"mes": "Out/23", "valor": 114}, {"mes": "Nov/23", "valor": 91}, {"mes": "Dez/23", "valor": 129}, {"mes": "Jan/24", "valor": 115}, {"mes": "Fev/24", "valor": 94}, {"mes": "Mar/24", "valor": 155}, {"mes": "Abr/24", "valor": 133}]	22_qtde_Mai25.jpg	2026-03-07 21:09:32.382358
27	1	FEVEREIRO/2024	2	2024	Qtde de Docs	98.00	+36.1%	22.00	-21.4%	54.00	+28.6%	0.00	22.00	\N	\N	\N	\N	22_qtde_Mar25.jpg	2026-03-07 21:09:32.382358
28	1	JULHO/2024	7	2024	Qtde de Docs	172.00	+48.3%	53.00	+60.6%	95.00	+25%	0.00	24.00	\N	\N	\N	[{"mes": "Mar/25", "valor": 155}]	22_qtde_Set25.jpg	2026-03-07 21:09:32.382358
\.


--
-- Data for Name: corretoras; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.corretoras (id, nome, cnpj, regiao, telefone, email, created_at, active) FROM stdin;
1	Sierra Seguros	\N	Caxias do Sul / Serra Gaúcha, RS	\N	\N	2026-03-07 18:50:03.094929	t
\.


--
-- Data for Name: cotacao_resultados; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cotacao_resultados (id, cotacao_id, seguradora, premio, franquia, parcelas, numero_cotacao, mensagem, status, created_at) FROM stdin;
\.


--
-- Data for Name: cotacoes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.cotacoes (id, corretora_id, usuario_id, cliente_id, veiculo_id, tipo, status, cnh_data, crvl_data, condutor_data, cep_pernoite, agilizador_url, created_at) FROM stdin;
\.


--
-- Data for Name: documentos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.documentos (id, cliente_id, tipo, arquivo_path, dados_extraidos, created_at) FROM stdin;
\.


--
-- Data for Name: usuarios; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.usuarios (id, corretora_id, nome, email, senha_hash, role, telegram_id, telefone, active, created_at, last_login) FROM stdin;
3	1	Maurício	\N	\N	corretor	\N	\N	t	2026-03-07 18:50:03.095721	\N
4	1	Carole	\N	\N	operacional	\N	\N	t	2026-03-07 18:50:03.095721	\N
5	1	Kênia	\N	\N	operacional	\N	\N	t	2026-03-07 18:50:03.095721	\N
6	1	Amanda	\N	\N	operacional	\N	\N	t	2026-03-07 18:50:03.095721	\N
1	1	Eduardo	contato@sierraseguros.com.br	$2b$12$cGAfKHOTcQUXBsU9kS0f1O1p/cyI1J6Gk4F1nssR2nH0/GjbD/95u	admin	2104676074	\N	t	2026-03-07 18:50:03.095721	2026-03-07 18:54:25.697301
2	1	Fabrício (Fafá)	fafa@sierraseguros.com.br	$2b$12$cGAfKHOTcQUXBsU9kS0f1O1p/cyI1J6Gk4F1nssR2nH0/GjbD/95u	admin	6553672222	\N	t	2026-03-07 18:50:03.095721	2026-03-07 19:06:14.33043
\.


--
-- Data for Name: veiculos; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.veiculos (id, cliente_id, placa, chassi, marca_modelo, ano_fabricacao, ano_modelo, cor, combustivel, cep_pernoite, created_at) FROM stdin;
\.


--
-- Name: apolices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.apolices_id_seq', 1, false);


--
-- Name: clientes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.clientes_id_seq', 1, false);


--
-- Name: comissoes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.comissoes_id_seq', 1, false);


--
-- Name: corp_clientes_docs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: sierra
--

SELECT pg_catalog.setval('public.corp_clientes_docs_id_seq', 1, false);


--
-- Name: corp_export_raw_id_seq; Type: SEQUENCE SET; Schema: public; Owner: sierra
--

SELECT pg_catalog.setval('public.corp_export_raw_id_seq', 1, false);


--
-- Name: corp_relatorios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: sierra
--

SELECT pg_catalog.setval('public.corp_relatorios_id_seq', 28, true);


--
-- Name: corretoras_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.corretoras_id_seq', 1, true);


--
-- Name: cotacao_resultados_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cotacao_resultados_id_seq', 1, false);


--
-- Name: cotacoes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.cotacoes_id_seq', 1, false);


--
-- Name: documentos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.documentos_id_seq', 1, false);


--
-- Name: usuarios_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.usuarios_id_seq', 6, true);


--
-- Name: veiculos_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.veiculos_id_seq', 1, false);


--
-- Name: apolices apolices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices
    ADD CONSTRAINT apolices_pkey PRIMARY KEY (id);


--
-- Name: clientes clientes_corretora_id_cpf_cnpj_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clientes
    ADD CONSTRAINT clientes_corretora_id_cpf_cnpj_key UNIQUE (corretora_id, cpf_cnpj);


--
-- Name: clientes clientes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clientes
    ADD CONSTRAINT clientes_pkey PRIMARY KEY (id);


--
-- Name: comissoes comissoes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comissoes
    ADD CONSTRAINT comissoes_pkey PRIMARY KEY (id);


--
-- Name: corp_clientes_docs corp_clientes_docs_pkey; Type: CONSTRAINT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_clientes_docs
    ADD CONSTRAINT corp_clientes_docs_pkey PRIMARY KEY (id);


--
-- Name: corp_export_raw corp_export_raw_pkey; Type: CONSTRAINT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_export_raw
    ADD CONSTRAINT corp_export_raw_pkey PRIMARY KEY (id);


--
-- Name: corp_relatorios corp_relatorios_pkey; Type: CONSTRAINT; Schema: public; Owner: sierra
--

ALTER TABLE ONLY public.corp_relatorios
    ADD CONSTRAINT corp_relatorios_pkey PRIMARY KEY (id);


--
-- Name: corretoras corretoras_cnpj_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.corretoras
    ADD CONSTRAINT corretoras_cnpj_key UNIQUE (cnpj);


--
-- Name: corretoras corretoras_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.corretoras
    ADD CONSTRAINT corretoras_pkey PRIMARY KEY (id);


--
-- Name: cotacao_resultados cotacao_resultados_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacao_resultados
    ADD CONSTRAINT cotacao_resultados_pkey PRIMARY KEY (id);


--
-- Name: cotacoes cotacoes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes
    ADD CONSTRAINT cotacoes_pkey PRIMARY KEY (id);


--
-- Name: documentos documentos_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documentos
    ADD CONSTRAINT documentos_pkey PRIMARY KEY (id);


--
-- Name: usuarios usuarios_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_email_key UNIQUE (email);


--
-- Name: usuarios usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_pkey PRIMARY KEY (id);


--
-- Name: usuarios usuarios_telegram_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_telegram_id_key UNIQUE (telegram_id);


--
-- Name: veiculos veiculos_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.veiculos
    ADD CONSTRAINT veiculos_pkey PRIMARY KEY (id);


--
-- Name: idx_apolices_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apolices_status ON public.apolices USING btree (status);


--
-- Name: idx_apolices_vigencia; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_apolices_vigencia ON public.apolices USING btree (vigencia_fim);


--
-- Name: idx_clientes_corretora; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_clientes_corretora ON public.clientes USING btree (corretora_id);


--
-- Name: idx_clientes_cpf; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_clientes_cpf ON public.clientes USING btree (cpf_cnpj);


--
-- Name: idx_corp_cd_apolice; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_apolice ON public.corp_clientes_docs USING btree (apolice);


--
-- Name: idx_corp_cd_cliente; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_cliente ON public.corp_clientes_docs USING btree (cliente);


--
-- Name: idx_corp_cd_cpf; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_cpf ON public.corp_clientes_docs USING btree (cpf_cnpj);


--
-- Name: idx_corp_cd_ramo; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_ramo ON public.corp_clientes_docs USING btree (ramo);


--
-- Name: idx_corp_cd_seguradora; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_seguradora ON public.corp_clientes_docs USING btree (seguradora);


--
-- Name: idx_corp_cd_status; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_status ON public.corp_clientes_docs USING btree (status);


--
-- Name: idx_corp_cd_vigencia; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_cd_vigencia ON public.corp_clientes_docs USING btree (inicio_vigencia, fim_vigencia);


--
-- Name: idx_corp_rel_periodo; Type: INDEX; Schema: public; Owner: sierra
--

CREATE INDEX idx_corp_rel_periodo ON public.corp_relatorios USING btree (ano, mes, aba);


--
-- Name: idx_cotacoes_cliente; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_cotacoes_cliente ON public.cotacoes USING btree (cliente_id);


--
-- Name: idx_cotacoes_corretora; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_cotacoes_corretora ON public.cotacoes USING btree (corretora_id);


--
-- Name: idx_cotacoes_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_cotacoes_status ON public.cotacoes USING btree (status);


--
-- Name: idx_usuarios_telegram; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_usuarios_telegram ON public.usuarios USING btree (telegram_id);


--
-- Name: idx_veiculos_placa; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_veiculos_placa ON public.veiculos USING btree (placa);


--
-- Name: apolices apolices_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices
    ADD CONSTRAINT apolices_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id);


--
-- Name: apolices apolices_corretora_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices
    ADD CONSTRAINT apolices_corretora_id_fkey FOREIGN KEY (corretora_id) REFERENCES public.corretoras(id);


--
-- Name: apolices apolices_cotacao_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices
    ADD CONSTRAINT apolices_cotacao_id_fkey FOREIGN KEY (cotacao_id) REFERENCES public.cotacoes(id);


--
-- Name: apolices apolices_veiculo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.apolices
    ADD CONSTRAINT apolices_veiculo_id_fkey FOREIGN KEY (veiculo_id) REFERENCES public.veiculos(id);


--
-- Name: clientes clientes_corretora_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clientes
    ADD CONSTRAINT clientes_corretora_id_fkey FOREIGN KEY (corretora_id) REFERENCES public.corretoras(id);


--
-- Name: comissoes comissoes_apolice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comissoes
    ADD CONSTRAINT comissoes_apolice_id_fkey FOREIGN KEY (apolice_id) REFERENCES public.apolices(id);


--
-- Name: comissoes comissoes_corretora_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comissoes
    ADD CONSTRAINT comissoes_corretora_id_fkey FOREIGN KEY (corretora_id) REFERENCES public.corretoras(id);


--
-- Name: comissoes comissoes_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.comissoes
    ADD CONSTRAINT comissoes_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: cotacao_resultados cotacao_resultados_cotacao_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacao_resultados
    ADD CONSTRAINT cotacao_resultados_cotacao_id_fkey FOREIGN KEY (cotacao_id) REFERENCES public.cotacoes(id) ON DELETE CASCADE;


--
-- Name: cotacoes cotacoes_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes
    ADD CONSTRAINT cotacoes_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id);


--
-- Name: cotacoes cotacoes_corretora_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes
    ADD CONSTRAINT cotacoes_corretora_id_fkey FOREIGN KEY (corretora_id) REFERENCES public.corretoras(id);


--
-- Name: cotacoes cotacoes_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes
    ADD CONSTRAINT cotacoes_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.usuarios(id);


--
-- Name: cotacoes cotacoes_veiculo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.cotacoes
    ADD CONSTRAINT cotacoes_veiculo_id_fkey FOREIGN KEY (veiculo_id) REFERENCES public.veiculos(id);


--
-- Name: documentos documentos_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.documentos
    ADD CONSTRAINT documentos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id);


--
-- Name: usuarios usuarios_corretora_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.usuarios
    ADD CONSTRAINT usuarios_corretora_id_fkey FOREIGN KEY (corretora_id) REFERENCES public.corretoras(id);


--
-- Name: veiculos veiculos_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.veiculos
    ADD CONSTRAINT veiculos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.clientes(id);


--
-- Name: TABLE apolices; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.apolices TO sierra;


--
-- Name: SEQUENCE apolices_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.apolices_id_seq TO sierra;


--
-- Name: TABLE clientes; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.clientes TO sierra;


--
-- Name: SEQUENCE clientes_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.clientes_id_seq TO sierra;


--
-- Name: TABLE comissoes; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.comissoes TO sierra;


--
-- Name: SEQUENCE comissoes_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.comissoes_id_seq TO sierra;


--
-- Name: TABLE corretoras; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.corretoras TO sierra;


--
-- Name: SEQUENCE corretoras_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.corretoras_id_seq TO sierra;


--
-- Name: TABLE cotacao_resultados; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.cotacao_resultados TO sierra;


--
-- Name: SEQUENCE cotacao_resultados_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.cotacao_resultados_id_seq TO sierra;


--
-- Name: TABLE cotacoes; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.cotacoes TO sierra;


--
-- Name: SEQUENCE cotacoes_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.cotacoes_id_seq TO sierra;


--
-- Name: TABLE documentos; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.documentos TO sierra;


--
-- Name: SEQUENCE documentos_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.documentos_id_seq TO sierra;


--
-- Name: TABLE usuarios; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.usuarios TO sierra;


--
-- Name: SEQUENCE usuarios_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.usuarios_id_seq TO sierra;


--
-- Name: TABLE veiculos; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.veiculos TO sierra;


--
-- Name: SEQUENCE veiculos_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON SEQUENCE public.veiculos_id_seq TO sierra;


--
-- PostgreSQL database dump complete
--

\unrestrict jw8Pj03AWaYkdxH6bSOQ97B4kjTksKnRxg0W8fe8vKgFrSeMMP95xPEqYqHA3rx

