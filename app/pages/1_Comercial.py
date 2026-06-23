"""Painel Comercial — vendas/CRM (lê os Parquet, reusa os _chart_* comerciais)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # app/pages -> app -> raiz
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.lib.render import seletor_e_render  # noqa: E402

st.set_page_config(
    page_title="Comercial — Reports Corretora", page_icon="🟢", layout="wide"
)
st.title("🟢 Painel Comercial")
st.caption(
    "O que vender mais à carteira — concentração, margens, renovações e performance."
)
seletor_e_render("comercial")
