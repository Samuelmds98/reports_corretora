"""Saúde do Pipeline — contexto da execução (guardrails) + qualidade de dados."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.lib.data import (load_dq_history, load_dq_resumo,  # noqa: E402
                          load_parquet)

st.set_page_config(
    page_title="Saúde do Pipeline — Reports Corretora", page_icon="⚙️", layout="wide"
)
st.title("⚙️ Saúde do Pipeline")
st.caption(
    "Governança da execução: a 'forma' do input e a evolução da qualidade de dados."
)

# ── Guardrails / contexto da execução ────────────────────────────────────────
st.subheader("Contexto da execução (guardrails)")
rc = load_parquet("operacional", "run_context")
if rc is None or rc.empty:
    st.info(
        "Sem `run_context`. Rode `python Main.py --input-dir data/exemplo --force`."
    )
else:
    st.caption(
        "Mede janela temporal por INÍCIO DE VIGÊNCIA, taxa de órfãos e nº de categorias — "
        "alerta sobre distorções de base filtrada/janelada. Só sinaliza."
    )
    st.dataframe(rc, use_container_width=True, hide_index=True)

st.divider()

# ── Resumo de DQ atual ───────────────────────────────────────────────────────
st.subheader("Qualidade de dados — resumo da última execução")
resumo = load_dq_resumo()
if resumo is None or resumo.empty:
    st.info("Sem resumo de DQ (`DQ_Reports.xlsx`).")
else:
    st.dataframe(resumo, use_container_width=True, hide_index=True)
    # Barra por ocorrências, se houver uma coluna numérica e uma de rótulo
    num_cols = [c for c in resumo.columns if pd.api.types.is_numeric_dtype(resumo[c])]
    lab_cols = [
        c for c in resumo.columns if not pd.api.types.is_numeric_dtype(resumo[c])
    ]
    if num_cols and lab_cols:
        try:
            st.bar_chart(resumo.set_index(lab_cols[0])[num_cols[0]])
        except Exception:
            pass

st.divider()

# ── Histórico de DQ (tendência) ──────────────────────────────────────────────
st.subheader("Histórico de qualidade de dados (tendência)")
hist = load_dq_history()
if hist is None or hist.empty:
    st.info(
        "Sem histórico acumulado (`dq_history.parquet`) — aparece após algumas execuções."
    )
else:
    st.caption(f"{len(hist):,} registros acumulados ao longo das execuções.")
    st.dataframe(hist, use_container_width=True, hide_index=True)
    # Tentativa de série temporal: 1ª coluna datetime × 1ª coluna numérica
    dt_cols = [c for c in hist.columns if pd.api.types.is_datetime64_any_dtype(hist[c])]
    num_cols = [c for c in hist.columns if pd.api.types.is_numeric_dtype(hist[c])]
    if dt_cols and num_cols:
        try:
            serie = hist.groupby(dt_cols[0])[num_cols[0]].sum()
            st.line_chart(serie)
        except Exception:
            pass
