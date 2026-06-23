"""
app/lib/data.py

Carregamento (cacheado) dos artefatos que o pipeline já grava em `outputs/`.
O app Streamlit NÃO recalcula nada — apenas lê os Parquet/XLSX produzidos por
`Main.py` e os entrega aos mesmos `_chart_*` de `report_html.py`. Assim, app e
HTML mostram exatamente o mesmo número (fonte única de lógica de gráfico).
"""

from pathlib import Path

import pandas as pd
import streamlit as st

# app/lib/data.py -> app/lib -> app -> raiz do projeto
ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"


@st.cache_data(show_spinner=False)
def load_parquet(track: str, name: str) -> pd.DataFrame:
    """Lê `outputs/<track>/parquet/<name>.parquet` (DataFrame vazio se ausente)."""
    p = OUTPUTS / track / "parquet" / f"{name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


@st.cache_data(show_spinner=False)
def load_dq_resumo() -> pd.DataFrame:
    """Resumo de DQ — não há Parquet; lê a aba 0_RESUMO_DQ de `DQ_Reports.xlsx`."""
    p = OUTPUTS / "operacional" / "DQ_Reports.xlsx"
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(p, sheet_name="0_RESUMO_DQ", engine="openpyxl")
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_dq_history() -> pd.DataFrame:
    """Histórico acumulado de DQ (`outputs/operacional/dq_history.parquet`)."""
    p = OUTPUTS / "operacional" / "dq_history.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def audit_file(track: str, name: str) -> Path:
    """Caminho do workbook de auditoria (Agregado|Lastro) de uma visão."""
    return OUTPUTS / track / "auditoria" / name


def outputs_ready() -> bool:
    """True se o pipeline já gerou ao menos os Parquet comerciais."""
    return (OUTPUTS / "comercial" / "parquet").exists() and any(
        (OUTPUTS / "comercial" / "parquet").glob("*.parquet")
    )
