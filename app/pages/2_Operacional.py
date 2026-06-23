"""Painel Operacional / Qualidade — saúde do dado e do processo."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.lib.render import seletor_e_render  # noqa: E402

st.set_page_config(
    page_title="Operacional — Reports Corretora", page_icon="🟠", layout="wide"
)
st.title("🟠 Painel Operacional / Qualidade")
st.caption(
    "Furos de cadastro e processo — o pipeline só sinaliza, o saneamento é na origem."
)
seletor_e_render("operacional")
