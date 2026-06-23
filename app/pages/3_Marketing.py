"""Painel Marketing — base inteira (cliente × prospect), personas e aquisição."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.lib.render import seletor_e_render  # noqa: E402

st.set_page_config(
    page_title="Marketing — Reports Corretora", page_icon="🔵", layout="wide"
)
st.title("🔵 Painel Marketing")
st.caption("Quem ainda converter — 68% da base são prospects, invisíveis ao Comercial.")
seletor_e_render("marketing")
