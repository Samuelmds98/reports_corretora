"""
Testes do carregamento do mapa de produtos a partir de `configs/product_types.csv`
(fonte de verdade editável pelo negócio, carregada por `src/parameters.py`).
"""

import pytest

from src.parameters import PRODUCT_TYPE_MAP, _load_product_type_map

_TIPOS_VALIDOS = {"RENOVÁVEL", "RECORRENTE", "TRANSACIONAL"}


def test_mapa_carregado_do_csv():
    assert len(PRODUCT_TYPE_MAP) >= 20  # base atual: 29 produtos
    assert PRODUCT_TYPE_MAP["AUTOMÓVEL"] == "RENOVÁVEL"
    assert PRODUCT_TYPE_MAP["VIAGEM"] == "TRANSACIONAL"
    assert PRODUCT_TYPE_MAP["ODONTO"] == "RECORRENTE"


def test_todos_os_tipos_sao_validos():
    assert set(PRODUCT_TYPE_MAP.values()) <= _TIPOS_VALIDOS


def test_loader_arquivo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        _load_product_type_map(tmp_path / "nao_existe.csv")


def test_loader_le_csv_customizado(tmp_path):
    csv = tmp_path / "p.csv"
    csv.write_text(
        "produto,tipo_vigencia\nTESTE A,RENOVÁVEL\nTESTE B,TRANSACIONAL\n",
        encoding="utf-8",
    )
    m = _load_product_type_map(csv)
    assert m == {"TESTE A": "RENOVÁVEL", "TESTE B": "TRANSACIONAL"}
