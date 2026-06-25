"""
app/Home.py — entrypoint do app Streamlit "Reports Corretora".

Camada de consumo interativa (Fase 3 do roadmap) para o TCC. NÃO substitui a
geração local de HTML/XLSX (que o `Main.py` segue produzindo p/ a rede): este app
apenas LÊ os Parquet já gerados e reusa os mesmos `_chart_*` de `report_html.py`.

Rodar:  streamlit run app/Home.py   (após um `python Main.py --input-dir data/exemplo`)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # app/ -> raiz
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app.lib.data import outputs_ready  # noqa: E402

st.set_page_config(page_title="Reports Corretora", page_icon="📊", layout="wide")

st.title("📊 Reports Corretora")
st.markdown(
    "Plataforma de **reports / inteligência de dados** de uma corretora de seguros "
    "(público geral, PF/PJ). Esta é a camada de consumo interativa — os mesmos números, "
    "gráficos e recomendações dos relatórios locais, agora navegáveis."
)

if not outputs_ready():
    st.warning(
        "**Os dados ainda não foram gerados.** Rode o pipeline antes de abrir os painéis:\n\n"
        "```\npython Main.py --input-dir data/exemplo --force\n```\n\n"
        "O app lê os Parquet de `outputs/*/parquet/` (gerados pelo pipeline)."
    )
else:
    st.success(
        "Dados carregados de `outputs/` — escolha um painel abaixo ou na barra lateral."
    )

st.divider()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown("### 🟢 Comercial")
    st.caption(
        "Vendas/CRM: ABC, market share, renovações, win-back, margens, produtor."
    )
    st.page_link("pages/1_Comercial.py", label="Abrir painel →")
with c2:
    st.markdown("### 🟠 Operacional")
    st.caption(
        "Qualidade de cadastro/processo: completude, status×situação, DQ, acionabilidade."
    )
    st.page_link("pages/2_Operacional.py", label="Abrir painel →")
with c3:
    st.markdown("### 🔵 Marketing")
    st.caption(
        "Base inteira (cliente × prospect): personas, alvos de aquisição, audiência."
    )
    st.page_link("pages/3_Marketing.py", label="Abrir painel →")
with c4:
    st.markdown("### ⚙️ Saúde do Pipeline")
    st.caption("Contexto da execução (guardrails) + tendência de qualidade de dados.")
    st.page_link("pages/4_Saude_Pipeline.py", label="Abrir →")

st.divider()
st.caption(
    "Rastreabilidade: cada visão linka o workbook de auditoria (Agregado | Lastro) com os "
    "registros de origem. Dados de exemplo são fictícios (anonimizados)."
)
