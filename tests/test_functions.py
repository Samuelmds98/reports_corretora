"""
Testes do motor de regras (`src/functions.py`) — a lógica de negócio mais crítica:
saneamento (CPF, raiz de apólice), status do produto, rating e flag de último ciclo.
Usa DataFrames mínimos montados à mão (não depende de Excel). Roda com: `pytest`.
"""

import numpy as np
import pandas as pd
import pytest

from src.functions import (calculate_rating, clean_cpf_cnpj,
                           extract_policy_root, flag_last_cycle,
                           get_product_status)

TODAY = pd.Timestamp("2026-06-16")


# ── clean_cpf_cnpj ────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("123.456.789-01", "12345678901"),  # remove pontuação
        ("12345678901", "12345678901"),  # já limpo
        ("12345", "00000012345"),  # padding p/ 11
        ("11.222.333/0001-44", "11222333000144"),  # CNPJ 14
        ("", "00000000000"),  # vazio vira 11 zeros
    ],
)
def test_clean_cpf_cnpj(entrada, esperado):
    assert clean_cpf_cnpj(entrada) == esperado


def test_clean_cpf_cnpj_nulo():
    assert clean_cpf_cnpj(np.nan) == ""
    assert clean_cpf_cnpj(None) == ""


# ── extract_policy_root ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "apolice,raiz",
    [
        ("12345/2024", "12345"),  # remove "/" e sufixo de ano
        ("ABC-123.2025", "ABC123"),  # remove especiais e ano
        ("999-2023", "999"),  # ano no fim
        ("2024", "2024"),  # só o ano: NÃO remove (lookbehind exige algo antes)
        ("APOLICE100", "APOLICE100"),  # sem ano, inalterada
    ],
)
def test_extract_policy_root(apolice, raiz):
    assert extract_policy_root(apolice) == raiz


def test_extract_policy_root_nulo():
    assert extract_policy_root(np.nan) == ""


# ── calculate_rating (1–5★ top-down) ─────────────────────────────────────────
def _produtos(linhas):
    """Monta o DataFrame que `calculate_rating` consome."""
    return pd.DataFrame(
        linhas, columns=["PRODUTO", "STATUS_PRODUTO", "MAX_INICIO_VIGENCIA"]
    )


def test_rating_5_estrelas():
    # recorrente>=1 E renovável>=2 E transacional_12m>=1
    df = _produtos(
        [
            ("AP INDIVIDUAL", "ATIVO", TODAY),  # RECORRENTE
            ("AUTOMÓVEL", "ATIVO", TODAY),  # RENOVÁVEL
            ("RESIDENCIAL", "ATIVO", TODAY),  # RENOVÁVEL
            ("VIAGEM", "ATIVO", TODAY),  # TRANSACIONAL
        ]
    )
    r = calculate_rating(df, TODAY)
    assert r["RATING_ESTRELAS"] == 5
    assert r["STATUS_GLOBAL"] == "ATIVO"


def test_rating_3_estrelas_duas_categorias():
    # 2 categorias distintas (sem o trio do 4/5★)
    df = _produtos(
        [
            ("AUTOMÓVEL", "ATIVO", TODAY),  # RENOVÁVEL
            ("AP INDIVIDUAL", "ATIVO", TODAY),  # RECORRENTE
        ]
    )
    assert calculate_rating(df, TODAY)["RATING_ESTRELAS"] == 3


def test_rating_2_estrelas_mesma_categoria():
    # 2 produtos ativos, 1 categoria
    df = _produtos(
        [
            ("AUTOMÓVEL", "ATIVO", TODAY),  # RENOVÁVEL
            ("RESIDENCIAL", "ATIVO", TODAY),  # RENOVÁVEL
        ]
    )
    assert calculate_rating(df, TODAY)["RATING_ESTRELAS"] == 2


def test_rating_1_estrela_mono_produto():
    df = _produtos([("AUTOMÓVEL", "ATIVO", TODAY)])
    assert calculate_rating(df, TODAY)["RATING_ESTRELAS"] == 1


def test_rating_0_inativo():
    # Único produto INATIVO -> rating 0, status global INATIVO
    df = _produtos([("AUTOMÓVEL", "INATIVO", TODAY - pd.Timedelta(days=400))])
    r = calculate_rating(df, TODAY)
    assert r["RATING_ESTRELAS"] == 0
    assert r["STATUS_GLOBAL"] == "INATIVO"


def test_rating_transacional_inativo_dentro_12m_conta():
    # TRANSACIONAL inativo mas com vigência nos últimos 12 meses ainda conta
    df = _produtos([("VIAGEM", "INATIVO", TODAY - pd.Timedelta(days=100))])
    r = calculate_rating(df, TODAY)
    assert r["STATUS_GLOBAL"] == "ATIVO"
    assert r["RATING_ESTRELAS"] == 1


