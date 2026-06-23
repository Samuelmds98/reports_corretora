"""
parameters.py

Dicionários de mapeamento para o motor de rating "Reports Corretora".
"""

# Mapeamento do "NOME ABREVIADO DO PRODUTO" para "TIPO DE VIGÊNCIA"
PRODUCT_TYPE_MAP = {
    "AP INDIVIDUAL": "RECORRENTE",
    "PECULIO + AP": "RECORRENTE",
    "AP/DIT": "RECORRENTE",
    "AP IND SERIT/DIT": "RECORRENTE",
    "AUTOMÓVEL": "RENOVÁVEL",
    "EMPRESARIAL": "RENOVÁVEL",
    "RESIDENCIAL": "RENOVÁVEL",
    "CONSORCIO": "RECORRENTE",
    "ODONTO": "RECORRENTE",
    "EQUIPAMENTOS": "RENOVÁVEL",
    "PGBL INDIVIDUAL": "RECORRENTE",
    "RENDA POR INVALIDEZ": "RECORRENTE",
    "RENDA MENSAL TEMP": "RECORRENTE",
    "PENSAO TEMP. AOS DEP": "RECORRENTE",
    "INVALIDEZ PERMANENTE": "RECORRENTE",
    "PREVIDÊNCIA": "RECORRENTE",
    "VGBL INDIVIDUAL": "RECORRENTE",
    "RC PROFISSIONAL": "RENOVÁVEL",
    "VIAGEM": "TRANSACIONAL",
    "VIDA EM GRUPO": "RECORRENTE",
    "VIDA INDIVIDUAL": "RECORRENTE",
    "SERIT MAIS": "RECORRENTE",
    "SERIT/VG": "RECORRENTE",
    "INDIVIDUAL SERIT/DIT": "RECORRENTE",
    "SERIT/AP": "RECORRENTE",
    "DOENÇAS GRAVES": "RECORRENTE",
    "PREV + RISCO": "RECORRENTE",
    "HORIZONTE": "RECORRENTE",
    "RISCO DE PREVIDENCIA": "RECORRENTE",
}

# Sufixos de anos a serem removidos na extração da raiz da apólice
YEAR_SUFFIXES = [str(y) for y in range(2000, 2030)]

# Produtores "internos"/casa: NÃO são força de vendas. Quando não há produtor (ou não
# há repasse de comissão), o cliente não pertence à carteira de ninguém e fica no nome
# da própria empresa. Identificados por palavra-chave no nome do PRODUTOR e avaliados à
# parte (fora do ranking e da concentração de produtores externos). Editável pelo negócio.
PRODUTOR_INTERNO_KEYWORDS = ("UNIMED",)

# Apelidos/duplicidades de cadastro de PRODUTOR: o MESMO produtor aparece com nomes
# diferentes (cadastro antigo × novo). Mapeia variante -> nome canônico (chave em CAIXA
# ALTA, comparada com o nome normalizado). Editável pelo negócio conforme forem achados.
PRODUTOR_ALIASES = {
    "LIDUINA ROMERO": "LIDUINA MARIA BELMINO ROMERO",
}


def normalize_producer(name):
    """Resolve o nome canônico de um produtor (aplica PRODUTOR_ALIASES)."""
    if name is None:
        return name
    chave = str(name).strip().upper()
    return PRODUTOR_ALIASES.get(chave, name)
