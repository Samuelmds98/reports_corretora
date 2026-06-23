"""
app/lib/render.py

Renderização de uma visão no Streamlit: o MESMO gráfico Plotly + as MESMAS listas
de Insights/Recomendações que vão para o HTML, agora interativos, com download do
workbook de auditoria (lastro). Os textos de insight trazem `<b>` (HTML) — render
com `unsafe_allow_html=True` (conteúdo é do próprio projeto).
"""

import streamlit as st

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _lista(titulo, itens, cor):
    st.markdown(f"**{titulo}**")
    if not itens:
        st.caption("—")
        return
    html = "".join(f"<li>{i}</li>" for i in itens)
    st.markdown(
        f"<ul style='margin-top:0;padding-left:18px;color:#333'>{html}</ul>",
        unsafe_allow_html=True,
    )


def render_visao(visao):
    """Renderiza uma visão do registry (gráfico + insights + recs + auditoria)."""
    st.subheader(visao["title"])
    st.caption(visao["subtitle"])

    df = visao["loader"]()
    if df is None or df.empty:
        st.info(
            "Sem dados para esta visão. Rode o pipeline primeiro: "
            "`python Main.py --input-dir data/exemplo --force`."
        )
        return

    try:
        fig, insights, recs = visao["chart"](df)
    except Exception as e:  # não derruba a página por causa de 1 visão
        st.error(f"Falha ao renderizar esta visão: {e}")
        return

    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        _lista("💡 Insights", insights, "verde")
    with col2:
        _lista("🎯 Recomendações", recs, "laranja")

    audit = visao.get("audit")
    if audit is not None and audit.exists():
        with open(audit, "rb") as fh:
            st.download_button(
                f"📥 Auditoria (lastro) — {audit.name}",
                fh.read(),
                file_name=audit.name,
                mime=_XLSX_MIME,
                key=f"audit_{visao['key']}",
            )
        st.caption(
            "Cada número desta visão tem o lastro (registros de origem com arquivo e "
            "linha) no workbook acima — rastreabilidade ponta a ponta."
        )


def seletor_e_render(track: str):
    """Sidebar com a lista de visões do track + render da escolhida."""
    from app.lib.registry import visoes_do_track

    visoes = visoes_do_track(track)
    if not visoes:
        st.info("Nenhuma visão registrada para este painel.")
        return
    titulos = [v["title"] for v in visoes]
    escolha = st.sidebar.radio("Análise", titulos, key=f"sel_{track}")
    visao = next(v for v in visoes if v["title"] == escolha)
    render_visao(visao)