# ── get_product_status (Bloco A apólices / Bloco B faturas) ──────────────────
def _grupo(linhas):
    cols = [
        "CPF_LIMPO",
        "SEGURADORA (ABREVIADO)",
        "RAMO",
        "APÓLICE",
        "TIPO DE NEGÓCIO",
        "TIPO DOCUMENTO",
        "INÍCIO DE VIGÊNCIA",
        "TÉRMINO DE VIGÊNCIA",
    ]
    return pd.DataFrame(linhas, columns=cols)


def test_status_apolice_ativa():
    g = _grupo(
        [
            (
                "1",
                "ALFA",
                "AUTO",
                "100",
                "N",
                "APÓLICE",
                TODAY - pd.Timedelta(days=30),
                TODAY + pd.Timedelta(days=300),
            )
        ]
    )
    assert get_product_status(g, {}, TODAY) == "ATIVO"


def test_status_apolice_vencida_inativa():
    g = _grupo(
        [
            (
                "1",
                "ALFA",
                "AUTO",
                "100",
                "N",
                "APÓLICE",
                TODAY - pd.Timedelta(days=400),
                TODAY - pd.Timedelta(days=35),
            )
        ]
    )
    assert get_product_status(g, {}, TODAY) == "INATIVO"


def test_status_apolice_cancelada():
    inicio = TODAY - pd.Timedelta(days=30)
    termino = TODAY + pd.Timedelta(days=300)
    g = _grupo([("1", "ALFA", "AUTO", "100", "N", "APÓLICE", inicio, termino)])
    # Cancelamento dentro da janela e <= hoje
    cancel_index = {("1", "ALFA", "AUTO", "100"): [TODAY - pd.Timedelta(days=5)]}
    assert get_product_status(g, cancel_index, TODAY) == "CANCELADO"


def test_status_fatura_recente_ativa():
    # Sem N/R, fatura iniciada nos últimos 90 dias -> ATIVO
    g = _grupo(
        [
            (
                "1",
                "ALFA",
                "SAÚDE",
                "200",
                "ER",
                "FATURA",
                TODAY - pd.Timedelta(days=20),
                TODAY + pd.Timedelta(days=10),
            )
        ]
    )
    assert get_product_status(g, {}, TODAY) == "ATIVO"


def test_status_fatura_antiga_inativa():
    g = _grupo(
        [
            (
                "1",
                "ALFA",
                "SAÚDE",
                "200",
                "ER",
                "FATURA",
                TODAY - pd.Timedelta(days=200),
                TODAY - pd.Timedelta(days=170),
            )
        ]
    )
    assert get_product_status(g, {}, TODAY) == "INATIVO"


# ── flag_last_cycle ───────────────────────────────────────────────────────────
def test_flag_last_cycle_mantem_so_ciclo_vigente():
    # Mesma apólice (raiz "100") renovada: 2024 (N) e 2025 (R) -> só 2025 é último ciclo
    df = pd.DataFrame(
        {
            "CPF_LIMPO": ["1", "1"],
            "SEGURADORA (ABREVIADO)": ["ALFA", "ALFA"],
            "NOME ABREVIADO DO PRODUTO": ["AUTOMÓVEL", "AUTOMÓVEL"],
            "APÓLICE": ["100-2024", "100-2025"],
            "TIPO DE NEGÓCIO": ["N", "R"],
            "INÍCIO DE VIGÊNCIA": [
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2025-01-01"),
            ],
        }
    )
    out = flag_last_cycle(df).sort_values("INÍCIO DE VIGÊNCIA")
    assert out["EH_ULTIMO_CICLO"].tolist() == [False, True]


def test_flag_last_cycle_fatura_conta_todas():
    # Só FATURA (sem N/R): todas as linhas contam (cada fatura é um pagamento)
    df = pd.DataFrame(
        {
            "CPF_LIMPO": ["1", "1"],
            "SEGURADORA (ABREVIADO)": ["ALFA", "ALFA"],
            "NOME ABREVIADO DO PRODUTO": ["AP INDIVIDUAL", "AP INDIVIDUAL"],
            "APÓLICE": ["200", "200"],
            "TIPO DE NEGÓCIO": ["ER", "ER"],
            "INÍCIO DE VIGÊNCIA": [
                pd.Timestamp("2025-01-01"),
                pd.Timestamp("2025-02-01"),
            ],
        }
    )
    assert flag_last_cycle(df)["EH_ULTIMO_CICLO"].tolist() == [True, True]
