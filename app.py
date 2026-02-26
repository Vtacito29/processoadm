"""Arquivo: app.py | Objetivo: Aplicacao Flask completa para gestao de processos, usuarios, importacao/exportacao e historico."""
"""
Aplicacao Flask para controlar o ciclo de vida de processos entre gerencias.

- Configuracoes e constantes de ambiente
- Models SQLAlchemy (Usuario, Processo, Movimentacao, CampoExtra)
- Funcoes utilitarias (normalizacao, datas, ilustracoes)
- Rotas Flask (dashboard, gerencia, autenticacao, CRUD de processos)
- Inicializacao do app/banco e filtros de template
"""

import json
import logging
import os
import secrets
import re
import sys
import site
import tempfile
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

import pandas as pd
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    send_file,
    jsonify,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text, or_, cast
from sqlalchemy.orm import joinedload, selectinload
from werkzeug.security import check_password_hash, generate_password_hash
# removed upload feature

# === Caminhos e constantes basicas ===
# Caminho base do projeto e local do banco SQLite
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "controle_processos.db")
# Caminho onde as imagens de ilustracao ficam armazenadas
STATIC_IMG_DIR = os.path.join(BASE_DIR, "static", "img")
INTERESSADOS_PATH = os.path.join(BASE_DIR, "interessados.txt")

# Importacao com mapeamento de colunas
IMPORT_CACHE_DIR = os.path.join(BASE_DIR, "tmp_imports")
IMPORT_CACHE_TTL_MIN = 90
IMPORT_CACHE: Dict[str, Dict[str, object]] = {}
OPENPYXL_MIN_VERSION = "3.1.5"
MAX_IMPORT_FILE_SIZE_MB = 50
IMPORT_COMMIT_BATCH_DEFAULT = 250


def _env_int(nome: str, padrao: int) -> int:
    """Le inteiro de variavel de ambiente com fallback seguro."""
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao

IMPORT_FIELDS = [
    ("numero_sei", "Número SEI"),
    ("assunto", "Assunto"),
    ("interessado", "Interessado"),
    ("concessionaria", "Concessionaria"),
    ("gerencia", "Gerência"),
    ("data_entrada", "Data de entrada"),
    ("prazo", "Prazo"),
    ("responsavel_adm", "Responsavel ADM"),
    ("observacao", "Observacao"),
    ("observacoes_complementares", "Observacoes complementares"),
    ("coordenadoria", "Coordenadoria"),
    ("equipe_area", "Equipe / Area"),
    ("responsavel_equipe", "Responsavel equipe"),
    ("tipo_processo", "Tipo de processo"),
    ("palavras_chave", "Palavras-chave"),
    ("status", "Status"),
    ("data_status", "Data status"),
    ("prazo_equipe", "Prazo equipe"),
    ("tramitado_para", "Tramitado para"),
    ("classificacao_institucional", "Classificacao institucional"),
    ("descricao_melhorada", "Descricao melhorada"),
    ("finalizado_em", "Finalizado em"),
    ("finalizado_por", "Finalizado por"),
    ("data_saida", "Data de saída"),
]

ALIAS_PARA_CAMPO = {
    "NUMERO SEI": "numero_sei",
    "NÚMERO SEI": "numero_sei",
    "NUMERO PROCESSO SEI": "numero_sei",
    "NÚMERO PROCESSO SEI": "numero_sei",
    "PROCESSO SEI": "numero_sei",
    "SEI": "numero_sei",
    "ASSUNTO": "assunto",
    "INTERESSADO": "interessado",
    "CONCESSIONARIA": "concessionaria",
    "GERENCIA": "gerencia",
    "GERÊNCIA": "gerencia",
    "DATA ENTRADA": "data_entrada",
    "DATA DE ENTRADA": "data_entrada",
    "ENTRADA": "data_entrada",
    "PRAZO": "prazo",
    "PRAZO SUROD": "prazo",
    "RESPONSAVEL ADM": "responsavel_adm",
    "PLANILHADO POR": "responsavel_adm",
    "OBSERVACAO": "observacao",
    "OBSERVACOES": "observacao",
    "OBSERVACOES COMPLEMENTARES": "observacoes_complementares",
    "COORDENADORIA": "coordenadoria",
    "EQUIPE AREA": "equipe_area",
    "RESPONSAVEL EQUIPE": "responsavel_equipe",
    "TIPO DE PROCESSO": "tipo_processo",
    "PALAVRAS CHAVE": "palavras_chave",
    "STATUS": "status",
    "DATA STATUS": "data_status",
    "PRAZO EQUIPE": "prazo_equipe",
    "TRAMITADO PARA": "tramitado_para",
    "CLASSIFICACAO INSTITUCIONAL": "classificacao_institucional",
    "DESCRICAO MELHORADA": "descricao_melhorada",
    "FINALIZADO EM": "finalizado_em",
    "FINALIZADO POR": "finalizado_por",
    "DATA SAIDA": "data_saida",
    "DATA DE SAIDA": "data_saida",
    "DATA SAÍDA": "data_saida",
    "DATA DE SAÍDA": "data_saida",
}

# Conjunto de gerencias conhecidas (ENTRADA apenas para normalizacao antiga)
# Conjunto completo utilizado para normalizacao de nomes de gerencias
GERENCIAS_CANONICAS = ["ENTRADA", "GABINETE", "GEENG", "GEPLAN", "GEDEX", "GEFOR", "SAIDA"]
GERENCIA_PADRAO = "GABINETE"
GERENCIAS_REVISAO = ["SAIDA"]
GERENCIAS = [ger for ger in GERENCIAS_CANONICAS if ger not in {"ENTRADA", "SAIDA"}]
GERENCIAS_DESTINOS = GERENCIAS + GERENCIAS_REVISAO
GERENCIA_ALIAS_GABINETE = "Acessoria Técnica"
GERENCIAS_TRAMITE_EXIBICAO = (
    ["SAIDA"]
    + [ger for ger in GERENCIAS if ger != "GABINETE"]
    + [GERENCIA_ALIAS_GABINETE]
)
ORDEM_GERENCIAS = {ger: idx for idx, ger in enumerate(GERENCIAS)}

# Quando verdadeiro, o site opera em modo "vitrine" sem ler/escrever dados reais.
# Quando true, app roda em modo vitrine (sem escrever no banco)
SITE_EM_CONFIGURACAO = (
    os.environ.get("SITE_EM_CONFIGURACAO", "0").strip().lower()
    in {"1", "true", "on", "yes"}
)
# Quando true, zera e recria as tabelas ao subir a aplicacao
RESET_DATABASE_ON_START = (
    os.environ.get("RESET_DATABASE_ON_START", "0").strip().lower()
    in {"1", "true", "on", "yes"}
)
AUTO_CORRIGIR_DADOS_ON_START = (
    os.environ.get("AUTO_CORRIGIR_DADOS_ON_START", "0").strip().lower()
    in {"1", "true", "on", "yes"}
)
MAX_IMPORT_FILE_SIZE_BYTES = max(1, _env_int("MAX_IMPORT_FILE_SIZE_MB", MAX_IMPORT_FILE_SIZE_MB)) * 1024 * 1024
IMPORT_COMMIT_BATCH_SIZE = max(1, _env_int("IMPORT_COMMIT_BATCH_SIZE", IMPORT_COMMIT_BATCH_DEFAULT))

ILUSTRACAO_FORMATOS_SUPORTADOS = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")
CAMPO_EXTRA_TIPOS = {
    "texto": "Texto livre",
    "numero": "Número",
    "data": "Data",
}
CONCESSIONARIAS = [
    "N/A",
    "TODAS",
    "L01 - AUTOBAN",
    "L03 - TEBE",
    "L05 - VIANORTE",
    "L06 - INTERVIAS",
    "L07 - ROTA DAS BANDEIRAS",
    "L08 - TRIANGULO DO SOL",
    "L11 - RENOVIAS",
    "L12 - VIAOESTE",
    "L13 - COLINAS",
    "L16 - CART",
    "L19 - VIA RONDON",
    "L20 - SPVIAS",
    "L21 - RODOVIAS DO TIETE",
    "L22 - ECOVIAS IMIGRANTES",
    "L23 - ECOVIAS LESTE PAULISTA",
    "L24 - RODOANEL OESTE",
    "L25 - SPMAR",
    "L26 - VIA SP SERRA - RODOANEL NORTE",
    "L27 - TAMOIOS",
    "L28 - ENTREVIAS",
    "L29 - VIAPAULISTA",
    "L30 - EIXOSP",
    "L31 - ECOVIAS NOROESTE PAULISTA",
    "L32 - NOVO LITORAL",
    "L33 - ROTA SOROCABANA",
    "L34 - ECOVIAS RAPOSO CASTELLO",
]
TIPOS_PROCESSO = [
    "POE",
    "PROJETO DE LEI",
    "EVENTO",
    "QUALIFICAÇÃO TÉCNICA",
    "SIC",
    "JUDICIAL",
    "JUDICIAL-ISENÇÃO",
    "SOLICITAÇÃO TÉCNICA",
    "PLEITO DE REEQUILÍBRIO - EVASÃO",
    "PEDIDO DE ISENÇÃO",
    "PLEITO DE REEQUILÍBRIO - EIXOS SUSPENSOS",
    "IMPLANTAÇÃO",
    "CSP - OBRIGAÇÃO CONTRATUAL",
    "PLEITO DE REEQUILÍBRIO - PAP",
    "IMPLANTAÇÃO / ADEQUAÇÃO APÓS OBRAS",
    "REVITALIZAÇÃO (COMPROVAÇÃO)",
    "REVITALIZAÇÃO (ESCOPO E COMPROVAÇÃO)",
    "DESLIGAMENTO DEFINITIVO (COMPROVAÇÃO)",
    "DEMANDA DE ALTERAÇÃO CONTRATUAL",
    "FREE FLOW",
    "MEDIÇÃO",
    "RAIA - INCIDENTE ADMINISTRATIVO",
    "POC - PROOF OF CONCEPT",
    "CIRCULAR",
    "RESPOSTA DE PROCESSO PILOTO",
    "ÁRVORE DECISÓRIA - ATENDIMENTO",
    "PF",
    "PE",
    "AB",
    "SOLICITAÇÃO DE INFORMAÇÃO",
    "PARLAMENTAR",
    "PLEITO",
]
# Status variam por gerencia; ajuste as listas conforme necessario.
STATUS_POR_GERENCIA = {
    "GABINETE": [
        "EM ANÁLISE",
        "FINALIZADO",
        "SOBRESTADO",
        "NÃO PERTINENTE",
        "ARQUIVO SUROD",
    ],
    "GEENG": [
        "EM FILA DE ANÁLISE",
        "EM ANÁLISE",
        "AGUARDANDO RETORNO DA CONCESSIONÁRIA",
        "TRAMITADO PARA O GAB.-SUROD",
        "TRAMITADO PARA A GEDEX",
        "TRAMITADO PARA A GEFOR",
        "TRAMITADO PARA A GEPLAN",
        "SOBRESTADO",
        "TRAMITADO PARA OUTRA ÁREA/SETOR",
        "ARQUIVO",
        "FINALIZADO",
    ],
    "GEPLAN": [
        "EM FILA DE ANÁLISE",
        "EM ANÁLISE",
        "AGUARDANDO RETORNO DA CONCESSIONÁRIA",
        "TRAMITADO PARA O GAB.-SUROD",
        "TRAMITADO PARA A GEENG",
        "TRAMITADO PARA A GEFOR",
        "TRAMITADO PARA A GEDEX",
        "SOBRESTADO",
        "TRAMITADO PARA A SUTID",
        "AGUARDANDO RETORNO DA GERÊNCIA",
        "FINALIZADO",
    ],
    "GEDEX": [
        "EM FILA DE ANÁLISE",
        "EM ANÁLISE",
        "AGUARDANDO RETORNO DA CONCESSIONÁRIA",
        "AGUARDANDO SUBSÍDIO DE OUTRA ÁREA",
        "TRAMITADO PARA O GAB.-SUROD",
        "TRAMITADO PARA A GEENG",
        "TRAMITADO PARA A GEFOR",
        "TRAMITADO PARA A GEPLAN",
        "SOBRESTADO",
        "ARQUIVADO",
        "CONCLUIDO POR ORIENTAÇÃO",
        "FINALIZADO",
    ],
    "GEFOR": [
        "EM FILA DE ANÁLISE",
        "EM ANÁLISE",
        "AGUARDANDO ASSINATURA",
        "ASSINADO",
        "AGUARDANDO RETORNO DA CONCESSIONÁRIA",
        "AGUARDANDO RETORNO DE OUTRA ÁREA",
        "SOBRESTADO",
        "TRATADO EM OUTRO PROCESSO",
        "ARQUIVADO",
        "CONTROLADO EM OUTRA PLANILHA",
        "TRAMITADO PARA O GAB.-SUROD",
        "TRAMITADO PARA A GEENG",
        "TRAMITADO PARA A GEPLAN",
        "TRAMITADO PARA A GEDEX",
        "FINALIZADO",
    ],
}
CLASSIFICACOES_INSTITUCIONAIS = [
    "GAB-SUROD",
    "TJSP",
    "TCE",
    "MPSP",
    "SPI",
    "FALASP.GOV_SP",
    "DIRETORIA_RAQUEL",
    "DIRETORIA_SANTI",
    "DIRETORIA_DIEGO",
    "DIRETORIA_FERNANDA",
    "PRE_GAB",
    "DIRETOR_PRESIDENTE",
    "CSP",
    "PROMOTORIA DE JUSTIÇA",
    "ALESP",
    "PGE",
    "P/ DELIBERAÇÃO_CONSELHO",
    "PRE-GAB-ARI",
    "DEMANDA_PARLAMENTAR",
]
DESTINOS_SAIDA = [
    "GABINETE DA PRESIDÊNCIA",
    "GAB/DIÁRIO OFICIAL",
    "GAB/COOR. CONTROLE EXTERNO",
    "GAB/REUNIÃO DO CONSELHO DIRETOR",
    "GAB/ASSESSORIA DA COMUNICAÇÃO CERIMÔNIAL",
    "GAB/CJ",
    "OUVIDORIA",
    "SUTID",
    "SUADI",
    "SUREF",
    "SUINV",
    "SUSAM",
    "SUHID",
    "SUAEP",
    "SUCOL",
    "ASRIN",
    "SUADI/CEDOC ARQUIVO",
    "DIRETORIA_RAQUEL",
    "DIRETORIA_SANTI",
    "DIRETORIA_DIEGO",
    "DIRETORIA_FERNANDA",
    "GAB/ ASS. DE RELAÇÕES INTITUCIONAIS",
    "CEDOC CADASTRO",
    "SUROD ARQUIVO",
    "SUMEF",
    "SUADI/SERV",
    "GAB/ PREMIO CONCESSIONÁRIA DO ANO",
    "EXTERNO",
    "SUROD",
]
COORDENADORIAS_POR_GERENCIA = {
    "GABINETE": ["GAB_ASSESSORIA"],
    "GEDEX": ["GEDEX_ASSESSORIA"],
    "GEPLAN": ["COTEC", "COREG"],
    "GEFOR": ["COFOR", "COFIR", "COFEX"],
    "GEENG": ["COINT", "COPRO", "GEENG_ADM"],
}
EQUIPES_POR_COORDENADORIA = {
    "GAB_ASSESSORIA": ["ASSESSORIA_TÉCNICA", "ASSESSORIA_ADMINISTRATIVA"],
    "GEDEX_ASSESSORIA": ["SANCIONATÓRIO", "SEGUROS", "CONTROLE_EXTERNO", "NORMATIVO"],
    "COTEC": [
        "LT_01",
        "LT_06",
        "LT_07",
        "LT_11",
        "LT_12",
        "LT_13",
        "LT_16",
        "LT_19",
        "LT_20",
        "LT_21",
        "LT_22",
        "LT_23",
        "LT_24",
        "LT_25",
        "LT_26",
        "LT_27",
        "LT_28",
        "LT_29",
        "LT_30",
        "LT_31",
        "LT_32",
        "LT_33",
        "LT_34",
    ],
    "COREG": ["REGULATÓRIO"],
    "COFOR": [
        "EQUIPAMENTOS_COFOR",
        "OPERAÇÕES",
        "TÚNEIS",
        "PEDÁGIO",
        "PESAGEM",
        "ISENÇÃO_DE_PEDÁGIO",
        "SAU",
        "TECNOLOGIA",
    ],
    "COFIR": ["CONTRATOS", "INVESTIMENTOS", "SOLICITAÇÕES_EXTERNAS"],
    "COFEX": ["CONSERVAÇÃO", "CRONOGRAMA"],
    "COINT": ["ACESSOS", "FAIXA_DE_DOMINIO", "GEOMETRIA", "TRAFEGO", "SINALIZAÇÃO_E_SEGURANÇA_VIARIA"],
    "COPRO": ["DRENAGEM", "PAVIMENTO", "OAE", "EQUIPAMENTOS_COPRO", "GEOTECNIA"],
    "GEENG_ADM": ["ADM"],
}
RESPONSAVEIS_POR_EQUIPE = {
    "EQUIPAMENTOS_COFOR": ["MARCILIO", "BRUNO", "FABRICIO", "JOSÉ TAVARES"],
    "OPERAÇÕES": ["DIONATA", "JOSÉ TAVARES", "JOÃO", "RAFAELA"],
    "PESAGEM": ["ANA CINTHIA", "JOSÉ TAVARES"],
    "TÚNEIS": ["BENICIO", "BRUNA", "JOSÉ TAVARES"],
    "PEDÁGIO": ["LINCOLN SEIJI", "BEATRIZ BELLUZZO", "MATHEUS RODRIGUES", "JOSÉ TAVARES"],
    "ISENÇÃO_DE_PEDÁGIO": ["JOSÉ TAVARES", "GABRIELLY OLIVEIRA", "MARCUS VINICIUS"],
    "SAU": ["JOSÉ TAVARES", "NATHALIA", "JEAN", "ANA CINTHIA"],
    "TECNOLOGIA": ["JOSÉ TAVARES", "VICTOR HUGO"],
    "CONTRATOS": ["JOSÉ TAVARES", "MARCOS TADEU", "ANA BEATRIZ", "GUILHERME FORTE"],
    "INVESTIMENTOS": ["JOSÉ TAVARES", "MARCOS TADEU", "SUELI ALVES", "GUILHERME FORTE"],
    "SOLICITAÇÕES_EXTERNAS": ["JOSÉ TAVARES", "MARCOS TADEU", "SUELI ALVES", "GUILHERME FORTE"],
    "CONSERVAÇÃO": [
        "DIEGO MANTOVANI",
        "ANDRESSA CAROLINE",
        "FERNANDO CARLOS",
        "MARCIA CRISTINA",
        "JEAN LUCAS",
        "JOSÉ GLEISSON",
        "SAMUEL DUTRA",
        "ANDRÉ JOSÉ",
        "ANTONIO ISRAEL",
        "GREYCE YAMASCHITA",
        "ARIVALDO ROBERTO",
        "WALYSON HENRIQUE",
        "JOSÉ TAVARES",
    ],
    "CRONOGRAMA": [
        "BENICIO JUNIOR",
        "JOSÉ TAVARES",
        "ANDRÉ JOSÉ",
        "ANDRESSA CAROLINE",
        "ANTONIO ISRAEL",
        "ARIVALDO ROBERTO",
        "DIEGO MANTOVANI",
        "GREYCE YAMASCHITA",
        "JEAN LUCAS",
        "JOSÉ GLEISSON",
        "MARCIA CRISTINA",
        "SAMUEL DUTRA",
        "WALYSON HENRIQUE",
        "FERNANDO CARLOS",
    ],
    "ACESSOS": [
        "ANTONIO CARLOS ROMANO",
        "THIAGO LOPES DA ROCHA",
        "ANA CANDIDA ALVES DA COSTA ANTUNES",
        "CAROLINE RODRIGUES MENDES",
        "MARCELE BRAVO",
    ],
    "FAIXA_DE_DOMINIO": [
        "JOSÉ EDUARDO SARDEIRO RORIZ",
        "JOSÉ CARLOS DE CASTRO FERREIRA FILHO",
        "MARCELE BRAVO",
    ],
    "GEOMETRIA": [
        "MARIA MARTHA IERVOLINO P. SICILIANO",
        "BRUNO FORNAZIERO MATEUS",
        "GIOVANNA DA CONCEIÇÃO MASSAFERA PAIVA",
        "MARCELE BRAVO",
    ],
    "TRAFEGO": ["DAIANE FÁVARO", "MARCELE BRAVO", "WANDERSON HUGUS"],
    "SINALIZAÇÃO_E_SEGURANÇA_VIARIA": [
        "LEONARDO HITOSHI HOTTA",
        "ANGELA GOMES DE MELO",
        "MÚCIO JOSÉ TEODORO DA CUNHA",
        "ALESSANDRE ADLER AMORIM",
        "BRUNA YUKIKO UEMURA UEDA",
        "MARCELE BRAVO",
    ],
    "DRENAGEM": ["FLAVIO JOSÉ ARAUJO", "MARCELE BRAVO", "NAYARA YOKOYAMA"],
    "PAVIMENTO": [
        "ADRIAN GRASSON FILHO",
        "ANA LUISA ARANHA",
        "LADY DAYANA VEGA RODRIGUEZ",
        "MARCELE BRAVO",
        "NAYARA YOKOYAMA",
        "ALISSON ALBERTO",
    ],
    "OAE": [
        "JONAS TEIXEIRA DE VASCONCELOS",
        "HERMAN PICCININ PAGOTTO",
        "MARCELE BRAVO",
        "NAYARA YOKOYAMA",
    ],
    "EQUIPAMENTOS_COPRO": ["ANDRE FAGUNDES DA ROCHA", "MARCELE BRAVO", "NAYARA YOKOYAMA"],
    "GEOTECNIA": [
        "ALISSON ALBERTO DE LIMA MEDEIROS",
        "MARCELE BRAVO",
        "NAYARA YOKOYAMA",
        "CARLOS EDUARDO",
    ],
    "ADM": ["MARCELE BRAVO", "NAYARA YOKOYAMA", "LETICIA ROCHA"],
    "SANCIONATÓRIO": [
        "THIAGO ALVARES",
        "EDUARDO SIMON",
        "ZILÁ",
        "ANNA CAROLINA",
        "JORGE SAD",
        "JOSIANE SANTOS",
        "BERNARDO GUERRA",
    ],
    "SEGUROS": ["JULIEL OLIVEIRA", "MARCIA TEODORO", "CAROLINE DRUMOND", "BERNARDO GUERRA"],
    "CONTROLE_EXTERNO": ["VINICIUS SYBILLA", "CARLA NOGUEIRÃO", "FABIANA VARONE", "BERNARDO GUERRA"],
    "NORMATIVO": ["THIAGO ALVARES", "BERNARDO GUERRA", "SIDNEY JUNIOR", "FABIANA VARONE", "EDUARDO SIMON"],
    "CRONOGRAMA_COTEC": [
        "ALICE TELES",
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
        "JOICE SANTOS",
    ],
    "REGULATÓRIO": ["ALICE TELES", "PAULA", "LETICIA"],
    "LT_01": [
        "ALICE TELES",
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_06": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_07": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_11": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_12": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_13": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_16": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_19": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_20": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_21": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_22": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_23": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_24": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_25": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_26": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_27": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_28": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_29": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_30": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_31": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_32": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_33": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "LT_34": [
        "THAIS",
        "ANDRÉ",
        "SUSANA",
        "LUCIANE",
        "FABRICIO",
        "CAROL LOUISE",
        "GREYCE E ISRAEL",
        "ANA CAROLINA",
        "GUSTAVO GIAMPA",
        "NATERCIA",
        "RANDI",
    ],
    "ASSESSORIA_TÉCNICA": ["RONI ARAUJO", "CAMILA"],
    "ASSESSORIA_ADMINISTRATIVA": ["HEBERTY", "ANTONIO MARCOS", "NILMA BRITO", "MARCOS VICENTE"],
}
RESPONSAVEIS_ADM = [
    "HEBERTY",
    "ANTONIO MARCOS",
    "MARCOS VICENTE",
    "NILMA BRITO",
    "CARLA",
    "LETICIA ROCHA",
    "DAIANE FIALHO",
    "MARIA CAROLINA",
    "RODRIGO ASSIS",
]


def _carregar_lista_texto(caminho: str) -> List[str]:
    if not os.path.isfile(caminho):
        return []
    with open(caminho, "r", encoding="utf-8") as arquivo:
        linhas = [linha.strip() for linha in arquivo if linha.strip()]
    vistos = set()
    resultado = []
    for linha in linhas:
        if linha in vistos:
            continue
        vistos.add(linha)
        resultado.append(linha)
    return resultado


INTERESSADOS = _carregar_lista_texto(INTERESSADOS_PATH)



def _slugificar(valor: str) -> str:
    """Gera um identificador simplificado (minusculo e sem acentos)."""
    if not valor:
        return ""
    normalizado = unicodedata.normalize("NFKD", valor)
    return "".join(char for char in normalizado if char.isalnum()).lower()


def _gerar_senha_temporaria(nome: str, data_base: Optional[datetime] = None) -> str:
    """Cria uma senha padrao baseada no primeiro nome e data de criacao."""
    data_ref = data_base or datetime.utcnow()
    primeiro_nome = (limpar_texto(nome).split() or [""])[0]
    primeiro_nome = _slugificar(primeiro_nome) or "usuario"
    return f"{primeiro_nome}{data_ref:%d%m%Y}"


# === Ilustracoes por gerencia (assets estaticos) ===
def _listar_ilustracoes_disponiveis() -> Dict[str, str]:
    """Monta um dicionario slug->caminho relativo para as imagens existentes."""
    ilustracoes = {}
    pasta_gerencias = os.path.join(STATIC_IMG_DIR, "gerencias")
    if not os.path.isdir(pasta_gerencias):
        return ilustracoes

    for nome_arquivo in os.listdir(pasta_gerencias):
        _, extensao = os.path.splitext(nome_arquivo)
        if extensao.lower() not in ILUSTRACAO_FORMATOS_SUPORTADOS:
            continue
        slug = _slugificar(os.path.splitext(nome_arquivo)[0])
        caminho_relativo = os.path.join("gerencias", nome_arquivo).replace("\\", "/")
        ilustracoes.setdefault(slug, caminho_relativo)
    return ilustracoes


def _resolver_ilustracao_por_slug(slug: str, disponiveis: Dict[str, str]) -> Optional[str]:
    """Busca uma ilustracao correspondente ao slug informado."""
    if not slug:
        return None
    return disponiveis.get(slug)


def _resolver_ilustracoes_por_gerencia(disponiveis: Dict[str, str]) -> Dict[str, str]:
    """Mapeia cada gerencia para o arquivo de ilustracao disponivel."""
    ilustracoes = {}
    for gerencia in GERENCIAS:
        slug = _slugificar(gerencia)
        ilustracao = _resolver_ilustracao_por_slug(slug, disponiveis)
        if ilustracao:
            ilustracoes[gerencia] = ilustracao
    return ilustracoes


def buscar_usuario_por_login(identificador: str) -> Optional["Usuario"]:
    """Busca usuario pelo username ou email."""
    if not identificador:
        return None
    identificador = identificador.strip().lower()
    usuario = (
        Usuario.query.filter(func.lower(Usuario.username) == identificador).first()
    )
    if not usuario and "@" in identificador:
        usuario = (
            Usuario.query.filter(func.lower(Usuario.email) == identificador).first()
        )
    return usuario


def gerar_username_unico(nome: str, email: str) -> str:
    """Gera um username unico a partir do nome ou email."""
    base = _slugificar(nome) or _slugificar(email.split("@")[0] if email else "")
    if not base:
        base = f"user{int(datetime.utcnow().timestamp())}"
    username = base
    contador = 1
    while buscar_usuario_por_login(username):
        username = f"{base}{contador}"
        contador += 1
    return username


def usuario_pode_configurar_campos(gerencia: Optional[str]) -> bool:
    """Verifica se o usuario atual pode gerenciar campos extras de uma gerencia."""
    if not gerencia or not current_user.is_authenticated:
        return False
    if usuario_tem_acesso_total():
        return True
    return current_user.is_gerente and usuario_pode_editar_gerencia(gerencia)


def usuario_tem_acesso_total(usuario: Optional["Usuario"] = None) -> bool:
    """Retorna se o usuario possui permissao total (acesso_total)."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    return bool(getattr(usuario_ref, "acesso_total", False))


def _normalizar_lista_gerencias(valores: List[str]) -> List[str]:
    """Normaliza e remove duplicidades de uma lista de gerencias."""
    normalizadas: List[str] = []
    for valor in valores or []:
        ger = normalizar_gerencia(valor, permitir_entrada=True)
        if ger and ger not in normalizadas:
            normalizadas.append(ger)
    return normalizadas


def serializar_gerencias_liberadas(gerencias: List[str]) -> Optional[str]:
    """Serializa gerencias liberadas em JSON para persistencia."""
    lista = _normalizar_lista_gerencias(gerencias)
    if not lista:
        return None
    return json.dumps(lista, ensure_ascii=False)


def obter_gerencias_liberadas_usuario(usuario: Optional["Usuario"] = None) -> List[str]:
    """Retorna as gerencias em que o usuario pode atuar."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return []
    if usuario_tem_acesso_total(usuario_ref):
        return [g for g in GERENCIAS_DESTINOS]

    gerencias: List[str] = []
    bruto = getattr(usuario_ref, "gerencias_liberadas", None)
    if bruto:
        try:
            dados = json.loads(bruto)
            if isinstance(dados, list):
                gerencias.extend([str(item) for item in dados if item])
        except Exception:
            gerencias.extend([parte.strip() for parte in str(bruto).split(",") if parte.strip()])

    ger_padrao = normalizar_gerencia(
        getattr(usuario_ref, "gerencia_padrao", None), permitir_entrada=True
    )
    if ger_padrao:
        gerencias.append(ger_padrao)
    return _normalizar_lista_gerencias(gerencias)


def usuario_tem_liberacao_gerencia(
    gerencia: Optional[str], usuario: Optional["Usuario"] = None
) -> bool:
    """Confere se o usuario possui liberacao para a gerencia informada."""
    ger_alvo = normalizar_gerencia(gerencia, permitir_entrada=True)
    if not ger_alvo:
        return False
    gerencias = set(obter_gerencias_liberadas_usuario(usuario))
    return ger_alvo in gerencias


def usuario_eh_admin_principal(usuario: Optional["Usuario"] = None) -> bool:
    """Confere se o usuario corresponde ao admin principal configurado."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    if bool(getattr(usuario_ref, "is_admin_principal", False)):
        return True
    alvo_username = normalizar_chave(DEFAULT_ADMIN_USER or "")
    alvo_email = (DEFAULT_ADMIN_EMAIL or "").strip().lower()
    username_ref = normalizar_chave(getattr(usuario_ref, "username", "") or "")
    email_ref = (getattr(usuario_ref, "email", "") or "").strip().lower()
    if alvo_username and username_ref == alvo_username:
        return True
    if alvo_email and email_ref == alvo_email:
        return True
    return False


def usuario_pode_conceder_acesso_total(usuario: Optional["Usuario"] = None) -> bool:
    """Permite conceder acesso total para admin principal e acesso total."""
    return usuario_tem_acesso_total(usuario) or usuario_eh_admin_principal(usuario)


def usuario_pode_excluir_usuarios(usuario: Optional["Usuario"] = None) -> bool:
    """Permite excluir usuarios para admin principal e acesso total."""
    return usuario_tem_acesso_total(usuario) or usuario_eh_admin_principal(usuario)


def usuario_pode_editar_gerencia(
    gerencia: Optional[str], usuario: Optional["Usuario"] = None
) -> bool:
    """Permite editar/tramitar somente a gerencia do usuario."""
    usuario_ref = usuario or current_user
    if not gerencia or not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    if usuario_tem_acesso_total(usuario_ref):
        return True

    gerencia_alvo = normalizar_gerencia(gerencia, permitir_entrada=True)
    gerencias_usuario = set(obter_gerencias_liberadas_usuario(usuario_ref))
    if not gerencia_alvo or not gerencias_usuario:
        return False
    if gerencia_alvo in gerencias_usuario:
        return True
    if "GABINETE" in gerencias_usuario and gerencia_alvo == "SAIDA":
        return True
    return False


def usuario_pode_editar_processo(
    processo: Optional["Processo"], usuario: Optional["Usuario"] = None
) -> bool:
    """Permissao de edicao em nivel de processo."""
    if not processo:
        return False
    return usuario_pode_editar_gerencia(processo.gerencia, usuario=usuario)


def usuario_pode_cadastrar_processo(usuario: Optional["Usuario"] = None) -> bool:
    """Define se o usuario pode cadastrar novos processos."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    if usuario_tem_acesso_total(usuario_ref):
        return True
    return bool(
        getattr(usuario_ref, "is_admin", False) or getattr(usuario_ref, "is_gerente", False)
    )


def usuario_pode_finalizar_gerencia(usuario: Optional["Usuario"] = None) -> bool:
    """Define se o usuario pode finalizar/tramitar processos na propria gerencia."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    if usuario_tem_acesso_total(usuario_ref):
        return True
    return bool(getattr(usuario_ref, "pode_finalizar_gerencia", True))


def usuario_pode_exportar_global(usuario: Optional["Usuario"] = None) -> bool:
    """Permite exportar relatorios gerais conforme permissao explicitada."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    return usuario_tem_acesso_total(usuario_ref)


def usuario_pode_importar_global(usuario: Optional["Usuario"] = None) -> bool:
    """Permite importar planilhas gerais conforme permissao explicitada."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    return usuario_tem_acesso_total(usuario_ref)


def usuario_pode_exportar_gerencia(
    gerencia: Optional[str], usuario: Optional["Usuario"] = None
) -> bool:
    """Permite exportar relatorios da gerencia quando permitido."""
    if not gerencia:
        return False
    usuario_ref = usuario or current_user
    if not usuario_pode_editar_gerencia(gerencia, usuario=usuario_ref):
        return False
    if usuario_tem_acesso_total(usuario_ref):
        return True
    return bool(
        getattr(usuario_ref, "is_admin", False) or getattr(usuario_ref, "is_gerente", False)
    )


def _permissoes_por_perfil(perfil: Optional[str]) -> Dict[str, bool]:
    """Define permissões adicionais a partir do perfil selecionado."""
    perfil_norm = (perfil or "usuario").strip().lower()
    if perfil_norm == "acesso_total":
        return {"cadastrar": True, "exportar": True, "importar": True}
    if perfil_norm == "admin":
        return {"cadastrar": True, "exportar": True, "importar": True}
    if perfil_norm == "gerente":
        return {"cadastrar": True, "exportar": True, "importar": False}
    return {"cadastrar": False, "exportar": False, "importar": False}


def usuario_pode_cadastrar_usuarios(usuario: Optional["Usuario"] = None) -> bool:
    """Define se o usuario pode cadastrar novos usuarios."""
    usuario_ref = usuario or current_user
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return False
    if usuario_tem_acesso_total(usuario_ref):
        return True
    if usuario_eh_admin_principal(usuario_ref):
        return True
    return bool(
        getattr(usuario_ref, "is_admin", False) or getattr(usuario_ref, "is_gerente", False)
    )


def perfis_disponiveis_para_usuario(
    usuario: Optional["Usuario"] = None,
) -> List[tuple]:
    """Lista perfis permitidos para quem esta cadastrando."""
    usuario_ref = usuario or current_user
    labels = {
        "usuario": "Usuário",
        "gerente": "Gerente",
        "acesso_total": "Acesso total",
        "admin": "Assessoria",
    }
    if not usuario_ref or not getattr(usuario_ref, "is_authenticated", False):
        return [("usuario", labels["usuario"])]
    if usuario_eh_admin_principal(usuario_ref):
        return [
            ("usuario", labels["usuario"]),
            ("gerente", labels["gerente"]),
            ("admin", labels["admin"]),
            ("acesso_total", labels["acesso_total"]),
        ]
    if getattr(usuario_ref, "is_admin", False):
        return [
            ("usuario", labels["usuario"]),
            ("gerente", labels["gerente"]),
            ("admin", labels["admin"]),
        ]
    if usuario_tem_acesso_total(usuario_ref):
        return [
            ("usuario", labels["usuario"]),
            ("gerente", labels["gerente"]),
            ("admin", labels["admin"]),
            ("acesso_total", labels["acesso_total"]),
        ]
    if getattr(usuario_ref, "is_gerente", False):
        return [
            ("usuario", labels["usuario"]),
            ("gerente", labels["gerente"]),
        ]
    return [("usuario", labels["usuario"])]


def _montar_opcoes_usuario_cadastro() -> tuple[
    List[str], Dict[str, List[str]], List[str], Dict[str, List[str]], Dict[str, List[str]]
]:
    """Monta opcoes e sugestoes para tela de cadastro de usuarios."""
    coords_coletadas: List[str] = []
    mapa_equipes: Dict[str, List[str]] = {}
    mapa_equipes_slugs: Dict[str, Set[str]] = {}
    chave_coord_por_slug: Dict[str, str] = {}
    coordenadorias_por_gerencia: Dict[str, List[str]] = {}
    coordenadorias_por_gerencia_slugs: Dict[str, Set[str]] = {}
    pessoas_por_gerencia: Dict[str, List[str]] = {}
    pessoas_por_gerencia_slugs: Dict[str, Set[str]] = {}

    def _registrar_coord_em_gerencia(gerencia: Optional[str], coord_valor: Optional[str]) -> None:
        ger = normalizar_gerencia(gerencia, permitir_entrada=True)
        coord = limpar_texto(coord_valor, "")
        if not ger or not coord:
            return
        lista = coordenadorias_por_gerencia.setdefault(ger, [])
        slugs = coordenadorias_por_gerencia_slugs.setdefault(ger, set())
        slug = normalizar_chave(coord)
        if slug in slugs:
            return
        slugs.add(slug)
        lista.append(coord)

    def _registrar_pessoa_em_gerencia(gerencia: Optional[str], nome_valor: Optional[str]) -> None:
        ger = normalizar_gerencia(gerencia, permitir_entrada=True)
        nome = limpar_texto(nome_valor, "")
        if not ger or not nome:
            return
        lista = pessoas_por_gerencia.setdefault(ger, [])
        slugs = pessoas_por_gerencia_slugs.setdefault(ger, set())
        slug = normalizar_chave(nome)
        if slug in slugs:
            return
        slugs.add(slug)
        lista.append(nome)

    def _registrar_coord(valor: Optional[str]) -> None:
        coord = limpar_texto(valor, "")
        if not coord:
            return
        slug = normalizar_chave(coord)
        if slug in chave_coord_por_slug:
            return
        chave_coord_por_slug[slug] = coord
        coords_coletadas.append(coord)

    def _registrar_equipe(coord_valor: Optional[str], equipe_valor: Optional[str]) -> None:
        coord = limpar_texto(coord_valor, "")
        equipe = limpar_texto(equipe_valor, "")
        if not coord or not equipe:
            return
        _registrar_coord(coord)
        chave_coord = chave_coord_por_slug.get(normalizar_chave(coord), coord)
        lista = mapa_equipes.setdefault(chave_coord, [])
        slugs = mapa_equipes_slugs.setdefault(chave_coord, set())
        slug_equipe = normalizar_chave(equipe)
        if slug_equipe not in slugs:
            slugs.add(slug_equipe)
            lista.append(equipe)

    for _, coords in COORDENADORIAS_POR_GERENCIA.items():
        for coord in coords:
            _registrar_coord(coord)
    for ger, coords in COORDENADORIAS_POR_GERENCIA.items():
        for coord in coords:
            _registrar_coord_em_gerencia(ger, coord)

    for coord, equipes in EQUIPES_POR_COORDENADORIA.items():
        _registrar_coord(coord)
        for equipe in equipes:
            _registrar_equipe(coord, equipe)

    for usuario in Usuario.query.order_by(Usuario.nome.asc()).all():
        _registrar_coord(usuario.coordenadoria)
        _registrar_equipe(usuario.coordenadoria, usuario.equipe_area)
        _registrar_coord_em_gerencia(usuario.gerencia_padrao, usuario.coordenadoria)

    pares_processo = db.session.query(
        Processo.gerencia,
        Processo.coordenadoria,
        Processo.equipe_area,
        Processo.responsavel_adm,
        Processo.responsavel_equipe,
    ).all()
    for ger, coord, equipe, resp_adm, resp_eq in pares_processo:
        _registrar_coord(coord)
        _registrar_equipe(coord, equipe)
        _registrar_coord_em_gerencia(ger, coord)

    for ger in GERENCIAS_DESTINOS:
        for nome_resp in obter_responsaveis_por_gerencia(ger):
            _registrar_pessoa_em_gerencia(ger, nome_resp)

    coordenadorias = _ordenar_nomes_unicos(coords_coletadas)
    equipes_unicas = _ordenar_nomes_unicos(
        [item for itens in mapa_equipes.values() for item in itens]
    )
    mapa_ordenado = {
        coord: _ordenar_nomes_unicos(mapa_equipes.get(coord, []))
        for coord in coordenadorias
    }
    coordenadorias_ger_map = {
        ger: _ordenar_nomes_unicos(coords)
        for ger, coords in coordenadorias_por_gerencia.items()
    }
    pessoas_ger_map = {
        ger: _ordenar_nomes_unicos(nomes)
        for ger, nomes in pessoas_por_gerencia.items()
    }
    return coordenadorias, mapa_ordenado, equipes_unicas, coordenadorias_ger_map, pessoas_ger_map


def coletar_dados_extra_form(gerencia: Optional[str], origem: Dict[str, str]) -> Dict[str, str]:
    """Coleta valores de campos extras submetidos via formulario."""
    if not gerencia:
        return {}
    dados = {}
    for campo in listar_campos_gerencia(gerencia):
        chave = f"extra_{campo.slug}"
        valor_bruto = origem.get(chave)
        if valor_bruto is None or str(valor_bruto).strip() == "":
            continue
        valor = str(valor_bruto).strip()
        if campo.tipo == "data":
            data = parse_date(valor)
            if data:
                dados[campo.slug] = data.strftime("%Y-%m-%d")
        else:
            dados[campo.slug] = valor
    return dados


def serializar_campos_extra(campos: List["CampoExtra"]) -> List[Dict[str, str]]:
    """Transforma objetos CampoExtra em estruturas simples."""
    return [
        {"id": campo.id, "slug": campo.slug, "label": campo.label, "tipo": campo.tipo}
        for campo in campos
    ]


def gerar_mapa_campos_extra() -> Dict[str, List[Dict[str, str]]]:
    """Retorna mapa gerencia->campos extras serializados."""
    return {
        gerencia: serializar_campos_extra(lista)
        for gerencia, lista in obter_campos_por_gerencia().items()
    }


def obter_campos_por_gerencia() -> Dict[str, List["CampoExtra"]]:
    """Retorna os campos extras agrupados pela gerencia."""
    campos = CampoExtra.query.order_by(CampoExtra.criado_em.asc()).all()
    agrupados: Dict[str, List[CampoExtra]] = defaultdict(list)
    for campo in campos:
        agrupados[campo.gerencia].append(campo)
    return agrupados


def listar_campos_gerencia(gerencia: str) -> List["CampoExtra"]:
    """Retorna campos configurados para uma gerencia especifica."""
    if not gerencia:
        return []
    return CampoExtra.query.filter_by(gerencia=gerencia).order_by(CampoExtra.criado_em.asc()).all()


def obter_status_por_gerencia(gerencia: Optional[str]) -> List[str]:
    """Retorna status configurados para a gerencia informada."""
    if not gerencia:
        return []
    return STATUS_POR_GERENCIA.get(gerencia, [])


def obter_coordenadorias_por_gerencia(gerencia: Optional[str]) -> List[str]:
    """Lista coordenadorias disponiveis para a gerencia informada (fixas + dinamicas)."""
    ger_norm = normalizar_gerencia(gerencia, permitir_entrada=True)
    if not ger_norm:
        return []

    valores = list(COORDENADORIAS_POR_GERENCIA.get(ger_norm, []))
    vistos = {normalizar_chave(item) for item in valores}

    pares_usuarios = (
        db.session.query(Usuario.coordenadoria)
        .filter(Usuario.coordenadoria.isnot(None))
        .filter(func.lower(Usuario.gerencia_padrao) == ger_norm.lower())
        .all()
    )
    for (coord,) in pares_usuarios:
        coord_txt = limpar_texto(coord, "")
        if not coord_txt:
            continue
        chave = normalizar_chave(coord_txt)
        if chave in vistos:
            continue
        vistos.add(chave)
        valores.append(coord_txt)

    pares_processos = (
        db.session.query(Processo.coordenadoria)
        .filter(Processo.coordenadoria.isnot(None))
        .filter(func.lower(Processo.gerencia) == ger_norm.lower())
        .all()
    )
    for (coord,) in pares_processos:
        coord_txt = limpar_texto(coord, "")
        if not coord_txt:
            continue
        chave = normalizar_chave(coord_txt)
        if chave in vistos:
            continue
        vistos.add(chave)
        valores.append(coord_txt)

    return _ordenar_nomes_unicos(valores)


def obter_equipes_por_coordenadoria(coordenadoria: Optional[str]) -> List[str]:
    """Lista equipes disponiveis para a coordenadoria informada (fixas + dinamicas)."""
    coord = limpar_texto(coordenadoria, "")
    if not coord:
        return []
    coord_norm = normalizar_chave(coord)

    coord_chave = next(
        (item for item in EQUIPES_POR_COORDENADORIA if normalizar_chave(item) == coord_norm),
        coord,
    )
    valores = list(EQUIPES_POR_COORDENADORIA.get(coord_chave, []))
    vistos = {normalizar_chave(item) for item in valores}

    equipes_usuarios = (
        db.session.query(Usuario.equipe_area)
        .filter(Usuario.equipe_area.isnot(None))
        .filter(func.lower(Usuario.coordenadoria) == coord.lower())
        .all()
    )
    for (equipe,) in equipes_usuarios:
        equipe_txt = limpar_texto(equipe, "")
        if not equipe_txt:
            continue
        chave = normalizar_chave(equipe_txt)
        if chave in vistos:
            continue
        vistos.add(chave)
        valores.append(equipe_txt)

    equipes_processos = (
        db.session.query(Processo.equipe_area)
        .filter(Processo.equipe_area.isnot(None))
        .filter(func.lower(Processo.coordenadoria) == coord.lower())
        .all()
    )
    for (equipe,) in equipes_processos:
        equipe_txt = limpar_texto(equipe, "")
        if not equipe_txt:
            continue
        chave = normalizar_chave(equipe_txt)
        if chave in vistos:
            continue
        vistos.add(chave)
        valores.append(equipe_txt)

    return _ordenar_nomes_unicos(valores)


def obter_responsaveis_por_equipe(equipe: Optional[str]) -> List[str]:
    """Lista responsaveis disponiveis para a equipe informada."""
    equipe_txt = limpar_texto(equipe, "")
    if not equipe_txt:
        return []
    equipe_chave = next(
        (item for item in RESPONSAVEIS_POR_EQUIPE if normalizar_chave(item) == normalizar_chave(equipe_txt)),
        equipe_txt,
    )
    nomes = list(RESPONSAVEIS_POR_EQUIPE.get(equipe_chave, []))

    usuarios = (
        Usuario.query.filter(Usuario.aparece_atribuido_sei.is_(True))
        .filter(Usuario.equipe_area.isnot(None))
        .filter(func.lower(Usuario.equipe_area) == equipe_txt.lower())
        .all()
    )
    for usuario in usuarios:
        nome = limpar_texto(usuario.nome or usuario.username, "")
        if nome:
            nomes.append(nome)

    resp_processos = (
        db.session.query(Processo.responsavel_equipe)
        .filter(Processo.equipe_area.isnot(None))
        .filter(Processo.responsavel_equipe.isnot(None))
        .filter(func.lower(Processo.equipe_area) == equipe_txt.lower())
        .all()
    )
    for (nome_proc,) in resp_processos:
        nome = limpar_texto(nome_proc, "")
        if nome:
            nomes.append(nome)

    return _ordenar_nomes_unicos(nomes)


def obter_equipes_por_gerencia(gerencia: Optional[str]) -> List[str]:
    """Lista equipes disponiveis para uma gerencia."""
    coordenadorias = obter_coordenadorias_por_gerencia(gerencia)
    resultado = []
    vistos = set()
    for coord in coordenadorias:
        for equipe in obter_equipes_por_coordenadoria(coord):
            if equipe in vistos:
                continue
            vistos.add(equipe)
            resultado.append(equipe)
    return resultado


def obter_responsaveis_por_gerencia(gerencia: Optional[str]) -> List[str]:
    """Lista responsaveis disponiveis para uma gerencia."""
    equipes = obter_equipes_por_gerencia(gerencia)
    resultado = []
    vistos = set()
    for equipe in equipes:
        for responsavel in obter_responsaveis_por_equipe(equipe):
            if responsavel in vistos:
                continue
            vistos.add(responsavel)
            resultado.append(responsavel)
    ger_norm = normalizar_gerencia(gerencia, permitir_entrada=True)
    if ger_norm:
        extras = (
            db.session.query(Processo.responsavel_equipe)
            .filter(Processo.gerencia.isnot(None))
            .filter(Processo.responsavel_equipe.isnot(None))
            .filter(func.lower(Processo.gerencia) == ger_norm.lower())
            .all()
        )
        for (nome_extra,) in extras:
            nome = limpar_texto(nome_extra, "")
            if not nome or nome in vistos:
                continue
            vistos.add(nome)
            resultado.append(nome)
    return resultado


def _nome_usuario_exibicao(usuario: "Usuario") -> str:
    nome = limpar_texto(getattr(usuario, "nome", None) or getattr(usuario, "username", None) or "")
    return nome


def _normalizar_nome_usuario(valor: Optional[str]) -> str:
    texto = limpar_texto(valor, "")
    return normalizar_chave(texto) if texto else ""


def _ordenar_nomes_unicos(nomes: List[str]) -> List[str]:
    vistos = set()
    resultado: List[str] = []
    for nome in sorted([n for n in nomes if n], key=lambda item: normalizar_chave(item)):
        chave = normalizar_chave(nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(nome)
    return resultado


def listar_usuarios_por_gerencia(gerencia: Optional[str]) -> List["Usuario"]:
    """Retorna usuarios ativos da gerencia informada."""
    if not gerencia:
        return []
    usuarios = Usuario.query.order_by(Usuario.nome.asc()).all()
    return [
        usuario
        for usuario in usuarios
        if bool(getattr(usuario, "aparece_atribuido_sei", False))
        and bool(normalizar_gerencia(getattr(usuario, "gerencia_padrao", None), permitir_entrada=True))
        and usuario_tem_liberacao_gerencia(gerencia, usuario=usuario)
    ]


def obter_nomes_usuarios(usuarios: List["Usuario"]) -> List[str]:
    """Lista nomes unicos para uso em selects/datalists."""
    return _ordenar_nomes_unicos([_nome_usuario_exibicao(usuario) for usuario in usuarios])


def mapear_nomes_usuarios_por_campo(
    usuarios: List["Usuario"], campo: str
) -> Dict[str, List[str]]:
    """Agrupa nomes de usuarios pelo campo indicado (ex: coordenadoria/equipe_area)."""
    agrupados: Dict[str, List[str]] = defaultdict(list)
    for usuario in usuarios:
        chave = limpar_texto(getattr(usuario, campo, None), "")
        if not chave:
            continue
        nome = _nome_usuario_exibicao(usuario)
        if not nome:
            continue
        agrupados[chave].append(nome)
    return {chave: _ordenar_nomes_unicos(nomes) for chave, nomes in agrupados.items()}


def filtrar_usuarios_por_coordenadoria_equipe(
    usuarios: List["Usuario"],
    coordenadoria: Optional[str],
    equipe: Optional[str],
) -> List["Usuario"]:
    """Filtra usuarios por coordenadoria/equipe (quando informadas)."""
    coord_norm = _normalizar_nome_usuario(coordenadoria)
    equipe_norm = _normalizar_nome_usuario(equipe)
    if not coord_norm and not equipe_norm:
        return usuarios
    filtrados: List["Usuario"] = []
    for usuario in usuarios:
        coord_user = _normalizar_nome_usuario(getattr(usuario, "coordenadoria", None))
        equipe_user = _normalizar_nome_usuario(getattr(usuario, "equipe_area", None))
        if coord_norm and coord_user == coord_norm:
            filtrados.append(usuario)
            continue
        if equipe_norm and equipe_user == equipe_norm:
            filtrados.append(usuario)
    return filtrados


def localizar_usuario_por_texto(
    valor: str, *, gerencia: Optional[str] = None
) -> Optional["Usuario"]:
    """Localiza usuario por nome/username (aceita 'Nome (username)')."""
    texto = limpar_texto(valor, "")
    if not texto:
        return None
    nome = texto
    username = ""
    if "(" in texto and texto.endswith(")"):
        base, _, sufixo = texto.rpartition("(")
        nome = base.strip() or texto
        username = sufixo[:-1].strip()
    chave_nome = _normalizar_nome_usuario(nome)
    chave_username = _normalizar_nome_usuario(username) if username else ""
    candidatos = (
        listar_usuarios_por_gerencia(gerencia)
        if gerencia
        else Usuario.query.order_by(Usuario.nome.asc()).all()
    )
    for usuario in candidatos:
        if chave_username and _normalizar_nome_usuario(usuario.username) == chave_username:
            return usuario
        if chave_nome and _normalizar_nome_usuario(usuario.nome) == chave_nome:
            return usuario
        if chave_nome and _normalizar_nome_usuario(usuario.username) == chave_nome:
            return usuario
    return None


def usuario_permitido_para_atribuicao(
    usuario: Optional["Usuario"], processo: "Processo"
) -> bool:
    """Valida se o usuario pode receber atribuicao do processo."""
    if not usuario or not processo:
        return False
    ger_proc = normalizar_gerencia(processo.gerencia, permitir_entrada=True)
    if ger_proc and not usuario_tem_liberacao_gerencia(ger_proc, usuario=usuario):
        return False
    coord_proc = limpar_texto(processo.coordenadoria, "")
    equipe_proc = limpar_texto(processo.equipe_area, "")
    if not coord_proc and not equipe_proc:
        return True
    coord_ok = coord_proc and _normalizar_nome_usuario(getattr(usuario, "coordenadoria", None)) == _normalizar_nome_usuario(coord_proc)
    equipe_ok = equipe_proc and _normalizar_nome_usuario(getattr(usuario, "equipe_area", None)) == _normalizar_nome_usuario(equipe_proc)
    return bool(coord_ok or equipe_ok)


def listar_responsaveis_por_contexto(processo: "Processo") -> List[str]:
    """Lista responsaveis permitidos conforme coordenadoria/equipe do processo."""
    if not processo:
        return []
    equipe = limpar_texto(processo.equipe_area, "")
    if equipe:
        return obter_responsaveis_por_equipe(equipe)
    coordenadoria = limpar_texto(processo.coordenadoria, "")
    if coordenadoria:
        equipes = obter_equipes_por_coordenadoria(coordenadoria)
        nomes: List[str] = []
        for eq in equipes:
            nomes.extend(obter_responsaveis_por_equipe(eq))
        return _ordenar_nomes_unicos(nomes)
    return obter_responsaveis_por_gerencia(processo.gerencia)


def responsavel_em_lista(nome: str, processo: "Processo") -> bool:
    """Confere se o nome pertence a lista permitida do processo."""
    if not nome or not processo:
        return False
    chave = _normalizar_nome_usuario(nome)
    return any(_normalizar_nome_usuario(item) == chave for item in listar_responsaveis_por_contexto(processo))


def obter_responsaveis_adm_disponiveis() -> List[str]:
    """Lista usuarios disponiveis para responsavel ADM."""
    if RESPONSAVEIS_ADM:
        resultado = []
        vistos = set()
        for nome in RESPONSAVEIS_ADM:
            nome_limpo = (nome or "").strip()
            if not nome_limpo:
                continue
            chave = normalizar_chave(nome_limpo)
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append(nome_limpo)
        return resultado

    usuarios = Usuario.query.order_by(Usuario.nome.asc()).all()
    resultado = []
    vistos = set()
    for usuario in usuarios:
        nome = (usuario.nome or usuario.username or "").strip()
        if not nome:
            continue
        chave = normalizar_chave(nome)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(nome)
    return resultado


# === Cache de ilustracoes para uso nos templates ===
# Cache inicial das imagens encontradas no diretorio estatico
_ILUSTRACOES_DISPONIVEIS = _listar_ilustracoes_disponiveis()
# Dicionario final usado pelos templates (somente com paths existentes)
GERENCIA_ILUSTRACOES = _resolver_ilustracoes_por_gerencia(_ILUSTRACOES_DISPONIVEIS)
# Fallback utilizado quando nenhuma imagem especifica for encontrada
ILUSTRACAO_GERENCIA_PADRAO = (
    _resolver_ilustracao_por_slug("default", _ILUSTRACOES_DISPONIVEIS)
    or _ILUSTRACOES_DISPONIVEIS.get(_slugificar(GERENCIA_PADRAO))
    or next(iter(_ILUSTRACOES_DISPONIVEIS.values()), "gerencias/default.png")
)

# Credenciais padrao controladas por variaveis de ambiente
def _env_bool(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "on", "yes"}


DEFAULT_ADMIN_USER = os.environ.get("DEFAULT_ADMIN_USER", "vinicius.ferreira")
DEFAULT_ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "123")
DEFAULT_ADMIN_NAME = os.environ.get(
    "DEFAULT_ADMIN_NAME", "Vinícius Tácito Cavalcante Fereira"
)
DEFAULT_ADMIN_EMAIL = os.environ.get(
    "DEFAULT_ADMIN_EMAIL", "vinicius.ferreira@artesp.sp.gov.br"
)
DEFAULT_ADMIN_GERENCIA = os.environ.get("DEFAULT_ADMIN_GERENCIA", "GABINETE")
DEFAULT_ADMIN_COORDENADORIA = os.environ.get(
    "DEFAULT_ADMIN_COORDENADORIA", "Acessoria Técnica"
)
DEFAULT_ADMIN_EQUIPE = os.environ.get("DEFAULT_ADMIN_EQUIPE", "")
DEFAULT_ADMIN_PERFIL = os.environ.get("DEFAULT_ADMIN_PERFIL", "acesso_total").strip().lower()

# === Setup Flask, banco e autenticacao ===
# Configuracao principal do Flask
app = Flask(__name__)
database_url = os.environ.get("DATABASE_URL", "").strip()
# Render/Postgres pode fornecer URL com esquema `postgres://`, normaliza para SQLAlchemy.
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "troque-esta-chave"),
    SQLALCHEMY_DATABASE_URI=database_url or f"sqlite:///{DB_PATH}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_pre_ping": True,
    },
)
app.permanent_session_lifetime = timedelta(hours=4)
# upload configuration removed

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"


# === Models ===
class Usuario(UserMixin, db.Model):
    """Representa um usuario autenticado capaz de operar o sistema."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    nome = db.Column(db.String(120), nullable=False)
    gerencia_padrao = db.Column(db.String(50), nullable=True)
    gerencias_liberadas = db.Column(db.Text, nullable=True)
    coordenadoria = db.Column(db.String(120), nullable=True)
    equipe_area = db.Column(db.String(120), nullable=True)
    aparece_atribuido_sei = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_admin_principal = db.Column(db.Boolean, default=False)
    is_gerente = db.Column(db.Boolean, default=False)
    acesso_total = db.Column(db.Boolean, default=False)
    must_reset_password = db.Column(db.Boolean, default=False)
    pode_cadastrar_processo = db.Column(db.Boolean, default=False)
    pode_finalizar_gerencia = db.Column(db.Boolean, default=True)
    pode_exportar = db.Column(db.Boolean, default=False)
    pode_importar = db.Column(db.Boolean, default=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password: str) -> None:
        """Armazena o hash da senha informada."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Confere se a senha informada coincide com o hash salvo."""
        return check_password_hash(self.password_hash, password)


class Processo(db.Model):
    """Modelagem do processo cadastrado e movido entre gerencias."""

    __tablename__ = "processos"

    id = db.Column(db.Integer, primary_key=True)
    numero_sei = db.Column(db.String(50), unique=False, nullable=False)
    assunto = db.Column(db.String(255), nullable=False)
    interessado = db.Column(db.String(255), nullable=False)
    concessionaria = db.Column(db.String(255))
    descricao = db.Column(db.Text)
    gerencia = db.Column(db.String(50), nullable=False, default=GERENCIA_PADRAO)
    prazo = db.Column(db.Date)
    data_entrada = db.Column(db.Date)
    responsavel_adm = db.Column(db.String(255))
    observacao = db.Column(db.Text)
    data_entrada_geplan = db.Column(db.Date)
    descricao_melhorada = db.Column(db.Text)
    coordenadoria = db.Column(db.String(255))
    equipe_area = db.Column(db.String(255))
    responsavel_equipe = db.Column(db.String(255))
    tipo_processo = db.Column(db.String(255))
    palavras_chave = db.Column(db.String(255))
    status = db.Column(db.String(100))
    data_status = db.Column(db.Date)
    prazo_equipe = db.Column(db.Date)
    observacoes_complementares = db.Column(db.Text)
    data_saida = db.Column(db.Date)
    tramitado_para = db.Column(db.String(50))
    finalizado_em = db.Column(db.DateTime)
    finalizado_por = db.Column(db.String(80))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    dados_extra = db.Column(db.JSON, default=dict)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    movimentacoes = db.relationship(
        "Movimentacao",
        back_populates="processo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    assigned_to = db.relationship(
        "Usuario",
        backref="processos_atribuidos",
        lazy="joined",
        foreign_keys=[assigned_to_id],
    )

    def __repr__(self) -> str:
        return f"<Processo {self.numero_sei}>"

    @property
    def numero_sei_base(self) -> str:
        """Numero SEI sem o prefixo da gerencia (ou valor original, se houver)."""
        extras = self.dados_extra or {}
        if extras.get("numero_sei_original"):
            return str(extras["numero_sei_original"]).strip()
        numero = (self.numero_sei or "").strip()
        if "-" in numero:
            return numero.split("-", 1)[1].strip()
        return numero

    @property
    def classificacao_institucional(self) -> Optional[str]:
        """Mapeia a descricao original para o campo de classificacao institucional."""
        return self.descricao

    @classificacao_institucional.setter
    def classificacao_institucional(self, valor: Optional[str]) -> None:
        self.descricao = valor


class Movimentacao(db.Model):
    """Registra a trilha de movimentacoes e finalizacoes de um processo."""

    __tablename__ = "movimentacoes"

    id = db.Column(db.Integer, primary_key=True)
    processo_id = db.Column(
        db.Integer,
        db.ForeignKey("processos.id", ondelete="CASCADE"),
        nullable=False,
    )
    de_gerencia = db.Column(db.String(50), nullable=False)
    para_gerencia = db.Column(db.String(50), nullable=False)
    motivo = db.Column(db.Text, nullable=False)
    usuario = db.Column(db.String(80))
    # Tipo de movimentacao: 'movimentacao', 'finalizacao_gerencia', 'finalizado_geral'
    tipo = db.Column(db.String(40), default="movimentacao")
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    # Snapshot dos dados especificos da gerencia no momento da movimentacao
    dados_snapshot = db.Column(db.JSON, nullable=True)

    processo = db.relationship("Processo", back_populates="movimentacoes")

    def __repr__(self) -> str:
        return f"<Movimentacao {self.processo_id} {self.de_gerencia}->{self.para_gerencia}>"


class CampoExtra(db.Model):
    """Define campos personalizados por gerencia."""

    __tablename__ = "campos_extra"

    id = db.Column(db.Integer, primary_key=True)
    gerencia = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), nullable=False, unique=False)
    tipo = db.Column(db.String(20), nullable=False, default="texto")
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class ImportacaoTemp(db.Model):
    """Armazena arquivos temporarios de importacao para sobreviver a reinicios."""

    __tablename__ = "importacoes_temp"

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    nome_arquivo = db.Column(db.String(255), nullable=False)
    conteudo = db.Column(db.LargeBinary, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Notificacao(db.Model):
    """Avisos simples direcionados a um usuario."""

    __tablename__ = "notificacoes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    processo_id = db.Column(db.Integer, db.ForeignKey("processos.id"))
    mensagem = db.Column(db.Text, nullable=False)
    lida = db.Column(db.Boolean, default=False)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow)
    criado_por = db.Column(db.String(120))

    usuario = db.relationship("Usuario", backref="notificacoes")
    processo = db.relationship("Processo")


def registrar_notificacao(usuario: Usuario, mensagem: str, processo: Optional[Processo] = None) -> None:
    """Cria uma notificacao para um usuario."""
    if not usuario or not mensagem:
        return
    notif = Notificacao(
        user_id=usuario.id,
        mensagem=mensagem.strip(),
        processo_id=processo.id if processo else None,
        criado_por=current_user.nome if current_user and current_user.is_authenticated else None,
    )
    db.session.add(notif)
    # Commit sera realizado pelo fluxo chamador

@login_manager.user_loader
def load_user(user_id: str) -> Optional[Usuario]:
    if user_id and user_id.isdigit():
        return db.session.get(Usuario, int(user_id))
    return None


# === Hooks de requisicao e contexto ===
@app.before_request
def carregar_usuario():
    """Mantem usuario atual no contexto global e renova a sessao."""
    g.usuario = current_user if current_user.is_authenticated else None
    if current_user.is_authenticated:
        session.permanent = True


@app.before_request
def exigir_troca_senha():
    """Redireciona usuarios que precisam atualizar a senha."""
    if (
        current_user.is_authenticated
        and current_user.must_reset_password
        and request.endpoint not in {"trocar_senha", "logout", "login", "static"}
    ):
        return redirect(url_for("trocar_senha"))


@app.context_processor
def contexto_global():
    """Injeta informacoes basicas disponiveis em todos os templates."""
    notificacoes_recentes = []
    notificacoes_nao_lidas = 0
    notificacao_unread = None
    if current_user.is_authenticated and not SITE_EM_CONFIGURACAO:
        notificacoes_recentes = (
            Notificacao.query.filter_by(user_id=current_user.id)
            .order_by(Notificacao.criada_em.desc())
            .limit(15)
            .all()
        )
        notificacoes_nao_lidas = sum(1 for n in notificacoes_recentes if not n.lida)
        notificacao_unread = next((n for n in notificacoes_recentes if not n.lida), None)
    return {
        "current_user": current_user,
        "current_year": datetime.utcnow().year,
        "GERENCIAS": GERENCIAS,
        "GERENCIAS_DESTINOS": GERENCIAS_DESTINOS,
        "GERENCIAS_TRAMITE_EXIBICAO": GERENCIAS_TRAMITE_EXIBICAO,
        "GERENCIA_ALIAS_GABINETE": GERENCIA_ALIAS_GABINETE,
        "GERENCIA_PADRAO": GERENCIA_PADRAO,
        "SITE_EM_CONFIGURACAO": SITE_EM_CONFIGURACAO,
        "notificacoes_recentes": notificacoes_recentes,
        "notificacoes_nao_lidas": notificacoes_nao_lidas,
        "notificacao_unread": notificacao_unread,
        # Helper para uso em templates: data de entrada na gerencia
        "calcular_data_entrada_na_gerencia": data_entrada_na_gerencia,
    }


# === Autenticacao e perfil ===
@app.route("/login", methods=["GET", "POST"])
def login():
    """Tela de autenticacao e gestao de usuarios."""
    criacao = None
    def _perfil_usuario(usuario: "Usuario") -> str:
        if getattr(usuario, "acesso_total", False):
            return "acesso_total"
        if getattr(usuario, "is_admin", False):
            return "admin"
        if getattr(usuario, "is_gerente", False):
            return "gerente"
        return "usuario"
    if request.method == "POST":
        acao = request.form.get("form_action", "login")
        if acao == "register":
            if not current_user.is_authenticated or not usuario_pode_cadastrar_usuarios():
                abort(403)
            nome = limpar_texto(request.form.get("nome"))
            email = limpar_texto(request.form.get("email"))
            perfil = request.form.get("perfil") or "usuario"
            perfis_disponiveis = [p[0] for p in perfis_disponiveis_para_usuario(current_user)]
            if perfil not in perfis_disponiveis:
                perfil = "usuario"
            if perfil == "acesso_total" and not usuario_pode_conceder_acesso_total(current_user):
                perfil = "usuario"
            perfil_acesso_total = perfil == "acesso_total"
            gerencia_padrao = normalizar_gerencia(
                request.form.get("gerencia_padrao"), permitir_entrada=True
            )
            gerencias_form = request.form.getlist("gerencias_liberadas")
            if not gerencias_form:
                gerencias_form = request.form.getlist("gerencias")
            if not gerencias_form:
                gerencia_legacy = request.form.get("gerencia")
                if gerencia_legacy:
                    gerencias_form = [gerencia_legacy]
            gerencias_liberadas = _normalizar_lista_gerencias(gerencias_form)
            permissoes = _permissoes_por_perfil(perfil)
            perm_cadastrar = permissoes["cadastrar"]
            perm_exportar = permissoes["exportar"]
            perm_importar = permissoes["importar"]
            erros = []
            if not nome:
                erros.append("Nome")
            if not email:
                erros.append("Email")
            elif buscar_usuario_por_login(email):
                erros.append("Email (ja utilizado)")
            nome_existente = (
                Usuario.query.filter(func.lower(Usuario.nome) == nome.lower()).first()
                if nome
                else None
            )
            if nome_existente:
                erros.append("Nome (ja utilizado)")
            if not gerencias_liberadas:
                erros.append("Gerencias liberadas")
            coord = limpar_texto(request.form.get("coordenadoria"))
            equipe = limpar_texto(request.form.get("equipe_area"))
            pode_finalizar_gerencia = (
                (request.form.get("pode_finalizar_gerencia") or "0").strip().lower()
                in {"1", "true", "on", "yes"}
            )
            pode_finalizar_gerencia = True if perfil != "usuario" else pode_finalizar_gerencia
            adicionar_atribuido_sei = (
                (request.form.get("adicionar_atribuido_sei") or "0").strip().lower()
                in {"1", "true", "on", "yes"}
            )
            if erros:
                flash("Preencha corretamente: " + ", ".join(erros), "warning")
            else:
                username = gerar_username_unico(nome, email)
                senha_temporaria = _gerar_senha_temporaria(nome)
                gerencia_padrao = gerencia_padrao or None
                gerencias_serializadas = serializar_gerencias_liberadas(gerencias_liberadas)
                coord_padrao = coord
                equipe_padrao = equipe
                novo = Usuario(
                    username=username,
                    email=email,
                    nome=nome,
                    gerencia_padrao=gerencia_padrao,
                    gerencias_liberadas=gerencias_serializadas,
                    coordenadoria=coord_padrao,
                    equipe_area=equipe_padrao,
                    aparece_atribuido_sei=bool(
                        adicionar_atribuido_sei
                        and coord_padrao
                        and equipe_padrao
                    ),
                    is_admin=(perfil == "admin"),
                    is_gerente=(perfil in {"admin", "gerente"}),
                    acesso_total=(perfil == "acesso_total"),
                    must_reset_password=True,
                    pode_cadastrar_processo=perm_cadastrar,
                    pode_finalizar_gerencia=True if perfil_acesso_total else pode_finalizar_gerencia,
                    pode_exportar=perm_exportar,
                    pode_importar=perm_importar,
                )
                novo.set_password(senha_temporaria)
                db.session.add(novo)
                db.session.commit()
                criacao = {"username": username, "senha": senha_temporaria, "email": email}
                flash(
                    f"Usuário {username} criado com sucesso. Entregue a senha temporaria ao colaborador.",
                    "success",
                )
        elif acao == "update_user":
            if not current_user.is_authenticated or not usuario_pode_excluir_usuarios():
                abort(403)

            usuario_id_raw = limpar_texto(request.form.get("usuario_id"), "")
            try:
                usuario_id = int(usuario_id_raw)
            except Exception:
                usuario_id = 0
            usuario = db.session.get(Usuario, usuario_id) if usuario_id else None
            if not usuario:
                flash("Usuario nao encontrado para edicao.", "warning")
                return redirect(url_for("login", form_action="register"))
            if (
                normalizar_chave(usuario.username or "") == normalizar_chave(DEFAULT_ADMIN_USER or "")
                and not usuario_tem_acesso_total(current_user)
            ):
                flash("Nao e permitido editar o administrador principal por esta tela.", "warning")
                return redirect(url_for("login", form_action="register"))

            nome = limpar_texto(request.form.get("nome"))
            email = limpar_texto(request.form.get("email"))
            perfil = request.form.get("perfil") or "usuario"
            perfil_atual = _perfil_usuario(usuario)
            perfis_disponiveis = [p[0] for p in perfis_disponiveis_para_usuario(current_user)]
            if perfil_atual not in perfis_disponiveis:
                perfis_disponiveis.append(perfil_atual)
            if perfil not in perfis_disponiveis:
                perfil = perfil_atual
            if perfil == "acesso_total" and not usuario_pode_conceder_acesso_total(current_user):
                perfil = perfil_atual
            perfil_acesso_total = perfil == "acesso_total"

            gerencia_padrao = normalizar_gerencia(
                request.form.get("gerencia_padrao"), permitir_entrada=True
            )
            gerencias_liberadas = _normalizar_lista_gerencias(
                request.form.getlist("gerencias_liberadas")
            )
            if not gerencias_liberadas:
                gerencias_liberadas = _normalizar_lista_gerencias(request.form.getlist("gerencias"))
            coord = limpar_texto(request.form.get("coordenadoria"))
            equipe = limpar_texto(request.form.get("equipe_area"))
            pode_finalizar_gerencia = (
                (request.form.get("pode_finalizar_gerencia") or "0").strip().lower()
                in {"1", "true", "on", "yes"}
            )
            pode_finalizar_gerencia = True if perfil != "usuario" else pode_finalizar_gerencia
            erros = []
            if not nome:
                erros.append("Nome")
            if not email:
                erros.append("Email")
            else:
                email_existente = (
                    Usuario.query.filter(func.lower(Usuario.email) == email.lower())
                    .filter(Usuario.id != usuario.id)
                    .first()
                )
                if email_existente:
                    erros.append("Email (ja utilizado)")
            nome_existente = (
                Usuario.query.filter(func.lower(Usuario.nome) == nome.lower())
                .filter(Usuario.id != usuario.id)
                .first()
                if nome
                else None
            )
            if nome_existente:
                erros.append("Nome (ja utilizado)")
            if not gerencias_liberadas:
                erros.append("Gerencias liberadas")
            if erros:
                flash("Preencha corretamente: " + ", ".join(erros), "warning")
                return redirect(url_for("login", form_action="register"))

            permissoes = _permissoes_por_perfil(perfil)
            usuario.nome = nome
            usuario.email = email
            usuario.gerencia_padrao = gerencia_padrao or None
            usuario.gerencias_liberadas = serializar_gerencias_liberadas(gerencias_liberadas)
            usuario.coordenadoria = coord or None
            usuario.equipe_area = equipe or None
            usuario.is_admin = perfil == "admin"
            usuario.is_gerente = perfil in {"admin", "gerente"}
            usuario.acesso_total = perfil_acesso_total
            usuario.pode_cadastrar_processo = permissoes["cadastrar"]
            usuario.pode_finalizar_gerencia = (
                True if perfil_acesso_total else pode_finalizar_gerencia
            )
            usuario.pode_exportar = permissoes["exportar"]
            usuario.pode_importar = permissoes["importar"]
            db.session.commit()
            flash(f"Usuario {usuario.username} atualizado com sucesso.", "success")
            return redirect(url_for("login", form_action="register"))
        else:
            identificador = limpar_texto(request.form.get("username"))
            senha = request.form.get("password") or ""
            usuario = buscar_usuario_por_login(identificador)
            if usuario and usuario.check_password(senha):
                login_user(usuario, remember=bool(request.form.get("remember")))
                flash(f"Bem-vindo, {usuario.nome}.", "success")
                destino = request.args.get("next")
                if usuario.must_reset_password:
                    return redirect(url_for("trocar_senha"))
                return redirect(destino or url_for("index"))
            flash("Credenciais invalidas. Verifique login e senha.", "danger")

    pode_registrar = current_user.is_authenticated and usuario_pode_cadastrar_usuarios()
    perfis_disponiveis = (
        perfis_disponiveis_para_usuario(current_user) if pode_registrar else []
    )
    gerencia_padrao_usuario = (
        normalizar_gerencia(current_user.gerencia_padrao, permitir_entrada=True)
        if current_user.is_authenticated
        else None
    )
    gerencia_forcada = False
    pode_gerenciar_usuarios = current_user.is_authenticated and usuario_pode_excluir_usuarios()
    coordenadorias_cadastro: List[str] = []
    equipes_por_coordenadoria_cadastro: Dict[str, List[str]] = {}
    equipes_cadastro: List[str] = []
    coordenadorias_por_gerencia_cadastro: Dict[str, List[str]] = {}
    pessoas_por_gerencia_cadastro: Dict[str, List[str]] = {}
    usuarios_existentes = []
    if pode_registrar:
        (
            coordenadorias_cadastro,
            equipes_por_coordenadoria_cadastro,
            equipes_cadastro,
            coordenadorias_por_gerencia_cadastro,
            pessoas_por_gerencia_cadastro,
        ) = _montar_opcoes_usuario_cadastro()
        for usuario in Usuario.query.order_by(Usuario.nome.asc()).all():
            usuarios_existentes.append(
                {
                    "id": usuario.id,
                    "nome": usuario.nome or "",
                    "username": usuario.username or "",
                    "email": usuario.email or "",
                    "coordenadoria": usuario.coordenadoria or "",
                    "equipe_area": usuario.equipe_area or "",
                }
            )
    usuarios_para_gerenciar = []
    if pode_gerenciar_usuarios:
        for usuario in Usuario.query.order_by(Usuario.nome.asc()).all():
            usuarios_para_gerenciar.append(
                {
                    "id": usuario.id,
                    "username": usuario.username,
                    "email": usuario.email,
                    "nome": usuario.nome,
                    "coordenadoria": usuario.coordenadoria or "",
                    "equipe_area": usuario.equipe_area or "",
                    "perfil": _perfil_usuario(usuario),
                    "gerencias": obter_gerencias_liberadas_usuario(usuario),
                    "pode_finalizar_gerencia": bool(
                        getattr(usuario, "pode_finalizar_gerencia", True)
                    ),
                    "gerencia_padrao": normalizar_gerencia(
                        usuario.gerencia_padrao, permitir_entrada=True
                    ),
                }
            )
    return render_template(
        "login.html",
        pode_registrar=pode_registrar,
        criacao_usuario=criacao,
        gerencias=GERENCIAS,
        perfis_disponiveis=perfis_disponiveis,
        gerencia_forcada=gerencia_forcada,
        gerencia_padrao_usuario=gerencia_padrao_usuario,
        pode_gerenciar_usuarios=pode_gerenciar_usuarios,
        usuarios_para_gerenciar=usuarios_para_gerenciar,
        coordenadorias_cadastro=coordenadorias_cadastro,
        equipes_por_coordenadoria_cadastro=equipes_por_coordenadoria_cadastro,
        equipes_cadastro=equipes_cadastro,
        coordenadorias_por_gerencia_cadastro=coordenadorias_por_gerencia_cadastro,
        pessoas_por_gerencia_cadastro=pessoas_por_gerencia_cadastro,
        usuarios_existentes=usuarios_existentes,
    )


@app.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@login_required
def excluir_usuario(usuario_id: int):
    """Remove um usuario do sistema (apenas admin principal)."""
    if not usuario_pode_excluir_usuarios():
        abort(403)
    usuario = db.session.get(Usuario, usuario_id)
    if not usuario:
        abort(404)
    if usuario.id == current_user.id:
        flash("Voce nao pode excluir o proprio usuario.", "warning")
        return redirect(url_for("login", form_action="register"))
    if (
        normalizar_chave(usuario.username or "") == normalizar_chave(DEFAULT_ADMIN_USER or "")
        and not usuario_tem_acesso_total(current_user)
    ):
        flash("Nao e permitido excluir o admin principal.", "warning")
        return redirect(url_for("login", form_action="register"))

    Processo.query.filter(Processo.assigned_to_id == usuario.id).update(
        {
            Processo.assigned_to_id: None,
            Processo.responsavel_equipe: None,
        },
        synchronize_session=False,
    )
    CampoExtra.query.filter(CampoExtra.criado_por_id == usuario.id).update(
        {CampoExtra.criado_por_id: None},
        synchronize_session=False,
    )
    Notificacao.query.filter_by(user_id=usuario.id).delete()
    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuario {usuario.username} excluido com sucesso.", "success")
    return redirect(url_for("login", form_action="register"))


@app.route("/logout")
@login_required
def logout():
    """Finaliza a sessao do usurio autenticado."""
    logout_user()
    flash("Voce saiu do sistema.", "info")
    return redirect(url_for("login"))


@app.route("/trocar-senha", methods=["GET", "POST"])
@login_required
def trocar_senha():
    """Permite definir uma nova senha (obrigatorio no primeiro acesso)."""
    if request.method == "POST":
        atual = request.form.get("senha_atual") or ""
        nova = request.form.get("senha_nova") or ""
        confirma = request.form.get("senha_confirma") or ""
        if not current_user.check_password(atual):
            flash("Senha atual incorreta.", "danger")
        elif len(nova) < 6:
            flash("A nova senha deve ter pelo menos 6 caracteres.", "warning")
        elif nova != confirma:
            flash("A confirmacao precisa ser igual a nova senha.", "warning")
        else:
            current_user.set_password(nova)
            current_user.must_reset_password = False
            db.session.commit()
            flash("Senha atualizada com sucesso.", "success")
            return redirect(url_for("index"))
    return render_template("reset_password.html")


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    """Permite que o usuario edite os dados do proprio perfil."""
    usuario = current_user
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual") or ""
        if not usuario.check_password(senha_atual):
            flash("Senha atual incorreta.", "danger")
            return render_template("perfil.html", gerencias=GERENCIAS)

        nome = limpar_texto(request.form.get("nome"))
        email = limpar_texto(request.form.get("email"))
        username = limpar_texto(request.form.get("username"))
        gerencia_raw = limpar_texto(request.form.get("gerencia"))
        gerencia = (
            normalizar_gerencia(gerencia_raw, permitir_entrada=True)
            if gerencia_raw
            else None
        )
        coordenadoria = limpar_texto(request.form.get("coordenadoria"))
        equipe = limpar_texto(request.form.get("equipe_area"))
        senha_nova = request.form.get("senha_nova") or ""
        senha_confirma = request.form.get("senha_confirma") or ""
        erros = []

        if not nome:
            erros.append("Nome")
        if not email:
            erros.append("Email")
        else:
            email_existente = (
                Usuario.query.filter(func.lower(Usuario.email) == email.lower())
                .filter(Usuario.id != usuario.id)
                .first()
            )
            if email_existente:
                erros.append("Email (ja utilizado)")
        if not username:
            erros.append("Usuario")
        else:
            username_existente = (
                Usuario.query.filter(func.lower(Usuario.username) == username.lower())
                .filter(Usuario.id != usuario.id)
                .first()
            )
            if username_existente:
                erros.append("Usuario (ja utilizado)")

        if gerencia_raw and not gerencia:
            erros.append("GerÃªncia (invalida)")

        if not usuario_tem_acesso_total(usuario):
            if not gerencia:
                erros.append("GerÃªncia")
            if not coordenadoria:
                erros.append("Coordenadoria")
            if not equipe:
                erros.append("Equipe/Setor")

        if senha_nova or senha_confirma:
            if len(senha_nova) < 6:
                erros.append("Nova senha (min. 6 caracteres)")
            elif senha_nova != senha_confirma:
                erros.append("Confirmacao de senha")

        if erros:
            flash("Preencha corretamente: " + ", ".join(erros), "warning")
        else:
            usuario.nome = nome
            usuario.email = email
            usuario.username = username
            usuario.gerencia_padrao = gerencia
            usuario.gerencias_liberadas = (
                serializar_gerencias_liberadas([gerencia])
                if gerencia and not usuario_tem_acesso_total(usuario)
                else None
            )
            usuario.coordenadoria = coordenadoria or None
            usuario.equipe_area = equipe or None
            if senha_nova:
                usuario.set_password(senha_nova)
                usuario.must_reset_password = False
            db.session.commit()
            flash("Perfil atualizado com sucesso.", "success")

    return render_template("perfil.html", gerencias=GERENCIAS)


# === Utilitarios de normalizacao e parsing ===
def normalizar_chave(valor: str) -> str:
    """Remove acentos e normaliza texto para comparacoes consistentes."""
    return (
        unicodedata.normalize("NFKD", str(valor))
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
        .strip()
        .replace("  ", " ")
    )


def normalizar_coluna_importacao(valor: str) -> str:
    """Normaliza cabecalhos de planilha para mapeamento de importacao."""
    base = normalizar_chave(valor)
    return re.sub(r"[^A-Z0-9]+", " ", base).strip()


def _limpar_cache_importacao() -> None:
    """Remove arquivos temporarios antigos de importacao."""
    if not IMPORT_CACHE:
        return
    limite = datetime.utcnow() - timedelta(minutes=IMPORT_CACHE_TTL_MIN)
    expirados = []
    for token, info in IMPORT_CACHE.items():
        criado_em = info.get("criado_em")
        if criado_em and criado_em < limite:
            expirados.append(token)
    for token in expirados:
        info = IMPORT_CACHE.pop(token, None)
        caminho = info.get("caminho") if info else None
        if caminho:
            try:
                os.remove(caminho)
            except OSError:
                pass
    try:
        removidos = (
            ImportacaoTemp.query.filter(ImportacaoTemp.criado_em < limite)
            .delete(synchronize_session=False)
        )
        if removidos:
            db.session.commit()
    except Exception:
        db.session.rollback()


def _diretorios_importacao_temp() -> List[str]:
    """Lista destinos de arquivos temporarios da importacao."""
    return [
        IMPORT_CACHE_DIR,
        os.path.join(tempfile.gettempdir(), "controle_processos_imports"),
    ]


def _localizar_arquivo_importacao(token: str) -> Optional[str]:
    """Procura arquivo temporario em disco quando cache em memoria nao existe."""
    if not token:
        return None
    prefixo = f"{token}."
    for base in _diretorios_importacao_temp():
        try:
            if not os.path.isdir(base):
                continue
            for nome in os.listdir(base):
                if nome.startswith(prefixo):
                    return os.path.join(base, nome)
        except OSError:
            continue
    return None


def _registrar_importacao_temp(arquivo) -> Optional[str]:
    """Salva arquivo temporario e retorna um token de referencia."""
    if not arquivo or not arquivo.filename:
        return None
    _limpar_cache_importacao()
    ext = os.path.splitext(arquivo.filename)[1] or ".xlsx"
    token = secrets.token_urlsafe(16)
    conteudo_bytes = b""
    try:
        stream = getattr(arquivo, "stream", None)
        if stream is not None:
            posicao = stream.tell()
            stream.seek(0, os.SEEK_SET)
            conteudo_bytes = stream.read() or b""
            stream.seek(posicao, os.SEEK_SET)
    except Exception:
        conteudo_bytes = b""

    if conteudo_bytes:
        try:
            db.session.add(
                ImportacaoTemp(
                    token=token,
                    nome_arquivo=arquivo.filename,
                    conteudo=conteudo_bytes,
                    criado_em=datetime.utcnow(),
                )
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Erro ao salvar importacao temporaria no banco.")

    destinos = _diretorios_importacao_temp()
    ultimo_erro = None
    for base in destinos:
        try:
            os.makedirs(base, exist_ok=True)
            caminho = os.path.join(base, f"{token}{ext}")
            try:
                if getattr(arquivo, "stream", None) is not None:
                    arquivo.stream.seek(0, os.SEEK_SET)
            except Exception:
                pass
            arquivo.save(caminho)
            IMPORT_CACHE[token] = {
                "caminho": caminho,
                "criado_em": datetime.utcnow(),
                "nome": arquivo.filename,
            }
            return token
        except Exception as exc:
            ultimo_erro = exc
            logger.exception("Erro ao salvar arquivo temporario de importacao em %s", base)
    if conteudo_bytes:
        IMPORT_CACHE[token] = {
            "caminho": None,
            "criado_em": datetime.utcnow(),
            "nome": arquivo.filename,
        }
        return token
    if ultimo_erro:
        return None
    return None


def _tamanho_upload_bytes(arquivo) -> int:
    """Retorna tamanho do upload em bytes quando possivel."""
    if not arquivo:
        return 0
    tamanho = getattr(arquivo, "content_length", None)
    if isinstance(tamanho, int) and tamanho > 0:
        return tamanho
    stream = getattr(arquivo, "stream", None)
    if stream is None:
        return 0
    try:
        posicao = stream.tell()
        stream.seek(0, os.SEEK_END)
        total = stream.tell()
        stream.seek(posicao, os.SEEK_SET)
        return int(total) if total and total > 0 else 0
    except Exception:
        return 0


def _obter_importacao_temp(token: str) -> Optional[Dict[str, object]]:
    """Recupera informacoes do arquivo temporario de importacao."""
    if not token:
        return None
    info = IMPORT_CACHE.get(token)
    if info and info.get("caminho") and os.path.exists(str(info.get("caminho"))):
        return info

    caminho = _localizar_arquivo_importacao(token)
    if caminho:
        info = {
            "caminho": caminho,
            "criado_em": datetime.utcnow(),
            "nome": os.path.basename(caminho),
        }
        IMPORT_CACHE[token] = info
        return info

    registro = ImportacaoTemp.query.filter_by(token=token).first()
    if not registro or not registro.conteudo:
        return None
    ext = os.path.splitext(registro.nome_arquivo or "")[1] or ".xlsx"
    caminho_recuperado = None
    for base in _diretorios_importacao_temp():
        try:
            os.makedirs(base, exist_ok=True)
            caminho_recuperado = os.path.join(base, f"{token}{ext}")
            with open(caminho_recuperado, "wb") as arquivo:
                arquivo.write(registro.conteudo)
            break
        except Exception:
            caminho_recuperado = None
            continue
    if not caminho_recuperado:
        return None
    info = {
        "caminho": caminho_recuperado,
        "criado_em": datetime.utcnow(),
        "nome": registro.nome_arquivo or os.path.basename(caminho_recuperado),
    }
    IMPORT_CACHE[token] = info
    return info


def _remover_importacao_temp(token: str) -> None:
    """Remove arquivo temporario apos importacao."""
    if not token:
        return
    info = IMPORT_CACHE.pop(token, None)
    caminho = info.get("caminho") if info else None
    if caminho:
        try:
            os.remove(caminho)
        except OSError:
            pass
    caminho_disco = _localizar_arquivo_importacao(token)
    if caminho_disco:
        try:
            os.remove(caminho_disco)
        except OSError:
            pass
    try:
        ImportacaoTemp.query.filter_by(token=token).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _sugerir_mapeamento_importacao(colunas: List[str]) -> Dict[str, str]:
    """Gera sugestao de mapeamento com base nos nomes das colunas."""
    mapeamento = {
        normalizar_coluna_importacao(alias): campo for alias, campo in ALIAS_PARA_CAMPO.items()
    }
    sugestao: Dict[str, str] = {}
    for col in colunas:
        chave_norm = normalizar_coluna_importacao(col)
        campo = mapeamento.get(chave_norm)
        if campo and campo not in sugestao:
            sugestao[campo] = col
    return sugestao


def _xlrd_disponivel() -> bool:
    """Indica se o suporte a arquivos .xls esta instalado."""
    try:
        import xlrd  # noqa: F401
    except Exception:
        return False
    return True


def _adicionar_site_packages_venv() -> None:
    """Garante que o site-packages (global, user e .venv) esteja no sys.path."""
    caminhos = []
    try:
        caminhos.extend(site.getsitepackages())
    except Exception:
        pass
    try:
        user_site = site.getusersitepackages()
    except Exception:
        user_site = None
    if user_site:
        caminhos.append(user_site)
    caminhos.append(os.path.join(BASE_DIR, ".venv", "Lib", "site-packages"))

    normalizados = {os.path.normcase(os.path.normpath(p)) for p in sys.path if p}
    for caminho in caminhos:
        if not caminho or not os.path.isdir(caminho):
            continue
        chave = os.path.normcase(os.path.normpath(caminho))
        if chave in normalizados:
            continue
        try:
            site.addsitedir(caminho)
        except Exception:
            pass
        if chave not in {os.path.normcase(os.path.normpath(p)) for p in sys.path if p}:
            sys.path.insert(0, caminho)
        normalizados.add(chave)


def _comando_instalar_pip(pacote: str) -> str:
    """Monta um comando de instalacao usando o Python da .venv quando possivel."""
    venv_python = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    executavel = venv_python if os.path.isfile(venv_python) else (sys.executable or "python")
    return f'"{executavel}" -m pip install {pacote}'


def _dependencia_disponivel(modulo: str) -> bool:
    """Testa se um modulo pode ser importado."""
    try:
        __import__(modulo)
    except Exception:
        return False
    return True


def _normalizar_versao_modulo(versao: str) -> List[int]:
    """Converte uma string de versao em lista numerica comparavel."""
    if not versao:
        return []
    numeros = []
    for parte in re.split(r"[._+-]", str(versao)):
        if parte.isdigit():
            numeros.append(int(parte))
            continue
        match = re.match(r"(\\d+)", parte)
        if match:
            numeros.append(int(match.group(1)))
        break
    return numeros


def _versao_atual_suporta(minima: str, atual: str) -> bool:
    """Indica se a versao atual e >= versao minima."""
    atual_nums = _normalizar_versao_modulo(atual)
    minima_nums = _normalizar_versao_modulo(minima)
    if not minima_nums:
        return True
    tamanho = max(len(atual_nums), len(minima_nums))
    atual_nums += [0] * (tamanho - len(atual_nums))
    minima_nums += [0] * (tamanho - len(minima_nums))
    return atual_nums >= minima_nums


def _checar_openpyxl() -> Optional[str]:
    """Valida se openpyxl esta instalado e com versao suficiente."""
    _adicionar_site_packages_venv()
    try:
        import openpyxl  # noqa: F401
    except Exception:
        cmd = _comando_instalar_pip(f"openpyxl>={OPENPYXL_MIN_VERSION}")
        return f"Falta instalar openpyxl para ler arquivos .xlsx. Execute: {cmd}"
    versao = getattr(openpyxl, "__version__", "")
    if not _versao_atual_suporta(OPENPYXL_MIN_VERSION, versao):
        cmd = _comando_instalar_pip(f"openpyxl>={OPENPYXL_MIN_VERSION}")
        return (
            f"A versao atual do openpyxl ({versao}) e antiga. "
            f"Requer {OPENPYXL_MIN_VERSION}+ para ler .xlsx. Execute: {cmd}"
        )
    return None


def _garantir_dependencia_excel(engine: Optional[str]) -> Optional[str]:
    """Tenta garantir dependencias do engine e retorna erro amigavel se faltar."""
    if engine == "openpyxl":
        return _checar_openpyxl()
    if engine == "xlrd":
        if _dependencia_disponivel("xlrd"):
            return None
        _adicionar_site_packages_venv()
        if _dependencia_disponivel("xlrd"):
            return None
        cmd = _comando_instalar_pip("xlrd")
        return f"Arquivo .xls exige o pacote xlrd. Execute: {cmd} ou salve como .xlsx."
    return None


def _excel_engine_para(caminho: str) -> Optional[str]:
    """Define o engine do pandas para leitura de Excel pelo sufixo do arquivo."""
    ext = os.path.splitext(str(caminho or ""))[1].lower()
    if ext == ".xls":
        return "xlrd"
    if ext in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "openpyxl"
    return None


def _coletar_planilhas_excel(caminho: str) -> List[str]:
    """Retorna a lista de abas (planilhas) disponiveis no Excel."""
    try:
        engine = _excel_engine_para(caminho)
        kwargs = {"engine": engine} if engine else {}
        arquivo = pd.ExcelFile(caminho, **kwargs)
    except Exception:
        return []
    return [str(nome) for nome in arquivo.sheet_names or []]


def _validar_suporte_excel(caminho: str) -> Optional[str]:
    """Retorna mensagem de erro caso o tipo de arquivo nao seja suportado."""
    ext = os.path.splitext(str(caminho or ""))[1].lower()
    suportadas = {".xls", ".xlsx", ".xlsm", ".xltx", ".xltm"}
    if ext and ext not in suportadas:
        return "Formato nao suportado. Use .xlsx ou .xls."
    if ext == ".xls" and not _xlrd_disponivel():
        return "Arquivo .xls exige o pacote xlrd. Instale xlrd ou salve como .xlsx."
    return None


def _mensagem_erro_excel(caminho: str, exc: Exception) -> str:
    """Converte erros comuns de leitura do Excel em mensagens amigaveis."""
    mensagem = str(exc) or exc.__class__.__name__
    ext = os.path.splitext(str(caminho or ""))[1].lower()
    if isinstance(exc, ImportError):
        if "openpyxl" in mensagem.lower():
            cmd = _comando_instalar_pip(f"openpyxl>={OPENPYXL_MIN_VERSION}")
            match = re.search(r"requires version '([^']+)'", mensagem)
            if match:
                return (
                    f"openpyxl precisa da versao {match.group(1)} ou superior. "
                    f"Execute: {cmd}"
                )
            return f"Falta instalar openpyxl para ler arquivos .xlsx. Execute: {cmd}"
        if "xlrd" in mensagem.lower():
            return "Arquivo .xls exige o pacote xlrd. Instale xlrd ou salve como .xlsx."
    if "excel file format cannot be determined" in mensagem.lower():
        return "Formato da planilha nao foi reconhecido. Salve como .xlsx."
    if "file is not a zip file" in mensagem.lower() or "badzipfile" in mensagem.lower():
        return "Arquivo nao parece um .xlsx valido. Salve novamente como .xlsx."
    if ext not in {"", ".xls", ".xlsx", ".xlsm", ".xltx", ".xltm"}:
        return "Formato nao suportado. Use .xlsx ou .xls."
    return "Nao foi possivel ler o arquivo Excel informado."


def _normalizar_linha_cabecalho(valor, padrao: int = 1) -> int:
    """Garante um numero de linha valido (1-based) para cabecalho."""
    try:
        linha = int(valor)
    except (TypeError, ValueError):
        return padrao
    return linha if linha > 0 else padrao


def limpar_texto(valor, default: str = "") -> str:
    """Retorna string limpa ou valor padrao quando entrada estiver vazia."""
    if valor is None:
        return default
    try:
        if pd.isna(valor):
            return default
    except Exception:
        pass
    texto = str(valor).strip()
    return default if texto.upper() in {"", "NAN", "NAT"} else texto


def normalizar_gerencia(valor, *, permitir_entrada: bool = False) -> Optional[str]:
    """Converte nomes livres de gerencia para os codigos aceitos pelo sistema."""
    nome = limpar_texto(valor)
    if not nome:
        return None

    ascii_nome = (
        unicodedata.normalize("NFKD", nome)
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
    )
    ascii_nome = " ".join(ascii_nome.split())

    if "ACESSORIA TECNICA" in f" {ascii_nome} " or "ASSESSORIA TECNICA" in f" {ascii_nome} ":
        return "GABINETE"
    if ascii_nome == "ENTRADA":
        return "ENTRADA" if permitir_entrada else GERENCIA_PADRAO
    if ascii_nome == "SAIDA":
        return "SAIDA"

    # Captura tokens ou ocorrencias dentro do texto (ex.: "GEPLAN - DOP", "Equipe GEDEX")
    tokens = [t for t in re.split(r"[^A-Z0-9]+", ascii_nome) if t]
    for token in tokens:
        if token == "ENTRADA":
            return "ENTRADA" if permitir_entrada else GERENCIA_PADRAO
        if token in GERENCIAS_DESTINOS:
            return token

    for ger in GERENCIAS_DESTINOS:
        marcador = f" {ger} "
        if ascii_nome == ger or ascii_nome.endswith(ger) or ascii_nome.startswith(ger) or marcador in f" {ascii_nome} ":
            return ger

    return None


def extrair_numero_base_sei(valor: str) -> str:
    """Extrai o numero base do SEI, removendo prefixo de gerencia quando houver."""
    numero = limpar_texto(valor, "")
    if not numero:
        return ""
    if "-" in numero:
        prefixo, sufixo = numero.split("-", 1)
        if normalizar_gerencia(prefixo, permitir_entrada=True):
            numero = sufixo
    return limpar_texto(numero, "")


def obter_chave_processo_em_dados(dados_extra: Optional[Dict[str, object]]) -> Optional[str]:
    """Retorna a chave de agrupamento do processo quando existir em dados_extra."""
    if not isinstance(dados_extra, dict):
        return None
    chave = limpar_texto(dados_extra.get("chave_processo"), "")
    return chave or None


def obter_chave_processo_relacional(processo: Optional["Processo"]) -> Optional[str]:
    """Retorna a chave de agrupamento do processo para relacionar demandas."""
    if not processo:
        return None
    return obter_chave_processo_em_dados(processo.dados_extra or {})


def gerar_chave_relacionamento_numero(numero_base: str, chave_processo: Optional[str]) -> str:
    """Gera identificador de agrupamento a partir do numero base e chave do processo."""
    base = (numero_base or "").strip().lower()
    if not base:
        return ""
    if chave_processo:
        return f"chave:{chave_processo}"
    return f"base:{base}"


def processo_pertence_mesmo_grupo(
    item: "Processo",
    *,
    numero_base: str,
    chave_referencia: Optional[str] = None,
) -> bool:
    """Valida se um processo pertence ao mesmo grupo logico (demanda) do numero base."""
    if not item or item.numero_sei_base != numero_base:
        return False
    chave_item = obter_chave_processo_relacional(item)
    if chave_referencia:
        return chave_item == chave_referencia
    # Grupo legado: sem chave explicita, seguimos agrupando apenas os sem chave.
    return not chave_item


def obter_chave_referencia_unica_por_base(relacionados: List["Processo"]) -> Optional[str]:
    """Define chave de relacionamento quando existe apenas uma para o numero base."""
    if not relacionados:
        return None
    chaves_ativas = {
        obter_chave_processo_relacional(item)
        for item in relacionados
        if item.finalizado_em is None
    }
    chaves_ativas.discard(None)
    if len(chaves_ativas) == 1:
        return next(iter(chaves_ativas))
    if len(chaves_ativas) > 1:
        return None
    chaves = {obter_chave_processo_relacional(item) for item in relacionados}
    chaves.discard(None)
    if len(chaves) == 1:
        return next(iter(chaves))
    return None


def gerar_nova_chave_processo(numero_base: str) -> str:
    """Gera identificador unico para iniciar um novo ciclo do mesmo numero SEI."""
    base = re.sub(r"[^a-z0-9]+", "", (numero_base or "").strip().lower())[:24]
    if not base:
        base = "sei"
    carimbo = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{base}-{carimbo}-{secrets.token_hex(4)}"


def analisar_numero_para_cadastro(numero_informado: str) -> Dict[str, object]:
    """Inspeciona se ha demandas ativas/finalizadas para o numero informado."""
    numero_base = extrair_numero_base_sei(numero_informado)
    resultado: Dict[str, object] = {
        "numero_base": numero_base,
        "ativos_count": 0,
        "finalizados_count": 0,
        "ativos_gerencias": [],
        "precisa_decisao": False,
        "apenas_finalizados": False,
        "chave_referencia": None,
        "prefill": None,
    }
    if not numero_base or SITE_EM_CONFIGURACAO:
        return resultado

    relacionados = [p for p in Processo.query.all() if p.numero_sei_base == numero_base]
    ativos = [p for p in relacionados if not p.finalizado_em]
    finalizados = [p for p in relacionados if p.finalizado_em]

    gerencias_ativas = []
    vistos = set()
    for item in ativos:
        ger = normalizar_gerencia(item.gerencia, permitir_entrada=True) or limpar_texto(item.gerencia, "")
        if ger and ger not in vistos:
            vistos.add(ger)
            gerencias_ativas.append(ger)
    gerencias_ativas = ordenar_gerencias_preferencial(gerencias_ativas)

    chave_referencia = None
    if ativos:
        relacionados_ordenados = sorted(
            ativos,
            key=lambda p: p.atualizado_em or p.finalizado_em or p.criado_em or datetime.min,
            reverse=True,
        )
        for item in relacionados_ordenados:
            chave_item = obter_chave_processo_relacional(item)
            if chave_item:
                chave_referencia = chave_item
                break

    resultado["ativos_count"] = len(ativos)
    resultado["finalizados_count"] = len(finalizados)
    resultado["ativos_gerencias"] = gerencias_ativas
    resultado["precisa_decisao"] = len(ativos) > 0
    resultado["apenas_finalizados"] = len(ativos) == 0 and len(finalizados) > 0
    resultado["chave_referencia"] = chave_referencia

    referencia = None
    origem_referencia = ""
    if ativos:
        referencia = sorted(
            ativos,
            key=lambda p: p.atualizado_em or p.criado_em or datetime.min,
            reverse=True,
        )[0]
        origem_referencia = "ativa"
    elif finalizados:
        referencia = sorted(
            finalizados,
            key=lambda p: p.finalizado_em or p.atualizado_em or p.criado_em or datetime.min,
            reverse=True,
        )[0]
        origem_referencia = "finalizada"
    if referencia:
        resultado["prefill"] = {
            "assunto": referencia.assunto or "",
            "interessado": referencia.interessado or "",
            "concessionaria": referencia.concessionaria or "",
            "origem": origem_referencia,
            "total_relacionados": len(relacionados),
        }
    return resultado


def parse_date(valor) -> Optional[date]:
    """Converte diferentes formatos de data em objetos date padronizados."""
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except Exception:
        pass
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def data_entrada_na_gerencia(processo: "Processo", gerencia: Optional[str]) -> Optional[date]:
    """Retorna a data em que o processo entrou na gerencia indicada.

    Procura a ultima movimentacao cujo destino (para_gerencia) coincide com a
    gerencia informada. Caso nao haja, usa a data_entrada do processo; se ainda
    ausente, usa a data de criacao do registro.
    """
    if not processo or not gerencia:
        return None
    try:
        movs = sorted(
            processo.movimentacoes,
            key=lambda m: m.criado_em or datetime.min,
            reverse=True,
        )
        for m in movs:
            if (m.para_gerencia or "").upper() == gerencia.upper():
                return m.criado_em.date() if m.criado_em else None
    except Exception:
        pass
    if processo.data_entrada:
        return processo.data_entrada
    return processo.criado_em.date() if processo.criado_em else None


def ordenar_gerencias_preferencial(origem: List[str]) -> List[str]:
    """Ordena gerencias na ordem visual padrao: GABINETE, GEENG, GEPLAN, GEDEX, GEFOR."""
    vistos = set()
    unicas: List[str] = []
    for nome in origem:
        if not nome:
            continue
        texto = str(nome).strip()
        if not texto:
            continue
        chave = texto.upper()
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(texto)
    return sorted(
        unicas,
        key=lambda nome: (
            ORDEM_GERENCIAS.get(
                normalizar_gerencia(nome, permitir_entrada=True) or str(nome).strip().upper(),
                999,
            ),
            str(nome).strip().upper(),
        ),
    )


def aplicar_edicao_processo(
    processo_ref: Processo, form_data, campos_extras_def: List["CampoExtra"]
) -> None:
    def texto(campo: str) -> Optional[str]:
        valor = limpar_texto(form_data.get(campo), "")
        return valor or None

    def data(campo: str) -> Optional[date]:
        return parse_date(form_data.get(campo))

    # Atualiza apenas campos presentes no POST para evitar sobrescrever quando salvar apenas extras
    if "prazo" in form_data:
        processo_ref.prazo = data("prazo")
    if "concessionaria" in form_data:
        processo_ref.concessionaria = texto("concessionaria")
    if "responsavel_adm" in form_data:
        processo_ref.responsavel_adm = texto("responsavel_adm")
    if "observacao" in form_data:
        processo_ref.observacao = texto("observacao")
    # Data de entrada na gerencia e exibida de forma informativa (movimentacoes)
    if "descricao_melhorada" in form_data:
        processo_ref.descricao_melhorada = texto("descricao_melhorada")
    if "coordenadoria" in form_data:
        processo_ref.coordenadoria = texto("coordenadoria")
    if "equipe_area" in form_data:
        processo_ref.equipe_area = texto("equipe_area")
    if "responsavel_equipe" in form_data:
        processo_ref.responsavel_equipe = texto("responsavel_equipe")
    if "tipo_processo" in form_data:
        processo_ref.tipo_processo = texto("tipo_processo")
    if "palavras_chave" in form_data:
        processo_ref.palavras_chave = texto("palavras_chave")
    if "status" in form_data:
        novo_status = texto("status")
        if novo_status != processo_ref.status:
            processo_ref.status = novo_status
            # Ao alterar status, atribui data_status automaticamente (UTC hoje)
            processo_ref.data_status = datetime.utcnow().date() if novo_status else None
    if "prazo_equipe" in form_data:
        processo_ref.prazo_equipe = data("prazo_equipe")
    # Data de saida e registrada ao finalizar; nao e editada aqui
    if "obs" in form_data:
        processo_ref.observacoes_complementares = texto("obs")
    if processo_ref.gerencia == "SAIDA" and "destino_saida" in form_data:
        destino_bruto = limpar_texto(form_data.get("destino_saida"), "")
        destino_norm = destino_bruto.casefold()
        destino_saida = next(
            (item for item in DESTINOS_SAIDA if item.casefold() == destino_norm),
            None,
        )
        processo_ref.tramitado_para = destino_saida
    elif "tramitado_para" in form_data:
        destino_bruto = limpar_texto(form_data.get("tramitado_para"), "")
        processo_ref.tramitado_para = normalizar_gerencia(destino_bruto) or None

    if "classificacao_institucional" in form_data:
        classificacao = limpar_texto(form_data.get("classificacao_institucional"), "")
        processo_ref.classificacao_institucional = classificacao or None

    # Atualiza campos extras desta gerencia junto com a edicao
    valores = coletar_dados_extra_form(processo_ref.gerencia, form_data)
    dados = processo_ref.dados_extra or {}
    definidos = {campo.slug for campo in campos_extras_def}
    for slug in definidos:
        if slug in valores:
            dados[slug] = valores[slug]
        else:
            dados.pop(slug, None)
    processo_ref.dados_extra = dados
    processo_ref.atualizado_em = datetime.utcnow()


def sincronizar_atribuicao_responsavel_equipe(
    processo: Processo, responsavel_anterior: str
) -> Optional[str]:
    """Sincroniza atribuicao baseada no campo responsavel_equipe."""
    responsavel_atual = limpar_texto(processo.responsavel_equipe, "")
    if _normalizar_nome_usuario(responsavel_atual) == _normalizar_nome_usuario(responsavel_anterior):
        return None
    if not responsavel_atual:
        processo.assigned_to = None
        return None
    usuario = localizar_usuario_por_texto(responsavel_atual, gerencia=processo.gerencia)
    if usuario and usuario_permitido_para_atribuicao(usuario, processo):
        processo.assigned_to = usuario
        processo.responsavel_equipe = _nome_usuario_exibicao(usuario) or responsavel_atual
        if current_user.is_authenticated and usuario.id != current_user.id:
            registrar_notificacao(
                usuario,
                f"O processo {processo.numero_sei_base} foi atribuido para voce.",
                processo,
            )
        return None
    if responsavel_em_lista(responsavel_atual, processo):
        processo.assigned_to = None
        return None
    processo.responsavel_equipe = responsavel_anterior or None
    return (
        "Responsavel da equipe informado nao pertence a lista valida "
        "da gerencia/coordenadoria/equipe deste processo."
    )


def coletar_valores_distintos(coluna) -> List[str]:
    """Retorna valores unicos de uma coluna textual para uso em filtros."""
    resultados = db.session.query(coluna).filter(coluna.isnot(None)).all()
    valores = {limpar_texto(resultado[0]) for resultado in resultados if limpar_texto(resultado[0])}
    return sorted(valores, key=lambda texto: texto.upper())


def _normalizar_snapshot(snapshot):
    """Garante que o snapshot salvo na movimentacao seja um dicionario."""
    if not snapshot:
        return None
    if isinstance(snapshot, dict):
        return snapshot
    if isinstance(snapshot, str):
        try:
            return json.loads(snapshot)
        except Exception:
            return {"_raw": snapshot}
    return snapshot


def _normalizar_dados_extra(dados_extra):
    """Garante dicionario para dados extras mesmo em bases legadas (texto JSON)."""
    normalizado = _normalizar_snapshot(dados_extra)
    return normalizado if isinstance(normalizado, dict) else {}


def coletar_gerencias_envolvidas(processo: Processo) -> List[str]:
    """Retorna a trilha de gerencias pelas quais o processo passou."""
    vistos = set()
    trilha: List[str] = []

    def registrar(nome: Optional[str]) -> None:
        if not nome:
            return
        texto = str(nome).strip()
        if not texto:
            return
        slug = texto.upper()
        if slug in {"FINALIZADO", "SAIDA", "ENTRADA", "CADASTRO"} or slug in vistos:
            return
        vistos.add(slug)
        trilha.append(texto)

    movimentacoes = sorted(
        processo.movimentacoes,
        key=lambda mov: mov.criado_em or datetime.min,
    )
    for mov in movimentacoes:
        tipo_mov = (mov.tipo or "").strip().lower()
        if tipo_mov == "cadastro":
            registrar(mov.para_gerencia)
            continue
        registrar(mov.de_gerencia)
        registrar(mov.para_gerencia)

    registrar(processo.gerencia)
    return ordenar_gerencias_preferencial(trilha)


def capturar_estado_historico_processo(processo: Processo) -> Dict[str, str]:
    """Captura campos relevantes para detectar alteracoes de edicao."""
    def _fmt_data(valor: Optional[date]) -> str:
        return valor.isoformat() if valor else ""

    return {
        "prazo": _fmt_data(processo.prazo),
        "concessionaria": processo.concessionaria or "",
        "responsavel_adm": processo.responsavel_adm or "",
        "observacao": processo.observacao or "",
        "descricao_melhorada": processo.descricao_melhorada or "",
        "coordenadoria": processo.coordenadoria or "",
        "equipe_area": processo.equipe_area or "",
        "responsavel_equipe": processo.responsavel_equipe or "",
        "tipo_processo": processo.tipo_processo or "",
        "palavras_chave": processo.palavras_chave or "",
        "status": processo.status or "",
        "prazo_equipe": _fmt_data(processo.prazo_equipe),
        "observacoes_complementares": processo.observacoes_complementares or "",
        "tramitado_para": processo.tramitado_para or "",
        "classificacao_institucional": processo.classificacao_institucional or "",
        "dados_extra": json.dumps(processo.dados_extra or {}, ensure_ascii=False, sort_keys=True),
    }


def descrever_mudancas_historico(
    estado_antes: Dict[str, str], estado_depois: Dict[str, str]
) -> List[str]:
    """Retorna lista textual de mudancas para auditoria no historico."""
    labels = {
        "prazo": "Prazo SUROD",
        "concessionaria": "Concessionaria",
        "responsavel_adm": "Responsavel ADM",
        "observacao": "Observacao",
        "descricao_melhorada": "Descricao melhorada",
        "coordenadoria": "Coordenadoria",
        "equipe_area": "Equipe/Area",
        "responsavel_equipe": "Responsavel equipe",
        "tipo_processo": "Tipo de processo",
        "palavras_chave": "Palavras-chave",
        "status": "Status",
        "prazo_equipe": "Prazo equipe",
        "observacoes_complementares": "Observacoes complementares",
        "tramitado_para": "Tramitado para",
        "classificacao_institucional": "Classificacao institucional",
        "dados_extra": "Campos extras",
    }
    mudancas: List[str] = []
    for chave, label in labels.items():
        antes = (estado_antes.get(chave) or "").strip()
        depois = (estado_depois.get(chave) or "").strip()
        if antes == depois:
            continue
        if chave == "dados_extra":
            mudancas.append(f"{label} atualizados")
            continue
        antes_txt = antes or "-"
        depois_txt = depois or "-"
        mudancas.append(f"{label}: {antes_txt} -> {depois_txt}")
    return mudancas


def _termo_por_gerencia(gerencia: Optional[str], tipo: str = "") -> str:
    """Define se o evento deve tratar como demanda ou processo."""
    tipo_norm = (tipo or "").strip().lower()
    if tipo_norm == "finalizado_geral":
        return "Processo"
    ger_norm = normalizar_gerencia(gerencia, permitir_entrada=True)
    if ger_norm == "SAIDA":
        return "Processo"
    return "Demanda"


def _flexao_acao(termo: str, masc: str, fem: str) -> str:
    """Escolhe flexao verbal conforme o termo (Processo/Demanda)."""
    return masc if termo == "Processo" else fem


def _substituir_termo_processo(texto: str, termo: str) -> str:
    """Ajusta textos legados que ainda usam 'Processo' quando o termo e Demanda."""
    if termo == "Processo":
        return texto
    texto = re.sub(r"\bPROCESSO ATRIBUIDO\b", "DEMANDA ATRIBUIDA", texto)
    texto = re.sub(r"\bProcesso atribuido\b", "Demanda atribuida", texto)
    texto = re.sub(r"\bprocesso atribuido\b", "demanda atribuida", texto)
    texto = re.sub(r"\bPROCESSO\b", "DEMANDA", texto)
    texto = re.sub(r"\bProcesso\b", "Demanda", texto)
    texto = re.sub(r"\bprocesso\b", "demanda", texto)
    return texto


def montar_texto_evento_historico(
    mov: "Movimentacao", *, gerencia_criacao: Optional[str] = None
) -> str:
    """Gera texto padrao e legivel para exibicao do historico."""
    usuario = mov.usuario or "usuario"
    tipo = (mov.tipo or "").strip().lower()
    de = mov.de_gerencia or "-"
    para = mov.para_gerencia or "-"
    motivo = (mov.motivo or "").strip()
    termo = _termo_por_gerencia(de, tipo)

    if tipo == "cadastro":
        ger = para if para and para != "-" else (gerencia_criacao or "-")
        termo_cadastro = _termo_por_gerencia(ger, tipo)
        acao = _flexao_acao(termo_cadastro, "cadastrado", "cadastrada")
        envio = _flexao_acao(termo_cadastro, "enviado", "enviada")
        return (
            f"{termo_cadastro} {acao} por {usuario} e {envio} para {ger}."
        )
    if tipo == "finalizacao_gerencia":
        acao = _flexao_acao(termo, "finalizado", "finalizada")
        envio = _flexao_acao(termo, "enviado", "enviada")
        return (
            f"{termo} {acao} em {de} por {usuario} e {envio} para {para}."
        )
    if tipo == "finalizado_geral":
        return f"Processo encerrado em {de} por {usuario}."
    if tipo == "edicao":
        acao = _flexao_acao(termo, "editado", "editada")
        texto = f"{termo} {acao} na gerencia {de} por {usuario}."
        if motivo:
            texto += f" Alteracoes: {motivo}."
        return texto
    if tipo == "status":
        sujeito = "do processo" if termo == "Processo" else "da demanda"
        return (
            f"Status {sujeito} atualizado na gerencia {de} para: "
            f"{motivo or '-'} por {usuario}."
        )
    if tipo == "atribuicao":
        if motivo:
            return _substituir_termo_processo(motivo, termo)
        acao = _flexao_acao(termo, "atribuido", "atribuida")
        return f"{termo} {acao} na gerencia {de} por {usuario}."
    if tipo == "devolucao_gabinete":
        acao = _flexao_acao(termo, "devolvido", "devolvida")
        return (
            f"{termo} {acao} para GABINETE por {usuario}. Motivo: {motivo or '-'}."
        )

    acao = _flexao_acao(termo, "movido", "movida")
    texto = f"{termo} {acao} de {de} para {para} por {usuario}."
    if motivo:
        texto += f" Motivo: {motivo}."
    return texto


def coletar_gerencias_com_demanda_por_base(
    numero_base: str,
    *,
    ignorar_ids: Optional[set] = None,
    chave_referencia: Optional[str] = None,
) -> List[str]:
    """Lista gerencias que ja tiveram demanda para o mesmo numero base."""
    if not numero_base:
        return []

    ignorar = set(ignorar_ids or set())
    gerencias = set()
    relacionados = [p for p in Processo.query.all() if p.id not in ignorar]

    for item in relacionados:
        if not processo_pertence_mesmo_grupo(
            item,
            numero_base=numero_base,
            chave_referencia=chave_referencia,
        ):
            continue
        for ger in coletar_gerencias_envolvidas(item):
            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
            if ger_norm and ger_norm not in {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}:
                gerencias.add(ger_norm)
        ger_atual = normalizar_gerencia(item.gerencia, permitir_entrada=True)
        if ger_atual and ger_atual not in {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}:
            gerencias.add(ger_atual)

    return ordenar_gerencias_preferencial(list(gerencias))


def obter_origem_saida(processo: Processo) -> Optional[str]:
    """Retorna a gerencia de origem que enviou o processo para SAIDA."""
    movs = sorted(
        processo.movimentacoes,
        key=lambda mov: mov.criado_em or datetime.min,
    )
    for mov in reversed(movs):
        if mov.para_gerencia == "SAIDA":
            return mov.de_gerencia or processo.gerencia
    return processo.gerencia


def serializar_processo_para_relatorio(processo: Processo) -> Dict[str, object]:
    """Transforma o processo em estrutura serializavel para o painel de finalizados."""
    movimentacoes = sorted(
        processo.movimentacoes,
        key=lambda mov: mov.criado_em or datetime.min,
    )
    gerencias_trilha = coletar_gerencias_envolvidas(processo)
    gerencia_criacao = gerencias_trilha[0] if gerencias_trilha else (processo.gerencia or "-")
    chave_relacionamento = gerar_chave_relacionamento_numero(
        processo.numero_sei_base,
        obter_chave_processo_relacional(processo),
    )
    cadastro_mov = next(
        (mov for mov in movimentacoes if (mov.tipo or "").strip().lower() == "cadastro"),
        None,
    )
    usuario_cadastro = cadastro_mov.usuario if cadastro_mov and cadastro_mov.usuario else None
    if not usuario_cadastro and movimentacoes:
        primeiro_usuario = next((mov.usuario for mov in movimentacoes if mov.usuario), None)
        usuario_cadastro = primeiro_usuario or None
    if not usuario_cadastro:
        usuario_cadastro = processo.finalizado_por or None
    ultima_finalizacao = None
    snapshot_finalizacao = None
    if not processo.finalizado_em:
        for mov in reversed(movimentacoes):
            if mov.tipo == "finalizacao_gerencia":
                ultima_finalizacao = mov
                break
        snapshot_finalizacao = _normalizar_snapshot(
            getattr(ultima_finalizacao, "dados_snapshot", None)
        ) if ultima_finalizacao else None

    return {
        "id": processo.id,
        "numero_sei": processo.numero_sei,
        "numero_sei_base": processo.numero_sei_base,
        "chave_relacionamento": chave_relacionamento,
        "assunto": (snapshot_finalizacao or {}).get("assunto") or processo.assunto,
        "interessado": (snapshot_finalizacao or {}).get("interessado") or processo.interessado,
        "concessionaria": (snapshot_finalizacao or {}).get("concessionaria") or processo.concessionaria,
        "classificacao_institucional": (
            (snapshot_finalizacao or {}).get("classificacao_institucional") or processo.descricao
        ),
        "descricao_melhorada": (
            (snapshot_finalizacao or {}).get("descricao_melhorada") or processo.descricao_melhorada
        ),
        "observacao": (snapshot_finalizacao or {}).get("observacao") or processo.observacao,
        "gerencia": processo.gerencia,
        "destino_saida": processo.tramitado_para,
        "coordenadoria": (snapshot_finalizacao or {}).get("coordenadoria") or processo.coordenadoria,
        "equipe_area": (snapshot_finalizacao or {}).get("equipe_area") or processo.equipe_area,
        "responsavel_adm": (snapshot_finalizacao or {}).get("responsavel_adm") or processo.responsavel_adm,
        "responsavel_equipe": (snapshot_finalizacao or {}).get("responsavel_equipe") or processo.responsavel_equipe,
        "tipo_processo": (snapshot_finalizacao or {}).get("tipo_processo") or processo.tipo_processo,
        "palavras_chave": (snapshot_finalizacao or {}).get("palavras_chave") or processo.palavras_chave,
        "status": (snapshot_finalizacao or {}).get("status") or processo.status,
        "prazo": parse_date((snapshot_finalizacao or {}).get("prazo")) or processo.prazo,
        "data_entrada": parse_date((snapshot_finalizacao or {}).get("data_entrada")) or processo.data_entrada,
        "data_entrada_geplan": parse_date((snapshot_finalizacao or {}).get("data_entrada_geplan"))
        or processo.data_entrada_geplan,
        "observacoes_complementares": (
            (snapshot_finalizacao or {}).get("observacoes_complementares")
            or processo.observacoes_complementares
        ),
        "responsavel": processo.assigned_to.username if processo.assigned_to else None,
        "dados_extra": (snapshot_finalizacao or {}).get("extras") or processo.dados_extra or {},
        "criado_em": processo.criado_em.isoformat() if processo.criado_em else None,
        "finalizado_em": (
            processo.finalizado_em.isoformat()
            if processo.finalizado_em
            else (
                ultima_finalizacao.criado_em.isoformat()
                if ultima_finalizacao and ultima_finalizacao.criado_em
                else None
            )
        ),
        "finalizado_por": processo.finalizado_por,
        "gerencias_involvidas": gerencias_trilha,
        "gerencia_criacao": gerencia_criacao,
        "usuario_cadastro": usuario_cadastro,
        "movimentacoes": [
            {
                "de": mov.de_gerencia,
                "para": mov.para_gerencia,
                "motivo": mov.motivo,
                "usuario": mov.usuario,
                "tipo": mov.tipo,
                "data": mov.criado_em.isoformat() if mov.criado_em else None,
                "dados": _normalizar_snapshot(getattr(mov, "dados_snapshot", None)),
                "texto": montar_texto_evento_historico(
                    mov, gerencia_criacao=gerencia_criacao
                ),
            }
            for mov in movimentacoes
        ],
    }


def obter_opcoes_painel_finalizados() -> Dict[str, List[str]]:
    """Monta os valores exibidos nos selects de filtro da tela de verificacao."""
    return {
        "gerencias": GERENCIAS,
        "coordenadorias": coletar_valores_distintos(Processo.coordenadoria),
        "equipes": coletar_valores_distintos(Processo.equipe_area),
        "interessados": coletar_valores_distintos(Processo.interessado),
    }


def garantir_usuario_padrao():
    """Cria um usuario administrador inicial quando o banco esta vazio."""
    perfil = DEFAULT_ADMIN_PERFIL or "admin"
    is_admin = perfil == "admin"
    is_gerente = perfil in {"admin", "gerente"}
    acesso_total = perfil == "acesso_total"
    pode_cadastrar = _env_bool("DEFAULT_ADMIN_PODE_CADASTRAR", is_admin or acesso_total)
    pode_exportar = _env_bool("DEFAULT_ADMIN_PODE_EXPORTAR", is_admin or acesso_total)
    pode_importar = _env_bool("DEFAULT_ADMIN_PODE_IMPORTAR", is_admin or acesso_total)
    usuario = Usuario.query.filter_by(is_admin_principal=True).first()
    if not usuario:
        filtros_admin = []
        if DEFAULT_ADMIN_USER:
            filtros_admin.append(
                func.lower(Usuario.username) == DEFAULT_ADMIN_USER.lower()
            )
        if DEFAULT_ADMIN_EMAIL:
            filtros_admin.append(
                func.lower(Usuario.email) == DEFAULT_ADMIN_EMAIL.lower()
            )
        usuario = Usuario.query.filter(or_(*filtros_admin)).first() if filtros_admin else None
    gerencia_padrao_admin = DEFAULT_ADMIN_GERENCIA or GERENCIA_PADRAO
    gerencias_liberadas_admin = serializar_gerencias_liberadas([gerencia_padrao_admin])
    if not usuario:
        usuario = Usuario(
            username=DEFAULT_ADMIN_USER,
            email=DEFAULT_ADMIN_EMAIL,
            nome=DEFAULT_ADMIN_NAME,
            gerencia_padrao=gerencia_padrao_admin,
            gerencias_liberadas=gerencias_liberadas_admin,
            coordenadoria=DEFAULT_ADMIN_COORDENADORIA or None,
            equipe_area=DEFAULT_ADMIN_EQUIPE or None,
            is_admin=is_admin,
            is_admin_principal=True,
            is_gerente=is_gerente,
            acesso_total=acesso_total,
            must_reset_password=False,
            pode_cadastrar_processo=pode_cadastrar,
            pode_finalizar_gerencia=True,
            pode_exportar=pode_exportar,
            pode_importar=pode_importar,
        )
        usuario.set_password(DEFAULT_ADMIN_PASSWORD)
        db.session.add(usuario)
        db.session.commit()
        app.logger.warning(
            "Usurio padro '%s' criado. Altere a senha via DEFAULT_ADMIN_PASSWORD.",
            DEFAULT_ADMIN_USER,
        )
    else:
        atualizou = False
        if is_admin and not usuario.is_admin:
            usuario.is_admin = True
            atualizou = True
        if not usuario.is_admin_principal:
            usuario.is_admin_principal = True
            atualizou = True
        if acesso_total and not usuario.acesso_total:
            usuario.acesso_total = True
            atualizou = True
        if not acesso_total and usuario.acesso_total:
            usuario.acesso_total = False
            atualizou = True
        if not usuario.gerencia_padrao:
            usuario.gerencia_padrao = DEFAULT_ADMIN_GERENCIA or GERENCIA_PADRAO
            atualizou = True
        if not usuario.gerencias_liberadas and usuario.gerencia_padrao:
            usuario.gerencias_liberadas = serializar_gerencias_liberadas([usuario.gerencia_padrao])
            atualizou = True
        if usuario.coordenadoria is None and DEFAULT_ADMIN_COORDENADORIA:
            usuario.coordenadoria = DEFAULT_ADMIN_COORDENADORIA
            atualizou = True
        if usuario.equipe_area is None and DEFAULT_ADMIN_EQUIPE:
            usuario.equipe_area = DEFAULT_ADMIN_EQUIPE
            atualizou = True
        if usuario.pode_finalizar_gerencia is None:
            usuario.pode_finalizar_gerencia = True
            atualizou = True
        if atualizou:
            db.session.commit()


def promover_usuarios_acesso_total() -> None:
    """Garante acesso total apenas quando configurado explicitamente."""
    perfil_norm = (DEFAULT_ADMIN_PERFIL or "").strip().lower()
    if perfil_norm != "acesso_total":
        return
    alvo_admin = normalizar_chave(DEFAULT_ADMIN_USER)
    alvo_email = (DEFAULT_ADMIN_EMAIL or "").strip().lower()
    usuarios = Usuario.query.all()
    tem_principal = any(getattr(u, "is_admin_principal", False) for u in usuarios)
    alterados = 0
    for usuario in usuarios:
        if tem_principal:
            deve_acesso_total = bool(getattr(usuario, "is_admin_principal", False))
        else:
            chave_username = normalizar_chave(usuario.username or "")
            email_usuario = (usuario.email or "").strip().lower()
            deve_acesso_total = chave_username == alvo_admin or (
                alvo_email and email_usuario == alvo_email
            )
        if usuario.acesso_total != deve_acesso_total:
            usuario.acesso_total = deve_acesso_total
            alterados += 1
    if alterados:
        db.session.commit()


def preencher_planilhador_padrao():
    """Preenche responsavel_adm quando estiver vazio, usando o usuario atribuido ou um valor generico."""
    pendentes = (
        Processo.query.filter(
            (Processo.responsavel_adm.is_(None))
            | (func.trim(Processo.responsavel_adm) == "")
        ).all()
    )
    alterados = 0
    for processo in pendentes:
        nome_planilhador = None
        if processo.assigned_to:
            nome_planilhador = processo.assigned_to.nome or processo.assigned_to.username
        if not nome_planilhador:
            nome_planilhador = "USUARIO"
        processo.responsavel_adm = nome_planilhador
        alterados += 1
    if alterados:
        db.session.commit()
        app.logger.info("Planilhador preenchido automaticamente em %s processos.", alterados)


# === Importacao de dados e inicializacao do banco ===
def inicializar():
    """Garante estrutura inicial do banco, dados base e normalizacoes."""
    if RESET_DATABASE_ON_START:
        app.logger.warning("RESET_DATABASE_ON_START=1 -> limpando todas as tabelas.")
        db.drop_all()
        db.session.commit()
    db.create_all()
    garantir_colunas_extra()
    garantir_usuario_padrao()
    if AUTO_CORRIGIR_DADOS_ON_START:
        promover_usuarios_acesso_total()
        preencher_planilhador_padrao()
        corrigidos = corrigir_gerencias_sem_cadastro()
        if corrigidos:
            app.logger.info("Gerncias atualizadas automaticamente: %s.", corrigidos)
    else:
        app.logger.info(
            "AUTO_CORRIGIR_DADOS_ON_START=0 -> pulando normalizacoes pesadas no startup."
        )


def aplicar_filtro_devolvidos_gabinete(consulta):
    """Remove processos marcados como devolvidos do gabinete."""
    dados_extra_txt = func.lower(cast(Processo.dados_extra, db.Text))
    return consulta.filter(
        or_(
            Processo.dados_extra.is_(None),
            ~dados_extra_txt.like('%"devolvido_gabinete"%true%'),
        )
    )


def aplicar_filtro_somente_devolvidos_gabinete(consulta):
    """Mantem apenas processos marcados como devolvidos ao gabinete."""
    dados_extra_txt = func.lower(cast(Processo.dados_extra, db.Text))
    return consulta.filter(dados_extra_txt.like('%"devolvido_gabinete"%true%'))


def obter_contagens_por_gerencia():
    """Calcula quantidade de processos ativos por gerencia."""
    contagens = {ger: 0 for ger in GERENCIAS}
    consulta = (
        db.session.query(Processo.gerencia, func.count(Processo.id))
        .filter(Processo.finalizado_em.is_(None))
    )
    consulta = aplicar_filtro_devolvidos_gabinete(consulta)
    for ger, total in consulta.group_by(Processo.gerencia).all():
        if ger in contagens:
            contagens[ger] = total
    return contagens


def obter_metricas_processos() -> Dict[str, Optional[float]]:
    """Calcula indicadores gerais de processos (andamento, finalizados e tempo medio)."""
    consulta_andamento = db.session.query(func.count(Processo.id)).filter(
        Processo.finalizado_em.is_(None)
    )
    consulta_andamento = aplicar_filtro_devolvidos_gabinete(consulta_andamento)
    total_andamento = consulta_andamento.scalar() or 0

    total_finalizados = (
        db.session.query(func.count(Processo.id))
        .filter(Processo.finalizado_em.isnot(None))
        .scalar()
    ) or 0

    registros_finalizados = (
        db.session.query(Processo.data_entrada, Processo.finalizado_em)
        .filter(
            Processo.finalizado_em.isnot(None),
            Processo.data_entrada.isnot(None),
        )
        .all()
    )

    duracoes_segundos = [
        (finalizado - datetime.combine(entrada, datetime.min.time())).total_seconds()
        for entrada, finalizado in registros_finalizados
        if entrada and finalizado and finalizado >= datetime.combine(entrada, datetime.min.time())
    ]

    tempo_medio_dias = (
        (sum(duracoes_segundos) / len(duracoes_segundos)) / 86400 if duracoes_segundos else None
    )

    return {
        "andamento": int(total_andamento),
        "finalizados": int(total_finalizados),
        "tempo_medio_dias": tempo_medio_dias,
    }


def corrigir_gerencias_sem_cadastro() -> int:
    """Ajusta registros antigos mapeando gerencias para nomenclatura atual."""
    atualizados = 0
    for processo in Processo.query.all():
        gerencia_corrigida = normalizar_gerencia(processo.gerencia, permitir_entrada=True)
        if not gerencia_corrigida:
            continue
        if gerencia_corrigida == "ENTRADA":
            gerencia_corrigida = GERENCIA_PADRAO
        if processo.gerencia != gerencia_corrigida:
            processo.gerencia = gerencia_corrigida
            atualizados += 1
    if atualizados:
        db.session.commit()
    return atualizados


def garantir_colunas_extra():
    """Adiciona colunas novas quando o banco foi criado em versoes antigas."""
    insp = inspect(db.engine)
    colunas = {col["name"] for col in insp.get_columns("processos")}
    alteracoes = []
    if "finalizado_em" not in colunas:
        alteracoes.append("ALTER TABLE processos ADD COLUMN finalizado_em DATETIME")
    if "finalizado_por" not in colunas:
        alteracoes.append("ALTER TABLE processos ADD COLUMN finalizado_por VARCHAR(80)")
    if "assigned_to_id" not in colunas:
        alteracoes.append("ALTER TABLE processos ADD COLUMN assigned_to_id INTEGER")
    if "dados_extra" not in colunas:
        alteracoes.append("ALTER TABLE processos ADD COLUMN dados_extra TEXT")

    for comando in alteracoes:
        with db.engine.begin() as conexao:
            conexao.execute(text(comando))

    # Ajustes na tabela de usuarios
    colunas_usuarios = {col["name"] for col in insp.get_columns("usuarios")}
    alteracoes_usuarios = []
    adicionou_permissoes = False
    if "is_admin" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN is_admin BOOLEAN DEFAULT 0")
    if "is_admin_principal" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN is_admin_principal BOOLEAN DEFAULT 0"
        )
    if "is_gerente" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN is_gerente BOOLEAN DEFAULT 0")
    if "acesso_total" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN acesso_total BOOLEAN DEFAULT 0")
    if "must_reset_password" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN must_reset_password BOOLEAN DEFAULT 0"
        )
    if "email" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN email VARCHAR(255)")
    if "nome" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN nome VARCHAR(120)")
    if "gerencia_padrao" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN gerencia_padrao VARCHAR(50)")
    if "gerencias_liberadas" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN gerencias_liberadas TEXT")
    if "coordenadoria" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN coordenadoria VARCHAR(120)")
    if "equipe_area" not in colunas_usuarios:
        alteracoes_usuarios.append("ALTER TABLE usuarios ADD COLUMN equipe_area VARCHAR(120)")
    if "aparece_atribuido_sei" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN aparece_atribuido_sei BOOLEAN DEFAULT FALSE"
        )
    if "pode_cadastrar_processo" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN pode_cadastrar_processo BOOLEAN DEFAULT 0"
        )
        adicionou_permissoes = True
    if "pode_finalizar_gerencia" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN pode_finalizar_gerencia BOOLEAN DEFAULT TRUE"
        )
    if "pode_exportar" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN pode_exportar BOOLEAN DEFAULT 0"
        )
        adicionou_permissoes = True
    if "pode_importar" not in colunas_usuarios:
        alteracoes_usuarios.append(
            "ALTER TABLE usuarios ADD COLUMN pode_importar BOOLEAN DEFAULT 0"
        )
        adicionou_permissoes = True

    for comando in alteracoes_usuarios:
        with db.engine.begin() as conexao:
            conexao.execute(text(comando))
    with db.engine.begin() as conexao:
        conexao.execute(
            text(
                "UPDATE usuarios SET pode_finalizar_gerencia = TRUE "
                "WHERE pode_finalizar_gerencia IS NULL"
            )
        )
    if adicionou_permissoes:
        with db.engine.begin() as conexao:
            conexao.execute(
                text(
                    "UPDATE usuarios SET "
                    "pode_exportar = 1, "
                    "pode_importar = 1 "
                    "WHERE is_admin = 1 OR acesso_total = 1 OR is_gerente = 1"
                )
            )
            conexao.execute(
                text(
                    "UPDATE usuarios SET pode_cadastrar_processo = 1 "
                    "WHERE is_admin = 1 OR acesso_total = 1 OR gerencia_padrao = 'GABINETE'"
                )
            )

    usuarios_sem_lista = (
        Usuario.query.filter(
            Usuario.gerencia_padrao.isnot(None),
            or_(
                Usuario.gerencias_liberadas.is_(None),
                func.trim(Usuario.gerencias_liberadas) == "",
            ),
        ).all()
    )
    if usuarios_sem_lista:
        for usuario in usuarios_sem_lista:
            usuario.gerencias_liberadas = serializar_gerencias_liberadas(
                [usuario.gerencia_padrao]
            )
        db.session.commit()

    # Ajustes na tabela de movimentacoes
    colunas_mov = {col["name"] for col in insp.get_columns("movimentacoes")}
    alteracoes_mov = []
    if "dados_snapshot" not in colunas_mov:
        alteracoes_mov.append("ALTER TABLE movimentacoes ADD COLUMN dados_snapshot TEXT")
    if "tipo" not in colunas_mov:
        alteracoes_mov.append("ALTER TABLE movimentacoes ADD COLUMN tipo VARCHAR(40) DEFAULT 'movimentacao'")

    for comando in alteracoes_mov:
        with db.engine.begin() as conexao:
            conexao.execute(text(comando))

    # Indices para reduzir tempo de filtros/ordenacao nas telas com alto volume.
    # (apenas colunas fisicas existentes no banco)
    insp = inspect(db.engine)
    colunas_proc_atual = {col["name"] for col in insp.get_columns("processos")}
    colunas_mov_atual = {col["name"] for col in insp.get_columns("movimentacoes")}

    indices = []
    if "finalizado_em" in colunas_proc_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_processos_finalizado_em ON processos (finalizado_em)"
        )
    if "numero_sei" in colunas_proc_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_processos_numero_sei ON processos (numero_sei)"
        )
    if "gerencia" in colunas_proc_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_processos_gerencia ON processos (gerencia)"
        )
    if "atualizado_em" in colunas_proc_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_processos_atualizado_em ON processos (atualizado_em)"
        )
    if "processo_id" in colunas_mov_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_movimentacoes_processo_id ON movimentacoes (processo_id)"
        )
    if "criado_em" in colunas_mov_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_movimentacoes_criado_em ON movimentacoes (criado_em)"
        )
    if "tipo" in colunas_mov_atual:
        indices.append(
            "CREATE INDEX IF NOT EXISTS idx_movimentacoes_tipo ON movimentacoes (tipo)"
        )

    for comando in indices:
        with db.engine.begin() as conexao:
            conexao.execute(text(comando))


# === Filtros de template (datas) ===
@app.template_filter("date_input")
def filtro_date_input(valor):
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    return ""


@app.template_filter("date_br")
def filtro_date_br(valor):
    if isinstance(valor, datetime):
        valor = valor.date()
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return "-"


@app.template_filter("trilha_gerencias")
def filtro_trilha_gerencias(valores):
    """Formata lista de gerencias com seta entre elas."""
    if not valores:
        return "-"
    if isinstance(valores, str):
        return valores
    nomes = ordenar_gerencias_preferencial(
        [str(valor).strip() for valor in valores if str(valor).strip()]
    )
    return " -> ".join(nomes) if nomes else "-"


# === Rotas principais (Dashboard e listagens) ===
@app.route("/")
def index():
    """Renderiza o dashboard principal com filtros e paginacao."""
    filtro_gerencia_bruto = request.args.get("gerencia", "")
    filtro_gerencia = normalizar_gerencia(filtro_gerencia_bruto)
    filtro_sei = request.args.get("sei", "").strip()
    filtro_prazo = (request.args.get("prazo") or "").strip().lower()
    pagina = request.args.get("page", type=int, default=1)
    por_pagina = 10

    hoje = datetime.utcnow().date()

    processos = []
    paginacao = None
    contagens = {ger: 0 for ger in GERENCIAS}
    metricas = None
    contagem_saida = 0
    meus_processos_total = 0
    meus_processos_novos = 0
    gerencia_padrao_usuario = None

    if not SITE_EM_CONFIGURACAO:
        consulta = Processo.query.filter(Processo.finalizado_em.is_(None))
        consulta = aplicar_filtro_devolvidos_gabinete(consulta)
        if filtro_gerencia:
            consulta = consulta.filter(Processo.gerencia == filtro_gerencia)
        if filtro_sei:
            consulta = consulta.filter(Processo.numero_sei.ilike(f"%{filtro_sei}%"))
        if filtro_prazo == "vencido":
            consulta = consulta.filter(Processo.prazo.isnot(None), Processo.prazo < hoje)
        elif filtro_prazo == "proximo":
            limite = hoje + timedelta(days=7)
            consulta = consulta.filter(
                Processo.prazo.isnot(None),
                Processo.prazo >= hoje,
                Processo.prazo <= limite,
            )
        elif filtro_prazo == "em_dia":
            limite = hoje + timedelta(days=7)
            consulta = consulta.filter(
                or_(Processo.prazo.is_(None), Processo.prazo > limite)
            )

        paginacao = consulta.order_by(Processo.atualizado_em.desc()).paginate(
            page=pagina, per_page=por_pagina, error_out=False
        )
        processos = paginacao.items
        contagens = obter_contagens_por_gerencia()
        metricas = obter_metricas_processos()
        contagem_saida = (
            db.session.query(func.count(Processo.id))
            .filter(Processo.finalizado_em.is_(None), Processo.gerencia == "SAIDA")
            .scalar()
            or 0
        )
        if current_user.is_authenticated:
            gerencias_usuario = [
                g for g in obter_gerencias_liberadas_usuario(current_user) if g in GERENCIAS
            ]
            gerencia_padrao_usuario = (
                gerencias_usuario[0]
                if gerencias_usuario
                else (
                    normalizar_gerencia(current_user.gerencia_padrao or "", permitir_entrada=True)
                    or "GABINETE"
                )
            )
            filtro_meus_processos = [
                Processo.finalizado_em.is_(None),
                Processo.assigned_to_id == current_user.id,
            ]
            if gerencias_usuario:
                filtro_meus_processos.append(Processo.gerencia.in_(gerencias_usuario))
            else:
                filtro_meus_processos.append(Processo.gerencia == gerencia_padrao_usuario)
            meus_processos_total = (
                aplicar_filtro_devolvidos_gabinete(
                    db.session.query(func.count(Processo.id)).filter(*filtro_meus_processos)
                ).scalar()
                or 0
            )
            vistos = session.get("meus_processos_visto", 0)
            meus_processos_novos = max(meus_processos_total - vistos, 0)

    return render_template(
        "pg_inicial.html",
        processos=processos,
        paginacao=paginacao,
        contagens=contagens,
        contagem_saida=contagem_saida,
        imagens_gerencias=GERENCIA_ILUSTRACOES,
        imagem_gerencia_padrao=ILUSTRACAO_GERENCIA_PADRAO,
        metricas=metricas,
        filtro_gerencia=filtro_gerencia or "",
        filtro_sei=filtro_sei,
        filtro_prazo=filtro_prazo,
        now=hoje,
        now_plus_7=hoje + timedelta(days=7),
        extras_por_gerencia=gerar_mapa_campos_extra(),
        pode_exportar_global=usuario_pode_exportar_global(),
        pode_importar_global=usuario_pode_importar_global(),
        pode_cadastrar_processo=usuario_pode_cadastrar_processo(),
        meus_processos_total=meus_processos_total,
        meus_processos_novos=meus_processos_novos,
        gerencia_padrao_usuario=gerencia_padrao_usuario,
    )


@app.route("/exportar-geral", methods=["POST"])
@login_required
def exportar_geral():
    """Exporta processos em Excel com escopo global (ativos, finalizados ou todos)."""
    if not usuario_pode_exportar_global():
        flash("Sem permissao para exportar relatorios.", "danger")
        return redirect(url_for("index"))

    escopo = request.form.get("escopo") or "ativos"
    filtro_gerencia = normalizar_gerencia(request.form.get("gerencia") or "", permitir_entrada=True)
    colunas = request.form.getlist("colunas")
    if not colunas:
        flash("Selecione ao menos uma coluna para exportar.", "warning")
        return redirect(url_for("index"))

    base_colunas = {
        "numero_sei": ("Número SEI", lambda p: p.numero_sei_base),
        "assunto": ("Assunto", lambda p: p.assunto),
        "interessado": ("Interessado", lambda p: p.interessado),
        "concessionaria": ("Concessionaria", lambda p: p.concessionaria),
        "gerencia": ("Gerência", lambda p: p.gerencia),
        "data_entrada": ("Data entrada", lambda p: p.data_entrada.strftime("%d/%m/%Y") if p.data_entrada else ""),
        "prazo": ("Prazo SUROD", lambda p: p.prazo.strftime("%d/%m/%Y") if p.prazo else ""),
        "status": ("Status", lambda p: p.status),
        "prazo_equipe": ("Prazo equipe", lambda p: p.prazo_equipe.strftime("%d/%m/%Y") if p.prazo_equipe else ""),
        "responsavel_adm": ("Responsavel Adm", lambda p: p.responsavel_adm),
        "coordenadoria": ("Coordenadoria", lambda p: p.coordenadoria),
        "equipe_area": ("Equipe / Area", lambda p: p.equipe_area),
        "responsavel_equipe": ("Responsavel (Equipe)", lambda p: p.responsavel_equipe),
        "tipo_processo": ("Tipo de processo", lambda p: p.tipo_processo),
        "palavras_chave": ("Palavras-chave", lambda p: p.palavras_chave),
        "observacoes_complementares": (
            "Observacoes complementares",
            lambda p: p.observacoes_complementares,
        ),
        "finalizado_em": (
            "Finalizado em",
            lambda p: p.finalizado_em.strftime("%d/%m/%Y %H:%M") if p.finalizado_em else "",
        ),
    }

    extras_por_gerencia = obter_campos_por_gerencia()
    extras_map = {}
    for ger, campos in extras_por_gerencia.items():
        for campo in campos:
            extras_map[f"extra:{ger}:{campo.slug}"] = (campo.label, ger, campo.slug)

    consulta = Processo.query
    if filtro_gerencia:
        consulta = consulta.filter(Processo.gerencia == filtro_gerencia)
    if escopo == "ativos":
        consulta = consulta.filter(Processo.finalizado_em.is_(None))
    elif escopo == "finalizados":
        consulta = consulta.filter(Processo.finalizado_em.isnot(None))

    processos = consulta.order_by(Processo.atualizado_em.desc()).all()
    if not processos:
        flash("Nenhum processo encontrado para exportacao.", "info")
        return redirect(url_for("index"))

    cabecalhos = []
    for chave in colunas:
        if chave in base_colunas:
            cabecalhos.append(base_colunas[chave][0])
        elif chave in extras_map:
            label, ger, _ = extras_map[chave]
            cabecalhos.append(f"{label} ({ger})")
        else:
            cabecalhos.append(chave)

    linhas = []
    for proc in processos:
        linha = []
        for chave in colunas:
            if chave in base_colunas:
                _, getter = base_colunas[chave]
                linha.append(getter(proc))
            elif chave in extras_map:
                _, ger_destino, slug = extras_map[chave]
                if proc.gerencia == ger_destino:
                    linha.append((proc.dados_extra or {}).get(slug, ""))
                else:
                    linha.append("")
            else:
                linha.append("")
        linhas.append(linha)

    df = pd.DataFrame(linhas, columns=cabecalhos)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Processos", index=False)
    buffer.seek(0)
    nome_arquivo = f"processos_geral_{datetime.utcnow():%Y%m%d%H%M}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/importar-excel", methods=["GET", "POST"])
@login_required
def importar_excel():
    """Importa processos a partir de uma planilha Excel."""
    if SITE_EM_CONFIGURACAO:
        flash("Importacao de processos indisponivel durante a configuracao.", "info")
        return redirect(url_for("index"))
    if not usuario_pode_importar_global():
        flash("Sem permissao para importar planilhas.", "danger")
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template(
            "importar_excel.html",
            etapa="upload",
            campos_importacao=IMPORT_FIELDS,
        )

    acao = (request.form.get("acao") or "mapear").strip().lower()

    if acao == "mapear":
        token = request.form.get("token")
        info = _obter_importacao_temp(token) if token else None
        caminho = info.get("caminho") if info else None
        if not caminho:
            arquivo = request.files.get("arquivo")
            if not arquivo or not arquivo.filename:
                flash("Selecione um arquivo Excel para importar.", "warning")
                return redirect(url_for("importar_excel"))
            tamanho_upload = _tamanho_upload_bytes(arquivo)
            if tamanho_upload and tamanho_upload > MAX_IMPORT_FILE_SIZE_BYTES:
                limite_mb = int(MAX_IMPORT_FILE_SIZE_BYTES / (1024 * 1024))
                tamanho_mb = round(tamanho_upload / (1024 * 1024), 2)
                flash(
                    (
                        f"Arquivo muito grande ({tamanho_mb} MB). "
                        f"Limite atual: {limite_mb} MB."
                    ),
                    "warning",
                )
                return redirect(url_for("importar_excel"))

            token = _registrar_importacao_temp(arquivo)
            if not token:
                flash("Nao foi possivel preparar o arquivo de importacao.", "danger")
                return redirect(url_for("importar_excel"))
            info = _obter_importacao_temp(token)
            caminho = info.get("caminho") if info else None
            if not caminho:
                flash("Nao foi possivel localizar o arquivo de importacao.", "danger")
                return redirect(url_for("importar_excel"))

        suporte_msg = _validar_suporte_excel(caminho)
        if suporte_msg:
            flash(suporte_msg, "warning")
            _remover_importacao_temp(token)
            return redirect(url_for("importar_excel"))
        engine = _excel_engine_para(caminho)
        dependencia_msg = _garantir_dependencia_excel(engine)
        if dependencia_msg:
            flash(dependencia_msg, "danger")
            _remover_importacao_temp(token)
            return redirect(url_for("importar_excel"))

        sheet_names = _coletar_planilhas_excel(caminho)
        sheet_name = request.form.get("sheet_name")
        if sheet_names:
            if sheet_name not in sheet_names:
                sheet_name = sheet_names[0]
        else:
            sheet_name = 0

        header_row = _normalizar_linha_cabecalho(request.form.get("header_row"), 1)
        header_index = max(header_row - 1, 0)

        try:
            kwargs = {"engine": engine} if engine else {}
            df_preview = pd.read_excel(
                caminho,
                nrows=5,
                sheet_name=sheet_name,
                header=header_index,
                **kwargs,
            )
        except Exception as exc:
            app.logger.exception("Erro ao ler planilha de importacao: %s", exc)
            flash(_mensagem_erro_excel(caminho, exc), "danger")
            _remover_importacao_temp(token)
            return redirect(url_for("importar_excel"))

        if df_preview.empty:
            flash("A planilha esta vazia.", "warning")
            _remover_importacao_temp(token)
            return redirect(url_for("importar_excel"))

        df_preview.columns = [str(col) for col in df_preview.columns]
        colunas = [str(col) for col in df_preview.columns]
        preview = df_preview.fillna("").to_dict(orient="records")
        sugestoes = _sugerir_mapeamento_importacao(colunas)

        return render_template(
            "importar_excel.html",
            etapa="mapa",
            token=token,
            colunas=colunas,
            preview=preview,
            nome_arquivo=info.get("nome") if info else None,
            mapa_atual=sugestoes,
            campos_importacao=IMPORT_FIELDS,
            sheet_names=sheet_names,
            sheet_name_atual=sheet_name,
            header_row=header_row,
        )

    token = request.form.get("token")
    info = _obter_importacao_temp(token)
    caminho = info.get("caminho") if info else None
    if not caminho:
        flash("Arquivo de importacao expirou. Envie novamente.", "warning")
        return redirect(url_for("importar_excel"))

    suporte_msg = _validar_suporte_excel(caminho)
    if suporte_msg:
        flash(suporte_msg, "warning")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))
    engine = _excel_engine_para(caminho)
    dependencia_msg = _garantir_dependencia_excel(engine)
    if dependencia_msg:
        flash(dependencia_msg, "danger")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))

    sheet_name = request.form.get("sheet_name") or 0
    header_row = _normalizar_linha_cabecalho(request.form.get("header_row"), 1)
    header_index = max(header_row - 1, 0)
    try:
        kwargs = {"engine": engine} if engine else {}
        df = pd.read_excel(caminho, sheet_name=sheet_name, header=header_index, **kwargs)
    except Exception as exc:
        app.logger.exception("Erro ao ler planilha de importacao: %s", exc)
        flash(_mensagem_erro_excel(caminho, exc), "danger")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))

    if df.empty:
        flash("A planilha esta vazia.", "warning")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))

    df.columns = [str(col) for col in df.columns]
    colunas = [str(col) for col in df.columns]
    sugestoes = _sugerir_mapeamento_importacao(colunas)

    mapeamento_usuario = {}
    for campo, _ in IMPORT_FIELDS:
        coluna = request.form.get(f"map_{campo}")
        if coluna:
            mapeamento_usuario[campo] = coluna

    colunas_map = {**sugestoes, **mapeamento_usuario}
    colunas_map = {campo: col for campo, col in colunas_map.items() if col in df.columns}

    if "numero_sei" not in colunas_map:
        preview = df.head(5).fillna("").to_dict(orient="records")
        flash("Mapeie a coluna Número SEI para continuar.", "danger")
        return render_template(
            "importar_excel.html",
            etapa="mapa",
            token=token,
            colunas=colunas,
            preview=preview,
            nome_arquivo=info.get("nome") if info else None,
            mapa_atual=colunas_map,
            campos_importacao=IMPORT_FIELDS,
            sheet_names=_coletar_planilhas_excel(caminho),
            sheet_name_atual=sheet_name,
            header_row=header_row,
        )

    obrigatorios = ["numero_sei"]
    faltando = [campo for campo in obrigatorios if campo not in colunas_map]
    if faltando:
        nomes = {
            "numero_sei": "Número SEI",
        }
        faltando_nomes = ", ".join(nomes.get(campo, campo) for campo in faltando)
        flash(f"Planilha sem colunas obrigatorias: {faltando_nomes}.", "danger")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))

    extras_por_gerencia = obter_campos_por_gerencia()
    extras_label_map = {
        ger: {normalizar_coluna_importacao(campo.label): campo for campo in campos}
        for ger, campos in extras_por_gerencia.items()
    }
    extras_colunas = {}
    for col in df.columns:
        texto_col = str(col)
        match = re.match(r"^(.*)\(([^)]+)\)\s*$", texto_col)
        if not match:
            continue
        label = match.group(1).strip()
        gerencia_bruta = match.group(2).strip()
        gerencia = normalizar_gerencia(gerencia_bruta, permitir_entrada=True)
        if not gerencia:
            continue
        campos_gerencia = extras_label_map.get(gerencia)
        if not campos_gerencia:
            continue
        label_norm = normalizar_coluna_importacao(label)
        campo_extra = campos_gerencia.get(label_norm)
        if campo_extra:
            extras_colunas[col] = campo_extra

    importados = 0
    pendentes_lote = 0
    invalidos = []
    responsavel_padrao = current_user.nome or current_user.username or "USUARIO"

    def obter_valor(row, campo):
        col = colunas_map.get(campo)
        if not col:
            return None
        return row.get(col)

    def texto_opcional(valor):
        texto = limpar_texto(valor, "")
        return texto or None

    def limitar_texto_bd(valor, max_len):
        """Limita texto para caber em colunas VARCHAR sem quebrar importacao."""
        texto = texto_opcional(valor)
        if texto is None or max_len <= 0:
            return texto
        return texto[:max_len]

    def limpar_numero_sei(valor):
        if valor is None:
            return ""
        try:
            if pd.isna(valor):
                return ""
        except Exception:
            pass
        if isinstance(valor, int):
            return str(valor)
        if isinstance(valor, float) and valor.is_integer():
            return str(int(valor))
        texto = str(valor).strip()
        if re.fullmatch(r"\d+\.0", texto):
            return texto[:-2]
        return texto

    def extrair_prefixo_gerencia(numero):
        numero = (numero or "").strip()
        if not numero:
            return None, ""
        if "-" in numero:
            prefixo_bruto, resto = numero.split("-", 1)
            prefixo_norm = normalizar_gerencia(prefixo_bruto)
            if prefixo_norm:
                return prefixo_norm, resto.strip()
        return None, numero

    def parse_datetime(valor):
        if valor is None:
            return None
        try:
            if pd.isna(valor):
                return None
        except Exception:
            pass
        if isinstance(valor, datetime):
            return valor
        if isinstance(valor, date):
            return datetime.combine(valor, datetime.min.time())
        data = parse_date(valor)
        if data:
            return datetime.combine(data, datetime.min.time())
        return None

    def _commit_lote_importacao() -> bool:
        """Confirma o lote atual de importacao no banco."""
        nonlocal importados, pendentes_lote
        if pendentes_lote <= 0:
            return True
        try:
            db.session.commit()
            importados += pendentes_lote
            pendentes_lote = 0
            return True
        except Exception as exc:
            db.session.rollback()
            app.logger.exception("Erro ao salvar lote da importacao: %s", exc)
            return False

    for idx, row in df.iterrows():
        linha_num = idx + 2
        numero_raw = limpar_numero_sei(obter_valor(row, "numero_sei"))
        assunto = limpar_texto(obter_valor(row, "assunto"), "NAO INFORMADO")
        interessado = limpar_texto(obter_valor(row, "interessado"), "NAO INFORMADO")
        if not numero_raw:
            invalidos.append(f"Linha {linha_num}: Número SEI ausente")
            continue

        gerencia_col = normalizar_gerencia(obter_valor(row, "gerencia"))
        prefixo_gerencia, numero_base = extrair_prefixo_gerencia(numero_raw)
        gerencia = gerencia_col or prefixo_gerencia or GERENCIA_PADRAO
        if not numero_base:
            invalidos.append(f"Linha {linha_num}: Número SEI ausente")
            continue

        numero_formatado = f"{gerencia}-{numero_base}".strip()[:50]

        prazo = parse_date(obter_valor(row, "prazo"))
        data_entrada = parse_date(obter_valor(row, "data_entrada"))
        data_status = parse_date(obter_valor(row, "data_status"))
        prazo_equipe = parse_date(obter_valor(row, "prazo_equipe"))
        data_saida = parse_date(obter_valor(row, "data_saida"))
        finalizado_em = parse_datetime(obter_valor(row, "finalizado_em"))
        status_raw = texto_opcional(obter_valor(row, "status"))
        if not finalizado_em and data_saida:
            finalizado_em = datetime.combine(data_saida, datetime.min.time())
        if not finalizado_em and status_raw:
            status_norm = normalizar_chave(status_raw)
            if "FINALIZADO" in status_norm and data_status:
                finalizado_em = datetime.combine(data_status, datetime.min.time())
        if isinstance(finalizado_em, datetime):
            # Importacao de planilha: hora desconhecida, padroniza para 00:00:00.
            finalizado_em = datetime.combine(finalizado_em.date(), datetime.min.time())

        responsavel_adm = (
            limitar_texto_bd(obter_valor(row, "responsavel_adm"), 255)
            or limitar_texto_bd(responsavel_padrao, 255)
            or "USUARIO"
        )
        tramitado_para_raw = texto_opcional(obter_valor(row, "tramitado_para"))
        tramitado_para = (
            normalizar_gerencia(tramitado_para_raw, permitir_entrada=True)
            if tramitado_para_raw
            else None
        ) or limitar_texto_bd(tramitado_para_raw, 50)

        dados_extra = {
            "numero_sei_original": numero_base,
            "gerencias_escolhidas": [gerencia],
        }

        if extras_colunas:
            for col, campo_extra in extras_colunas.items():
                if campo_extra.gerencia != gerencia:
                    continue
                valor_extra = row.get(col)
                if valor_extra is None:
                    continue
                try:
                    if pd.isna(valor_extra):
                        continue
                except Exception:
                    pass
                if campo_extra.tipo == "data":
                    data_extra = parse_date(valor_extra)
                    if data_extra:
                        dados_extra[campo_extra.slug] = data_extra.strftime("%Y-%m-%d")
                else:
                    texto_extra = texto_opcional(valor_extra)
                    if texto_extra:
                        dados_extra[campo_extra.slug] = texto_extra

        processo = Processo(
            numero_sei=numero_formatado,
            assunto=limitar_texto_bd(assunto, 255) or "NAO INFORMADO",
            interessado=limitar_texto_bd(interessado, 255) or "NAO INFORMADO",
            concessionaria=limitar_texto_bd(obter_valor(row, "concessionaria"), 255),
            descricao=texto_opcional(obter_valor(row, "descricao")),
            gerencia=limitar_texto_bd(gerencia, 50) or GERENCIA_PADRAO,
            prazo=prazo,
            data_entrada=data_entrada,
            responsavel_adm=responsavel_adm,
            observacao=texto_opcional(obter_valor(row, "observacao")),
            descricao_melhorada=texto_opcional(obter_valor(row, "descricao_melhorada")),
            coordenadoria=limitar_texto_bd(obter_valor(row, "coordenadoria"), 255),
            equipe_area=limitar_texto_bd(obter_valor(row, "equipe_area"), 255),
            responsavel_equipe=limitar_texto_bd(obter_valor(row, "responsavel_equipe"), 255),
            tipo_processo=limitar_texto_bd(obter_valor(row, "tipo_processo"), 255),
            palavras_chave=limitar_texto_bd(obter_valor(row, "palavras_chave"), 255),
            status=limitar_texto_bd(status_raw, 100),
            data_status=data_status,
            prazo_equipe=prazo_equipe,
            observacoes_complementares=texto_opcional(
                obter_valor(row, "observacoes_complementares")
            ),
            data_saida=data_saida,
            tramitado_para=tramitado_para,
            finalizado_em=finalizado_em,
            finalizado_por=limitar_texto_bd(obter_valor(row, "finalizado_por"), 80),
            dados_extra=dados_extra,
        )

        classificacao = texto_opcional(obter_valor(row, "classificacao_institucional"))
        if classificacao:
            processo.classificacao_institucional = classificacao

        db.session.add(processo)

        # Para linhas importadas sem trilha historica, cria uma trilha minima consistente
        # usando as datas da planilha (cadastro -> finalizacao gerencia -> encerramento geral).
        usuario_evento = (
            limitar_texto_bd(obter_valor(row, "finalizado_por"), 80)
            or responsavel_adm
            or limitar_texto_bd(current_user.username if current_user.is_authenticated else "importacao", 80)
            or "importacao"
        )
        data_cadastro = (
            datetime.combine(data_entrada, datetime.min.time())
            if data_entrada
            else (
                datetime.combine(finalizado_em.date(), datetime.min.time())
                if isinstance(finalizado_em, datetime)
                else datetime.utcnow()
            )
        )
        db.session.add(
            Movimentacao(
                processo=processo,
                de_gerencia="CADASTRO",
                para_gerencia=gerencia,
                motivo="Cadastro importado via planilha",
                usuario=usuario_evento,
                tipo="cadastro",
                criado_em=data_cadastro,
            )
        )

        if isinstance(finalizado_em, datetime):
            dados_snapshot_import = {
                "assunto": assunto,
                "interessado": interessado,
                "concessionaria": texto_opcional(obter_valor(row, "concessionaria")),
                "coordenadoria": texto_opcional(obter_valor(row, "coordenadoria")),
                "equipe_area": texto_opcional(obter_valor(row, "equipe_area")),
                "responsavel_equipe": texto_opcional(obter_valor(row, "responsavel_equipe")),
                "status": status_raw,
                "prazo": prazo.strftime("%Y-%m-%d") if prazo else None,
                "prazo_equipe": prazo_equipe.strftime("%Y-%m-%d") if prazo_equipe else None,
                "observacoes_complementares": texto_opcional(
                    obter_valor(row, "observacoes_complementares")
                ),
                "extras": dados_extra,
            }
            # Importacao sem horario: mantem 00:00:00 e a ordem e controlada pela UI.
            data_finalizacao_gerencia = datetime.combine(
                finalizado_em.date(), datetime.min.time()
            )
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia=gerencia,
                    para_gerencia="SAIDA",
                    motivo="Finalizacao importada via planilha",
                    usuario=usuario_evento,
                    tipo="finalizacao_gerencia",
                    criado_em=data_finalizacao_gerencia,
                    dados_snapshot=dados_snapshot_import,
                )
            )
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia="SAIDA",
                    para_gerencia="FINALIZADO",
                    motivo="Encerramento geral importado via planilha",
                    usuario=usuario_evento,
                    tipo="finalizado_geral",
                    criado_em=finalizado_em,
                )
            )
        pendentes_lote += 1
        if pendentes_lote >= IMPORT_COMMIT_BATCH_SIZE:
            if not _commit_lote_importacao():
                flash("Falha ao salvar a importacao no banco de dados.", "danger")
                _remover_importacao_temp(token)
                return redirect(url_for("importar_excel"))

    if not _commit_lote_importacao():
        flash("Falha ao salvar a importacao no banco de dados.", "danger")
        _remover_importacao_temp(token)
        return redirect(url_for("importar_excel"))

    _remover_importacao_temp(token)

    if importados:
        flash(f"Importacao concluida: {importados} processo(s) inserido(s).", "success")
    else:
        flash("Nenhum processo foi importado.", "warning")
    if invalidos:
        detalhe = ", ".join(invalidos[:5])
        if len(invalidos) > 5:
            detalhe = f"{detalhe}..."
        flash(
            f"{len(invalidos)} linha(s) ignoradas por falta de Número SEI: {detalhe}.",
            "warning",
        )
    return redirect(url_for("index"))


@app.route("/gerencia/<string:nome_gerencia>")
def gerencia(nome_gerencia):
    """Lista processos ativos de uma gerencia especifica."""
    gerencia_alvo = normalizar_gerencia(nome_gerencia, permitir_entrada=True)
    if not gerencia_alvo or gerencia_alvo == "ENTRADA":
        flash("Gerncia informada  invlida.", "warning")
        return redirect(url_for("index"))

    filtro_sei = request.args.get("sei", "").strip()
    filtro_coordenadoria = request.args.get("coordenadoria", "").strip()
    filtro_equipe_area = request.args.get("equipe_area", "").strip()
    filtro_responsavel_equipe = request.args.get("responsavel_equipe", "").strip()
    pagina = request.args.get("page", type=int, default=1)
    aba_ativa = (request.args.get("aba") or "interacoes").strip().lower()
    pode_ver_devolvidos = (
        gerencia_alvo == "GABINETE"
        and usuario_tem_liberacao_gerencia("GABINETE", usuario=current_user)
    )
    if gerencia_alvo == "SAIDA":
        aba_ativa = "interacoes"
    abas_permitidas = {"interacoes", "arquivos"}
    if pode_ver_devolvidos:
        abas_permitidas.add("devolvidos")
    if aba_ativa not in abas_permitidas:
        aba_ativa = "interacoes"
    campos_extra = serializar_campos_extra(listar_campos_gerencia(gerencia_alvo))
    pode_configurar = usuario_pode_configurar_campos(gerencia_alvo)
    pode_editar_gerencia = usuario_pode_editar_gerencia(gerencia_alvo)
    pode_exportar_gerencia = usuario_pode_exportar_gerencia(gerencia_alvo)
    hoje = datetime.utcnow().date()

    processos = []
    paginacao = None
    finalizados = []
    devolvidos = []
    total_devolvidos = 0
    origens_saida = {}
    gerencias_envolvidas_map = {}
    gerencias_abertas_map = {}
    trilhas_saida_map = {}
    usuarios_disponiveis = []
    meus_processos_total_usuario = 0

    def aplicar_filtros_processo(consulta):
        """Aplica filtros basicos informados via query string."""
        if filtro_sei:
            consulta = consulta.filter(Processo.numero_sei.ilike(f"%{filtro_sei}%"))
        if filtro_coordenadoria:
            consulta = consulta.filter(Processo.coordenadoria.ilike(f"%{filtro_coordenadoria}%"))
        if filtro_equipe_area:
            consulta = consulta.filter(Processo.equipe_area.ilike(f"%{filtro_equipe_area}%"))
        if filtro_responsavel_equipe:
            consulta = consulta.filter(
                Processo.responsavel_equipe.ilike(f"%{filtro_responsavel_equipe}%")
            )
        return consulta

    def ordenar_finalizados(proc: Processo) -> datetime:
        """Ordena finalizados pelos mais recentes (finalizado -> data_saida -> atualizado)."""
        if proc.finalizado_em:
            return proc.finalizado_em
        if proc.data_saida:
            return datetime.combine(proc.data_saida, datetime.min.time())
        if proc.atualizado_em:
            return proc.atualizado_em
        if proc.criado_em:
            return proc.criado_em
        return datetime.min

    def _ordem_processo(proc: Processo) -> datetime:
        return proc.atualizado_em or proc.criado_em or datetime.min

    def agrupar_processos_saida(
        lista_processos: List[Processo],
        chave_referencia_por_base: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[Dict[str, object]]:
        """Agrupa processos da SAIDA por numero base/chave para evitar duplicidade."""
        chave_referencia_por_base = chave_referencia_por_base or {}
        grupos: Dict[tuple, Dict[str, object]] = {}
        for proc in lista_processos:
            numero_base = proc.numero_sei_base
            chave_ref = obter_chave_processo_relacional(proc) or (
                chave_referencia_por_base.get(numero_base) if numero_base else None
            )
            if not numero_base:
                chave_grupo = (f"id:{proc.id}", "")
            else:
                chave_grupo = (numero_base, chave_ref or "")
            grupo = grupos.get(chave_grupo)
            if not grupo:
                grupos[chave_grupo] = {
                    "representante": proc,
                    "numero_base": numero_base,
                    "chave_ref": chave_ref,
                    "processos": [proc],
                }
                continue
            grupo["processos"].append(proc)
            if _ordem_processo(proc) > _ordem_processo(grupo["representante"]):
                grupo["representante"] = proc
        grupos_lista = list(grupos.values())
        grupos_lista.sort(key=lambda g: _ordem_processo(g["representante"]), reverse=True)
        return grupos_lista

    def paginar_lista(itens: List[object], pagina_atual: int, por_pagina: int):
        """Paginação simples para listas já carregadas."""
        total = len(itens)
        por_pagina = por_pagina or total or 1
        total_paginas = max(1, (total + por_pagina - 1) // por_pagina)
        pagina_atual = max(1, min(pagina_atual, total_paginas))
        inicio = (pagina_atual - 1) * por_pagina
        fim = inicio + por_pagina

        class PaginacaoSimples:
            def __init__(self):
                self.page = pagina_atual
                self.per_page = por_pagina
                self.total = total

            @property
            def pages(self):
                return total_paginas

            @property
            def has_prev(self):
                return self.page > 1

            @property
            def has_next(self):
                return self.page < self.pages

            @property
            def prev_num(self):
                return max(1, self.page - 1)

            @property
            def next_num(self):
                return min(self.pages, self.page + 1)

        return itens[inicio:fim], PaginacaoSimples()

    if not SITE_EM_CONFIGURACAO:
        consulta = Processo.query.filter(
            Processo.gerencia == gerencia_alvo, Processo.finalizado_em.is_(None)
        )
        if gerencia_alvo == "GABINETE":
            consulta = aplicar_filtro_devolvidos_gabinete(consulta)
        consulta = aplicar_filtros_processo(consulta)

        if gerencia_alvo == "SAIDA":
            processos_filtrados = consulta.order_by(Processo.atualizado_em.desc()).all()

            bases_filtradas = {
                proc.numero_sei_base for proc in processos_filtrados if proc.numero_sei_base
            }
            relacionados_por_base: Dict[str, List[Processo]] = {}
            if bases_filtradas:
                for item in Processo.query.all():
                    base_item = item.numero_sei_base
                    if base_item in bases_filtradas:
                        relacionados_por_base.setdefault(base_item, []).append(item)

            chave_referencia_por_base: Dict[str, Optional[str]] = {}
            for base_item, relacionados in relacionados_por_base.items():
                chave_referencia_por_base[base_item] = obter_chave_referencia_unica_por_base(
                    relacionados
                )

            grupos_saida = agrupar_processos_saida(
                processos_filtrados, chave_referencia_por_base
            )
            grupos_pagina, paginacao = paginar_lista(grupos_saida, pagina, 10)
            processos = [grupo["representante"] for grupo in grupos_pagina]

            ignorar = {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}
            for grupo in grupos_pagina:
                rep = grupo["representante"]
                numero_base = grupo["numero_base"]
                chave_ref = grupo["chave_ref"] or (
                    chave_referencia_por_base.get(numero_base) if numero_base else None
                )
                if not numero_base:
                    relacionados_grupo = grupo["processos"]
                else:
                    relacionados_grupo = [
                        p
                        for p in relacionados_por_base.get(numero_base, [])
                        if processo_pertence_mesmo_grupo(
                            p,
                            numero_base=numero_base,
                            chave_referencia=chave_ref,
                        )
                    ]
                gerencias_validas = set()
                for item in relacionados_grupo:
                    extras_item = _normalizar_dados_extra(item.dados_extra)
                    if extras_item.get("devolvido_gabinete"):
                        continue
                    for ger in coletar_gerencias_envolvidas(item):
                        ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                        if ger_norm and ger_norm not in ignorar:
                            gerencias_validas.add(ger_norm)
                    ger_atual = normalizar_gerencia(item.gerencia, permitir_entrada=True)
                    if ger_atual and ger_atual not in ignorar:
                        gerencias_validas.add(ger_atual)

                gerencias_env = set()
                gerencias_abertas = set()
                for item in relacionados_grupo:
                    extras_item = _normalizar_dados_extra(item.dados_extra)
                    if extras_item.get("devolvido_gabinete"):
                        continue
                    gerencias_item = extras_item.get("gerencias_escolhidas") or []
                    gerencias_filtradas = []
                    if gerencias_item:
                        for ger in gerencias_item:
                            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                            if (
                                ger_norm
                                and ger_norm not in ignorar
                                and (not gerencias_validas or ger_norm in gerencias_validas)
                            ):
                                gerencias_filtradas.append(ger_norm)
                    if gerencias_filtradas:
                        for ger in gerencias_filtradas:
                            gerencias_env.add(ger)
                    else:
                        for ger in coletar_gerencias_envolvidas(item):
                            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                            if ger_norm and ger_norm not in ignorar:
                                gerencias_env.add(ger_norm)
                    ger_atual = normalizar_gerencia(item.gerencia, permitir_entrada=True)
                    if ger_atual and ger_atual not in ignorar:
                        gerencias_env.add(ger_atual)
                        if item.finalizado_em is None:
                            gerencias_abertas.add(ger_atual)
                gerencias_envolvidas_map[rep.id] = ordenar_gerencias_preferencial(
                    list(gerencias_env)
                )
                gerencias_abertas_map[rep.id] = ordenar_gerencias_preferencial(
                    list(gerencias_abertas)
                )
                trilhas_por_chave: Dict[str, Dict[str, object]] = {}
                for item in relacionados_grupo:
                    trilha_itens: List[str] = []
                    extras_item = _normalizar_dados_extra(item.dados_extra)
                    if extras_item.get("devolvido_gabinete"):
                        continue
                    gerencias_item = extras_item.get("gerencias_escolhidas") or []
                    if gerencias_item:
                        for ger in gerencias_item:
                            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                            if (
                                ger_norm
                                and ger_norm not in ignorar
                                and (not gerencias_validas or ger_norm in gerencias_validas)
                            ):
                                trilha_itens.append(ger_norm)
                    if not trilha_itens:
                        for ger in coletar_gerencias_envolvidas(item):
                            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                            if ger_norm and ger_norm not in ignorar:
                                trilha_itens.append(ger_norm)
                    if not trilha_itens:
                        ger_atual = normalizar_gerencia(item.gerencia, permitir_entrada=True)
                        if ger_atual and ger_atual not in ignorar:
                            trilha_itens.append(ger_atual)
                    vistos_trilha = set()
                    trilha_unica: List[str] = []
                    for ger in trilha_itens:
                        ger_txt = str(ger).strip()
                        if not ger_txt:
                            continue
                        slug = ger_txt.upper()
                        if slug in ignorar or slug in vistos_trilha:
                            continue
                        vistos_trilha.add(slug)
                        trilha_unica.append(ger_txt)
                    if not trilha_unica:
                        continue
                    trilha_texto = " -> ".join(trilha_unica)
                    ger_atual_open = normalizar_gerencia(item.gerencia, permitir_entrada=True)
                    aberta = (
                        item.finalizado_em is None
                        and ger_atual_open
                        and ger_atual_open not in ignorar
                    )
                    slug_aberta = (
                        str(ger_atual_open).strip().upper() if aberta and ger_atual_open else ""
                    )
                    partes = [
                        {"nome": ger, "aberta": str(ger).strip().upper() == slug_aberta}
                        for ger in trilha_unica
                    ]
                    registro = trilhas_por_chave.get(trilha_texto)
                    if registro:
                        if aberta:
                            registro["aberta"] = True
                        partes_reg = registro.get("partes") or []
                        if partes:
                            mapa_partes = {
                                str(item_parte.get("nome", "")).strip().upper(): item_parte
                                for item_parte in partes_reg
                                if str(item_parte.get("nome", "")).strip()
                            }
                            for item_parte in partes:
                                if not item_parte.get("aberta"):
                                    continue
                                chave = str(item_parte.get("nome", "")).strip().upper()
                                if chave in mapa_partes:
                                    mapa_partes[chave]["aberta"] = True
                                else:
                                    partes_reg.append(item_parte)
                            registro["partes"] = partes_reg
                    else:
                        trilhas_por_chave[trilha_texto] = {
                            "texto": trilha_texto,
                            "aberta": aberta,
                            "partes": partes,
                        }
                trilhas_lista = list(trilhas_por_chave.values())
                def _nomes_trilha(registro: Dict[str, object]) -> List[str]:
                    partes_reg = registro.get("partes") or []
                    nomes = [
                        str(parte.get("nome", "")).strip()
                        for parte in partes_reg
                        if str(parte.get("nome", "")).strip()
                    ]
                    if nomes:
                        return nomes
                    texto_reg = str(registro.get("texto", "") or "")
                    return [p.strip() for p in texto_reg.split("->") if p.strip()]

                prefixos: Dict[str, List[Dict[str, object]]] = {}
                for reg in trilhas_lista:
                    nomes = _nomes_trilha(reg)
                    if len(nomes) > 1:
                        chave = nomes[0].strip().upper()
                        if chave:
                            prefixos.setdefault(chave, []).append(reg)

                removidos = set()
                for reg in trilhas_lista:
                    nomes = _nomes_trilha(reg)
                    if len(nomes) != 1:
                        continue
                    chave = nomes[0].strip().upper()
                    if not chave or chave not in prefixos:
                        continue
                    if reg.get("aberta"):
                        for reg_long in prefixos.get(chave, []):
                            reg_long["aberta"] = True
                            partes_long = reg_long.get("partes") or []
                            for parte in partes_long:
                                nome_parte = str(parte.get("nome", "")).strip().upper()
                                if nome_parte == chave:
                                    parte["aberta"] = True
                            reg_long["partes"] = partes_long
                    removidos.add(reg.get("texto"))

                if removidos:
                    trilhas_lista = [reg for reg in trilhas_lista if reg.get("texto") not in removidos]
                trilhas_saida_map[rep.id] = trilhas_lista
        else:
            paginacao = consulta.order_by(Processo.atualizado_em.desc()).paginate(
                page=pagina, per_page=10, error_out=False
            )
            processos = paginacao.items

        consulta_finalizados = Processo.query.filter(
            Processo.gerencia == gerencia_alvo, Processo.finalizado_em.isnot(None)
        )
        if gerencia_alvo == "GABINETE":
            consulta_finalizados = aplicar_filtro_devolvidos_gabinete(consulta_finalizados)
        consulta_finalizados = aplicar_filtros_processo(consulta_finalizados)
        finalizados = (
            consulta_finalizados.order_by(Processo.finalizado_em.desc()).limit(50).all()
        )
        if pode_ver_devolvidos:
            consulta_devolvidos = Processo.query.filter(
                Processo.gerencia == "GABINETE",
                Processo.finalizado_em.is_(None),
            )
            consulta_devolvidos = aplicar_filtro_somente_devolvidos_gabinete(
                consulta_devolvidos
            )
            devolvidos = consulta_devolvidos.order_by(Processo.atualizado_em.desc()).all()
            total_devolvidos = len(devolvidos)
        # Inclui processos finalizados nesta gerencia e tramitados para outra.
        if gerencia_alvo != "SAIDA":
            ids_saida = [
                pid
                for (pid,) in db.session.query(Movimentacao.processo_id)
                .filter(
                    Movimentacao.de_gerencia == gerencia_alvo,
                    Movimentacao.para_gerencia == "SAIDA",
                )
                .all()
            ]
            if ids_saida:
                ids_saida = [
                    pid
                    for (pid,) in Processo.query.filter(
                        Processo.id.in_(ids_saida), Processo.gerencia == "SAIDA"
                    )
                    .with_entities(Processo.id)
                    .all()
                ]
            ids_finalizacao = [
                pid
                for (pid,) in db.session.query(Movimentacao.processo_id)
                .filter(
                    Movimentacao.de_gerencia == gerencia_alvo,
                    Movimentacao.tipo == "finalizacao_gerencia",
                )
                .all()
            ]
            ids_devolvidos = [
                pid
                for (pid,) in db.session.query(Movimentacao.processo_id)
                .filter(
                    Movimentacao.de_gerencia == "SAIDA",
                    Movimentacao.para_gerencia != "SAIDA",
                    Movimentacao.tipo == "movimentacao",
                )
                .all()
            ]
            if ids_devolvidos:
                ids_devolvidos = set(
                    pid
                    for (pid,) in Processo.query.filter(
                        Processo.id.in_(ids_devolvidos),
                        Processo.gerencia != "SAIDA",
                        Processo.finalizado_em.is_(None),
                    )
                    .with_entities(Processo.id)
                    .all()
                )
            else:
                ids_devolvidos = set()
            ids_extras = {pid for pid in ids_saida + ids_finalizacao if pid not in ids_devolvidos}
            if ids_extras:
                finalizados_ids = {p.id for p in finalizados}
                extras = (
                    aplicar_filtros_processo(Processo.query.filter(Processo.id.in_(ids_extras)))
                    .order_by(Processo.atualizado_em.desc())
                    .all()
                )
                for proc in extras:
                    origens_saida[proc.id] = gerencia_alvo
                finalizados = list({p.id: p for p in finalizados + extras}.values())
        else:
            # Quando a gerencia e SAIDA exibimos a origem real
            for proc in processos:
                origens_saida[proc.id] = obter_origem_saida(proc)
            for proc in finalizados:
                origens_saida[proc.id] = obter_origem_saida(proc)
        if finalizados:
            finalizados = sorted(finalizados, key=ordenar_finalizados, reverse=True)
        usuarios_disponiveis = listar_usuarios_por_gerencia(gerencia_alvo)
        if current_user.is_authenticated:
            meus_processos_total_usuario = (
                db.session.query(func.count(Processo.id))
                .filter(
                    Processo.finalizado_em.is_(None),
                    Processo.assigned_to_id == current_user.id,
                    Processo.gerencia == gerencia_alvo,
                )
                .scalar()
                or 0
            )
            if request.args.get("ack_meus_processos"):
                session["meus_processos_visto"] = meus_processos_total_usuario

    for lista_proc in (processos, finalizados, devolvidos):
        for processo in lista_proc:
            processo.dados_extra = _normalizar_dados_extra(getattr(processo, "dados_extra", None))

    historico_finalizados = {}

    def _normalizar_texto_historico(texto: Optional[str]) -> str:
        return " ".join((texto or "").strip().lower().split())

    def _prioridade_evento_historico(texto: Optional[str]) -> int:
        texto_norm = _normalizar_texto_historico(texto)
        if texto_norm.startswith("destino saida"):
            return 40
        if "processo encerrado em saida" in texto_norm:
            return 30
        if "demanda finalizada" in texto_norm:
            return 20
        if "demanda cadastrada" in texto_norm:
            return 10
        return 0

    for processo in finalizados:
        eventos = []
        gerencia_criacao = origens_saida.get(processo.id) or processo.gerencia
        criador_legado = (
            processo.responsavel_adm
            or (processo.assigned_to.nome or processo.assigned_to.username if processo.assigned_to else None)
            or "usuario"
        )
        movs = sorted(processo.movimentacoes, key=lambda m: m.criado_em or datetime.min)

        possui_evento_cadastro = any((m.tipo or "").lower() == "cadastro" for m in movs)
        if not possui_evento_cadastro and processo.criado_em:
            termo_cad = _termo_por_gerencia(gerencia_criacao, "cadastro")
            acao_cad = _flexao_acao(termo_cad, "cadastrado", "cadastrada")
            envio_cad = _flexao_acao(termo_cad, "enviado", "enviada")
            eventos.append(
                {
                    "quando": processo.criado_em,
                    "texto": (
                        f"{termo_cad} {acao_cad} por {criador_legado} "
                        f"e {envio_cad} para {gerencia_criacao or '-'}."
                    ),
                }
            )

        for mov in movs:
            eventos.append(
                {
                    "quando": mov.criado_em,
                    "texto": montar_texto_evento_historico(
                        mov, gerencia_criacao=gerencia_criacao
                    ),
                }
            )

        possui_encerramento = any((m.tipo or "").lower() == "finalizado_geral" for m in movs)
        if processo.finalizado_em and not possui_encerramento:
            eventos.append(
                {
                    "quando": processo.finalizado_em,
                    "texto": (
                        f"Processo encerrado em {processo.gerencia} "
                        f"por {processo.finalizado_por or 'usuario'}."
                    ),
                }
            )

        eventos_ordenados = sorted(
            eventos, key=lambda e: e["quando"] or datetime.min
        )
        destino_saida = processo.tramitado_para if processo.gerencia == "SAIDA" else None
        if destino_saida:
            texto_destino = f"Destino SAIDA: {destino_saida}."
            if not any((ev.get("texto") or "").strip() == texto_destino for ev in eventos_ordenados):
                quando_destino = processo.finalizado_em or (
                    eventos_ordenados[-1]["quando"] if eventos_ordenados else None
                )
                if isinstance(quando_destino, datetime):
                    quando_destino = quando_destino + timedelta(seconds=1)
                eventos_ordenados.append(
                    {"quando": quando_destino, "texto": texto_destino}
                )

        eventos_unicos = []
        vistos_eventos = set()
        for evento in eventos_ordenados:
            quando = evento.get("quando")
            if isinstance(quando, datetime):
                chave_quando = int(quando.timestamp())
            else:
                chave_quando = 0
            chave_evento = (
                _normalizar_texto_historico(evento.get("texto")),
                chave_quando,
            )
            if chave_evento in vistos_eventos:
                continue
            vistos_eventos.add(chave_evento)
            eventos_unicos.append(evento)

        # Exibe historico do mais recente para o mais antigo.
        eventos_ordenados = sorted(
            eventos_unicos,
            key=lambda e: (
                e["quando"] or datetime.min,
                _prioridade_evento_historico(e.get("texto")),
            ),
            reverse=True,
        )
        historico_finalizados[processo.id] = eventos_ordenados

    snapshots_finalizados: Dict[int, Dict[str, object]] = {}
    if finalizados:
        ids_finalizados = [p.id for p in finalizados]
        movs = (
            Movimentacao.query.filter(
                Movimentacao.processo_id.in_(ids_finalizados),
                Movimentacao.de_gerencia == gerencia_alvo,
                Movimentacao.tipo.in_(["finalizacao_gerencia", "movimentacao"]),
            )
            .order_by(Movimentacao.criado_em.desc())
            .all()
        )
        for mov in movs:
            if mov.processo_id in snapshots_finalizados:
                continue
            snapshot = _normalizar_snapshot(getattr(mov, "dados_snapshot", None)) or {}
            if snapshot.get("data_status"):
                snapshot["data_status"] = parse_date(snapshot.get("data_status"))
            if snapshot.get("prazo_equipe"):
                snapshot["prazo_equipe"] = parse_date(snapshot.get("prazo_equipe"))
            if snapshot.get("prazo"):
                snapshot["prazo"] = parse_date(snapshot.get("prazo"))
            if snapshot.get("data_entrada"):
                snapshot["data_entrada"] = parse_date(snapshot.get("data_entrada"))
            if snapshot.get("data_entrada_geplan"):
                snapshot["data_entrada_geplan"] = parse_date(snapshot.get("data_entrada_geplan"))
            snapshots_finalizados[mov.processo_id] = snapshot

    return render_template(
        "gerencias.html",
        gerencia=gerencia_alvo,
        processos=processos,
        paginacao=paginacao,
        filtro_sei=filtro_sei,
        filtro_coordenadoria=filtro_coordenadoria,
        filtro_equipe_area=filtro_equipe_area,
        filtro_responsavel_equipe=filtro_responsavel_equipe,
        campos_extra=campos_extra,
        pode_configurar_campos=pode_configurar,
        pode_exportar_gerencia=pode_exportar_gerencia,
        pode_editar_gerencia=pode_editar_gerencia,
        pode_finalizar_gerencia=usuario_pode_finalizar_gerencia(),
        finalizados=finalizados,
        devolvidos=devolvidos,
        origens_saida=origens_saida,
        hoje=hoje,
        historico_finalizados=historico_finalizados,
        usuarios_disponiveis=usuarios_disponiveis,
        opcoes_coordenadorias=obter_coordenadorias_por_gerencia(gerencia_alvo),
        opcoes_equipes=obter_equipes_por_gerencia(gerencia_alvo),
        opcoes_equipes_por_coordenadoria=EQUIPES_POR_COORDENADORIA,
        opcoes_responsaveis=obter_responsaveis_por_gerencia(gerencia_alvo),
        opcoes_responsaveis_por_equipe=RESPONSAVEIS_POR_EQUIPE,
        snapshots_finalizados=snapshots_finalizados,
        aba_ativa=aba_ativa,
        pode_ver_devolvidos=pode_ver_devolvidos,
        total_devolvidos=total_devolvidos,
        gerencias_envolvidas_map=gerencias_envolvidas_map,
        gerencias_abertas_map=gerencias_abertas_map,
        trilhas_saida_map=trilhas_saida_map,
    )


@app.route("/gerencia/<string:nome_gerencia>/exportar", methods=["POST"])
@login_required
def exportar_gerencia(nome_gerencia: str):
    """Gera um arquivo Excel com processos da gerência (ativos/finalizados)."""
    gerencia_alvo = normalizar_gerencia(nome_gerencia, permitir_entrada=True)
    if not gerencia_alvo:
        flash("Gerência invalida para exportacao.", "warning")
        return redirect(url_for("index"))
    if not usuario_pode_exportar_gerencia(gerencia_alvo):
        flash("Sem permissao para exportar relatórios desta gerência.", "danger")
        return redirect(url_for("gerencia", nome_gerencia=gerencia_alvo))

    escopo = request.form.get("escopo") or "ativos"
    colunas = request.form.getlist("colunas")
    if not colunas:
        flash("Selecione ao menos uma coluna para exportar.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=gerencia_alvo))

    base_colunas = {
        "numero_sei": ("Número SEI", lambda p: p.numero_sei_base),
        "assunto": ("Assunto", lambda p: p.assunto),
        "interessado": ("Interessado", lambda p: p.interessado),
        "concessionaria": ("Concessionaria", lambda p: p.concessionaria),
        "gerencia": ("Gerência", lambda p: p.gerencia),
        "data_entrada": ("Data entrada", lambda p: p.data_entrada.strftime("%d/%m/%Y") if p.data_entrada else ""),
        "prazo": ("Prazo SUROD", lambda p: p.prazo.strftime("%d/%m/%Y") if p.prazo else ""),
        "status": ("Status", lambda p: p.status),
        "prazo_equipe": ("Prazo equipe", lambda p: p.prazo_equipe.strftime("%d/%m/%Y") if p.prazo_equipe else ""),
        "responsavel_adm": ("Responsavel Adm", lambda p: p.responsavel_adm),
        "coordenadoria": ("Coordenadoria", lambda p: p.coordenadoria),
        "equipe_area": ("Equipe / Area", lambda p: p.equipe_area),
        "responsavel_equipe": ("Responsavel (Equipe)", lambda p: p.responsavel_equipe),
        "tipo_processo": ("Tipo de processo", lambda p: p.tipo_processo),
        "palavras_chave": ("Palavras-chave", lambda p: p.palavras_chave),
        "observacoes_complementares": (
            "Observacoes complementares",
            lambda p: p.observacoes_complementares,
        ),
        "finalizado_em": (
            "Finalizado em",
            lambda p: p.finalizado_em.strftime("%d/%m/%Y %H:%M") if p.finalizado_em else "",
        ),
    }

    extras_defs = listar_campos_gerencia(gerencia_alvo)
    extras_map = {f"extra:{c.slug}": c for c in extras_defs}

    if escopo == "finalizados":
        consulta = Processo.query.filter(
            Processo.gerencia == gerencia_alvo, Processo.finalizado_em.isnot(None)
        )
    elif escopo == "todos":
        consulta = Processo.query.filter(Processo.gerencia == gerencia_alvo)
    else:  # ativos
        consulta = Processo.query.filter(
            Processo.gerencia == gerencia_alvo, Processo.finalizado_em.is_(None)
        )

    processos = consulta.order_by(Processo.atualizado_em.desc()).all()
    if not processos:
        flash("Nenhum processo encontrado para exportacao.", "info")
        return redirect(url_for("gerencia", nome_gerencia=gerencia_alvo))

    linhas = []
    cabecalhos = []
    for chave in colunas:
        if chave in base_colunas:
            cabecalhos.append(base_colunas[chave][0])
        elif chave in extras_map:
            cabecalhos.append(extras_map[chave].label)
        else:
            cabecalhos.append(chave)

    for proc in processos:
        linha = []
        for chave in colunas:
            if chave in base_colunas:
                _, getter = base_colunas[chave]
                linha.append(getter(proc))
            elif chave in extras_map:
                val = (proc.dados_extra or {}).get(extras_map[chave].slug, "")
                linha.append(val)
            else:
                linha.append("")
        linhas.append(linha)

    df = pd.DataFrame(linhas, columns=cabecalhos)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Processos", index=False)
    buffer.seek(0)

    nome_arquivo = f"processos_{gerencia_alvo.lower()}_{datetime.utcnow():%Y%m%d%H%M}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# === Gestao de campos extras por gerencia ===
@app.route("/gerencia/<string:nome_gerencia>/campos", methods=["GET", "POST"])
@login_required
def gerencia_campos(nome_gerencia):
    """Permite que gerentes/assessoria configurem campos extras."""
    gerencia_alvo = normalizar_gerencia(nome_gerencia, permitir_entrada=True)
    if not gerencia_alvo or gerencia_alvo == "ENTRADA":
        flash("Gerencia invalida para configuracao.", "warning")
        return redirect(url_for("index"))
    if not usuario_pode_configurar_campos(gerencia_alvo):
        abort(403)

    if request.method == "POST":
        acao = request.form.get("acao")
        if acao == "criar":
            label = limpar_texto(request.form.get("label"))
            tipo = request.form.get("tipo")
            if not label or tipo not in CAMPO_EXTRA_TIPOS:
                flash("Informe nome e tipo validos para o novo campo.", "warning")
            else:
                slug_base = _slugificar(label) or f"campo{int(datetime.utcnow().timestamp())}"
                slug = slug_base
                contador = 1
                while CampoExtra.query.filter_by(gerencia=gerencia_alvo, slug=slug).first():
                    slug = f"{slug_base}{contador}"
                    contador += 1
                campo = CampoExtra(
                    gerencia=gerencia_alvo,
                    label=label,
                    slug=slug,
                    tipo=tipo,
                    criado_por_id=current_user.id,
                )
                db.session.add(campo)
                db.session.commit()
                flash("Campo extra criado.", "success")
            return redirect(url_for("gerencia_campos", nome_gerencia=gerencia_alvo))
        elif acao == "remover":
            campo_id = request.form.get("campo_id", type=int)
            campo = CampoExtra.query.get_or_404(campo_id)
            if campo.gerencia != gerencia_alvo:
                abort(400)
            slug_removido = campo.slug
            db.session.delete(campo)
            for processo in Processo.query.filter_by(gerencia=gerencia_alvo).all():
                dados = processo.dados_extra or {}
                if slug_removido in dados:
                    dados.pop(slug_removido, None)
                    processo.dados_extra = dados
            db.session.commit()
            flash("Campo extra removido.", "info")
            return redirect(url_for("gerencia_campos", nome_gerencia=gerencia_alvo))

    campos = listar_campos_gerencia(gerencia_alvo)
    return render_template(
        "gerencia_campos.html",
        gerencia=gerencia_alvo,
        campos=campos,
        tipos=CAMPO_EXTRA_TIPOS,
    )


# === CRUD/Acoes do processo ===
@app.route("/processo/novo", methods=["GET", "POST"])
@login_required
def novo_processo():
    """Cria novo processo atribuindo diretamente a gerencia escolhida."""
    if SITE_EM_CONFIGURACAO:
        flash(
            "O cadastro de processos sera liberado apos a configuracao do banco de dados.",
            "info",
        )
        return redirect(url_for("index"))
    if not usuario_pode_cadastrar_processo():
        flash("Sem permissao para cadastrar novos processos.", "warning")
        return redirect(url_for("index"))

    gerencias_usuario = obter_gerencias_liberadas_usuario(current_user)
    gerencia_usuario = gerencias_usuario[0] if gerencias_usuario else normalizar_gerencia(
        getattr(current_user, "gerencia_padrao", None), permitir_entrada=True
    )
    gerencias_cadastro = GERENCIAS if usuario_tem_acesso_total(current_user) else (
        [g for g in gerencias_usuario if g in GERENCIAS] or ([gerencia_usuario] if gerencia_usuario else GERENCIAS)
    )

    form_data = {
        "data_entrada": request.form.get("data_entrada", "") if request.method == "POST" else "",
        "sei": request.form.get("sei", "") if request.method == "POST" else "",
        "prazo": request.form.get("prazo", "") if request.method == "POST" else "",
        "assunto": request.form.get("assunto", "") if request.method == "POST" else "",
        "interessado": request.form.get("interessado", "") if request.method == "POST" else "",
        "concessionaria": request.form.get("concessionaria", "") if request.method == "POST" else "N/A",
        "responsavel_adm": request.form.get("responsavel_adm", "") if request.method == "POST" else "",
        "observacao": request.form.get("observacao", "") if request.method == "POST" else "",
        "gerencias": request.form.getlist("gerencias") if request.method == "POST" else ([gerencia_usuario] if gerencia_usuario else []),
    }
    mensagens = []
    campos_invalidos: List[str] = []
    opcoes_responsavel_adm = obter_responsaveis_adm_disponiveis()
    analise_numero = {}

    if request.method == "POST":
        erros = []
        erros_invalidos: List[str] = []

        def obter_texto(campo, titulo):
            valor = limpar_texto(request.form.get(campo))
            if not valor:
                erros.append(titulo)
                campos_invalidos.append(campo)
            return valor

        def obter_data(campo, titulo, obrigatorio=True):
            valor = parse_date(request.form.get(campo))
            if obrigatorio and not valor:
                erros.append(titulo)
                campos_invalidos.append(campo)
            return valor

        def obter_texto_opcional(campo):
            return limpar_texto(request.form.get(campo))

        data_entrada = obter_data("data_entrada", "Data de entrada")
        numero_sei = obter_texto("sei", "Numero SEI")
        analise_numero = analisar_numero_para_cadastro(numero_sei)
        prazo = obter_data("prazo", "Prazo SUROD", obrigatorio=False)
        assunto = obter_texto("assunto", "Assunto")
        interessado = obter_texto("interessado", "Interessado")
        concessionaria = obter_texto("concessionaria", "Concessionaria")
        responsavel_adm = obter_texto("responsavel_adm", "Responsavel Adm")
        observacao = obter_texto_opcional("observacao")
        if concessionaria:
            mapa_concessionarias = {
                normalizar_chave(item): item for item in CONCESSIONARIAS if item
            }
            concessionaria_norm = normalizar_chave(concessionaria)
            concessionaria_ok = mapa_concessionarias.get(concessionaria_norm)
            if not concessionaria_ok:
                erros_invalidos.append("Concessionaria")
                campos_invalidos.append("concessionaria")
            else:
                concessionaria = concessionaria_ok

        # Permite selecionar varias gerencias; criaremos um processo para cada uma
        gerencias_raw = request.form.getlist("gerencias")
        gerencias_normalizadas: List[str] = []
        for item in gerencias_raw:
            g = normalizar_gerencia(item)
            if g and g not in gerencias_normalizadas:
                gerencias_normalizadas.append(g)
        if not usuario_tem_acesso_total(current_user):
            gerencias_permitidas = {g for g in gerencias_cadastro if g in GERENCIAS}
            gerencias_invalidas = [
                g for g in gerencias_normalizadas if g not in gerencias_permitidas
            ]
            if gerencias_invalidas:
                erros.append("Gerencia(s)")
                campos_invalidos.append("gerencias")
                mensagens.append(
                    (
                        "danger",
                        "Voce so pode cadastrar processos nas gerencias liberadas do seu perfil.",
                    )
                )
            gerencias_normalizadas = [
                g for g in gerencias_normalizadas if g in gerencias_permitidas
            ]
        if not gerencias_normalizadas:
            erros.append("Gerencia(s)")
            campos_invalidos.append("gerencias")

        gerencias_ativas_numero = set(analise_numero.get("ativos_gerencias") or [])
        gerencias_bloqueadas = [
            ger for ger in gerencias_normalizadas if ger in gerencias_ativas_numero
        ]
        if gerencias_bloqueadas:
            lista = ", ".join(gerencias_bloqueadas)
            erros.append("Gerencia(s)")
            campos_invalidos.append("gerencias")
            mensagens.append(
                (
                    "danger",
                    "Ja existe demanda ativa com este numero nas gerencias: "
                    f"{lista}. Verifique a demanda em aberto e, se necessario, finalize-a antes de cadastrar novamente.",
                )
            )

        if erros or erros_invalidos:
            if erros:
                mensagens.append(
                    (
                        "danger",
                        "Preencha todos os campos obrigatorios: " + ", ".join(erros) + ".",
                    )
                )
            if erros_invalidos:
                mensagens.append(
                    (
                        "danger",
                        "Selecione um valor valido da lista: "
                        + ", ".join(erros_invalidos)
                        + ".",
                    )
                )
            return render_template(
                "processo_form.html",
                processo=None,
                modo_edicao=False,
                mensagens=mensagens,
                form_data=form_data,
                campos_invalidos=campos_invalidos,
                selected_gerencias=form_data.get("gerencias", []),
                opcoes_concessionarias=CONCESSIONARIAS,
                opcoes_tipo_processo=TIPOS_PROCESSO,
                opcoes_interessados=INTERESSADOS,
                opcoes_responsavel_adm=opcoes_responsavel_adm,
                analise_numero=analise_numero,
                gerencias_cadastro=gerencias_cadastro,
            )

        numeros_para_criar: List[str] = []
        for ger in gerencias_normalizadas:
            numero_atual = f"{ger}-{numero_sei}"
            numeros_para_criar.append(numero_atual[:50])

        extras_base = {
            "gerencias_escolhidas": gerencias_normalizadas,
            "numero_sei_original": numero_sei,
            "responsavel_adm_inicial": responsavel_adm,
        }
        numero_base = analise_numero.get("numero_base") or extrair_numero_base_sei(numero_sei)

        # Se o numero ja existe, pode haver alteracao de dados imutaveis do processo.
        # Nesse caso, propaga assunto/interessado/concessionaria para todas as demandas
        # (ativas e finalizadas) do mesmo numero base.
        campos_propagados = []
        relacionados_mesmo_numero: List[Processo] = []
        if numero_base:
            relacionados_mesmo_numero = [
                p for p in Processo.query.all() if p.numero_sei_base == numero_base
            ]
        if relacionados_mesmo_numero:
            referencia_existente = sorted(
                relacionados_mesmo_numero,
                key=lambda p: p.atualizado_em or p.finalizado_em or p.criado_em or datetime.min,
                reverse=True,
            )[0]
            assunto_ref = (referencia_existente.assunto or "").strip()
            interessado_ref = (referencia_existente.interessado or "").strip()
            concessionaria_ref = (referencia_existente.concessionaria or "").strip()
            if assunto.strip() != assunto_ref:
                campos_propagados.append("Assunto")
            if interessado.strip() != interessado_ref:
                campos_propagados.append("Interessado")
            if concessionaria.strip() != concessionaria_ref:
                campos_propagados.append("Concessionaria")

        if relacionados_mesmo_numero and campos_propagados:
            for item in relacionados_mesmo_numero:
                item.assunto = assunto
                item.interessado = interessado
                item.concessionaria = concessionaria
                item.atualizado_em = datetime.utcnow()
                db.session.add(
                    Movimentacao(
                        processo=item,
                        de_gerencia=item.gerencia or "CADASTRO",
                        para_gerencia=item.gerencia or "CADASTRO",
                        motivo=(
                            "Atualizacao global de dados base do processo: "
                            f"{', '.join(campos_propagados)}."
                        ),
                        usuario=current_user.username,
                        tipo="edicao",
                    )
                )
        chave_processo = analise_numero.get("chave_referencia") or None
        if analise_numero.get("apenas_finalizados") and numero_base:
            # Novo retorno de processo ja encerrado: inicia ciclo novo e nao consolida com historico anterior.
            chave_processo = gerar_nova_chave_processo(numero_base)
        elif not chave_processo and numero_base:
            relacionados = [
                p for p in Processo.query.all() if p.numero_sei_base == numero_base
            ]
            chave_processo = obter_chave_referencia_unica_por_base(relacionados)

        for ger_destino, numero_atual in zip(gerencias_normalizadas, numeros_para_criar):
            processo = Processo(
                numero_sei=numero_atual,
                assunto=assunto,
                interessado=interessado,
                concessionaria=concessionaria,
                gerencia=ger_destino,
                prazo=prazo,
                responsavel_adm=responsavel_adm,
                observacao=observacao,
                data_entrada=data_entrada,
                dados_extra={
                    **extras_base,
                    **(
                        {"chave_processo": chave_processo}
                        if chave_processo
                        else {}
                    ),
                    **(
                        {"decisao_mesmo_numero": "nova_demanda"}
                    ),
                },
            )
            db.session.add(processo)
            db.session.flush()
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia="CADASTRO",
                    para_gerencia=ger_destino,
                    motivo="Cadastro inicial do processo",
                    usuario=current_user.username,
                    tipo="cadastro",
                )
            )

        db.session.commit()
        if relacionados_mesmo_numero and campos_propagados:
            flash(
                "Dados base atualizados em todas as demandas do mesmo processo "
                f"({', '.join(campos_propagados)}).",
                "warning",
            )
        flash(
            f"Processo enviado para: {', '.join(gerencias_normalizadas)}. Cada numero SEI inclui o prefixo da gerencia.",
            "success",
        )


        return redirect(url_for("index"))

    return render_template(
        "processo_form.html",
        processo=None,
        modo_edicao=False,
        mensagens=mensagens,
        form_data=form_data,
        campos_invalidos=campos_invalidos,
        selected_gerencias=form_data.get("gerencias", []),
        opcoes_concessionarias=CONCESSIONARIAS,
        opcoes_tipo_processo=TIPOS_PROCESSO,
        opcoes_interessados=INTERESSADOS,
        opcoes_responsavel_adm=opcoes_responsavel_adm,
        analise_numero=analise_numero,
        gerencias_cadastro=gerencias_cadastro,
    )


@app.route("/processo/inspecionar-numero")
@login_required
def inspecionar_numero_processo():
    """Retorna informacoes sobre demandas com o mesmo numero base."""
    numero_informado = limpar_texto(request.args.get("numero"), "")
    dados = analisar_numero_para_cadastro(numero_informado)
    return jsonify(
        {
            "numero_base": dados.get("numero_base") or "",
            "ativos_count": dados.get("ativos_count") or 0,
            "finalizados_count": dados.get("finalizados_count") or 0,
            "ativos_gerencias": dados.get("ativos_gerencias") or [],
            "precisa_decisao": bool(dados.get("precisa_decisao")),
            "apenas_finalizados": bool(dados.get("apenas_finalizados")),
            "prefill": dados.get("prefill") or None,
        }
    )


@app.route("/verificar-dados")
def verificar_dados():
    """Exibe painel com processos finalizados e filtros dinamicos."""
    filtro_gerencia = normalizar_gerencia(request.args.get("gerencia"), permitir_entrada=True)
    coordenadoria = limpar_texto(request.args.get("coordenadoria"), "")
    equipe = limpar_texto(request.args.get("equipe"), "")
    interessado = limpar_texto(request.args.get("interessado"), "")
    numero_sei = limpar_texto(request.args.get("numero_sei"), "")
    data_inicio_str = (request.args.get("data_inicio") or "").strip()
    data_fim_str = (request.args.get("data_fim") or "").strip()

    data_inicio = parse_date(data_inicio_str) if data_inicio_str else None
    data_fim = parse_date(data_fim_str) if data_fim_str else None

    def _parse_iso_datetime(valor: Optional[str]) -> Optional[datetime]:
        if not valor:
            return None
        try:
            return datetime.fromisoformat(valor)
        except Exception:
            return None

    processos = []
    processos_data = []
    paginacao_processos = None
    pagina = request.args.get("page", type=int, default=1)
    por_pagina = 10
    metricas_base = {"andamento": 0, "finalizados": 0, "tempo_medio_dias": None}
    total_andamento = 0
    metricas_demandas = {
        "total_processos": 0,
        "andamento": 0,
        "finalizados": 0,
        "tempo_medio_legenda": "--",
    }
    opcoes = {
        "gerencias": GERENCIAS,
        "coordenadorias": [],
        "equipes": [],
        "interessados": [],
    }
    campos_extra_labels: Dict[str, str] = {}
    campos_extra_saida: List[CampoExtra] = []
    trilhas_gerencias: Dict[int, List[str]] = {}
    demandas: List[Dict[str, object]] = []

    if not SITE_EM_CONFIGURACAO:
        # Historico inclui apenas processos com finalizacao geral registrada.
        # Eager loading evita N+1 ao serializar movimentacoes e responsavel.
        consulta = (
            Processo.query.options(
                selectinload(Processo.movimentacoes),
                joinedload(Processo.assigned_to),
            )
            .filter(Processo.finalizado_em.isnot(None))
        )
        if coordenadoria:
            consulta = consulta.filter(func.lower(Processo.coordenadoria) == coordenadoria.lower())
        if equipe:
            consulta = consulta.filter(func.lower(Processo.equipe_area) == equipe.lower())
        if interessado:
            consulta = consulta.filter(func.lower(Processo.interessado) == interessado.lower())
        if numero_sei:
            consulta = consulta.filter(Processo.numero_sei.ilike(f"%{numero_sei}%"))
        if data_inicio:
            inicio = datetime.combine(data_inicio, datetime.min.time())
            consulta = consulta.filter(Processo.finalizado_em >= inicio)
        if data_fim:
            fim = datetime.combine(data_fim, datetime.max.time())
            consulta = consulta.filter(Processo.finalizado_em <= fim)

        consulta_ordenada = consulta.order_by(
            Processo.finalizado_em.desc(), Processo.atualizado_em.desc()
        )
        processos_raw = consulta_ordenada.all()
        def _chave_exata(proc: Processo) -> tuple:
            """Suprime apenas linhas 100% idênticas; mantém variações."""
            return (
                proc.id,
                proc.numero_sei_base,
                proc.numero_sei,
                proc.gerencia,
                proc.data_entrada,
                proc.assunto,
                proc.interessado,
                proc.concessionaria,
                proc.classificacao_institucional,
                proc.coordenadoria,
                proc.equipe_area,
                proc.responsavel_equipe,
                proc.responsavel_adm,
                proc.status,
                proc.tipo_processo,
                proc.palavras_chave,
                proc.finalizado_em,
                proc.prazo,
                proc.prazo_equipe,
            )

        processos = []
        vistos_processos: Set[tuple] = set()
        for proc in sorted(
            processos_raw,
            key=lambda p: (p.finalizado_em or datetime.min, p.atualizado_em or datetime.min),
            reverse=True,
        ):
            chave = _chave_exata(proc)
            if chave in vistos_processos:
                continue
            vistos_processos.add(chave)
            processos.append(proc)
        processos_union = list(processos_raw)
        processos_por_id = {proc.id: proc for proc in processos_union}

        def _gerencias_unicas(origem: List[str]) -> List[str]:
            vistos = set()
            resultado: List[str] = []
            for nome in origem:
                if not nome:
                    continue
                chave = nome.strip().upper()
                if chave not in vistos:
                    vistos.add(chave)
                    resultado.append(nome.strip())
            return resultado

        def _ordenar_gerencias(origem: List[str]) -> List[str]:
            return ordenar_gerencias_preferencial(_gerencias_unicas(origem))

        processos_data = []
        vistos_data: Set[tuple] = set()
        for proc in sorted(
            processos_union,
            key=lambda p: (p.finalizado_em or datetime.min, p.atualizado_em or datetime.min),
            reverse=True,
        ):
            base = serializar_processo_para_relatorio(proc)
            movimentos = base.get("movimentacoes") or []
            movimentos = sorted(movimentos, key=lambda m: m.get("data") or "")
            gerencias = []
            gerencias.extend(base.get("gerencias_involvidas") or [])
            dados_extra_base = base.get("dados_extra") or {}
            if isinstance(dados_extra_base, dict):
                gerencias.extend(dados_extra_base.get("gerencias_escolhidas") or [])
            gerencias.append(base.get("gerencia"))
            for mov in movimentos:
                gerencias.extend([mov.get("de"), mov.get("para")])
            ignorar = {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}
            gerencias = [g for g in gerencias if g and str(g).strip() and str(g).strip().upper() not in ignorar]
            base["movimentacoes"] = movimentos
            base["gerencias_involvidas"] = _ordenar_gerencias(
                [g for g in gerencias if g and str(g).strip()]
            )
            chave_data = (
                base.get("id"),
                base.get("numero_sei_base") or base.get("numero_sei"),
                base.get("gerencia"),
                base.get("data_entrada"),
                base.get("assunto"),
                base.get("interessado"),
                base.get("concessionaria"),
                base.get("coordenadoria"),
                base.get("equipe_area"),
                base.get("status"),
                base.get("finalizado_em"),
                base.get("responsavel_adm"),
                base.get("responsavel_equipe"),
                base.get("tipo_processo"),
                base.get("palavras_chave"),
            )
            if chave_data in vistos_data:
                continue
            vistos_data.add(chave_data)
            processos_data.append(base)

        def _registro_finalizado_por_processo(
            proc: Dict[str, object],
            proc_ref: Optional[Processo],
        ) -> Optional[Dict[str, object]]:
            """Retorna um unico registro consolidado por processo (1 linha na tabela de processos)."""
            movs = proc.get("movimentacoes") or []
            fim_iso = proc.get("finalizado_em")
            fim_dt = _parse_iso_datetime(fim_iso) if isinstance(fim_iso, str) else fim_iso
            if fim_dt:
                snapshot = {}
                data_final = fim_dt
                gerencia_final = proc.get("gerencia")
            else:
                finalizacoes = [
                    mov
                    for mov in movs
                    if mov.get("tipo") in {"finalizacao_gerencia", "finalizado_geral"}
                    and _normalizar_str(mov.get("de")) != "saida"
                ]
                if not finalizacoes:
                    return None
                finalizacoes = sorted(finalizacoes, key=lambda m: m.get("data") or "")
                ultima = finalizacoes[-1]
                snapshot = ultima.get("dados") or {}
                data_final = _parse_iso_datetime(ultima.get("data"))
                gerencia_final = ultima.get("de") or proc.get("gerencia")
            gerencias_concat = " -> ".join(proc.get("gerencias_involvidas") or [gerencia_final] if gerencia_final else [])
            status_val = snapshot.get("status") or proc.get("status") or "Finalizado"
            prazo_equipe = parse_date(snapshot.get("prazo_equipe")) if snapshot else None
            if not prazo_equipe and proc_ref:
                prazo_equipe = proc_ref.prazo_equipe
            observacoes_complementares = (snapshot or {}).get("observacoes_complementares")
            if not observacoes_complementares:
                observacoes_complementares = (
                    proc_ref.observacoes_complementares if proc_ref else proc.get("observacao")
                )
            dados_extra = proc.get("dados_extra") or {}
            planilhador = proc.get("responsavel_adm")
            if proc_ref and not planilhador:
                if proc_ref.assigned_to:
                    planilhador = proc_ref.assigned_to.nome or proc_ref.assigned_to.username
            data_entrada_gerencia = (
                data_entrada_na_gerencia(proc_ref, "SAIDA") if proc_ref else None
            )
            gerencia_origem = obter_origem_saida(proc_ref) if proc_ref else None
            destino_saida = proc_ref.tramitado_para if proc_ref else None
            return {
                "id": proc.get("id"),
                "numero_sei": proc.get("numero_sei"),
                "numero_sei_base": (
                    proc_ref.numero_sei_base if proc_ref else proc.get("numero_sei_base") or proc.get("numero_sei")
                ),
                "chave_relacionamento": proc.get("chave_relacionamento"),
                "data_entrada": proc_ref.data_entrada if proc_ref else None,
                "assunto": proc.get("assunto"),
                "interessado": proc.get("interessado"),
                "concessionaria": proc_ref.concessionaria if proc_ref else None,
                "gerencia": gerencias_concat or gerencia_final,
                "gerencia_origem": gerencia_origem,
                "destino_saida": destino_saida,
                "prazo": proc_ref.prazo if proc_ref else None,
                "coordenadoria": snapshot.get("coordenadoria") or proc.get("coordenadoria"),
                "equipe_area": snapshot.get("equipe_area") or proc.get("equipe_area"),
                "responsavel_equipe": snapshot.get("responsavel_equipe") or proc.get("responsavel_equipe"),
                "status": status_val,
                "status_equipe": status_val,
                "classificacao_institucional": (
                    proc_ref.classificacao_institucional if proc_ref else None
                ),
                "descricao_melhorada": proc_ref.descricao_melhorada if proc_ref else None,
                "finalizado_em": data_final,
                "responsavel_adm": proc.get("responsavel_adm"),
                "planilhador": planilhador,
                "tipo_processo": snapshot.get("tipo_processo") or proc.get("tipo_processo"),
                "palavras_chave": snapshot.get("palavras_chave") or proc.get("palavras_chave"),
                "prazo_equipe": prazo_equipe,
                "observacoes_complementares": observacoes_complementares,
                "data_entrada_gerencia": data_entrada_gerencia,
                "dados_extra": dados_extra,
            }

        def _normalizar_str(valor: Optional[str]) -> str:
            return (valor or "").strip().lower()

        registros_finalizados = []
        for proc in processos_data:
            proc_ref = processos_por_id.get(proc.get("id"))
            registro = _registro_finalizado_por_processo(proc, proc_ref)
            if not registro:
                continue

            gerencias_lista = (proc.get("gerencias_involvidas") or []) + (
                [proc.get("gerencia")] if proc.get("gerencia") else []
            )
            gerencias_lista = [
                g for g in gerencias_lista if g and _normalizar_str(g) not in {"saida", "finalizado", "entrada", "cadastro"}
            ]

            if filtro_gerencia and not any(_normalizar_str(g) == _normalizar_str(filtro_gerencia) for g in gerencias_lista):
                continue
            if coordenadoria and _normalizar_str(registro.get("coordenadoria")) != _normalizar_str(coordenadoria):
                continue
            if equipe and _normalizar_str(registro.get("equipe_area")) != _normalizar_str(equipe):
                continue
            if interessado and _normalizar_str(registro.get("interessado")) != _normalizar_str(interessado):
                continue
            if numero_sei and numero_sei.lower() not in (registro.get("numero_sei") or "").lower():
                continue
            data_final = registro.get("finalizado_em")
            if data_inicio and (not data_final or data_final.date() < data_inicio):
                continue
            if data_fim and (not data_final or data_final.date() > data_fim):
                continue

            gerencias_lista = _ordenar_gerencias(gerencias_lista)
            registro["gerencia"] = " -> ".join(gerencias_lista) if gerencias_lista else registro.get("gerencia")
            registros_finalizados.append(registro)

        # Calcula ciclos por numero base + mesma gerencia de origem (regra de ciclo de retorno).
        registros_por_base_all: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for registro in registros_finalizados:
            base = (
                (registro.get("numero_sei_base") or registro.get("numero_sei") or "").strip().lower()
                or f"id:{registro.get('id')}"
            )
            ger_origem = _normalizar_str(
                registro.get("gerencia_origem") or registro.get("gerencia")
            ) or "sem-gerencia"
            chave_grupo_ciclo = f"{base}::{ger_origem}"
            registros_por_base_all[chave_grupo_ciclo].append(registro)
        ciclo_por_id: Dict[int, Dict[str, int]] = {}
        total_ciclos_por_grupo: Dict[str, int] = {}
        for chave_grupo_ciclo, lista_base in registros_por_base_all.items():
            lista_base.sort(
                key=lambda r: (
                    r.get("finalizado_em")
                    if isinstance(r.get("finalizado_em"), datetime)
                    else (_parse_iso_datetime(r.get("finalizado_em")) if isinstance(r.get("finalizado_em"), str) else datetime.min)
                )
                or datetime.min
            )
            total = len(lista_base)
            total_ciclos_por_grupo[chave_grupo_ciclo] = total
            for indice, registro in enumerate(lista_base, start=1):
                if registro.get("id") is not None:
                    ciclo_por_id[int(registro.get("id"))] = {
                        "ciclo_numero": indice,
                        "ciclos_total": total,
                    }

        registros_finalizados_todos = list(registros_finalizados)

        for registro in registros_finalizados_todos:
            base = (
                (registro.get("numero_sei_base") or registro.get("numero_sei") or "").strip().lower()
                or f"id:{registro.get('id')}"
            )
            ger_origem = _normalizar_str(
                registro.get("gerencia_origem") or registro.get("gerencia")
            ) or "sem-gerencia"
            chave_grupo_ciclo = f"{base}::{ger_origem}"
            ciclo_info = (
                ciclo_por_id.get(int(registro.get("id")))
                if registro.get("id") is not None
                else None
            ) or {}
            registro["ciclo_numero"] = int(
                ciclo_info.get("ciclo_numero") or total_ciclos_por_grupo.get(chave_grupo_ciclo) or 1
            )
            registro["ciclos_total"] = int(
                ciclo_info.get("ciclos_total") or total_ciclos_por_grupo.get(chave_grupo_ciclo) or 1
            )

        # Processos finalizados: exibe todos os retornos juntos (lado a lado por numero base).
        processos_por_base: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for registro in registros_finalizados_todos:
            chave_base = (
                (registro.get("numero_sei_base") or registro.get("numero_sei") or "").strip().lower()
                or f"id:{registro.get('id')}"
            )
            processos_por_base[chave_base].append(registro)

        def _data_final_registro(reg: Dict[str, object]) -> datetime:
            val = reg.get("finalizado_em")
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                return _parse_iso_datetime(val) or datetime.min
            return datetime.min

        bases_ordenadas = sorted(
            processos_por_base.keys(),
            key=lambda base: max((_data_final_registro(r) for r in processos_por_base[base]), default=datetime.min),
            reverse=True,
        )
        processos: List[Dict[str, object]] = []
        for base in bases_ordenadas:
            grupo = sorted(processos_por_base[base], key=_data_final_registro, reverse=True)
            grupo_total = len(grupo)
            principal = dict(grupo[0]) if grupo else {}
            principal["grupo_retorno"] = grupo_total > 1
            principal["grupo_retorno_total"] = grupo_total

            # Consolidado: uma linha por processo base, com pares entrada/finalizacao por demanda.
            pares_datas: List[Dict[str, object]] = []
            vistos_pares: Set[str] = set()
            cores_pares = (
                "pareado-1",
                "pareado-2",
                "pareado-3",
                "pareado-4",
                "pareado-5",
                "pareado-6",
            )
            grupo_por_entrada = sorted(
                grupo,
                key=lambda r: (
                    r.get("data_entrada")
                    if isinstance(r.get("data_entrada"), date)
                    else datetime.min.date()
                ),
                reverse=True,
            )
            for idx_par, item in enumerate(grupo_por_entrada):
                data_entrada_item = item.get("data_entrada")
                if isinstance(data_entrada_item, datetime):
                    data_entrada_item = data_entrada_item.date()
                data_final_item = item.get("finalizado_em")
                if isinstance(data_final_item, str):
                    data_final_item = _parse_iso_datetime(data_final_item)
                if isinstance(data_final_item, date) and not isinstance(data_final_item, datetime):
                    data_final_item = datetime.combine(data_final_item, datetime.min.time())
                chave_par = (
                    f"{data_entrada_item.isoformat() if isinstance(data_entrada_item, date) else '-'}::"
                    f"{data_final_item.isoformat() if isinstance(data_final_item, datetime) else '-'}::"
                    f"{(item.get('gerencia_origem') or item.get('gerencia') or '').strip().lower()}"
                )
                if chave_par in vistos_pares:
                    continue
                vistos_pares.add(chave_par)
                cor = cores_pares[idx_par % len(cores_pares)]
                pares_datas.append(
                    {
                        "entrada": data_entrada_item,
                        "entrada_str": (
                            data_entrada_item.strftime("%d/%m/%Y")
                            if isinstance(data_entrada_item, date)
                            else "-"
                        ),
                        "finalizacao": data_final_item,
                        "finalizacao_str": (
                            data_final_item.strftime("%d/%m/%Y")
                            if isinstance(data_final_item, datetime)
                            else "-"
                        ),
                        "cor": cor,
                    }
                )

            datas_entrada_unicas: List[date] = []
            vistos_datas_entrada: Set[str] = set()
            for item in grupo:
                data_item = item.get("data_entrada")
                if isinstance(data_item, datetime):
                    data_item = data_item.date()
                if not isinstance(data_item, date):
                    continue
                chave_data = data_item.isoformat()
                if chave_data in vistos_datas_entrada:
                    continue
                vistos_datas_entrada.add(chave_data)
                datas_entrada_unicas.append(data_item)
            datas_entrada_unicas.sort(reverse=True)
            principal["datas_entrada"] = datas_entrada_unicas
            principal["data_entrada_display"] = (
                " | ".join(d.strftime("%d/%m/%Y") for d in datas_entrada_unicas)
                if datas_entrada_unicas
                else "-"
            )
            principal["pares_datas"] = pares_datas

            # Gerencias envolvidas consolidadas do grupo inteiro.
            gerencias_group: List[str] = []
            for item in grupo:
                valor = (item.get("gerencia") or item.get("gerencia_origem") or "").strip()
                if not valor:
                    continue
                partes = [p.strip() for p in valor.split("->") if p.strip()]
                if not partes:
                    partes = [valor]
                for parte in partes:
                    if _normalizar_str(parte) in {"saida", "finalizado", "entrada", "cadastro"}:
                        continue
                    gerencias_group.append(parte)
            gerencias_group = _ordenar_gerencias(gerencias_group)
            if gerencias_group:
                principal["gerencia"] = " -> ".join(gerencias_group)

            processos.append(principal)

        total_finalizados_indicador = len(bases_ordenadas)
        ids_finalizados_gerencia = {
            reg.get("id")
            for reg in registros_finalizados_todos
            if reg.get("id")
        }
        consulta_andamento = Processo.query.filter(Processo.finalizado_em.is_(None))
        if ids_finalizados_gerencia:
            consulta_andamento = consulta_andamento.filter(~Processo.id.in_(ids_finalizados_gerencia))
        if filtro_gerencia:
            consulta_andamento = consulta_andamento.filter(Processo.gerencia == filtro_gerencia)
        if coordenadoria:
            consulta_andamento = consulta_andamento.filter(func.lower(Processo.coordenadoria) == coordenadoria.lower())
        if equipe:
            consulta_andamento = consulta_andamento.filter(func.lower(Processo.equipe_area) == equipe.lower())
        if interessado:
            consulta_andamento = consulta_andamento.filter(func.lower(Processo.interessado) == interessado.lower())
        if numero_sei:
            consulta_andamento = consulta_andamento.filter(Processo.numero_sei.ilike(f"%{numero_sei}%"))

        total_andamento = consulta_andamento.count()
        duracoes_segundos = []
        for registro in processos:
            proc_ref = processos_por_id.get(registro.get("id"))
            data_entrada = proc_ref.data_entrada if proc_ref else registro.get("data_entrada")
            finalizado_em = registro.get("finalizado_em")
            if isinstance(finalizado_em, str):
                finalizado_em = _parse_iso_datetime(finalizado_em)
            if data_entrada and finalizado_em:
                entrada_dt = datetime.combine(data_entrada, datetime.min.time())
                if finalizado_em >= entrada_dt:
                    duracoes_segundos.append((finalizado_em - entrada_dt).total_seconds())
        tempo_medio_dias = (
            (sum(duracoes_segundos) / len(duracoes_segundos)) / 86400
            if duracoes_segundos
            else None
        )
        metricas_base = {
            "andamento": int(total_andamento),
            "finalizados": int(total_finalizados_indicador),
            "tempo_medio_dias": tempo_medio_dias,
        }
        opcoes = obter_opcoes_painel_finalizados()
        campos_extra_labels = {campo.slug: campo.label for campo in CampoExtra.query.all()}
        campos_extra_saida = listar_campos_gerencia("SAIDA")
        trilhas_gerencias = {
            int(proc.get("id")): list(proc.get("gerencias_involvidas") or [])
            for proc in processos_data
            if proc.get("id") is not None
        }
        ids_processos_union = [proc.id for proc in processos_union if proc.id is not None]
        movimentos_demanda: List[Movimentacao] = []
        if ids_processos_union:
            base_mov_query = (
                Movimentacao.query.options(
                    joinedload(Movimentacao.processo).joinedload(Processo.assigned_to),
                    joinedload(Movimentacao.processo).selectinload(Processo.movimentacoes),
                )
                .filter(Movimentacao.tipo.in_(["finalizacao_gerencia", "finalizado_geral"]))
                .order_by(Movimentacao.criado_em.desc())
            )
            # SQLite possui limite de parametros no IN; consulta em blocos.
            bloco = 700
            for inicio_idx in range(0, len(ids_processos_union), bloco):
                ids_bloco = ids_processos_union[inicio_idx : inicio_idx + bloco]
                movimentos_demanda.extend(
                    base_mov_query.filter(Movimentacao.processo_id.in_(ids_bloco)).all()
                )
        for mov in movimentos_demanda:
            proc = mov.processo
            if not proc:
                continue
            gerencia_mov = mov.de_gerencia or proc.gerencia
            if _normalizar_str(gerencia_mov) == "saida":
                continue
            if filtro_gerencia and _normalizar_str(gerencia_mov) != _normalizar_str(filtro_gerencia):
                continue
            snapshot = _normalizar_snapshot(getattr(mov, "dados_snapshot", None)) or {}
            coord = snapshot.get("coordenadoria") or proc.coordenadoria
            equipe_area = snapshot.get("equipe_area") or proc.equipe_area
            responsavel_equipe = snapshot.get("responsavel_equipe") or proc.responsavel_equipe
            status_val = snapshot.get("status") or proc.status
            planilhador = proc.responsavel_adm
            if not planilhador and proc.assigned_to:
                planilhador = proc.assigned_to.nome or proc.assigned_to.username
            prazo_equipe = parse_date(snapshot.get("prazo_equipe")) if snapshot else None
            if not prazo_equipe:
                prazo_equipe = proc.prazo_equipe
            observacoes_complementares = (
                snapshot.get("observacoes_complementares")
                or proc.observacoes_complementares
                or proc.observacao
            )
            tipo_processo = snapshot.get("tipo_processo") or proc.tipo_processo
            palavras_chave = snapshot.get("palavras_chave") or proc.palavras_chave
            dados_extra = snapshot.get("extras") or proc.dados_extra or {}
            data_entrada_gerencia = data_entrada_na_gerencia(proc, gerencia_mov)

            if coordenadoria and _normalizar_str(coord) != _normalizar_str(coordenadoria):
                continue
            if equipe and _normalizar_str(equipe_area) != _normalizar_str(equipe):
                continue
            if interessado and _normalizar_str(proc.interessado) != _normalizar_str(interessado):
                continue
            if numero_sei and numero_sei.lower() not in (proc.numero_sei or "").lower():
                continue
            if data_inicio and (not mov.criado_em or mov.criado_em.date() < data_inicio):
                continue
            if data_fim and (not mov.criado_em or mov.criado_em.date() > data_fim):
                continue

            chave_rel = gerar_chave_relacionamento_numero(
                proc.numero_sei_base,
                obter_chave_processo_relacional(proc),
            )
            demandas.append(
                {
                    "id": proc.id,
                    "numero_sei": proc.numero_sei,
                    "numero_sei_base": proc.numero_sei_base,
                    "chave_relacionamento": chave_rel,
                    "data_entrada": proc.data_entrada,
                    "assunto": proc.assunto,
                    "interessado": proc.interessado,
                    "concessionaria": proc.concessionaria,
                    "gerencia": gerencia_mov,
                    "gerencia_origem": gerencia_mov,
                    "destino_saida": (
                        proc.tramitado_para
                        if (mov.para_gerencia or "").strip().upper() == "SAIDA" and proc.tramitado_para
                        else mov.para_gerencia
                    ),
                    "prazo": proc.prazo,
                    "coordenadoria": coord,
                    "equipe_area": equipe_area,
                    "responsavel_equipe": responsavel_equipe,
                    "status": status_val,
                    "status_equipe": status_val,
                    "classificacao_institucional": proc.classificacao_institucional,
                    "descricao_melhorada": proc.descricao_melhorada,
                    "data_entrada_gerencia": data_entrada_gerencia,
                    "responsavel_adm": proc.responsavel_adm,
                    "planilhador": planilhador,
                    "tipo_processo": tipo_processo,
                    "palavras_chave": palavras_chave,
                    "prazo_equipe": prazo_equipe,
                    "observacoes_complementares": observacoes_complementares,
                    "dados_extra": dados_extra,
                    "data_saida": proc.data_saida,
                    "finalizado_em": mov.criado_em,
                    "ciclo_numero": (ciclo_por_id.get(proc.id) or {}).get("ciclo_numero", 1),
                    "ciclos_total": (ciclo_por_id.get(proc.id) or {}).get("ciclos_total", 1),
                }
            )

        demandas_existentes_ids = {
            int(d.get("id"))
            for d in demandas
            if d.get("id") is not None
        }
        for registro in registros_finalizados_todos:
            numero = (registro.get("numero_sei") or "").strip()
            if not numero:
                continue
            if registro.get("id") is not None and int(registro.get("id")) in demandas_existentes_ids:
                continue
            proc_ref = processos_por_id.get(registro.get("id"))
            data_final = registro.get("finalizado_em")
            if isinstance(data_final, str):
                data_final = _parse_iso_datetime(data_final)
            mov_final = None
            if proc_ref:
                movs_final = [
                    mov
                    for mov in proc_ref.movimentacoes
                    if mov.tipo in {"finalizacao_gerencia", "finalizado_geral"}
                ]
                if movs_final:
                    mov_final = sorted(
                        movs_final, key=lambda mov: mov.criado_em or datetime.min
                    )[-1]
                    if mov_final and mov_final.criado_em:
                        data_final = mov_final.criado_em

            planilhador = registro.get("planilhador") or registro.get("responsavel_adm")
            if not planilhador and proc_ref and proc_ref.assigned_to:
                planilhador = proc_ref.assigned_to.nome or proc_ref.assigned_to.username
            prazo_equipe = registro.get("prazo_equipe")
            if isinstance(prazo_equipe, str):
                prazo_equipe = parse_date(prazo_equipe)
            observacoes_complementares = registro.get("observacoes_complementares")
            if not observacoes_complementares and proc_ref:
                observacoes_complementares = proc_ref.observacoes_complementares or proc_ref.observacao
            dados_extra = registro.get("dados_extra") or (proc_ref.dados_extra if proc_ref else {}) or {}
            data_entrada_gerencia = registro.get("data_entrada_gerencia")
            gerencia_origem = registro.get("gerencia_origem") or (proc_ref.gerencia if proc_ref else None)
            if not data_entrada_gerencia and proc_ref and gerencia_origem:
                data_entrada_gerencia = data_entrada_na_gerencia(proc_ref, gerencia_origem)
            status_val = registro.get("status") or (proc_ref.status if proc_ref else None)
            status_equipe = registro.get("status_equipe") or status_val

            numero_base_reg = (
                registro.get("numero_sei_base")
                or (proc_ref.numero_sei_base if proc_ref else numero)
            )
            chave_rel = gerar_chave_relacionamento_numero(
                numero_base_reg,
                obter_chave_processo_em_dados(dados_extra),
            )
            demandas.append(
                {
                    "id": registro.get("id"),
                    "numero_sei": numero,
                    "numero_sei_base": numero_base_reg,
                    "chave_relacionamento": chave_rel,
                    "data_entrada": registro.get("data_entrada") or (proc_ref.data_entrada if proc_ref else None),
                    "assunto": registro.get("assunto") or (proc_ref.assunto if proc_ref else None),
                    "interessado": registro.get("interessado") or (proc_ref.interessado if proc_ref else None),
                    "concessionaria": registro.get("concessionaria")
                    or (proc_ref.concessionaria if proc_ref else None),
                    "gerencia": registro.get("gerencia") or gerencia_origem,
                    "gerencia_origem": gerencia_origem,
                    "destino_saida": registro.get("destino_saida")
                    or (proc_ref.tramitado_para if proc_ref else None),
                    "prazo": registro.get("prazo") or (proc_ref.prazo if proc_ref else None),
                    "coordenadoria": registro.get("coordenadoria")
                    or (proc_ref.coordenadoria if proc_ref else None),
                    "equipe_area": registro.get("equipe_area")
                    or (proc_ref.equipe_area if proc_ref else None),
                    "responsavel_equipe": registro.get("responsavel_equipe")
                    or (proc_ref.responsavel_equipe if proc_ref else None),
                    "status": status_val,
                    "status_equipe": status_equipe,
                    "classificacao_institucional": registro.get("classificacao_institucional")
                    or (proc_ref.classificacao_institucional if proc_ref else None),
                    "descricao_melhorada": registro.get("descricao_melhorada")
                    or (proc_ref.descricao_melhorada if proc_ref else None),
                    "data_entrada_gerencia": data_entrada_gerencia,
                    "responsavel_adm": registro.get("responsavel_adm")
                    or (proc_ref.responsavel_adm if proc_ref else None),
                    "planilhador": planilhador,
                    "tipo_processo": registro.get("tipo_processo")
                    or (proc_ref.tipo_processo if proc_ref else None),
                    "palavras_chave": registro.get("palavras_chave")
                    or (proc_ref.palavras_chave if proc_ref else None),
                    "prazo_equipe": prazo_equipe,
                    "observacoes_complementares": observacoes_complementares,
                    "dados_extra": dados_extra,
                    "data_saida": registro.get("data_saida") or (proc_ref.data_saida if proc_ref else None),
                    "finalizado_em": data_final if isinstance(data_final, datetime) else None,
                    "ciclo_numero": int(registro.get("ciclo_numero") or 1),
                    "ciclos_total": int(registro.get("ciclos_total") or 1),
                }
            )

        # Em demandas, o ciclo so conta quando repete o mesmo numero + mesma gerencia.
        demandas_por_base_gerencia: Dict[str, List[Dict[str, object]]] = defaultdict(list)
        for demanda in demandas:
            base = (
                (demanda.get("numero_sei_base") or demanda.get("numero_sei") or "").strip().lower()
                or f"id:{demanda.get('id')}"
            )
            ger = _normalizar_str(demanda.get("gerencia") or demanda.get("gerencia_origem")) or "sem-gerencia"
            demandas_por_base_gerencia[f"{base}::{ger}"].append(demanda)
        for _, lista_demandas in demandas_por_base_gerencia.items():
            lista_demandas.sort(
                key=lambda d: (
                    d.get("finalizado_em")
                    if isinstance(d.get("finalizado_em"), datetime)
                    else (_parse_iso_datetime(d.get("finalizado_em")) if isinstance(d.get("finalizado_em"), str) else datetime.min)
                )
                or datetime.min
            )
            total = len(lista_demandas)
            for idx, demanda in enumerate(lista_demandas, start=1):
                demanda["ciclo_numero_mesma_gerencia"] = idx
                demanda["ciclos_total_mesma_gerencia"] = total

        # Enriquecer processos para a ficha tecnica com demandas relacionadas por grupo.
        demandas_por_grupo: Dict[str, List[Dict[str, object]]] = {}
        for demanda in demandas:
            chave_grupo = (demanda.get("chave_relacionamento") or "").strip()
            if not chave_grupo:
                continue
            demandas_por_grupo.setdefault(chave_grupo, []).append(demanda)

        # Consolida o historico completo por grupo, incluindo todas as demandas relacionadas.
        bases_alvo = {
            (proc.get("chave_relacionamento") or "").strip()
            for proc in processos_data
            if proc.get("chave_relacionamento")
        }
        movimentos_completos_por_base: Dict[str, List[Dict[str, object]]] = {}
        if bases_alvo:
            bases_numero_sei = {
                (proc.get("numero_sei_base") or "").strip().lower()
                for proc in processos_data
                if (proc.get("numero_sei_base") or "").strip()
            }
            processos_relacionados: List[Processo] = []
            if bases_numero_sei:
                # numero_sei_base e propriedade Python (nao coluna SQL),
                # entao mapeamos ids candidatos antes de consultar com eager loading.
                ids_relacionados: Set[int] = set()
                candidatos = db.session.query(
                    Processo.id,
                    Processo.numero_sei,
                    Processo.dados_extra,
                ).all()
                for proc_id, numero_sei_item, dados_extra_item in candidatos:
                    numero_base_item = ""
                    if isinstance(dados_extra_item, dict):
                        numero_base_item = (
                            limpar_texto(dados_extra_item.get("numero_sei_original"), "")
                            or ""
                        )
                    if not numero_base_item:
                        numero_base_item = extrair_numero_base_sei(numero_sei_item or "")
                    if numero_base_item.strip().lower() in bases_numero_sei:
                        ids_relacionados.add(int(proc_id))

                if ids_relacionados:
                    query_relacionados = Processo.query.options(
                        selectinload(Processo.movimentacoes),
                        joinedload(Processo.assigned_to),
                    )
                    bloco = 700
                    ids_lista = list(ids_relacionados)
                    for inicio_idx in range(0, len(ids_lista), bloco):
                        ids_bloco = ids_lista[inicio_idx : inicio_idx + bloco]
                        processos_relacionados.extend(
                            query_relacionados.filter(Processo.id.in_(ids_bloco)).all()
                        )

            # Evita duplicidade ao agregar blocos.
            processos_relacionados_unicos = {p.id: p for p in processos_relacionados}.values()
            processos_relacionados = [
                p
                for p in processos_relacionados_unicos
                if gerar_chave_relacionamento_numero(
                    p.numero_sei_base,
                    obter_chave_processo_relacional(p),
                )
                in bases_alvo
            ]
            for proc_rel in processos_relacionados:
                base_rel = gerar_chave_relacionamento_numero(
                    proc_rel.numero_sei_base,
                    obter_chave_processo_relacional(proc_rel),
                )
                if not base_rel:
                    continue
                serial_rel = serializar_processo_para_relatorio(proc_rel)
                lista_eventos = movimentos_completos_por_base.setdefault(base_rel, [])
                movs_rel = serial_rel.get("movimentacoes") or []
                possui_cadastro = any(
                    (mov.get("tipo") or "").strip().lower() == "cadastro" for mov in movs_rel
                )
                if serial_rel.get("criado_em") and not possui_cadastro:
                    usuario_cadastro = (
                        serial_rel.get("usuario_cadastro")
                        or serial_rel.get("responsavel_adm")
                        or "usuario"
                    )
                    ger_cadastro = serial_rel.get("gerencia_criacao") or serial_rel.get("gerencia")
                    termo_cad = _termo_por_gerencia(ger_cadastro, "cadastro")
                    acao_cad = _flexao_acao(termo_cad, "cadastrado", "cadastrada")
                    envio_cad = _flexao_acao(termo_cad, "enviado", "enviada")
                    lista_eventos.append(
                        {
                            "de": "CADASTRO",
                            "para": ger_cadastro,
                            "motivo": "Cadastro inicial do processo",
                            "usuario": usuario_cadastro,
                            "tipo": "cadastro",
                            "data": serial_rel.get("criado_em"),
                            "texto": (
                                f"{termo_cad} {acao_cad} por {usuario_cadastro} "
                                f"e {envio_cad} para {ger_cadastro or '-'}."
                            ),
                            "numero_sei_ref": serial_rel.get("numero_sei"),
                        }
                    )

                for mov in movs_rel:
                    evento = dict(mov)
                    evento["numero_sei_ref"] = serial_rel.get("numero_sei")
                    lista_eventos.append(evento)

        for proc_data in processos_data:
            chave_base = (proc_data.get("chave_relacionamento") or "").strip()
            relacionadas = demandas_por_grupo.get(chave_base, [])
            proc_data["demandas_relacionadas"] = relacionadas
            eventos_base = movimentos_completos_por_base.get(chave_base, [])
            if eventos_base:
                vistos_eventos = set()
                eventos_unicos = []
                for evento in sorted(eventos_base, key=lambda m: m.get("data") or ""):
                    chave_evento = (
                        evento.get("data") or "",
                        evento.get("tipo") or "",
                        evento.get("usuario") or "",
                        evento.get("de") or "",
                        evento.get("para") or "",
                        evento.get("motivo") or "",
                        evento.get("texto") or "",
                        evento.get("numero_sei_ref") or "",
                    )
                    if chave_evento in vistos_eventos:
                        continue
                    vistos_eventos.add(chave_evento)
                    eventos_unicos.append(evento)
                proc_data["movimentacoes_completas"] = eventos_unicos
            if relacionadas:
                trilha = list(proc_data.get("gerencias_involvidas") or [])
                trilha_norm = {str(item).strip().upper() for item in trilha if str(item).strip()}
                for demanda in relacionadas:
                    ger = demanda.get("gerencia")
                    if not ger:
                        continue
                    ger_txt = str(ger).strip()
                    if not ger_txt:
                        continue
                    ger_norm = ger_txt.upper()
                    if ger_norm in {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}:
                        continue
                    if ger_norm not in trilha_norm:
                        trilha.append(ger_txt)
                        trilha_norm.add(ger_norm)
                proc_data["gerencias_involvidas"] = _ordenar_gerencias(trilha)

    if not SITE_EM_CONFIGURACAO:
        duracoes_demandas = []
        for demanda in demandas:
            data_entrada = demanda.get("data_entrada")
            finalizado_em = demanda.get("finalizado_em")
            if isinstance(finalizado_em, str):
                finalizado_em = _parse_iso_datetime(finalizado_em)
            elif isinstance(finalizado_em, date) and not isinstance(finalizado_em, datetime):
                finalizado_em = datetime.combine(finalizado_em, datetime.min.time())
            if data_entrada and finalizado_em:
                entrada_dt = datetime.combine(data_entrada, datetime.min.time())
                if finalizado_em >= entrada_dt:
                    duracoes_demandas.append((finalizado_em - entrada_dt).total_seconds())
        tempo_medio_demandas = (
            (sum(duracoes_demandas) / len(duracoes_demandas)) / 86400
            if duracoes_demandas
            else None
        )
        total_demandas = int(len(demandas))
        metricas_demandas = {
            "total_processos": int(total_andamento) + total_demandas,
            "andamento": int(total_andamento),
            "finalizados": total_demandas,
            "tempo_medio_legenda": (
                f"{tempo_medio_demandas:.1f} dias" if tempo_medio_demandas is not None else "--"
            ),
        }

    total_processos = 0
    if not SITE_EM_CONFIGURACAO:
        total_processos = metricas_base["andamento"] + metricas_base["finalizados"]

    metricas = {
        "total_processos": total_processos,
        "andamento": metricas_base["andamento"],
        "finalizados": metricas_base["finalizados"],
        "tempo_medio_legenda": (
            f"{metricas_base['tempo_medio_dias']:.1f} dias"
            if metricas_base["tempo_medio_dias"] is not None
            else "--"
        ),
    }

    filtros = {
        "gerencia": filtro_gerencia or "",
        "coordenadoria": coordenadoria,
        "equipe": equipe,
        "interessado": interessado,
        "numero_sei": numero_sei,
        "data_inicio": data_inicio_str,
        "data_fim": data_fim_str,
    }

    return render_template(
        "verificar_dados.html",
        processos=processos,
        processos_data=processos_data,
        demandas=demandas,
        opcoes=opcoes,
        metricas=metricas,
        metricas_demandas=metricas_demandas,
        filtros=filtros,
        campos_extra_labels=campos_extra_labels,
        campos_extra_saida=campos_extra_saida,
        trilhas_gerencias=trilhas_gerencias,
        paginacao_processos=paginacao_processos,
    )


def _render_tela_edicao_processo(
    processo: Processo,
    campos_def: List["CampoExtra"],
    *,
    mostrar_devolver: bool = False,
    mostrar_ficha: bool = False,
    valor_devolver: str = "",
    gerencias_relacionadas: Optional[List[str]] = None,
    bloquear_finalizacao_saida: bool = False,
    alerta_tramite: str = "",
    scroll_y: str = "",
):
    """Centraliza o contexto da tela de edicao para evitar divergencias entre fluxos."""
    opcoes_responsavel_adm = obter_responsaveis_adm_disponiveis()
    pode_editar = usuario_pode_editar_processo(processo)
    somente_visualizacao = not pode_editar
    gerencias_com_demanda = []
    demandas_relacionadas: List[Dict[str, object]] = []
    demandas_ficha: List[Dict[str, object]] = []
    if processo.gerencia == "SAIDA" and processo.numero_sei_base:
        origem_saida = normalizar_gerencia(obter_origem_saida(processo))
        chave_referencia = obter_chave_processo_relacional(processo)
        relacionados_mesma_base = [
            p
            for p in Processo.query.all()
            if p.numero_sei_base == processo.numero_sei_base
        ]
        if not chave_referencia:
            chave_referencia = obter_chave_referencia_unica_por_base(relacionados_mesma_base)
        relacionados_base = [
            p
            for p in relacionados_mesma_base
            if processo_pertence_mesmo_grupo(
                p,
                numero_base=processo.numero_sei_base,
                chave_referencia=chave_referencia,
            )
        ]
        relacionados_base = sorted(
            relacionados_base,
            key=lambda p: (
                ORDEM_GERENCIAS.get(
                    normalizar_gerencia(obter_origem_saida(p) if p.gerencia == "SAIDA" else p.gerencia) or "",
                    999,
                ),
                p.numero_sei or "",
            ),
        )
        gerencias_registradas: Set[str] = set()
        ignorar_gerencias = {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}
        def _snapshot_demanda(proc_item: Processo) -> Dict[str, object]:
            movs = sorted(
                proc_item.movimentacoes,
                key=lambda mov: mov.criado_em or datetime.min,
            )
            ultima_finalizacao = None
            for mov in reversed(movs):
                if mov.tipo in {"finalizacao_gerencia", "finalizado_geral"}:
                    ultima_finalizacao = mov
                    break
            snapshot = (
                _normalizar_snapshot(getattr(ultima_finalizacao, "dados_snapshot", None))
                if ultima_finalizacao
                else None
            ) or {}
            for campo_data in (
                "prazo",
                "prazo_equipe",
                "data_entrada",
                "data_entrada_geplan",
                "data_status",
            ):
                if snapshot.get(campo_data):
                    snapshot[campo_data] = parse_date(snapshot.get(campo_data))
            return snapshot

        for item in relacionados_base:
            gerencia_item = (
                obter_origem_saida(item) if item.gerencia == "SAIDA" else item.gerencia
            ) or item.gerencia
            ger_norm_reg = normalizar_gerencia(gerencia_item, permitir_entrada=True)
            if ger_norm_reg and ger_norm_reg not in ignorar_gerencias:
                gerencias_registradas.add(ger_norm_reg)
            status_item = item.status or ("Finalizado" if item.finalizado_em else "Em andamento")
            demandas_relacionadas.append(
                {
                    "gerencia": gerencia_item,
                    "numero_sei": item.numero_sei,
                    "numero_sei_base": item.numero_sei_base,
                    "status": status_item,
                    "coordenadoria": item.coordenadoria,
                    "equipe_area": item.equipe_area,
                    "responsavel_equipe": item.responsavel_equipe,
                    "responsavel_adm": item.responsavel_adm,
                }
            )
            snapshot = _snapshot_demanda(item)
            snapshot_extras = snapshot.get("extras") if snapshot else None
            status_ficha = snapshot.get("status") or item.status
            if not status_ficha:
                status_ficha = "Finalizado" if item.finalizado_em else "Em andamento"
            observacoes_ficha = (
                snapshot.get("observacoes_complementares")
                or snapshot.get("observacao")
                or item.observacoes_complementares
                or item.observacao
            )
            ger_norm = normalizar_gerencia(gerencia_item, permitir_entrada=True)
            campos_extra_ficha = (
                serializar_campos_extra(listar_campos_gerencia(ger_norm))
                if ger_norm
                else []
            )
            sufixo = (item.dados_extra or {}).get("sufixo") or ""
            numero_display = f"{item.numero_sei_base or item.numero_sei or ''}{sufixo}"
            demandas_ficha.append(
                {
                    "gerencia": gerencia_item,
                    "numero_sei": item.numero_sei,
                    "numero_sei_base": item.numero_sei_base,
                    "numero_display": numero_display,
                    "assunto": snapshot.get("assunto") or item.assunto,
                    "interessado": snapshot.get("interessado") or item.interessado,
                    "concessionaria": snapshot.get("concessionaria") or item.concessionaria,
                    "coordenadoria": snapshot.get("coordenadoria") or item.coordenadoria,
                    "equipe_area": snapshot.get("equipe_area") or item.equipe_area,
                    "responsavel_equipe": snapshot.get("responsavel_equipe")
                    or item.responsavel_equipe,
                    "palavras_chave": snapshot.get("palavras_chave") or item.palavras_chave,
                    "tipo_processo": snapshot.get("tipo_processo") or item.tipo_processo,
                    "responsavel_adm": snapshot.get("responsavel_adm") or item.responsavel_adm,
                    "status": status_ficha,
                    "observacoes": observacoes_ficha,
                    "finalizado_em": item.finalizado_em,
                    "data_entrada": item.data_entrada,
                    "campos_extra": campos_extra_ficha,
                    "extras_valores": snapshot_extras or item.dados_extra or {},
                }
            )
        destinos_pendentes = []
        for item in relacionados_base:
            destino_norm = normalizar_gerencia(item.tramitado_para, permitir_entrada=True)
            if (
                destino_norm
                and destino_norm not in ignorar_gerencias
                and destino_norm not in gerencias_registradas
            ):
                destinos_pendentes.append(destino_norm)
                gerencias_registradas.add(destino_norm)
        for destino in destinos_pendentes:
            campos_extra_destino = serializar_campos_extra(listar_campos_gerencia(destino))
            numero_base = processo.numero_sei_base or ""
            demandas_relacionadas.append(
                {
                    "gerencia": destino,
                    "numero_sei": numero_base or processo.numero_sei,
                    "numero_sei_base": numero_base or processo.numero_sei,
                    "status": "Pendente",
                    "coordenadoria": None,
                    "equipe_area": None,
                    "responsavel_equipe": None,
                    "responsavel_adm": processo.responsavel_adm,
                }
            )
            demandas_ficha.append(
                {
                    "gerencia": destino,
                    "numero_sei": None,
                    "numero_sei_base": numero_base or processo.numero_sei,
                    "numero_display": numero_base or processo.numero_sei or "",
                    "assunto": None,
                    "interessado": None,
                    "concessionaria": None,
                    "coordenadoria": None,
                    "equipe_area": None,
                    "responsavel_equipe": None,
                    "palavras_chave": None,
                    "tipo_processo": None,
                    "responsavel_adm": processo.responsavel_adm,
                    "status": "Pendente",
                    "observacoes": None,
                    "finalizado_em": None,
                    "data_entrada": None,
                    "campos_extra": campos_extra_destino,
                    "extras_valores": {},
                }
            )
        gerencias_com_demanda = [
            ger
            for ger in coletar_gerencias_com_demanda_por_base(
                processo.numero_sei_base,
                chave_referencia=chave_referencia,
            )
            if ger != origem_saida
        ]
    ficha_tecnica = None
    if demandas_ficha:
        def _coletar_valores(chave: str, origem: Optional[List[Dict[str, object]]] = None) -> List[str]:
            origem = origem if origem is not None else demandas_ficha
            valores = []
            vistos = set()
            for item in origem:
                valor = item.get(chave)
                if valor is None:
                    continue
                if isinstance(valor, str):
                    valor = valor.strip()
                if not valor:
                    continue
                if valor not in vistos:
                    vistos.add(valor)
                    valores.append(valor)
            return valores

        def _coletar_numeros() -> List[str]:
            valores = []
            vistos = set()
            for item in demandas_ficha:
                valor = (
                    item.get("numero_display")
                    or item.get("numero_sei_base")
                    or item.get("numero_sei")
                )
                if valor is None:
                    continue
                if isinstance(valor, str):
                    valor = valor.strip()
                if not valor:
                    continue
                if valor not in vistos:
                    vistos.add(valor)
                    valores.append(valor)
            return valores

        def _unir_valores(chave: str) -> str:
            valores = _coletar_valores(chave)
            if not valores:
                return "-"
            if len(valores) == 1:
                return valores[0]
            return " | ".join(valores)

        numeros = _coletar_numeros()
        gerencias = _coletar_valores("gerencia")
        if not gerencias and demandas_relacionadas:
            gerencias = _coletar_valores("gerencia", demandas_relacionadas)
        coordenadorias = _coletar_valores("coordenadoria")
        equipes = _coletar_valores("equipe_area")
        responsaveis = _coletar_valores("responsavel_equipe")
        if not coordenadorias and demandas_relacionadas:
            coordenadorias = _coletar_valores("coordenadoria", demandas_relacionadas)
        if not equipes and demandas_relacionadas:
            equipes = _coletar_valores("equipe_area", demandas_relacionadas)
        if not responsaveis and demandas_relacionadas:
            responsaveis = _coletar_valores("responsavel_equipe", demandas_relacionadas)
        data_entradas = [
            item.get("data_entrada")
            for item in demandas_ficha
            if item.get("data_entrada")
        ]
        data_entrada_min = min(data_entradas) if data_entradas else None
        finalizados = [
            item.get("finalizado_em")
            for item in demandas_ficha
            if item.get("finalizado_em")
        ]
        finalizado_max = max(finalizados) if finalizados else None

        campos_por_slug: Dict[str, Dict[str, object]] = {}
        for item in demandas_ficha:
            for campo in item.get("campos_extra") or []:
                if not isinstance(campo, dict):
                    continue
                slug = (campo.get("slug") or "").strip()
                if not slug:
                    continue
                if slug not in campos_por_slug:
                    campos_por_slug[slug] = campo

        extras_agg: Dict[str, List[str]] = {}
        for item in demandas_ficha:
            extras = item.get("extras_valores") or {}
            if not isinstance(extras, dict):
                continue
            for slug, valor in extras.items():
                if valor is None:
                    continue
                if isinstance(valor, str):
                    texto = valor.strip()
                else:
                    texto = str(valor).strip()
                if not texto:
                    continue
                lista = extras_agg.setdefault(slug, [])
                if texto not in lista:
                    lista.append(texto)

        extras_final = {slug: " | ".join(vals) for slug, vals in extras_agg.items()}
        numero_referencia = processo.numero_sei_base or (numeros[0] if numeros else "")

        ficha_tecnica = {
            "numero_referencia": numero_referencia,
            "numeros": numeros,
            "total_demandas": len(demandas_ficha),
            "assunto": _unir_valores("assunto"),
            "interessado": _unir_valores("interessado"),
            "concessionaria": _unir_valores("concessionaria"),
            "gerencia": " | ".join(gerencias) if gerencias else "-",
            "coordenadoria": " | ".join(coordenadorias) if coordenadorias else "-",
            "equipe_area": " | ".join(equipes) if equipes else "-",
            "responsavel_equipe": " | ".join(responsaveis) if responsaveis else "-",
            "palavras_chave": _unir_valores("palavras_chave"),
            "tipo_processo": _unir_valores("tipo_processo"),
            "responsavel_adm": _unir_valores("responsavel_adm"),
            "status": _unir_valores("status"),
            "observacoes": _unir_valores("observacoes"),
            "finalizado_em": finalizado_max,
            "data_entrada": data_entrada_min,
            "campos_extra": list(campos_por_slug.values()),
            "extras_valores": extras_final,
        }

    return render_template(
        "processo_form.html",
        processo=processo,
        modo_edicao=True,
        campos_extra=serializar_campos_extra(campos_def),
        valores_extra=processo.dados_extra or {},
        pode_configurar_campos=usuario_pode_configurar_campos(processo.gerencia),
        somente_visualizacao=somente_visualizacao,
        data_entrada_gerencia_atual=data_entrada_na_gerencia(processo, processo.gerencia),
        gerencias_relacionadas=gerencias_relacionadas or [],
        bloquear_finalizacao_saida=bloquear_finalizacao_saida,
        mostrar_devolver=mostrar_devolver,
        mostrar_ficha=mostrar_ficha,
        valor_devolver=valor_devolver,
        alerta_tramite=alerta_tramite,
        demandas_relacionadas=demandas_relacionadas,
        demandas_ficha=demandas_ficha,
        ficha_tecnica=ficha_tecnica,
        gerencias_com_demanda=gerencias_com_demanda,
        opcoes_concessionarias=CONCESSIONARIAS,
        opcoes_tipo_processo=TIPOS_PROCESSO,
        opcoes_interessados=INTERESSADOS,
        opcoes_responsavel_adm=opcoes_responsavel_adm,
        opcoes_status=obter_status_por_gerencia(processo.gerencia),
        opcoes_classificacao=CLASSIFICACOES_INSTITUCIONAIS,
        opcoes_coordenadorias=obter_coordenadorias_por_gerencia(processo.gerencia),
        opcoes_equipes=obter_equipes_por_coordenadoria(processo.coordenadoria),
        opcoes_equipes_por_coordenadoria=EQUIPES_POR_COORDENADORIA,
        opcoes_responsaveis=listar_responsaveis_por_contexto(processo),
        opcoes_responsaveis_por_equipe=RESPONSAVEIS_POR_EQUIPE,
        opcoes_destinos_saida=DESTINOS_SAIDA,
        scroll_y=scroll_y,
        pode_finalizar_gerencia=usuario_pode_finalizar_gerencia(),
    )


@app.route("/processo/<int:processo_id>/editar", methods=["GET", "POST"])
@login_required
def editar_processo(processo_id: int):
    """Permite revisar campos complementares de um processo existente."""
    if SITE_EM_CONFIGURACAO:
        flash(
            "A edicao de processos estara disponivel apos concluirmos a configuracao do banco.",
            "info",
        )
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    pode_editar = usuario_pode_editar_processo(processo)
    somente_visualizacao = not pode_editar
    # Campos extras desta gerencia (definicoes)
    campos_def = listar_campos_gerencia(processo.gerencia)

    if request.method == "POST":
        if somente_visualizacao:
            flash(
                "Seu perfil possui apenas visualizacao para esta gerencia.",
                "warning",
            )
            return redirect(url_for("editar_processo", processo_id=processo.id))
        estado_antes = capturar_estado_historico_processo(processo)
        responsavel_antes = estado_antes.get("responsavel_equipe") or ""
        aplicar_edicao_processo(processo, request.form, campos_def)
        aviso_atribuicao = sincronizar_atribuicao_responsavel_equipe(
            processo, responsavel_antes
        )
        if aviso_atribuicao:
            flash(aviso_atribuicao, "warning")
        estado_depois = capturar_estado_historico_processo(processo)
        mudancas_edicao = descrever_mudancas_historico(estado_antes, estado_depois)
        acao_post = (request.form.get("acao") or "").strip().lower()
        if processo.gerencia == "SAIDA" and acao_post == "devolver":
            nova_gerencia = normalizar_gerencia(
                request.form.get("nova_gerencia") or request.form.get("devolver_para")
            )
            comentario = limpar_texto(request.form.get("comentario"), "") or "Devolucao pela SAIDA"
            origem_saida = normalizar_gerencia(obter_origem_saida(processo))
            if not nova_gerencia:
                flash("Selecione a gerencia para devolver o processo.", "warning")
                return redirect(
                    url_for("editar_processo", processo_id=processo.id, acao="devolver")
                )
            if nova_gerencia == processo.gerencia:
                flash("Processo ja esta na gerencia selecionada.", "info")
                return redirect(
                    url_for(
                        "editar_processo",
                        processo_id=processo.id,
                        acao="devolver",
                        devolver_para=nova_gerencia,
                    )
                )
            if processo.numero_sei_base:
                chave_referencia = obter_chave_processo_relacional(processo)
                gerencias_com_historico = set(
                    coletar_gerencias_com_demanda_por_base(
                        processo.numero_sei_base,
                        chave_referencia=chave_referencia,
                    )
                )
                if (
                    nova_gerencia != origem_saida
                    and nova_gerencia in gerencias_com_historico
                ):
                    flash(
                        "Ja existe (ou ja existiu) demanda deste processo nessa gerencia. Envio bloqueado.",
                        "warning",
                    )
                    return redirect(
                        url_for(
                            "editar_processo",
                            processo_id=processo.id,
                            acao="devolver",
                            devolver_para=nova_gerencia,
                        )
                    )

            snapshot = {
                "numero_sei": processo.numero_sei,
                "numero_sei_base": processo.numero_sei_base,
                "assunto": processo.assunto,
                "interessado": processo.interessado,
                "concessionaria": processo.concessionaria,
                "classificacao_institucional": processo.descricao,
                "descricao_melhorada": processo.descricao_melhorada,
                "observacao": processo.observacao,
                "responsavel_adm": processo.responsavel_adm,
                "planilhado_por": processo.responsavel_adm
                or (processo.assigned_to.nome if processo.assigned_to else None)
                or (processo.assigned_to.username if processo.assigned_to else None),
                "prazo": processo.prazo.strftime("%Y-%m-%d") if processo.prazo else None,
                "data_entrada": processo.data_entrada.strftime("%Y-%m-%d")
                if processo.data_entrada
                else None,
                "data_entrada_geplan": processo.data_entrada_geplan.strftime("%Y-%m-%d")
                if processo.data_entrada_geplan
                else None,
                "coordenadoria": processo.coordenadoria,
                "equipe_area": processo.equipe_area,
                "responsavel_equipe": processo.responsavel_equipe,
                "tipo_processo": processo.tipo_processo,
                "palavras_chave": processo.palavras_chave,
                "status": processo.status,
                "data_status": processo.data_status.isoformat()
                if processo.data_status
                else None,
                "prazo_equipe": processo.prazo_equipe.strftime("%Y-%m-%d")
                if processo.prazo_equipe
                else None,
                "observacoes_complementares": processo.observacoes_complementares,
                "extras": processo.dados_extra or {},
            }
            if origem_saida and nova_gerencia == origem_saida:
                movimentacao = Movimentacao(
                    processo=processo,
                    de_gerencia=processo.gerencia,
                    para_gerencia=nova_gerencia,
                    motivo=comentario,
                    usuario=current_user.username,
                    tipo="movimentacao",
                    dados_snapshot=snapshot,
                )
                processo.gerencia = nova_gerencia
                processo.tramitado_para = None
                processo.assigned_to = None
                db.session.add(movimentacao)
                mensagem_sucesso = "Processo devolvido com sucesso."
            else:
                numero_base = processo.numero_sei_base or processo.numero_sei
                extras_novo = dict(processo.dados_extra or {})
                gerencias_escolhidas = []
                for ger in extras_novo.get("gerencias_escolhidas") or []:
                    ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
                    if ger_norm and ger_norm not in gerencias_escolhidas:
                        gerencias_escolhidas.append(ger_norm)
                if nova_gerencia not in gerencias_escolhidas:
                    gerencias_escolhidas.append(nova_gerencia)
                extras_novo["gerencias_escolhidas"] = gerencias_escolhidas
                if numero_base:
                    extras_novo["numero_sei_original"] = numero_base
                extras_novo["responsavel_adm_inicial"] = processo.responsavel_adm or (
                    (processo.dados_extra or {}).get("responsavel_adm_inicial")
                )

                nova_demanda = Processo(
                    numero_sei=f"{nova_gerencia}-{numero_base}".strip()[:50],
                    assunto=processo.assunto,
                    interessado=processo.interessado,
                    concessionaria=processo.concessionaria,
                    descricao=processo.descricao,
                    descricao_melhorada=processo.descricao_melhorada,
                    gerencia=nova_gerencia,
                    prazo=processo.prazo,
                    data_entrada=datetime.utcnow().date(),
                    responsavel_adm=processo.responsavel_adm,
                    observacao=processo.observacao,
                    dados_extra=extras_novo,
                )
                db.session.add(nova_demanda)
                db.session.flush()
                db.session.add(
                    Movimentacao(
                        processo=processo,
                        de_gerencia="SAIDA",
                        para_gerencia=nova_gerencia,
                        motivo=f"{comentario} (nova demanda criada)",
                        usuario=current_user.username,
                        tipo="movimentacao",
                        dados_snapshot=snapshot,
                    )
                )
                db.session.add(
                    Movimentacao(
                        processo=nova_demanda,
                        de_gerencia="SAIDA",
                        para_gerencia=nova_gerencia,
                        motivo=comentario,
                        usuario=current_user.username,
                        tipo="movimentacao",
                        dados_snapshot=snapshot,
                    )
                )
                processo.tramitado_para = nova_gerencia
                mensagem_sucesso = "Nova demanda criada e enviada com sucesso."
            db.session.commit()
            flash(mensagem_sucesso, "success")
            return redirect(url_for("gerencia", nome_gerencia="SAIDA"))

        if mudancas_edicao:
            status_antes = (estado_antes.get("status") or "").strip()
            status_depois = (estado_depois.get("status") or "").strip()
            if status_antes != status_depois:
                db.session.add(
                    Movimentacao(
                        processo=processo,
                        de_gerencia=processo.gerencia,
                        para_gerencia=processo.gerencia,
                        motivo=status_depois or "-",
                        usuario=current_user.username,
                        tipo="status",
                    )
                )
                mudancas_edicao = [
                    m for m in mudancas_edicao if not m.startswith("Status:")
                ]
            if mudancas_edicao:
                db.session.add(
                    Movimentacao(
                        processo=processo,
                        de_gerencia=processo.gerencia,
                        para_gerencia=processo.gerencia,
                        motivo="; ".join(mudancas_edicao[:8]),
                        usuario=current_user.username,
                        tipo="edicao",
                    )
                )

        db.session.commit()
        # Decide destino conforme tipo de salvamento (apenas extras -> permanece na edicao)
        somente_extras = True
        for chave in request.form.keys():
            if not (chave or "").startswith("extra_"):
                somente_extras = False
                break
        redirect_to = request.form.get("redirect_to") or ""
        redirect_path = None
        if redirect_to:
            parsed = urlparse(redirect_to)
            if not parsed.scheme and not parsed.netloc:
                redirect_path = redirect_to
        if somente_extras:
            flash("Campos extras atualizados.", "success")
        else:
            flash("Processo atualizado com sucesso.", "success")
        if redirect_path:
            return redirect(redirect_path)
        return redirect(url_for("editar_processo", processo_id=processo.id))

    mostrar_devolver = (request.args.get("acao") or "").strip().lower() == "devolver"
    mostrar_ficha = (request.args.get("mostrar_ficha") or "").strip() == "1"
    valor_devolver = limpar_texto(request.args.get("devolver_para"), "")
    alerta_tramite = normalizar_gerencia(
        limpar_texto(request.args.get("alerta_tramite"), ""),
        permitir_entrada=True,
    ) or ""
    return _render_tela_edicao_processo(
        processo,
        campos_def,
        mostrar_devolver=mostrar_devolver,
        mostrar_ficha=mostrar_ficha,
        valor_devolver=valor_devolver,
        gerencias_relacionadas=[],
        bloquear_finalizacao_saida=False,
        alerta_tramite=alerta_tramite,
        scroll_y=(request.args.get("scroll_y") or ""),
    )


@app.route("/processo/<int:processo_id>/classificacao", methods=["POST"])
@login_required
def atualizar_classificacao(processo_id: int):
    """Atualiza a classificacao institucional (ex.: FALA SP)."""
    if SITE_EM_CONFIGURACAO:
        flash("Classificacao indisponivel ate a configuracao final do sistema.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para editar este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    classificacao = limpar_texto(request.form.get("classificacao"), "")
    classificacao_anterior = processo.classificacao_institucional or ""
    processo.classificacao_institucional = classificacao or None
    if (classificacao_anterior or "") != (classificacao or ""):
        db.session.add(
            Movimentacao(
                processo=processo,
                de_gerencia=processo.gerencia,
                para_gerencia=processo.gerencia,
                motivo=(
                    f"Classificacao institucional: {classificacao_anterior or '-'} -> {classificacao or '-'}"
                ),
                usuario=current_user.username,
                tipo="edicao",
            )
        )
    db.session.commit()
    flash("Classificacao atualizada.", "success")
    destino = request.form.get("gerencia_origem") or processo.gerencia
    return redirect(url_for("gerencia", nome_gerencia=destino))


@app.route("/processo/<int:processo_id>/finalizar", methods=["POST"])
@login_required
def finalizar_processo(processo_id: int):
    """Registra a conclusao do processo e opcionalmente salva um comentario."""
    if SITE_EM_CONFIGURACAO:
        flash("Finalizacao de processos sera liberada apos configuracao do banco.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para tramitar/finalizar este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    if not usuario_pode_finalizar_gerencia():
        flash(
            "Seu perfil permite visualizar/editar/salvar, mas nao permite finalizar processos.",
            "warning",
        )
        return redirect(url_for("editar_processo", processo_id=processo.id))
    responsavel_atual = processo.assigned_to
    if processo.finalizado_em:
        flash("Processo ja estava finalizado.", "info")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))

    def _numero_base(proc: Processo) -> str:
        return proc.numero_sei_base

    comentario = limpar_texto(request.form.get("comentario"), "")
    if processo.gerencia == "SAIDA":
        destino_bruto = None
    else:
        destino_bruto = request.form.get("tramitado_para") or request.form.get("destino")
    destino = normalizar_gerencia(destino_bruto) if destino_bruto else None
    destino_bloqueado = False
    origem_gerencia = processo.gerencia  # manter para redirecionar sempre para a pagina de origem

    if processo.gerencia == "SAIDA":
        destino_saida = limpar_texto(request.form.get("destino_saida"), "")
        if not destino_saida:
            flash("Informe o destino SAÍDA antes de finalizar.", "warning")
            return redirect(url_for("editar_processo", processo_id=processo.id))

    # Aplica alteracoes do formulario antes de finalizar
    status_antes_finalizacao = (processo.status or "").strip()
    campos_def = listar_campos_gerencia(processo.gerencia)
    aplicar_edicao_processo(processo, request.form, campos_def)
    status_depois_finalizacao = (processo.status or "").strip()
    if status_antes_finalizacao != status_depois_finalizacao:
        db.session.add(
            Movimentacao(
                processo=processo,
                de_gerencia=processo.gerencia,
                para_gerencia=processo.gerencia,
                motivo=status_depois_finalizacao or "-",
                usuario=current_user.username,
                tipo="status",
            )
        )

    if processo.gerencia != "SAIDA" and not destino:
        db.session.commit()
        flash("Informe a gerencia em 'Tramitar para' para finalizar.", "warning")
        return redirect(url_for("editar_processo", processo_id=processo.id))

    if processo.gerencia != "SAIDA":
        obrigatorios_finalizar = {
            "Coordenadoria": processo.coordenadoria,
            "Equipe / Área": processo.equipe_area,
            "Atribuído SEI": processo.responsavel_equipe,
            "Status": processo.status,
        }
        faltando = [
            campo
            for campo, valor in obrigatorios_finalizar.items()
            if not limpar_texto(valor)
        ]
        if faltando:
            db.session.commit()
            flash(
                "Preencha os campos obrigatórios para finalizar: "
                + ", ".join(faltando)
                + ".",
                "warning",
            )
            return redirect(url_for("editar_processo", processo_id=processo.id))

    if processo.gerencia == "SAIDA" and not destino:
        numero_base = _numero_base(processo)
        relacionados = []
        if numero_base:
            candidatos = Processo.query.filter(
                Processo.id != processo.id,
                Processo.finalizado_em.is_(None),
            ).all()
            for candidato in candidatos:
                if _numero_base(candidato) == numero_base and candidato.gerencia != "SAIDA":
                    relacionados.append(candidato)
        if relacionados:
            gerencias_rel = sorted({f"{p.gerencia} ({p.numero_sei_base})" for p in relacionados})
            campos_def_render = listar_campos_gerencia(processo.gerencia)
            return _render_tela_edicao_processo(
                processo,
                campos_def_render,
                gerencias_relacionadas=gerencias_rel,
                bloquear_finalizacao_saida=True,
                scroll_y=(request.form.get("scroll_y") or ""),
            )

    if destino:
        # Finaliza etapa na gerencia atual (sempre envia para SAIDA).
        # Se houver destino diferente de SAIDA, cria uma nova demanda na gerencia escolhida.
        snapshot = {
            "numero_sei": processo.numero_sei,
            "numero_sei_base": processo.numero_sei_base,
            "assunto": processo.assunto,
            "interessado": processo.interessado,
            "concessionaria": processo.concessionaria,
            "classificacao_institucional": processo.descricao,
            "descricao_melhorada": processo.descricao_melhorada,
            "observacao": processo.observacao,
            "responsavel_adm": processo.responsavel_adm,
            "planilhado_por": processo.responsavel_adm
            or (processo.assigned_to.nome if processo.assigned_to else None)
            or (processo.assigned_to.username if processo.assigned_to else None),
            "prazo": processo.prazo.strftime("%Y-%m-%d") if processo.prazo else None,
            "data_entrada": processo.data_entrada.strftime("%Y-%m-%d") if processo.data_entrada else None,
            "data_entrada_geplan": processo.data_entrada_geplan.strftime("%Y-%m-%d")
            if processo.data_entrada_geplan
            else None,
            "coordenadoria": processo.coordenadoria,
            "equipe_area": processo.equipe_area,
            "responsavel_equipe": processo.responsavel_equipe,
            "tipo_processo": processo.tipo_processo,
            "palavras_chave": processo.palavras_chave,
            "status": processo.status,
            "data_status": processo.data_status.isoformat() if processo.data_status else None,
            "prazo_equipe": processo.prazo_equipe.strftime('%Y-%m-%d') if processo.prazo_equipe else None,
            "observacoes_complementares": processo.observacoes_complementares,
            "extras": processo.dados_extra or {},
        }
        numero_base = processo.numero_sei_base or processo.numero_sei
        destino_nova_demanda = destino if destino != "SAIDA" else None
        if destino_nova_demanda and numero_base:
            chave_referencia = obter_chave_processo_relacional(processo)
            gerencias_com_historico = set(
                coletar_gerencias_com_demanda_por_base(
                    numero_base,
                    chave_referencia=chave_referencia,
                )
            )
            if destino_nova_demanda in gerencias_com_historico:
                destino_bloqueado = True
                destino_nova_demanda = None

        data_envio_saida = datetime.utcnow()
        processo.finalizado_em = None
        processo.finalizado_por = None
        processo.data_saida = data_envio_saida.date()
        processo.assigned_to = None
        processo.tramitado_para = None
        processo.gerencia = "SAIDA"

        extras_novo = dict(processo.dados_extra or {})
        gerencias_escolhidas = []
        for ger in extras_novo.get("gerencias_escolhidas") or []:
            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
            if ger_norm and ger_norm not in gerencias_escolhidas:
                gerencias_escolhidas.append(ger_norm)
        if "SAIDA" not in gerencias_escolhidas:
            gerencias_escolhidas.append("SAIDA")
        if destino_nova_demanda and destino_nova_demanda not in gerencias_escolhidas:
            gerencias_escolhidas.append(destino_nova_demanda)
        extras_novo["gerencias_escolhidas"] = gerencias_escolhidas
        if numero_base:
            extras_novo["numero_sei_original"] = numero_base
        extras_novo["responsavel_adm_inicial"] = processo.responsavel_adm or (
            (processo.dados_extra or {}).get("responsavel_adm_inicial")
        )

        processo.dados_extra = dict(extras_novo)

        movimentacao = Movimentacao(
            processo=processo,
            de_gerencia=origem_gerencia,
            para_gerencia="SAIDA",
            motivo=comentario or "Tramite para SAIDA",
            usuario=current_user.username,
            tipo="finalizacao_gerencia",
            dados_snapshot=snapshot,
        )
        db.session.add(movimentacao)
        if destino_nova_demanda:
            nova_demanda_destino = Processo(
                numero_sei=f"{destino_nova_demanda}-{numero_base}".strip()[:50],
                assunto=processo.assunto,
                interessado=processo.interessado,
                concessionaria=processo.concessionaria,
                descricao=processo.descricao,
                descricao_melhorada=processo.descricao_melhorada,
                gerencia=destino_nova_demanda,
                prazo=processo.prazo,
                data_entrada=datetime.utcnow().date(),
                responsavel_adm=processo.responsavel_adm,
                observacao=processo.observacao,
                dados_extra=dict(extras_novo),
            )
            db.session.add(nova_demanda_destino)
            db.session.flush()
            db.session.add(
                Movimentacao(
                    processo=nova_demanda_destino,
                    de_gerencia=origem_gerencia,
                    para_gerencia=destino_nova_demanda,
                    motivo=comentario or "Tramite por finalizacao",
                    usuario=current_user.username,
                    tipo="movimentacao",
                    dados_snapshot=snapshot,
                )
            )
        if destino_bloqueado:
            flash(
                f"A gerencia {destino} ja possui uma demanda deste processo. "
                "A demanda foi enviada para SAIDA, mas nao foi criada nova demanda nessa gerencia.",
                "warning",
            )
    else:
        # Sem destino especifico: marca como FINALIZADO geral.
        if processo.gerencia != "SAIDA":
            db.session.commit()
            flash(
                "Finalizacao geral so pode ocorrer na SAIDA. Envie para a SAIDA antes de finalizar.",
                "warning",
            )
            return redirect(url_for("editar_processo", processo_id=processo.id))
        # Quando estiver na SAIDA, finaliza em lote todas as demandas abertas do mesmo processo base.
        finalizados_em_lote: List[Processo] = []
        if processo.gerencia == "SAIDA" and processo.numero_sei_base:
            chave_referencia = obter_chave_processo_relacional(processo)
            finalizados_em_lote = [
                p
                for p in Processo.query.filter(
                    Processo.finalizado_em.is_(None),
                    Processo.gerencia == "SAIDA",
                ).all()
                if processo_pertence_mesmo_grupo(
                    p,
                    numero_base=processo.numero_sei_base,
                    chave_referencia=chave_referencia,
                )
            ]
        if not finalizados_em_lote:
            finalizados_em_lote = [processo]

        data_finalizacao = datetime.utcnow()
        data_saida_ref = data_finalizacao.date()
        destino_saida_final = processo.tramitado_para

        for item in finalizados_em_lote:
            responsavel_item = item.assigned_to
            item.finalizado_em = data_finalizacao
            item.finalizado_por = current_user.username
            item.status = item.status or "Finalizado"
            item.data_saida = data_saida_ref
            if destino_saida_final:
                item.tramitado_para = destino_saida_final
            db.session.add(
                Movimentacao(
                    processo=item,
                    de_gerencia=item.gerencia,
                    para_gerencia="FINALIZADO",
                    motivo=comentario or "Finalizacao",
                    usuario=current_user.username,
                    tipo="finalizado_geral",
                )
            )
            if responsavel_item and responsavel_item.id != current_user.id:
                registrar_notificacao(
                    responsavel_item,
                    f"O processo {item.numero_sei_base} foi finalizado por {current_user.username}.",
                    item,
                )

    # Notifica responsavel quando outra pessoa finaliza ou tramita
    if (
        responsavel_atual
        and responsavel_atual.id != current_user.id
        and not (processo.gerencia == "SAIDA" and not destino)
    ):
        destino_notificacao = None if destino_bloqueado else destino
        if not destino:
            acao = "finalizado"
        elif destino_bloqueado:
            acao = "finalizado e enviado para SAIDA"
        elif destino_notificacao == "SAIDA":
            acao = "finalizado e enviado para SAIDA"
        else:
            acao = (
                f"finalizado, enviado para SAIDA e nova demanda em {destino_notificacao}"
            )
        registrar_notificacao(
            responsavel_atual,
            f"O processo {processo.numero_sei_base} foi {acao} por {current_user.username}.",
            processo,
        )

    db.session.commit()
    if origem_gerencia == "SAIDA":
        flash("Processo finalizado com sucesso.", "success")
    else:
        flash("Demanda finalizada e enviada para SAIDA.", "success")
    # Sempre voltar para a pagina da gerencia de origem
    return redirect(url_for("gerencia", nome_gerencia=origem_gerencia))


@app.route("/processo/<int:processo_id>/excluir", methods=["POST"])
@login_required
def excluir_processo(processo_id: int):
    """Remove definitivamente o processo selecionado."""
    if SITE_EM_CONFIGURACAO:
        flash("Remocao de processos desabilitada durante a configuracao.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para excluir este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    gerencia_origem = processo.gerencia
    db.session.delete(processo)
    db.session.commit()
    flash("Processo removido.", "success")
    return redirect(url_for("gerencia", nome_gerencia=gerencia_origem))


@app.route("/processo/<int:processo_id>/mover", methods=["POST"])
@login_required
def mover_processo(processo_id: int):
    """Move um processo para outra gerencia e registra a movimentacao."""
    if SITE_EM_CONFIGURACAO:
        flash("Movimentacao desabilitada enquanto o banco estiver vazio.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para tramitar este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    nova_gerencia = normalizar_gerencia(request.form.get("nova_gerencia"))
    comentario = limpar_texto(request.form.get("comentario"), "")
    origem_movimentacao = processo.gerencia

    if not nova_gerencia:
        flash("Selecione uma gerencia de destino valida.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    if nova_gerencia == processo.gerencia:
        flash("Processo ja esta na gerencia selecionada.", "info")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    if not comentario:
        flash("Informe o motivo da movimentacao.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))

    if processo.gerencia == "SAIDA" and nova_gerencia != "SAIDA" and processo.numero_sei_base:
        origem_saida = normalizar_gerencia(obter_origem_saida(processo))
        chave_referencia = obter_chave_processo_relacional(processo)
        gerencias_com_historico = set(
            coletar_gerencias_com_demanda_por_base(
                processo.numero_sei_base,
                chave_referencia=chave_referencia,
            )
        )
        if nova_gerencia != origem_saida and nova_gerencia in gerencias_com_historico:
            flash(
                "Ja existe (ou ja existiu) demanda deste processo nessa gerencia. Envio bloqueado.",
                "warning",
            )
            return redirect(
                url_for(
                    "editar_processo",
                    processo_id=processo.id,
                    acao="devolver",
                    devolver_para=nova_gerencia,
                )
            )
    # Snapshot dos dados especificos da gerencia de origem
    snapshot = {
        "numero_sei": processo.numero_sei,
        "numero_sei_base": processo.numero_sei_base,
        "assunto": processo.assunto,
        "interessado": processo.interessado,
        "concessionaria": processo.concessionaria,
        "classificacao_institucional": processo.descricao,
        "descricao_melhorada": processo.descricao_melhorada,
        "observacao": processo.observacao,
        "responsavel_adm": processo.responsavel_adm,
        "planilhado_por": processo.responsavel_adm
        or (processo.assigned_to.nome if processo.assigned_to else None)
        or (processo.assigned_to.username if processo.assigned_to else None),
        "prazo": processo.prazo.strftime("%Y-%m-%d") if processo.prazo else None,
        "data_entrada": processo.data_entrada.strftime("%Y-%m-%d") if processo.data_entrada else None,
        "data_entrada_geplan": processo.data_entrada_geplan.strftime("%Y-%m-%d")
        if processo.data_entrada_geplan
        else None,
        "coordenadoria": processo.coordenadoria,
        "equipe_area": processo.equipe_area,
        "responsavel_equipe": processo.responsavel_equipe,
        "tipo_processo": processo.tipo_processo,
        "palavras_chave": processo.palavras_chave,
        "status": processo.status,
        "data_status": processo.data_status.isoformat() if processo.data_status else None,
        "prazo_equipe": processo.prazo_equipe.strftime("%Y-%m-%d") if processo.prazo_equipe else None,
        "observacoes_complementares": processo.observacoes_complementares,
        "extras": processo.dados_extra or {},
    }


    movimentacao = Movimentacao(
        processo=processo,
        de_gerencia=processo.gerencia,
        para_gerencia=nova_gerencia,
        motivo=comentario,
        usuario=current_user.username,
        tipo="movimentacao",
        dados_snapshot=snapshot,
    )
    processo.gerencia = nova_gerencia
    processo.tramitado_para = None
    processo.assigned_to = None
    # SAIDA funciona como revisao: mantem os dados para analise; outras gerencias reiniciam o ciclo
    if nova_gerencia != "SAIDA" and processo.gerencia != "SAIDA":
        processo.coordenadoria = None
        processo.equipe_area = None
        processo.responsavel_equipe = None
        processo.tipo_processo = None
        processo.palavras_chave = None
        processo.status = None
        processo.data_status = None
        processo.prazo_equipe = None
        processo.observacoes_complementares = None
        processo.dados_extra = {}

    db.session.add(movimentacao)
    db.session.commit()
    flash("Processo movido com sucesso.", "success")
    destino_redirect = "SAIDA" if origem_movimentacao == "SAIDA" else nova_gerencia
    return redirect(url_for("gerencia", nome_gerencia=destino_redirect))


@app.route("/processo/<int:processo_id>/devolver-gabinete", methods=["POST"])
@login_required
def devolver_para_gabinete(processo_id: int):
    """Devolve demanda para triagem do gabinete (aba de devolvidos)."""
    if SITE_EM_CONFIGURACAO:
        flash("Devolucao indisponivel enquanto o sistema estiver em configuracao.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para devolver este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))

    origem = normalizar_gerencia(processo.gerencia, permitir_entrada=True)

    motivo = limpar_texto(request.form.get("motivo"), "")
    if not motivo:
        flash("Informe o motivo da devolucao.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=origem or processo.gerencia, aba="interacoes"))

    dados_extra = dict(processo.dados_extra or {})
    dados_extra["devolvido_gabinete"] = True
    dados_extra["devolucao_origem"] = origem
    dados_extra["devolucao_motivo"] = motivo
    dados_extra["devolucao_em"] = datetime.utcnow().isoformat()
    processo.dados_extra = dados_extra
    processo.gerencia = "GABINETE"
    processo.status = "Devolvido ao Gabinete"
    processo.assigned_to = None
    processo.responsavel_equipe = None
    processo.tramitado_para = None
    processo.atualizado_em = datetime.utcnow()
    db.session.add(
        Movimentacao(
            processo=processo,
            de_gerencia=origem or "-",
            para_gerencia="GABINETE",
            motivo=motivo,
            usuario=current_user.username,
            tipo="devolucao_gabinete",
        )
    )
    db.session.commit()
    if origem == "GABINETE":
        flash("Processo movido para a aba de devolvidos do Gabinete.", "success")
    else:
        flash("Processo devolvido para o Gabinete (aba de devolvidos).", "success")
    return redirect(url_for("gerencia", nome_gerencia=origem or processo.gerencia, aba="interacoes"))


@app.route("/processo/<int:processo_id>/devolvido/reenviar", methods=["GET", "POST"])
@login_required
def reenviar_processo_devolvido(processo_id: int):
    """Exibe formulario para reenviar processo devolvido e cria novas demandas."""
    if SITE_EM_CONFIGURACAO:
        flash("Acao indisponivel enquanto o sistema estiver em configuracao.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_tem_liberacao_gerencia("GABINETE", usuario=current_user):
        flash("Apenas usuarios do GABINETE podem tratar devolvidos.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="interacoes"))

    if not usuario_pode_editar_gerencia("GABINETE"):
        flash("Sem permissao para tratar devolvidos do gabinete.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    dados_extra = dict(processo.dados_extra or {})
    if not dados_extra.get("devolvido_gabinete"):
        flash("Processo nao esta marcado como devolvido.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    mensagens = []
    campos_invalidos: List[str] = []
    selected_gerencias: List[str] = []
    opcoes_responsavel_adm = obter_responsaveis_adm_disponiveis()

    def _coletar_status_gerencias() -> Dict[str, List[str]]:
        numero_base = processo.numero_sei_base or processo.numero_sei or ""
        if not numero_base:
            return {"ativas": [], "finalizadas": [], "devolvidas": []}

        chave_referencia = obter_chave_processo_relacional(processo)
        relacionados = [
            item
            for item in Processo.query.all()
            if processo_pertence_mesmo_grupo(
                item,
                numero_base=numero_base,
                chave_referencia=chave_referencia,
            )
        ]

        ativas: set = set()
        finalizadas: set = set()
        devolvidas: set = set()

        for item in relacionados:
            dados_item = item.dados_extra or {}
            ger_item = normalizar_gerencia(item.gerencia, permitir_entrada=True)
            if (
                item.id != processo.id
                and ger_item
                and ger_item not in {"SAIDA", "FINALIZADO", "ENTRADA", "CADASTRO"}
                and item.finalizado_em is None
                and not dados_item.get("devolvido_gabinete")
            ):
                ativas.add(ger_item)

            if dados_item.get("devolvido_gabinete"):
                origem = normalizar_gerencia(
                    dados_item.get("devolucao_origem"), permitir_entrada=True
                )
                if origem:
                    devolvidas.add(origem)

            for mov in item.movimentacoes:
                tipo_mov = (mov.tipo or "").strip().lower()
                if tipo_mov == "finalizacao_gerencia":
                    ger_mov = normalizar_gerencia(
                        mov.de_gerencia, permitir_entrada=True
                    )
                    if ger_mov:
                        finalizadas.add(ger_mov)
                elif tipo_mov == "devolucao_gabinete":
                    ger_mov = normalizar_gerencia(
                        mov.de_gerencia, permitir_entrada=True
                    )
                    if ger_mov:
                        devolvidas.add(ger_mov)

        devolvidas = devolvidas.difference(ativas).difference(finalizadas)
        return {
            "ativas": ordenar_gerencias_preferencial(list(ativas)),
            "finalizadas": ordenar_gerencias_preferencial(list(finalizadas)),
            "devolvidas": ordenar_gerencias_preferencial(list(devolvidas)),
        }

    status_gerencias = _coletar_status_gerencias()

    if request.method == "POST":
        gerencias_raw = request.form.getlist("gerencias")
        gerencias_normalizadas: List[str] = []
        for item in gerencias_raw:
            ger = normalizar_gerencia(item, permitir_entrada=True)
            if ger and ger not in gerencias_normalizadas:
                gerencias_normalizadas.append(ger)
        selected_gerencias = gerencias_normalizadas
        numero_base = processo.numero_sei_base or processo.numero_sei or ""

        if not gerencias_normalizadas:
            mensagens.append(("danger", "Selecione ao menos uma gerencia para reenviar."))
            campos_invalidos.append("gerencias")
        elif not numero_base:
            mensagens.append(("danger", "Numero SEI invalido para reenviar o processo."))
            campos_invalidos.append("sei")
        else:
            gerencias_ativas = set(status_gerencias.get("ativas") or [])
            gerencias_finalizadas = set(status_gerencias.get("finalizadas") or [])
            gerencias_devolvidas = set(status_gerencias.get("devolvidas") or [])

            bloqueadas_ativas = [
                ger for ger in gerencias_normalizadas if ger in gerencias_ativas
            ]
            bloqueadas_finalizadas = [
                ger for ger in gerencias_normalizadas if ger in gerencias_finalizadas
            ]
            devolvidas_sel = [
                ger for ger in gerencias_normalizadas if ger in gerencias_devolvidas
            ]

            if bloqueadas_ativas:
                lista = ", ".join(bloqueadas_ativas)
                mensagens.append(
                    (
                        "danger",
                        "Ja existe demanda ativa deste processo nas gerencias: "
                        f"{lista}. Envio bloqueado.",
                    )
                )
                campos_invalidos.append("gerencias")
            if bloqueadas_finalizadas:
                lista = ", ".join(bloqueadas_finalizadas)
                mensagens.append(
                    (
                        "danger",
                        "Ja houve finalizacao deste processo nas gerencias: "
                        f"{lista}. Envio bloqueado.",
                    )
                )
                campos_invalidos.append("gerencias")
            confirmar_reenvio = (request.form.get("confirmar_reenvio") or "").strip() == "1"
            if devolvidas_sel and not confirmar_reenvio:
                lista = ", ".join(devolvidas_sel)
                mensagens.append(
                    (
                        "warning",
                        "O processo ja foi devolvido pelas gerencias: "
                        f"{lista}. Confirme para reenviar novamente.",
                    )
                )
                campos_invalidos.append("gerencias")

        if mensagens:
            return render_template(
                "processo_form.html",
                processo=processo,
                modo_edicao=False,
                reenviar_devolvido=True,
                mensagens=mensagens,
                form_data={},
                campos_invalidos=campos_invalidos,
                selected_gerencias=selected_gerencias,
                status_gerencias=status_gerencias,
                opcoes_concessionarias=CONCESSIONARIAS,
                opcoes_tipo_processo=TIPOS_PROCESSO,
                opcoes_interessados=INTERESSADOS,
                opcoes_responsavel_adm=opcoes_responsavel_adm,
            )

        dados_novos = dict(dados_extra)
        dados_novos.pop("devolvido_gabinete", None)
        dados_novos.pop("devolucao_origem", None)
        dados_novos.pop("devolucao_motivo", None)
        dados_novos.pop("devolucao_em", None)

        gerencias_escolhidas: List[str] = []
        for ger in dados_novos.get("gerencias_escolhidas") or []:
            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
            if ger_norm and ger_norm not in gerencias_escolhidas:
                gerencias_escolhidas.append(ger_norm)
        for ger in gerencias_normalizadas:
            if ger not in gerencias_escolhidas:
                gerencias_escolhidas.append(ger)
        dados_novos["gerencias_escolhidas"] = gerencias_escolhidas

        if numero_base:
            dados_novos["numero_sei_original"] = numero_base
        if processo.responsavel_adm or dados_novos.get("responsavel_adm_inicial"):
            dados_novos["responsavel_adm_inicial"] = processo.responsavel_adm or dados_novos.get(
                "responsavel_adm_inicial"
            )

        for ger_destino in gerencias_normalizadas:
            novo_processo = Processo(
                numero_sei=f"{ger_destino}-{numero_base}".strip()[:50],
                assunto=processo.assunto,
                interessado=processo.interessado,
                concessionaria=processo.concessionaria,
                descricao=processo.descricao,
                gerencia=ger_destino,
                prazo=processo.prazo,
                data_entrada=datetime.utcnow().date(),
                responsavel_adm=processo.responsavel_adm,
                observacao=processo.observacao,
                dados_extra=dict(dados_novos),
            )
            db.session.add(novo_processo)
            db.session.flush()
            db.session.add(
                Movimentacao(
                    processo=novo_processo,
                    de_gerencia="GABINETE",
                    para_gerencia=ger_destino,
                    motivo="Reenvio de processo devolvido",
                    usuario=current_user.username,
                    tipo="cadastro",
                )
            )

        db.session.delete(processo)
        db.session.commit()
        flash(
            f"Processo reenviado para: {', '.join(gerencias_normalizadas)}.",
            "success",
        )
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    return render_template(
        "processo_form.html",
        processo=processo,
        modo_edicao=False,
        reenviar_devolvido=True,
        mensagens=[],
        form_data={},
        campos_invalidos=[],
        selected_gerencias=selected_gerencias,
        status_gerencias=status_gerencias,
        opcoes_concessionarias=CONCESSIONARIAS,
        opcoes_tipo_processo=TIPOS_PROCESSO,
        opcoes_interessados=INTERESSADOS,
        opcoes_responsavel_adm=opcoes_responsavel_adm,
    )


@app.route("/processo/<int:processo_id>/devolvido/acao", methods=["POST"])
@login_required
def acao_processo_devolvido(processo_id: int):
    """Permite excluir ou reenviar processo devolvido no gabinete."""
    if SITE_EM_CONFIGURACAO:
        flash("Acao indisponivel enquanto o sistema estiver em configuracao.", "info")
        return redirect(url_for("index"))

    processo = Processo.query.get_or_404(processo_id)
    if not usuario_tem_liberacao_gerencia("GABINETE", usuario=current_user):
        flash("Apenas usuarios do GABINETE podem tratar devolvidos.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="interacoes"))

    if not usuario_pode_editar_gerencia("GABINETE"):
        flash("Sem permissao para tratar devolvidos do gabinete.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    dados_extra = dict(processo.dados_extra or {})
    if not dados_extra.get("devolvido_gabinete"):
        flash("Processo nao esta marcado como devolvido.", "warning")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    acao = (request.form.get("acao") or "").strip().lower()
    if acao == "excluir":
        numero = processo.numero_sei_base
        db.session.delete(processo)
        db.session.commit()
        flash(f"Processo {numero} excluido da caixa de devolvidos.", "success")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    if acao == "reenviar":
        nova_gerencia = normalizar_gerencia(request.form.get("nova_gerencia"))
        if not nova_gerencia or nova_gerencia == "GABINETE":
            flash("Selecione uma gerencia valida para reenviar.", "warning")
            return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

        numero_base = processo.numero_sei_base or processo.numero_sei
        if numero_base:
            chave_referencia = obter_chave_processo_relacional(processo)
            gerencias_com_historico = set(
                coletar_gerencias_com_demanda_por_base(
                    numero_base,
                    chave_referencia=chave_referencia,
                )
            )
            if nova_gerencia in gerencias_com_historico:
                flash(
                    "Ja existe (ou ja existiu) demanda deste processo nessa gerencia. Envio bloqueado.",
                    "warning",
                )
                return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))
        dados_novos = dict(dados_extra)
        dados_novos.pop("devolvido_gabinete", None)
        dados_novos.pop("devolucao_origem", None)
        dados_novos.pop("devolucao_motivo", None)
        dados_novos.pop("devolucao_em", None)
        gerencias_escolhidas = []
        for ger in dados_novos.get("gerencias_escolhidas") or []:
            ger_norm = normalizar_gerencia(ger, permitir_entrada=True)
            if ger_norm and ger_norm not in gerencias_escolhidas:
                gerencias_escolhidas.append(ger_norm)
        if nova_gerencia not in gerencias_escolhidas:
            gerencias_escolhidas.append(nova_gerencia)
        dados_novos["gerencias_escolhidas"] = gerencias_escolhidas
        if numero_base:
            dados_novos["numero_sei_original"] = numero_base

        novo_processo = Processo(
            numero_sei=f"{nova_gerencia}-{numero_base}".strip()[:50],
            assunto=processo.assunto,
            interessado=processo.interessado,
            concessionaria=processo.concessionaria,
            descricao=processo.descricao,
            gerencia=nova_gerencia,
            prazo=processo.prazo,
            data_entrada=datetime.utcnow().date(),
            responsavel_adm=processo.responsavel_adm,
            observacao=processo.observacao,
            dados_extra=dados_novos,
        )
        db.session.add(novo_processo)
        db.session.flush()
        db.session.add(
            Movimentacao(
                processo=novo_processo,
                de_gerencia="GABINETE",
                para_gerencia=nova_gerencia,
                motivo="Reenvio de processo devolvido",
                usuario=current_user.username,
                tipo="cadastro",
            )
        )
        db.session.delete(processo)
        db.session.commit()
        flash("Processo reenviado como nova demanda para a gerencia selecionada.", "success")
        return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))

    flash("Acao invalida para processo devolvido.", "warning")
    return redirect(url_for("gerencia", nome_gerencia="GABINETE", aba="devolvidos"))


@app.route("/processo/<int:processo_id>/atribuir", methods=["POST", "GET"])
@login_required
def atribuir_processo(processo_id: int):
    """Permite que usuarios assumam ou liberem processos."""
    if SITE_EM_CONFIGURACAO:
        flash("Atribuicoes estarao disponiveis apos a configuracao do banco.", "info")
        return redirect(url_for("index"))
    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para alterar atribuicao deste processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    if request.method == "GET":
        flash("Use os botoes da lista para atribuir processos.", "info")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))

    acao = request.form.get("acao")
    destino = request.form.get("destino") or processo.gerencia
    destinatario_raw = (request.form.get("destinatario_id") or "").strip()
    destinatario_id = int(destinatario_raw) if destinatario_raw.isdigit() else None
    destinatario_nome = ""
    if destinatario_raw and not destinatario_id:
        if destinatario_raw.lower().startswith("lista:"):
            destinatario_nome = destinatario_raw.split(":", 1)[1].strip()
        else:
            destinatario_nome = destinatario_raw.strip()
    dados_extra = dict(processo.dados_extra or {})
    if not dados_extra.get("responsavel_adm_inicial") and processo.responsavel_adm:
        dados_extra["responsavel_adm_inicial"] = processo.responsavel_adm
        processo.dados_extra = dados_extra

    def _nome_usuario(usuario: Optional[Usuario]) -> str:
        if not usuario:
            return "usuario"
        return usuario.nome or usuario.username or "usuario"

    gerencia_processo = normalizar_gerencia(processo.gerencia, permitir_entrada=True)

    if acao == "assumir":
        if (
            processo.assigned_to
            and processo.assigned_to_id != current_user.id
            and not usuario_tem_acesso_total()
        ):
            flash("Processo ja esta atribuido a outro usuario.", "warning")
        elif not usuario_tem_liberacao_gerencia(gerencia_processo, usuario=current_user):
            flash(
                "Voce so pode assumir demandas da sua propria gerencia.",
                "warning",
            )
        elif not usuario_permitido_para_atribuicao(current_user, processo):
            flash(
                "A atribuicao so pode ser feita para usuario da mesma coordenadoria ou equipe do processo.",
                "warning",
            )
        else:
            nome_destino = _nome_usuario(current_user)
            processo.assigned_to = current_user
            processo.responsavel_equipe = nome_destino
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia=processo.gerencia,
                    para_gerencia=processo.gerencia,
                    motivo=f'Processo atribuido por "{current_user.username}" para "{nome_destino}".',
                    usuario=current_user.username,
                    tipo="atribuicao",
                )
            )
            flash("Processo atribuido ao seu usuario.", "success")
    elif acao == "atribuir":
        if not destinatario_id and not destinatario_nome:
            flash("Selecione um usuario ou responsavel da lista.", "warning")
            return redirect(url_for("gerencia", nome_gerencia=destino))
        if destinatario_id:
            destinatario = db.session.get(Usuario, destinatario_id)
            if not destinatario:
                flash("Usuario destinatario nao encontrado.", "danger")
                return redirect(url_for("gerencia", nome_gerencia=destino))
            if not usuario_tem_liberacao_gerencia(gerencia_processo, usuario=destinatario):
                flash(
                    "A atribuicao so pode ser feita para usuario da mesma gerencia da demanda.",
                    "warning",
                )
                return redirect(url_for("gerencia", nome_gerencia=destino))
            if not usuario_permitido_para_atribuicao(destinatario, processo):
                flash(
                    "A atribuicao so pode ser feita para usuario da mesma coordenadoria ou equipe do processo.",
                    "warning",
                )
                return redirect(url_for("gerencia", nome_gerencia=destino))
            processo.assigned_to = destinatario
            nome_origem = _nome_usuario(current_user)
            nome_destino = _nome_usuario(destinatario)
            processo.responsavel_equipe = nome_destino
            if destinatario.id != current_user.id:
                registrar_notificacao(
                    destinatario,
                    f"{nome_origem} atribuiu o processo {processo.numero_sei_base} para voce.",
                    processo,
                )
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia=processo.gerencia,
                    para_gerencia=processo.gerencia,
                    motivo=f'Processo atribuido por "{current_user.username}" para "{nome_destino}".',
                    usuario=current_user.username,
                    tipo="atribuicao",
                )
            )
            flash("Processo atribuido para o usuario selecionado.", "success")
        else:
            candidato_usuario = localizar_usuario_por_texto(
                destinatario_nome, gerencia=gerencia_processo
            )
            if candidato_usuario:
                if not usuario_tem_liberacao_gerencia(
                    gerencia_processo, usuario=candidato_usuario
                ):
                    flash(
                        "O nome selecionado corresponde a um usuario sem liberacao para esta gerencia.",
                        "warning",
                    )
                    return redirect(url_for("gerencia", nome_gerencia=destino))
                if not usuario_permitido_para_atribuicao(candidato_usuario, processo):
                    flash(
                        "O nome selecionado corresponde a um usuario, mas fora da coordenadoria/equipe permitida.",
                        "warning",
                    )
                    return redirect(url_for("gerencia", nome_gerencia=destino))
                processo.assigned_to = candidato_usuario
                nome_origem = _nome_usuario(current_user)
                nome_destino = _nome_usuario(candidato_usuario)
                processo.responsavel_equipe = nome_destino
                if candidato_usuario.id != current_user.id:
                    registrar_notificacao(
                        candidato_usuario,
                        f"{nome_origem} atribuiu o processo {processo.numero_sei_base} para voce.",
                        processo,
                    )
                db.session.add(
                    Movimentacao(
                        processo=processo,
                        de_gerencia=processo.gerencia,
                        para_gerencia=processo.gerencia,
                        motivo=f'Processo atribuido por "{current_user.username}" para "{nome_destino}".',
                        usuario=current_user.username,
                        tipo="atribuicao",
                    )
                )
                flash(
                    f"O nome selecionado foi vinculado automaticamente ao usuario {nome_destino}.",
                    "success",
                )
                db.session.commit()
                return redirect(url_for("gerencia", nome_gerencia=destino))
            if not responsavel_em_lista(destinatario_nome, processo):
                flash("Selecione um responsavel valido da lista.", "warning")
                return redirect(url_for("gerencia", nome_gerencia=destino))
            nome_origem = _nome_usuario(current_user)
            processo.assigned_to = None
            processo.responsavel_equipe = destinatario_nome
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia=processo.gerencia,
                    para_gerencia=processo.gerencia,
                    motivo=f'Processo atribuido por "{nome_origem}" para "{destinatario_nome}".',
                    usuario=current_user.username,
                    tipo="atribuicao",
                )
            )
            flash("Processo atribuido para o responsavel selecionado.", "success")
    elif acao == "liberar":
        if processo.assigned_to_id in {None}:
            flash("Processo ja estava sem responsavel.", "info")
        elif processo.assigned_to_id == current_user.id or usuario_tem_acesso_total():
            nome_liberado = (
                processo.assigned_to.nome or processo.assigned_to.username
                if processo.assigned_to
                else "usuario"
            )
            processo.assigned_to = None
            processo.responsavel_equipe = None
            responsavel_inicial = (
                (processo.dados_extra or {}).get("responsavel_adm_inicial")
                if isinstance(processo.dados_extra, dict)
                else None
            )
            if responsavel_inicial:
                processo.responsavel_adm = responsavel_inicial
            db.session.add(
                Movimentacao(
                    processo=processo,
                    de_gerencia=processo.gerencia,
                    para_gerencia=processo.gerencia,
                    motivo=f'Processo liberado por "{current_user.username}" (antes atribuido para "{nome_liberado}").',
                    usuario=current_user.username,
                    tipo="atribuicao",
                )
            )
            flash("Processo liberado com sucesso.", "info")
        else:
            flash("Voce nao pode liberar um processo atribuido a outra pessoa.", "warning")
    else:
        flash("Acao desconhecida para atribuicao.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=destino))

    db.session.commit()
    return redirect(url_for("gerencia", nome_gerencia=destino))


@app.route("/notificacoes", methods=["POST"])
@login_required
def gerenciar_notificacoes():
    """Marca notificacoes como lidas ou remove alertas."""
    acao = request.form.get("acao", "marcar_todas")
    notif_id = request.form.get("id", type=int)

    if acao == "marcar" and notif_id:
        notif = Notificacao.query.filter_by(id=notif_id, user_id=current_user.id).first()
        if notif:
            notif.lida = True
            db.session.commit()
            flash("Notificacao marcada como lida.", "info")
    elif acao == "marcar_todas":
        Notificacao.query.filter_by(user_id=current_user.id, lida=False).update({Notificacao.lida: True})
        db.session.commit()
        flash("Notificacoes atualizadas.", "info")
    else:
        flash("Acao de notificacao desconhecida.", "warning")
    return redirect(request.referrer or url_for("index"))


def _resumo_processo_assistente(processo: Processo) -> str:
    """Monta um resumo curto para o assistente responder."""
    partes = [
        f"Numero SEI: {processo.numero_sei_base}",
        f"Gerencia: {processo.gerencia}",
    ]
    if processo.assigned_to:
        partes.append(f"Atribuido para: {processo.assigned_to.nome or processo.assigned_to.username}")
    if processo.status:
        partes.append(f"Status: {processo.status}")
    if processo.prazo_equipe:
        partes.append(f"Prazo: {processo.prazo_equipe.strftime('%d/%m/%Y')}")
    if processo.data_entrada:
        partes.append(f"Entrada: {processo.data_entrada.strftime('%d/%m/%Y')}")
    if processo.finalizado_em:
        partes.append(f"Finalizado em: {processo.finalizado_em.strftime('%d/%m/%Y %H:%M')}")
    historico = sorted(processo.movimentacoes, key=lambda m: m.criado_em or datetime.min, reverse=True)[:2]
    if historico:
        partes.append("Ultimos movimentos:")
        for mov in historico:
            partes.append(
                f"- {mov.de_gerencia} -> {mov.para_gerencia} em "
                f"{mov.criado_em.strftime('%d/%m/%Y %H:%M') if mov.criado_em else '-'}"
            )
    return "; ".join(partes)


def _normalizar_texto_assistente(texto: str) -> str:
    """Normaliza texto para heuristica simples do assistente."""
    return (
        unicodedata.normalize("NFKD", texto or "")
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )


def _extrair_periodo_assistente(pergunta: str) -> Dict[str, Optional[datetime]]:
    """Extrai periodo simples a partir da pergunta (ultima semana/mes/ano, etc.)."""
    texto = _normalizar_texto_assistente(pergunta)
    agora = datetime.utcnow()
    inicio = None
    fim = None
    legenda = ""

    if "hoje" in texto:
        inicio = datetime.combine(agora.date(), datetime.min.time())
        fim = agora
        legenda = "hoje"
        return {"inicio": inicio, "fim": fim, "legenda": legenda}

    match = re.search(r"ultim[oa]s?\s+(\d+)\s+dias", texto)
    if match:
        dias = int(match.group(1))
        inicio = agora - timedelta(days=max(dias, 1))
        fim = agora
        legenda = f"nos ultimos {dias} dias"
        return {"inicio": inicio, "fim": fim, "legenda": legenda}

    match = re.search(r"ultim[oa]s?\s+(\d+)\s+seman", texto)
    if match:
        semanas = int(match.group(1))
        inicio = agora - timedelta(days=max(semanas, 1) * 7)
        fim = agora
        legenda = f"nas ultimas {semanas} semanas"
        return {"inicio": inicio, "fim": fim, "legenda": legenda}

    match = re.search(r"ultim[oa]s?\s+(\d+)\s+mes", texto)
    if match:
        meses = int(match.group(1))
        inicio = agora - timedelta(days=max(meses, 1) * 30)
        fim = agora
        legenda = f"nos ultimos {meses} meses"
        return {"inicio": inicio, "fim": fim, "legenda": legenda}

    match = re.search(r"ultim[oa]s?\s+(\d+)\s+ano", texto)
    if match:
        anos = int(match.group(1))
        inicio = agora - timedelta(days=max(anos, 1) * 365)
        fim = agora
        legenda = f"nos ultimos {anos} anos"
        return {"inicio": inicio, "fim": fim, "legenda": legenda}

    if "ultima semana" in texto or "ultimo semana" in texto:
        inicio = agora - timedelta(days=7)
        fim = agora
        legenda = "na ultima semana"
    elif "ultimo mes" in texto:
        inicio = agora - timedelta(days=30)
        fim = agora
        legenda = "no ultimo mes"
    elif "ultimo ano" in texto:
        inicio = agora - timedelta(days=365)
        fim = agora
        legenda = "no ultimo ano"
    elif "este mes" in texto:
        inicio = datetime(agora.year, agora.month, 1)
        fim = agora
        legenda = "neste mes"
    elif "mes passado" in texto:
        primeiro_mes_atual = datetime(agora.year, agora.month, 1)
        ano = agora.year if agora.month > 1 else agora.year - 1
        mes = agora.month - 1 if agora.month > 1 else 12
        inicio = datetime(ano, mes, 1)
        fim = primeiro_mes_atual - timedelta(seconds=1)
        legenda = "no mes passado"
    elif "este ano" in texto:
        inicio = datetime(agora.year, 1, 1)
        fim = agora
        legenda = "neste ano"
    elif "ano passado" in texto:
        inicio = datetime(agora.year - 1, 1, 1)
        fim = datetime(agora.year, 1, 1) - timedelta(seconds=1)
        legenda = "no ano passado"

    return {"inicio": inicio, "fim": fim, "legenda": legenda}


def _extrair_gerencia_assistente(pergunta: str) -> Optional[str]:
    """Extrai uma gerencia mencionada na pergunta."""
    texto = _normalizar_texto_assistente(pergunta).upper()
    for ger in GERENCIAS_DESTINOS + ["GABINETE", "SAIDA"]:
        if ger in texto:
            return ger
    return None


def _extrair_nome_usuario_assistente(pergunta: str) -> Optional[str]:
    """Extrai nome de usuario a partir de expressoes como 'pelo fulano'."""
    texto = _normalizar_texto_assistente(pergunta)
    tokens = texto.split()
    stop = {
        "no",
        "na",
        "nos",
        "nas",
        "em",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "para",
        "por",
        "pelo",
        "pela",
        "ultimo",
        "ultima",
        "ultimos",
        "ultimas",
        "mes",
        "meses",
        "ano",
        "anos",
        "semana",
        "semanas",
        "dia",
        "dias",
        "gerencia",
        "processo",
        "processos",
        "cadastrados",
        "cadastrado",
        "finalizados",
        "finalizado",
    }
    for i, tok in enumerate(tokens):
        if tok in {"por", "pelo", "pela"}:
            nome_tokens = []
            for proximo in tokens[i + 1 :]:
                if proximo in stop:
                    break
                nome_tokens.append(proximo)
                if len(nome_tokens) >= 3:
                    break
            if nome_tokens:
                return " ".join(nome_tokens)
    return None


def _buscar_usuario_assistente(nome: str) -> Optional[Usuario]:
    """Busca usuario por nome ou username aproximado."""
    if not nome:
        return None
    alvo = _normalizar_texto_assistente(nome)
    if not alvo:
        return None
    usuarios = Usuario.query.order_by(Usuario.nome.asc()).all()
    for usuario in usuarios:
        if alvo == _normalizar_texto_assistente(usuario.username):
            return usuario
        if alvo == _normalizar_texto_assistente(usuario.nome):
            return usuario
    for usuario in usuarios:
        if alvo in _normalizar_texto_assistente(usuario.username):
            return usuario
        if alvo in _normalizar_texto_assistente(usuario.nome):
            return usuario
    return None


def _pergunta_parece_ajuda_site(pergunta: str) -> bool:
    """Indica se a pergunta parece ser sobre uso do site."""
    texto = _normalizar_texto_assistente(pergunta)
    if not texto:
        return False
    gatilhos = [
        "como ",
        "onde ",
        "qual menu",
        "qual botao",
        "o que e",
        "para que serve",
        "passo a passo",
        "ajuda",
        "funciona",
        "como usar",
        "como acessar",
        "como entrar",
    ]
    if any(gatilho in texto for gatilho in gatilhos):
        return True
    termos_site = [
        "login",
        "senha",
        "usuario",
        "permiss",
        "perfil",
        "novo processo",
        "cadastrar",
        "criar processo",
        "editar",
        "visualizar",
        "atribuir",
        "reatribuir",
        "desatribuir",
        "finalizar",
        "devolver",
        "reenviar",
        "exportar",
        "importar",
        "historico",
        "verificar dados",
        "dashboard",
        "inicio",
        "gerencia",
        "campos extras",
        "campo extra",
        "filtro",
        "buscar",
        "pesquisar",
        "assistente",
        "meus processos",
        "tela",
        "pagina",
        "botao",
        "menu",
        "card",
        "metricas",
        "tempo medio",
    ]
    return any(termo in texto for termo in termos_site)


def _montar_passos_confirmacao(titulo: str, filtros: List[str]) -> str:
    """Monta orientacao curta para confirmar no painel."""
    passos = [
        "1) Va em Inicio e clique em Exportar Excel.",
        "2) Selecione o escopo e as colunas necessarias.",
        "3) Abra no Excel e aplique os filtros desejados.",
    ]
    if filtros:
        passos.insert(2, f"2) Marque colunas que permitam filtrar por: {', '.join(filtros)}.")
    return f" Para confirmar com mais detalhes, siga: {' '.join(passos)}"


def _responder_pergunta_geral_assistente(pergunta: str) -> Optional[str]:
    """Responde perguntas gerais com contagens simples."""
    texto = _normalizar_texto_assistente(pergunta)
    if not texto:
        return None
    if "tempo medio" in texto:
        metricas = obter_metricas_processos()
        tempo_medio_dias = metricas.get("tempo_medio_dias")
        if tempo_medio_dias is None:
            return "Nao ha dados suficientes para calcular o tempo medio agora."
        return f"Tempo medio geral: {tempo_medio_dias:.1f} dia(s)."
    if not any(chave in texto for chave in ["quantos", "quantidade", "total"]):
        return None

    periodo = _extrair_periodo_assistente(pergunta)
    inicio = periodo.get("inicio")
    fim = periodo.get("fim")
    legenda_periodo = periodo.get("legenda")
    gerencia = _extrair_gerencia_assistente(pergunta)
    nome_usuario = _extrair_nome_usuario_assistente(pergunta)
    usuario = _buscar_usuario_assistente(nome_usuario) if nome_usuario else None

    def _label_periodo():
        return f" {legenda_periodo}" if legenda_periodo else ""

    if "cadastr" in texto or "registr" in texto:
        if nome_usuario and not usuario:
            return (
                f"Nao encontrei o usuario '{nome_usuario}'. Informe o nome ou username exato."
            )
        consulta = Movimentacao.query.filter(Movimentacao.tipo == "cadastro")
        if usuario:
            consulta = consulta.filter(
                func.lower(Movimentacao.usuario) == usuario.username.lower()
            )
        if gerencia:
            consulta = consulta.filter(Movimentacao.para_gerencia == gerencia)
        if inicio:
            consulta = consulta.filter(Movimentacao.criado_em >= inicio)
        if fim:
            consulta = consulta.filter(Movimentacao.criado_em <= fim)
        total = (
            consulta.with_entities(func.count(func.distinct(Movimentacao.processo_id)))
            .scalar()
            or 0
        )
        partes = [f"Encontrei {total} processo(s) cadastrados"]
        if usuario:
            partes.append(f"por {usuario.nome or usuario.username}")
        if gerencia:
            partes.append(f"na gerencia {gerencia}")
        partes.append(_label_periodo())
        filtros = ["Data de entrada", "Responsavel Adm", "Gerencia"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "cadastros", filtros
        )

    if "finaliz" in texto:
        consulta = Processo.query.filter(Processo.finalizado_em.isnot(None))
        if gerencia:
            consulta = consulta.filter(Processo.gerencia == gerencia)
        if inicio:
            consulta = consulta.filter(Processo.finalizado_em >= inicio)
        if fim:
            consulta = consulta.filter(Processo.finalizado_em <= fim)
        total = consulta.count()
        partes = [f"Encontrei {total} processo(s) finalizados"]
        if gerencia:
            partes.append(f"na gerencia {gerencia}")
        partes.append(_label_periodo())
        filtros = ["Finalizado em", "Gerencia"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "finalizados", filtros
        )

    if "sistema" in texto or "site" in texto or "base" in texto or "banco" in texto:
        consulta = Processo.query
        if inicio:
            consulta = consulta.filter(Processo.criado_em >= inicio)
        if fim:
            consulta = consulta.filter(Processo.criado_em <= fim)
        total = consulta.count()
        partes = [f"Encontrei {total} processo(s) no sistema"]
        partes.append(_label_periodo())
        filtros = ["Data de cadastro"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "processos", filtros
        )

    if "passou por" in texto or "passaram por" in texto:
        if not gerencia:
            return (
                "Qual gerencia voce quer analisar? Exemplos: GABINETE, GEPLAN, GEENG."
            )
        consulta = Movimentacao.query.filter(
            or_(
                Movimentacao.de_gerencia == gerencia,
                Movimentacao.para_gerencia == gerencia,
            )
        )
        if inicio:
            consulta = consulta.filter(Movimentacao.criado_em >= inicio)
        if fim:
            consulta = consulta.filter(Movimentacao.criado_em <= fim)
        total = (
            consulta.with_entities(func.count(func.distinct(Movimentacao.processo_id)))
            .scalar()
            or 0
        )
        partes = [f"Encontrei {total} processo(s) que passaram por {gerencia}"]
        partes.append(_label_periodo())
        filtros = ["Gerencia", "Data de entrada"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "movimentacoes", filtros
        )

    if any(
        chave in texto
        for chave in [
            "ativo",
            "ativos",
            "em andamento",
            "em aberto",
            "aberto",
            "abertos",
            "caixa",
            "fila",
            "pendente",
            "pendentes",
        ]
    ):
        consulta = Processo.query.filter(Processo.finalizado_em.is_(None))
        if gerencia:
            consulta = consulta.filter(Processo.gerencia == gerencia)
        if inicio:
            consulta = consulta.filter(Processo.data_entrada >= inicio.date())
        if fim:
            consulta = consulta.filter(Processo.data_entrada <= fim.date())
        total = consulta.count()
        partes = [f"Encontrei {total} processo(s) ativos"]
        if gerencia:
            partes.append(f"na gerencia {gerencia}")
        partes.append(_label_periodo())
        filtros = ["Gerencia", "Data de entrada"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "ativos", filtros
        )

    if gerencia:
        consulta = Processo.query.filter(Processo.gerencia == gerencia)
        if inicio:
            consulta = consulta.filter(Processo.data_entrada >= inicio.date())
        if fim:
            consulta = consulta.filter(Processo.data_entrada <= fim.date())
        total = consulta.count()
        partes = [f"Encontrei {total} processo(s) na gerencia {gerencia}"]
        partes.append(_label_periodo())
        filtros = ["Gerencia", "Data de entrada"]
        return " ".join([p for p in partes if p]).strip() + "." + _montar_passos_confirmacao(
            "gerencia", filtros
        )

    return None


def _responder_pergunta_site_assistente(pergunta: str) -> Optional[str]:
    """Responde perguntas sobre uso do site e funcionalidades."""
    texto = _normalizar_texto_assistente(pergunta)
    if not texto:
        return None

    def tem(*termos: str) -> bool:
        return any(termo in texto for termo in termos)

    if tem("senha", "trocar senha", "redefinir", "resetar", "mudar senha"):
        return (
            "Use a opcao 'Trocar senha' no menu do usuario. "
            "No primeiro acesso o sistema pede uma senha definitiva."
        )

    if tem("editar perfil", "meu perfil", "atualizar perfil"):
        return (
            "Use a opcao 'Editar perfil' no menu do usuario para atualizar nome, email e equipe."
        )

    if tem("cadastrar usuario", "cadastro usuario", "novo usuario", "criar usuario"):
        return (
            "Assessoria, gerentes e o administrador principal podem cadastrar usuarios. "
            "No menu do usuario, clique em 'Cadastrar usuario' e informe os dados e permissoes."
        )

    if tem("permiss", "perfil"):
        return (
            "Perfis disponiveis: Usuario, Gerente e Assessoria. "
            "Acesso total e um perfil especial com acesso geral (configuracao separada). "
            "Permissoes extras incluem cadastrar processo, exportar e importar planilhas."
        )

    if tem("login", "entrar", "acesso"):
        return (
            "Para entrar, use a tela de Login (/login) com usuario ou email e senha."
        )

    if tem("novo processo", "cadastrar processo", "criar processo", "registrar processo"):
        return (
            "No painel Inicio, clique em 'Novo processo', preencha o formulario e salve. "
            "Se o botao nao aparecer, seu perfil pode nao ter permissao."
        )

    if tem("editar", "visualizar", "ficha tecnica", "detalhe", "detalhes"):
        return (
            "No painel da gerencia, localize o processo e use o icone 'Editar' (lapis). "
            "Para apenas visualizar, use o icone de visualizacao/ficha tecnica."
        )

    if tem("atribuir", "reatribuir", "desatribuir") or (
        "responsavel" in texto and tem("como", "mudar", "alterar")
    ):
        return (
            "No painel da gerencia, clique no botao 'Atribuir' do processo, "
            "escolha o usuario e confirme. Para remover, use 'Desatribuir'."
        )

    if tem("finalizar", "encerrar", "concluir"):
        return (
            "No painel da gerencia, use o icone 'Finalizar' do processo "
            "ou abra o processo e finalize na secao de finalizacao."
        )

    if tem("devolver", "devolvido", "reenviar"):
        return (
            "Use o icone 'Devolver' no painel da gerencia. "
            "Processos devolvidos aparecem em 'Processos Devolvidos'. "
            "Para reenviar, abra o processo devolvido e use 'Reenviar'."
        )

    if tem("importar") and tem("exportar"):
        return (
            "No Inicio ha os botoes 'Importar Excel' e 'Exportar Excel' para entrada e saida de planilhas."
        )

    if tem("importar", "importacao", "planilha"):
        return (
            "No painel Inicio, clique em 'Importar Excel' e envie a planilha."
        )

    if tem("exportar", "exportacao", "relatorio", "excel"):
        return (
            "No painel Inicio, clique em 'Exportar Excel' para exportacao geral. "
            "Dentro de uma gerencia, use 'Exportar Excel' do painel da gerencia."
        )

    if tem("historico", "verificar dados"):
        return (
            "No topo do painel, clique em 'Historico de Processos' para ver processos finalizados, "
            "demandas e filtros."
        )

    if tem("meus processos"):
        return (
            "No topo do painel, use o menu 'Meus Processos' para ver processos atribuidos a voce."
        )

    if tem("campos extras", "campo extra", "configurar campos"):
        return (
            "No painel da gerencia, use 'Configurar campos extras' para cadastrar campos personalizados."
        )

    if tem("filtro", "buscar", "pesquisar", "sei"):
        return (
            "Nos paineis ha campos de busca e filtros por SEI, gerencia, coordenadoria, equipe, "
            "responsavel e status. Preencha os campos e aplique."
        )

    if tem("gerencia", "gerencias", "painel de processos", "acessar gerencia"):
        return (
            "Na pagina Inicio, os cards das gerencias permitem clicar em 'Acessar' para abrir o painel."
        )

    if tem("dashboard", "inicio", "metricas", "tempo medio", "andamento", "finalizados"):
        return (
            "No Inicio (Dashboard) voce ve metricas de andamento, finalizados e tempo medio. "
            "Os cards sao clicaveis para filtrar a lista."
        )

    if tem("assistente", "chat"):
        return (
            "O assistente responde perguntas sobre processos e sobre o sistema. "
            "Digite sua pergunta e, se for um processo especifico, informe o numero SEI."
        )

    if tem("ajuda", "duvida", "duvidas", "manual"):
        return (
            "Posso ajudar com cadastro, edicao, atribuicao, finalizacao, devolucao, "
            "exportacao/importacao, historico, usuarios, permissoes e filtros."
        )

    if tem("o que e", "para que serve", "como funciona", "sobre o sistema", "sobre o site"):
        return (
            "O Controle de Processos organiza e acompanha processos por gerencia, prazos, "
            "responsaveis e historico."
        )

    return None


def _pergunta_exige_numero(pergunta: str) -> bool:
    """Indica se a pergunta parece ser sobre um processo especifico."""
    texto = _normalizar_texto_assistente(pergunta)
    if not texto:
        return False
    if _pergunta_parece_ajuda_site(pergunta):
        return False
    padroes_gerais = [
        r"\bquantos?\b",
        r"\bquantidade\b",
        r"\btotal\b",
        r"\bpor\s+gerencia\b",
        r"\bpor\s+equipe\b",
        r"\bpor\s+coordenadoria\b",
        r"\bpor\s+area\b",
        r"\bpor\s+assunto\b",
        r"\bpor\s+status\b",
        r"\bprocessos\b",
        r"\bgerencias\b",
        r"\bmedia\b",
        r"\btempo\s+medio\b",
        r"\branking\b",
        r"\blist(ar|a|agem)?\b",
        r"\bestat\b",
    ]
    if any(re.search(padrao, texto) for padrao in padroes_gerais):
        return False
    padroes_especificos = [
        r"\bprocesso\b",
        r"\bsei\b",
        r"\bnumero\b",
        r"\bprazo\b",
        r"\bresponsavel\b",
        r"\batribu",
        r"\bstatus\b",
        r"\bassunto\b",
        r"\bfinaliz",
        r"\bmoviment",
        r"\bhistoric",
        r"\bentrada\b",
        r"\bconcessionaria\b",
        r"\binteressado\b",
    ]
    return any(re.search(padrao, texto) for padrao in padroes_especificos)


def _gerar_resposta_assistente(pergunta: str, processo: Optional[Processo]) -> str:
    """Gera uma resposta simples baseada nos dados locais do processo."""
    if not processo:
        return "Nao encontrei um processo com essas informacoes. Informe o numero SEI completo para uma resposta precisa."
    resumo = _resumo_processo_assistente(processo)
    texto = _normalizar_texto_assistente(pergunta)
    if not texto:
        return resumo

    def _fmt_data(valor):
        if not valor:
            return None
        if isinstance(valor, datetime):
            return valor.strftime("%d/%m/%Y %H:%M")
        return valor.strftime("%d/%m/%Y")

    if "prazo" in texto:
        prazo = processo.prazo_equipe or processo.prazo
        if prazo:
            rotulo = "Prazo da equipe" if processo.prazo_equipe else "Prazo"
            return (
                f"{rotulo}: {_fmt_data(prazo)}. "
                f"Status atual: {processo.status or 'sem status'}. {resumo}"
            )
        return f"O processo nao tem prazo cadastrado. {resumo}"

    if "status" in texto:
        status = processo.status or "sem status"
        data_status = _fmt_data(processo.data_status)
        if data_status:
            return f"Status: {status} (desde {data_status}). {resumo}"
        return f"Status: {status}. {resumo}"

    if "finalizado por" in texto or "quem finalizou" in texto:
        if processo.finalizado_por:
            return f"Finalizado por: {processo.finalizado_por}. {resumo}"
        if processo.finalizado_em:
            return f"O processo foi finalizado em {_fmt_data(processo.finalizado_em)}. {resumo}"
        return f"O processo ainda nao foi finalizado. {resumo}"

    if "finaliz" in texto:
        if processo.finalizado_em:
            return f"O processo foi finalizado em {_fmt_data(processo.finalizado_em)}. {resumo}"
        return f"O processo ainda nao foi finalizado. {resumo}"

    if "assunto" in texto:
        return f"O assunto e: {processo.assunto}. {resumo}"

    if "interessad" in texto:
        return f"Interessado: {processo.interessado}. {resumo}"

    if "concessionaria" in texto:
        valor = processo.concessionaria or "nao informada"
        return f"Concessionaria: {valor}. {resumo}"

    if "classific" in texto:
        valor = processo.classificacao_institucional or processo.descricao or "nao informada"
        return f"Classificacao institucional: {valor}. {resumo}"

    if "descricao melhorada" in texto:
        valor = processo.descricao_melhorada or processo.descricao or "nao informada"
        return f"Descricao melhorada: {valor}. {resumo}"

    if "descricao" in texto:
        valor = processo.descricao or "nao informada"
        return f"Descricao: {valor}. {resumo}"

    if "observacao" in texto or "observacoes" in texto:
        valor = processo.observacao or processo.observacoes_complementares or "nao informada"
        return f"Observacoes: {valor}. {resumo}"

    if "responsavel" in texto and ("adm" in texto or "administr" in texto):
        valor = processo.responsavel_adm or "nao informado"
        return f"Responsavel adm: {valor}. {resumo}"

    if "responsavel" in texto and ("equipe" in texto or "area" in texto or "coorden" in texto):
        valor = processo.responsavel_equipe or "nao informado"
        return f"Responsavel da equipe: {valor}. {resumo}"

    if "atribu" in texto or "responsavel" in texto:
        if processo.assigned_to:
            return (
                f"O processo esta atribuido para {processo.assigned_to.nome or processo.assigned_to.username}. "
                f"{resumo}"
            )
        if processo.responsavel_equipe:
            return f"Responsavel da equipe: {processo.responsavel_equipe}. {resumo}"
        return f"O processo nao esta atribuido. {resumo}"

    if "area" in texto or "coorden" in texto or "equipe" in texto:
        partes = []
        if processo.coordenadoria:
            partes.append(f"Coordenadoria: {processo.coordenadoria}")
        if processo.equipe_area:
            partes.append(f"Equipe/Area: {processo.equipe_area}")
        if processo.responsavel_equipe:
            partes.append(f"Responsavel da equipe: {processo.responsavel_equipe}")
        if not partes:
            partes.append("Nenhuma area ou coordenadoria cadastrada.")
        return " ".join(partes) + f" {resumo}"

    if "data entrada" in texto or "entrada" in texto:
        valor = _fmt_data(processo.data_entrada)
        if valor:
            return f"Entrada: {valor}. {resumo}"
        return f"Data de entrada nao informada. {resumo}"

    if "tipo" in texto and "processo" in texto:
        valor = processo.tipo_processo or "nao informado"
        return f"Tipo de processo: {valor}. {resumo}"

    if "palavra" in texto:
        valor = processo.palavras_chave or "nao informadas"
        return f"Palavras-chave: {valor}. {resumo}"

    if "tramitado" in texto:
        valor = processo.tramitado_para or "nao informado"
        return f"Tramitado para: {valor}. {resumo}"

    if "data saida" in texto or "saida" in texto:
        valor = _fmt_data(processo.data_saida)
        if valor:
            return f"Data de saida: {valor}. {resumo}"
        return f"Data de saida nao informada. {resumo}"

    if "campo extra" in texto or "campos extras" in texto or "dados extra" in texto:
        extras = processo.dados_extra or {}
        extras = {
            str(chave): valor
            for chave, valor in extras.items()
            if chave and valor and chave != "numero_sei_original"
        }
        if not extras:
            return f"Nao ha campos extras cadastrados. {resumo}"
        pares = [f"{chave}: {valor}" for chave, valor in extras.items()]
        return "Campos extras: " + "; ".join(pares) + f". {resumo}"

    if "moviment" in texto or "historico" in texto:
        return resumo

    if "parad" in texto or "tempo parado" in texto or "ha quanto tempo" in texto:
        referencias = [m.criado_em for m in processo.movimentacoes if m.criado_em]
        base_data = None
        if referencias:
            base_data = max(referencias)
        elif processo.atualizado_em:
            base_data = processo.atualizado_em
        elif processo.data_entrada:
            base_data = datetime.combine(processo.data_entrada, datetime.min.time())
        if base_data:
            dias = (datetime.utcnow().date() - base_data.date()).days
            return (
                f"O processo esta parado ha cerca de {dias} dia(s) (ultima movimentacao em "
                f"{_fmt_data(base_data)}). {resumo}"
            )
        return f"Nao foi possivel calcular o tempo parado. {resumo}"

    return resumo


@app.route("/assistente/responder", methods=["POST"])
@login_required
def assistente_responder():
    """Responde perguntas rápidas sobre processos usando os dados locais."""
    data = request.get_json(silent=True) or request.form
    pergunta = (data.get("pergunta") or "").strip()
    numero = (data.get("numero") or "").strip()
    processo_id = data.get("processo_id")
    processo = None
    exige_numero = _pergunta_exige_numero(pergunta)

    if exige_numero and not (numero or processo_id):
        return jsonify(
            {
                "resposta": "Para perguntas sobre um processo especifico, informe o numero SEI.",
                "referencia": None,
                "gerencia": None,
            }
        )

    if processo_id:
        try:
            processo = Processo.query.get(int(processo_id))
        except Exception:
            processo = None

    if not processo and numero:
        processo = (
            Processo.query.filter(func.lower(Processo.numero_sei) == numero.lower())
            .order_by(Processo.atualizado_em.desc())
            .first()
        )
        if not processo:
            processo = (
                Processo.query.filter(Processo.numero_sei.ilike(f"%{numero}%"))
                .order_by(Processo.atualizado_em.desc())
                .first()
            )

    if not processo:
        if exige_numero:
            return jsonify(
                {
                    "resposta": "Nao encontrei um processo com esse numero SEI. Verifique e tente novamente.",
                    "referencia": None,
                    "gerencia": None,
                }
            )
        resposta_geral = _responder_pergunta_geral_assistente(pergunta)
        if resposta_geral:
            return jsonify(
                {
                    "resposta": resposta_geral,
                    "referencia": None,
                    "gerencia": None,
                }
            )
        resposta_site = _responder_pergunta_site_assistente(pergunta)
        if resposta_site:
            return jsonify(
                {
                    "resposta": resposta_site,
                    "referencia": None,
                    "gerencia": None,
                }
            )
        return jsonify(
            {
                "resposta": "Nao consegui entender. Posso ajudar com processos (com numero SEI), contagens gerais e uso do site (cadastro, edicao, atribuicao, finalizacao, devolucao, exportacao/importacao, historico, usuarios e permissoes).",
                "referencia": None,
                "gerencia": None,
            }
        )

    resposta = _gerar_resposta_assistente(pergunta, processo)
    return jsonify(
        {
            "resposta": resposta,
            "referencia": processo.numero_sei if processo else None,
            "gerencia": processo.gerencia if processo else None,
        }
    )


@app.route("/processo/<int:processo_id>/campos-extra", methods=["POST"])
@login_required
def salvar_campos_extra(processo_id: int):
    """Armazena valores dos campos personalizados de uma gerencia."""
    processo = Processo.query.get_or_404(processo_id)
    if not usuario_pode_editar_processo(processo):
        flash("Sem permissao para editar este processo.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))
    if SITE_EM_CONFIGURACAO:
        flash("Campos extras estao indisponiveis durante a configuracao.", "info")
        return redirect(url_for("index"))

    campos_def = listar_campos_gerencia(processo.gerencia)
    if not campos_def:
        flash("Nenhum campo extra configurado para esta gerencia.", "warning")
        return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))

    valores = coletar_dados_extra_form(processo.gerencia, request.form)
    dados = processo.dados_extra or {}
    definidos = {campo.slug for campo in campos_def}

    # Atualiza e limpa chaves conforme formulario
    for slug in definidos:
        if slug in valores:
            dados[slug] = valores[slug]
        else:
            dados.pop(slug, None)

    processo.dados_extra = dados
    processo.atualizado_em = datetime.utcnow()
    db.session.commit()
    flash("Campos extras atualizados.", "success")
    return redirect(url_for("gerencia", nome_gerencia=processo.gerencia))


# === Bootstrap e entrypoints ===
_APP_INICIALIZADO = False


def preparar_app() -> Flask:
    """Executa rotinas de inicializacao apenas uma vez por processo."""
    global _APP_INICIALIZADO
    if _APP_INICIALIZADO:
        return app

    with app.app_context():
        inicializar()
    _APP_INICIALIZADO = True
    return app


def _executar_inicializacao():
    """Prepara banco e dados base quando o servidor inicia via flask run."""
    preparar_app()


if hasattr(app, "before_first_request"):
    app.before_first_request(_executar_inicializacao)
else:

    @app.before_request
    def _executar_inicializacao_compat():
        """Fallback para garantir inicializacao em versoes sem before_first_request."""
        if not _APP_INICIALIZADO:
            preparar_app()


def create_app() -> Flask:
    """Entry point utilizado por `flask --app app:create_app run`."""
    return preparar_app()


# Garante inicializacao imediata ao importar o modulo (evita erro de tabela inexistente no 1o request)
preparar_app()


def main():
    """Permite rodar a aplicacao diretamente com `python app.py`."""
    flask_app = preparar_app()
    host = os.environ.get("FLASK_RUN_HOST") or os.environ.get("HOST") or "0.0.0.0"
    port = int(os.environ.get("FLASK_RUN_PORT") or os.environ.get("PORT") or 5000)
    debug_env = os.environ.get("FLASK_DEBUG") or os.environ.get("DEBUG") or ""
    debug = str(debug_env).strip().lower() in {"1", "true", "on", "yes"}
    flask_app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
