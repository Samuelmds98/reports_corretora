"""
parameters.py

Parâmetros do motor "Reports Corretora". O mapa NOME ABREVIADO DO PRODUTO ->
TIPO DE VIGÊNCIA é a **fonte de verdade** das regras por produto e mora num CSV
editável pelo negócio em `configs/product_types.csv` (antes era um dict inline;
a origem documental era um export de planilha em `Página1.html`).
"""

import csv
from pathlib import Path

# configs/ na raiz do projeto (src/parameters.py -> src -> raiz -> configs)
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"
_PRODUCT_TYPES_FILE = _CONFIG_DIR / "product_types.csv"


def _load_product_type_map(path: Path = _PRODUCT_TYPES_FILE) -> dict:
    """
    Carrega o mapa produto -> tipo de vigência (RENOVÁVEL/RECORRENTE/TRANSACIONAL)
    do CSV de configuração. Colunas: `produto`, `tipo_vigencia`. Caminho derivado de
    `__file__` (reprodutível, independente do diretório de execução).
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração de produtos não encontrado: {path}. "
            "Ele é a fonte de verdade do PRODUCT_TYPE_MAP (produto -> tipo de vigência)."
        )
    mapping = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            produto = (row.get("produto") or "").strip()
            tipo = (row.get("tipo_vigencia") or "").strip()
            if produto:
                mapping[produto] = tipo
    return mapping


# Mapeamento do "NOME ABREVIADO DO PRODUTO" para "TIPO DE VIGÊNCIA" (do CSV de config)
PRODUCT_TYPE_MAP = _load_product_type_map()

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
