"""
report_html.py

Relatórios HTML auto-contidos com storytelling (Fase 5): cada análise vira um
`.html` com um gráfico Plotly interativo + seções de Insights e Recomendações
geradas dinamicamente a partir dos dados.

Os DataFrames já estão em memória ao final do pipeline — esta etapa não relê
nenhum Excel. Funções `_chart_*` são privadas e nunca mutam os DataFrames
recebidos (operam em `.copy()`/filtros). Erro em um visual não derruba os demais.
"""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version
from plotly.subplots import make_subplots

# ── Paleta corporativa (mesma do excel_report.py) ─────────────────────────────
VERDE = "#00925C"
AZUL = "#08484C"
VERDE_LIMA = "#B0CD4E"
LARANJA = "#EF7925"
CINZA_CLARO = "#F5F5F5"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.plot.ly/plotly-{plotlyjs_version}.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #FAFAFA; color: #1A1A1A; }}
    .header {{ background: {azul}; color: white; padding: 28px 40px; }}
    .header h1 {{ font-size: 22px; font-weight: 600; letter-spacing: 0.3px; }}
    .header p {{ font-size: 13px; opacity: 0.75; margin-top: 4px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 40px; }}
    .chart-box {{ background: white; border-radius: 8px; padding: 24px;
                  box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 28px; }}
    .section {{ background: white; border-radius: 8px; padding: 24px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 20px; }}
    .section h2 {{ font-size: 14px; font-weight: 600; text-transform: uppercase;
                   letter-spacing: 0.8px; margin-bottom: 16px; }}
    .insights h2 {{ color: {verde}; border-left: 4px solid {verde}; padding-left: 12px; }}
    .recomendacoes h2 {{ color: {laranja}; border-left: 4px solid {laranja}; padding-left: 12px; }}
    .auditoria h2 {{ color: {azul}; border-left: 4px solid {azul}; padding-left: 12px; }}
    .auditoria li::before {{ color: {azul}; }}
    .auditoria a {{ color: {azul}; font-weight: 600; }}
    ul {{ list-style: none; }}
    li {{ padding: 8px 0; font-size: 14px; line-height: 1.6; border-bottom: 1px solid #F0F0F0; }}
    li:last-child {{ border-bottom: none; }}
    li::before {{ content: "▸ "; color: #999; }}
    .insights li::before {{ color: {verde}; }}
    .recomendacoes li::before {{ color: {laranja}; }}
    .footer {{ text-align: center; font-size: 12px; color: #AAA; padding: 20px 0 40px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="container">
    <div class="chart-box">
      {plotly_div}
    </div>
    <div class="section insights">
      <h2>Insights</h2>
      <ul>{insights_html}</ul>
    </div>
    <div class="section recomendacoes">
      <h2>Recomendações</h2>
      <ul>{recomendacoes_html}</ul>
    </div>
    {audit_block}
  </div>
  <div class="footer">Gerado em {timestamp} — Raio X Cooperados</div>
</body>
</html>
"""

# Bloco de auditoria (rastreabilidade): linka o arquivo registro-a-registro da análise.
AUDIT_BLOCK_TEMPLATE = (
    '<div class="section auditoria">'
    "<h2>Auditoria</h2>"
    '<ul><li>{text} <a href="{href}">{label}</a>.</li></ul></div>'
)
_AUDIT_TEXT_LASTRO = (
    "Rastreabilidade total: cada número desta análise tem o lastro de registros de "
    "origem (com arquivo e linha) em"
)
_AUDIT_TEXT_DETALHE = "Detalhe registro a registro (todas as linhas) em"


def _audit_block(audit_ref):
    """
    Monta o bloco de rodapé de auditoria. `audit_ref` pode ser:
      - None → sem bloco;
      - str  → workbook de lastro em `../auditoria/<ref>` (padrão das visões comerciais);
      - (href, label[, text]) → link customizado (ex.: o XLSX registro-a-registro do
        track operacional, em `../<arquivo>.xlsx`).
    """
    if not audit_ref:
        return ""
    if isinstance(audit_ref, (tuple, list)):
        href, label = audit_ref[0], audit_ref[1]
        text = audit_ref[2] if len(audit_ref) > 2 else _AUDIT_TEXT_DETALHE
    else:
        href, label, text = f"../auditoria/{audit_ref}", audit_ref, _AUDIT_TEXT_LASTRO
    return AUDIT_BLOCK_TEMPLATE.format(href=href, label=label, text=text)


# Portal de navegação (índice) que consolida os HTMLs de um público em cards.
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #FAFAFA; color: #1A1A1A; }}
    .header {{ background: {accent}; color: white; padding: 36px 40px; }}
    .header h1 {{ font-size: 24px; font-weight: 600; }}
    .header p {{ font-size: 14px; opacity: 0.8; margin-top: 6px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 40px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }}
    .card {{ display: block; background: white; border-radius: 10px; padding: 20px 22px;
             box-shadow: 0 1px 4px rgba(0,0,0,0.08); text-decoration: none; color: inherit;
             border-left: 4px solid {accent}; transition: transform .08s, box-shadow .08s; }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.12); }}
    .card .num {{ font-size: 12px; color: {accent}; font-weight: 700; letter-spacing: .5px; }}
    .card h3 {{ font-size: 16px; font-weight: 600; margin: 6px 0; }}
    .card p {{ font-size: 13px; color: #666; line-height: 1.5; }}
    .card .go {{ display: inline-block; margin-top: 12px; font-size: 13px; font-weight: 600; color: {accent}; }}
    .footer {{ text-align: center; font-size: 12px; color: #AAA; padding: 28px 0 40px; }}
  </style>
</head>
<body>
  <div class="header"><h1>{title}</h1><p>{subtitle}</p></div>
  <div class="container"><div class="grid">{cards}</div></div>
  <div class="footer">Gerado em {timestamp} — Raio X Cooperados</div>
</body>
</html>
"""

# Página estática do roadmap de growth (item 4): cards descritivos, sem link/gráfico.
ROADMAP_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #FAFAFA; color: #1A1A1A; }}
    .header {{ background: {accent}; color: white; padding: 36px 40px; }}
    .header h1 {{ font-size: 24px; font-weight: 600; }}
    .header p {{ font-size: 14px; opacity: 0.85; margin-top: 6px; max-width: 760px; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 40px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px; }}
    .card {{ background: white; border-radius: 10px; padding: 20px 22px;
             box-shadow: 0 1px 4px rgba(0,0,0,0.08); border-left: 4px dashed {accent}; }}
    .card .num {{ font-size: 11px; color: {accent}; font-weight: 700; letter-spacing: .5px; }}
    .card h3 {{ font-size: 16px; font-weight: 600; margin: 6px 0; }}
    .card p {{ font-size: 13px; color: #666; line-height: 1.5; margin-top: 4px; }}
    .card p.how {{ color: {accent}; font-weight: 600; margin-top: 10px; }}
    .footer {{ text-align: center; font-size: 12px; color: #AAA; padding: 28px 0 40px; }}
  </style>
</head>
<body>
  <div class="header"><h1>{title}</h1><p>{subtitle}</p></div>
  <div class="container"><div class="grid">{cards}</div></div>
  <div class="footer">Gerado em {timestamp} — Raio X Cooperados</div>
</body>
</html>
"""


# ── Helpers de formatação e estilo ────────────────────────────────────────────
def _money(v):
    """Formata valores monetários: R$ 1,234,567 (ponto de milhar, sem decimal)."""
    try:
        return f"R$ {float(v):,.0f}"
    except (TypeError, ValueError):
        return "R$ 0"


def _pct(v):
    """Formata percentuais: 12.3%."""
    try:
        return f"{float(v):.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _style(fig, height=460):
    """Aplica o visual corporativo padrão a uma figura Plotly."""
    fig.update_layout(
        height=height,
        margin=dict(l=60, r=50, t=50, b=70),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Segoe UI, Arial, sans-serif", size=12, color="#1A1A1A"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hoverlabel=dict(font_size=12, font_family="Segoe UI, Arial"),
    )
    fig.update_xaxes(showgrid=False, linecolor="#DDD")
    fig.update_yaxes(showgrid=True, gridcolor="#F0F0F0", linecolor="#DDD")
    return fig


def _empty_fig(msg="Dados insuficientes para este gráfico"):
    """Figura placeholder quando não há dados para plotar."""
    fig = go.Figure()
    fig.add_annotation(
        text=msg,
        showarrow=False,
        font=dict(size=16, color="#999"),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
    )
    fig.update_layout(
        height=400,
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    return fig


def _no_data(msg="Dados insuficientes para esta análise no período."):
    """Retorno padrão (fig, insights, recs) quando o DataFrame está vazio."""
    return _empty_fig(), [msg], ["Sem recomendações — base sem registros suficientes."]


# ── Renderização e persistência ───────────────────────────────────────────────
def render_html_report(title, subtitle, fig, insights, recommendations, audit_ref=None):
    """
    Renderiza um HTML auto-contido com gráfico Plotly + seções de texto.
    `audit_ref` (nome do .xlsx em outputs/auditoria/) adiciona o bloco de
    rastreabilidade linkando o lastro daquela análise. Retorna a string HTML.
    """
    plotly_div = fig.to_html(
        include_plotlyjs=False, full_html=False, config={"responsive": True}
    )
    insights_html = "".join(f"<li>{item}</li>" for item in insights)
    recomendacoes_html = "".join(f"<li>{item}</li>" for item in recommendations)
    audit_block = _audit_block(audit_ref)

    return HTML_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        plotly_div=plotly_div,
        insights_html=insights_html,
        recomendacoes_html=recomendacoes_html,
        audit_block=audit_block,
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M"),
        plotlyjs_version=get_plotlyjs_version(),
        azul=AZUL,
        verde=VERDE,
        laranja=LARANJA,
    )


def save_report(html_str, filename, output_dir):
    """Salva o HTML no diretório de saída (cria se necessário). Retorna o Path."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_text(html_str, encoding="utf-8")
    return path


# ── Gráficos por análise ──────────────────────────────────────────────────────
def _chart_abc(df_abc):
    """
    Pareto da carteira: barras de prêmio por cliente (top 30) + linha % acumulado.
    Evidencia concentração de receita e identifica cooperados de alto valor.
    """
    if df_abc is None or df_abc.empty or "TOTAL_PREMIO_LIQ" not in df_abc.columns:
        return _no_data()

    df = df_abc.copy().sort_values("TOTAL_PREMIO_LIQ", ascending=False)
    top = df.head(30)

    cor_classe = {
        "Classe A": VERDE,
        "Classe B": VERDE_LIMA,
        "Classe C": LARANJA,
    }
    bar_colors = [cor_classe.get(str(c).split(" (")[0], AZUL) for c in top["CURVA_ABC"]]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=top["CPF_LIMPO"].astype(str),
            y=top["TOTAL_PREMIO_LIQ"],
            marker_color=bar_colors,
            name="Prêmio líquido",
            hovertemplate="CPF %{x}<br>Prêmio: R$ %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=top["CPF_LIMPO"].astype(str),
            y=top["%_ACUMULADO"] * 100,
            mode="lines+markers",
            line=dict(color=AZUL, width=2),
            name="% acumulado",
            hovertemplate="Acumulado: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color=LARANJA,
        secondary_y=True,
        annotation_text="80%",
        annotation_position="top left",
    )
    fig.update_xaxes(title_text="Cooperado (top 30)", showticklabels=False)
    fig.update_yaxes(title_text="Prêmio líquido (R$)", secondary_y=False)
    fig.update_yaxes(
        title_text="% acumulado", secondary_y=True, range=[0, 105], showgrid=False
    )
    _style(fig, height=480)

    n_total = len(df)
    classe_a = df[df["CURVA_ABC"].astype(str).str.startswith("Classe A")]
    n_a = len(classe_a)
    pct_a = (n_a / n_total * 100) if n_total else 0
    premio_total = df["TOTAL_PREMIO_LIQ"].sum()
    ticket_medio_a = classe_a["TOTAL_PREMIO_LIQ"].mean() if n_a else 0

    insights = [
        f"<b>{_pct(pct_a)}</b> dos cooperados ({n_a} de {n_total}) concentram ~80% da receita (Classe A).",
        f"Prêmio líquido total da carteira: <b>{_money(premio_total)}</b>.",
        f"Ticket médio de um cooperado Classe A: <b>{_money(ticket_medio_a)}</b>.",
    ]
    recommendations = [
        f"Priorizar contato trimestral com os <b>{n_a}</b> cooperados Classe A "
        f"(ticket médio {_money(ticket_medio_a)}) — núcleo da receita.",
        "Construir esteira de retenção dedicada à Classe A antes de prospectar a cauda.",
        "Avaliar potencial de upgrade da Classe B para diluir a dependência do topo.",
    ]
    return fig, insights, recommendations


def _chart_partner(df_partner):
    """
    Market share de seguradoras: barras horizontais ordenadas por volume de prêmio,
    com % de share no rótulo de cada barra.
    """
    if (
        df_partner is None
        or df_partner.empty
        or "TOTAL_PREMIO_LIQ" not in df_partner.columns
    ):
        return _no_data()

    df = df_partner.copy().sort_values("TOTAL_PREMIO_LIQ", ascending=False)
    tem_share = "MARKET_SHARE_RECEITA_%" in df.columns

    colors = [AZUL] + [VERDE] * (len(df) - 1)
    opac = [1.0] + [0.7] * (len(df) - 1)
    if tem_share:
        textos = [_pct(s) for s in df["MARKET_SHARE_RECEITA_%"]]
    else:
        textos = [_money(v) for v in df["TOTAL_PREMIO_LIQ"]]

    fig = go.Figure(
        go.Bar(
            x=df["TOTAL_PREMIO_LIQ"],
            y=df["SEGURADORA"].astype(str),
            orientation="h",
            marker=dict(color=colors, opacity=opac),
            text=textos,
            textposition="outside",
            hovertemplate="%{y}<br>Prêmio: R$ %{x:,.0f}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", title_text="")
    fig.update_xaxes(title_text="Prêmio líquido (R$)")
    _style(fig, height=max(420, 32 * len(df)))

    lider = df.iloc[0]
    n_seg = len(df)
    share_lider = lider["MARKET_SHARE_RECEITA_%"] if tem_share else 0
    share_top3 = df.head(3)["MARKET_SHARE_RECEITA_%"].sum() if tem_share else 0

    insights = [
        f"Líder de carteira: <b>{lider['SEGURADORA']}</b> com {_pct(share_lider)} do prêmio total.",
        f"Total de <b>{n_seg}</b> seguradoras com produção ativa.",
        f"As 3 maiores concentram <b>{_pct(share_top3)}</b> da receita.",
    ]
    recommendations = []
    if share_top3 > 70:
        recommendations.append(
            f"Alta concentração ({_pct(share_top3)} nas 3 maiores) — diversificar parceiros "
            "para reduzir risco de dependência."
        )
    else:
        recommendations.append(
            "Distribuição de parceiros saudável — manter monitoramento do share trimestral."
        )
    if tem_share:
        pequenas = df[df["MARKET_SHARE_RECEITA_%"] < 2]["SEGURADORA"].tolist()
        if pequenas:
            recommendations.append(
                f"Avaliar continuidade das {len(pequenas)} seguradoras com share < 2% "
                "(custo operacional vs. volume)."
            )
    recommendations.append(
        f"Negociar melhores condições com <b>{lider['SEGURADORA']}</b>, principal gerador de receita."
    )
    return fig, insights, recommendations


def _chart_specialty(df_specialty):
    """
    Heatmap de penetração de produto por especialidade médica.
    Revela onde há oportunidades de cross-sell por perfil profissional.
    """
    if (
        df_specialty is None
        or df_specialty.empty
        or "PENETRACAO_PCT" not in df_specialty.columns
    ):
        return _no_data()

    df = df_specialty.copy()
    esp_tot = (
        df.groupby("CARACTERÍSTICA")["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"]
        .first()
        .sort_values(ascending=False)
    )
    top_esp = esp_tot.head(15).index.tolist()
    prod_order = (
        df.groupby("PRODUTO")["PENETRACAO_PCT"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    sub = df[df["CARACTERÍSTICA"].isin(top_esp)]

    pivot = sub.pivot_table(
        index="CARACTERÍSTICA",
        columns="PRODUTO",
        values="PENETRACAO_PCT",
        aggfunc="mean",
    ).reindex(index=top_esp, columns=prod_order)

    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale=[[0, "#FFFFFF"], [1, VERDE]],
            zmin=0,
            zmax=100,
            texttemplate="%{z:.0f}%",
            textfont=dict(size=10),
            colorbar=dict(title="% penet."),
            hovertemplate="Especialidade: %{y}<br>Produto: %{x}<br>Penetração: %{z:.1f}%<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Produto", tickangle=-40)
    fig.update_yaxes(title_text="")
    _style(fig, height=max(460, 30 * len(top_esp)))

    prod_top = prod_order[0]
    prod_top_pen = df[df["PRODUTO"] == prod_top]["PENETRACAO_PCT"].mean()

    div = sub[sub["PENETRACAO_PCT"] > 20].groupby("CARACTERÍSTICA")["PRODUTO"].nunique()
    if not div.empty:
        esp_div, n_div = div.idxmax(), int(div.max())
    else:
        esp_div, n_div = "—", 0

    big = top_esp[0]
    rows_big = sub[sub["CARACTERÍSTICA"] == big].sort_values("PENETRACAO_PCT")
    opp = rows_big.iloc[0] if not rows_big.empty else None

    insights = [
        f"Produto com maior penetração média entre especialidades: <b>{prod_top}</b> ({_pct(prod_top_pen)}).",
        f"Especialidade mais diversificada: <b>{esp_div}</b> "
        f"({n_div} produtos com penetração acima de 20%).",
    ]
    recommendations = []
    if opp is not None:
        insights.append(
            f"Maior oportunidade: especialidade <b>{big}</b> tem só "
            f"{_pct(opp['PENETRACAO_PCT'])} de penetração em <b>{opp['PRODUTO']}</b>."
        )
        recommendations.append(
            f"Campanha de <b>{opp['PRODUTO']}</b> para a especialidade <b>{big}</b> "
            f"(maior base, penetração atual {_pct(opp['PENETRACAO_PCT'])})."
        )
    recommendations.append(
        f"Replicar o sucesso de <b>{prod_top}</b> nas especialidades de baixa penetração."
    )
    return fig, insights, recommendations


def _chart_cross_sell(df_prod_status):
    """
    Heatmap de co-posse: para cada par (A, B), quantos clientes têm ambos ativos.
    Identifica combos naturais e oportunidades de bundle.
    """
    if (
        df_prod_status is None
        or df_prod_status.empty
        or "STATUS_PRODUTO" not in df_prod_status.columns
    ):
        return _no_data()

    ativos = df_prod_status[df_prod_status["STATUS_PRODUTO"] == "ATIVO"].copy()
    if ativos.empty:
        return _no_data("Sem produtos ativos para análise de co-posse.")

    pivot = pd.crosstab(ativos["CPF_LIMPO"], ativos["PRODUTO"])
    pivot = (pivot > 0).astype(int)

    # Mantém apenas produtos com pelo menos 5 clientes ativos
    counts = pivot.sum(axis=0)
    keep = counts[counts >= 5].index
    if len(keep) < 2:
        return _no_data("Produtos ativos insuficientes (mínimo 2 com ≥5 clientes).")

    pivot = pivot[keep]
    co = pivot.T.dot(pivot).astype(float)
    # to_numpy(copy=True) evita "array is read-only" (view imutável no pandas 3.0)
    co_arr = co.to_numpy(copy=True)
    np.fill_diagonal(co_arr, 0)
    co = pd.DataFrame(co_arr, index=co.index, columns=co.columns)

    fig = go.Figure(
        go.Heatmap(
            z=co.values,
            x=co.columns.tolist(),
            y=co.index.tolist(),
            colorscale=[[0, "#FFFFFF"], [1, AZUL]],
            texttemplate="%{z:.0f}",
            textfont=dict(size=10),
            colorbar=dict(title="Clientes"),
            hovertemplate="%{y} + %{x}<br>Clientes com ambos: %{z:.0f}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Produto", tickangle=-40)
    fig.update_yaxes(title_text="Produto")
    _style(fig, height=max(480, 32 * len(keep)))

    # Par mais frequente (triângulo superior)
    mask = np.triu(np.ones(co.shape, dtype=bool), k=1)
    co_pairs = co.where(mask).stack()
    insights = []
    if not co_pairs.empty and co_pairs.max() > 0:
        prod_a, prod_b = co_pairs.idxmax()
        insights.append(
            f"Combo mais comum: <b>{prod_a} + {prod_b}</b> "
            f"({int(co_pairs.max())} clientes têm ambos ativos)."
        )
    iso = co.sum(axis=1)
    prod_iso = iso.idxmin()
    insights.append(
        f"Produto mais isolado: <b>{prod_iso}</b> — baixa co-posse, maior oportunidade de bundle."
    )
    insights.append(
        f"{len(keep)} produtos com massa crítica (≥5 clientes ativos) analisados."
    )

    recommendations = [
        "Montar ofertas combinadas a partir dos pares de maior co-posse já observada.",
        f"Desenhar bundle de entrada para <b>{prod_iso}</b>, hoje pouco associado a outros produtos.",
    ]
    return fig, insights, recommendations


def _chart_renewal(df_renewal):
    """
    Barra de renovações nos próximos 90 dias por urgência, com prêmio em risco
    por faixa. Fila de ação do corretor.
    """
    if df_renewal is None or df_renewal.empty or "URGENCIA" not in df_renewal.columns:
        return _no_data("Nenhuma renovação nos próximos 90 dias.")

    df = df_renewal.copy()
    ordem = ["🔴 Até 30 dias", "🟡 31 a 60 dias", "🟢 61 a 90 dias"]
    cor_map = {ordem[0]: LARANJA, ordem[1]: VERDE_LIMA, ordem[2]: VERDE}

    agg = df.groupby("URGENCIA").agg(
        n=("CPF_LIMPO", "size"), premio=("PREMIO_ULTIMO_CICLO", "sum")
    )
    agg = agg.reindex([o for o in ordem if o in agg.index])

    fig = go.Figure(
        go.Bar(
            x=agg.index.tolist(),
            y=agg["n"],
            marker_color=[cor_map.get(u, AZUL) for u in agg.index],
            text=[_money(p) for p in agg["premio"]],
            textposition="outside",
            hovertemplate="%{x}<br>Apólices: %{y}<br>Prêmio: %{text}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Urgência")
    fig.update_yaxes(title_text="Apólices a vencer")
    _style(fig, height=440)

    n_30 = int((df["DIAS_ATE_VENCIMENTO"] <= 30).sum())
    premio_30 = df[df["DIAS_ATE_VENCIMENTO"] <= 30]["PREMIO_ULTIMO_CICLO"].sum()
    n_total = len(df)
    premio_total = df["PREMIO_ULTIMO_CICLO"].sum()

    insights = [
        f"<b>{n_30}</b> apólices vencem em até 30 dias — {_money(premio_30)} em prêmio em risco.",
        f"Total de <b>{n_total}</b> renováveis nos próximos 90 dias ({_money(premio_total)}).",
    ]
    recommendations = [
        f"Priorizar ligações para as <b>{n_30}</b> apólices de 30 dias ({_money(premio_30)} em risco).",
        "Ordenar a fila internamente por RATING_ESTRELAS desc para focar o alto valor.",
        "Disparar lembrete automático de renovação para as faixas de 60 e 90 dias.",
    ]

    # Acionabilidade (corte a): a lista é trabalhável? (flags vindas do cadastro)
    if "CONTATAVEL" in df.columns:
        n_sem = int((~df["CONTATAVEL"]).sum())
        n_sem_30 = (
            int((~df[df["DIAS_ATE_VENCIMENTO"] <= 30]["CONTATAVEL"]).sum())
            if n_30
            else 0
        )
        pct_ok = (df["CONTATAVEL"].mean() * 100) if n_total else 0
        insights.append(
            f"Acionabilidade: <b>{pct_ok:.0f}%</b> da fila tem telefone ou e-mail. "
            f"<b>{n_sem}</b> sem nenhum canal ({n_sem_30} já nos 30 dias) — exigem rota via produtor."
        )
        recommendations.append(
            "Para os sem canal, acionar pelo produtor da apólice e atualizar o cadastro "
            "(o telefone/e-mail volta para a próxima rodada)."
        )
    return fig, insights, recommendations


def _chart_winback(df_winback):
    """
    Top 20 inativos por prêmio histórico, coloridos por dias sem atividade.
    Candidatos prioritários de reativação.
    """
    if (
        df_winback is None
        or df_winback.empty
        or "TOTAL_PREMIO_HISTORICO" not in df_winback.columns
    ):
        return _no_data("Nenhum candidato de win-back no período.")

    df = df_winback.copy().sort_values("TOTAL_PREMIO_HISTORICO", ascending=False)
    top = df.head(20).iloc[::-1]  # invertido p/ maior no topo do gráfico horizontal

    fig = go.Figure(
        go.Bar(
            x=top["TOTAL_PREMIO_HISTORICO"],
            y=top["CPF_LIMPO"].astype(str),
            orientation="h",
            marker=dict(
                color=top["DIAS_INATIVO"],
                colorscale=[[0, LARANJA], [1, VERDE_LIMA]],
                colorbar=dict(title="Dias inativo"),
            ),
            customdata=np.stack(
                [top["DIAS_INATIVO"], top["LISTA_PRODUTOS_ATIVOS"].astype(str)], axis=-1
            ),
            hovertemplate=(
                "CPF %{y}<br>Prêmio histórico: R$ %{x:,.0f}"
                "<br>Dias inativo: %{customdata[0]}"
                "<br>Produtos: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="Prêmio histórico (R$)")
    fig.update_yaxes(title_text="", showticklabels=False)
    _style(fig, height=540)

    n_total = len(df)
    premio_recuperavel = df["TOTAL_PREMIO_HISTORICO"].sum()
    mediana_dias = df["DIAS_INATIVO"].median()

    insights = [
        f"<b>{n_total}</b> ex-clientes candidatos a reativação.",
        f"Prêmio histórico recuperável: <b>{_money(premio_recuperavel)}</b>.",
        f"Mediana de tempo inativo: <b>{mediana_dias:.0f} dias</b>.",
    ]
    recommendations = [
        "Atacar primeiro o top 20 por prêmio histórico — maior valor já demonstrado.",
        f"Abordagem de reativação enquanto a mediana de inatividade ({mediana_dias:.0f} dias) "
        "ainda é recente.",
        "Oferecer condição de retorno para quem saiu há menos tempo (cor mais quente no gráfico).",
    ]
    return fig, insights, recommendations


def _chart_snapshot(df_snapshot):
    """
    Série temporal: clientes ativos (eixo esquerdo) e prêmio total (eixo direito)
    mês a mês. Evidencia sazonalidade e tendência da carteira.
    """
    if (
        df_snapshot is None
        or df_snapshot.empty
        or "MES_REFERENCIA" not in df_snapshot.columns
    ):
        return _no_data()

    df = df_snapshot.copy().sort_values("MES_REFERENCIA")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(
            x=df["MES_REFERENCIA"],
            y=df["CLIENTES_ATIVOS"],
            mode="lines+markers",
            line=dict(color=AZUL, width=2),
            name="Clientes ativos",
            hovertemplate="%{x}<br>Clientes: %{y}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df["MES_REFERENCIA"],
            y=df["PREMIO_TOTAL"],
            mode="lines+markers",
            line=dict(color=VERDE, width=2),
            name="Prêmio total",
            hovertemplate="%{x}<br>Prêmio: R$ %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_xaxes(title_text="Mês de referência")
    fig.update_yaxes(title_text="Clientes ativos", secondary_y=False)
    fig.update_yaxes(title_text="Prêmio total (R$)", secondary_y=True, showgrid=False)
    _style(fig, height=480)

    mes_max_cli = df.loc[df["CLIENTES_ATIVOS"].idxmax()]
    mes_max_prem = df.loc[df["PREMIO_TOTAL"].idxmax()]

    insights = [
        f"Pico de clientes ativos: <b>{int(mes_max_cli['CLIENTES_ATIVOS'])}</b> "
        f"em <b>{mes_max_cli['MES_REFERENCIA']}</b>.",
        f"Pico de prêmio: <b>{_money(mes_max_prem['PREMIO_TOTAL'])}</b> "
        f"em <b>{mes_max_prem['MES_REFERENCIA']}</b>.",
    ]
    if len(df) >= 13:
        ult = df.iloc[-1]
        ant = df.iloc[-13]
        if ant["TICKET_MEDIO_CLIENTE"]:
            cresc = (
                (ult["TICKET_MEDIO_CLIENTE"] - ant["TICKET_MEDIO_CLIENTE"])
                / ant["TICKET_MEDIO_CLIENTE"]
                * 100
            )
            insights.append(
                f"Ticket médio por cliente variou <b>{cresc:+.1f}%</b> em 12 meses "
                f"({ult['MES_REFERENCIA']} vs {ant['MES_REFERENCIA']})."
            )

    recommendations = [
        "Antecipar ações comerciais nos meses historicamente mais fracos da série.",
        "Investigar o que impulsionou o mês de pico e tentar reproduzir o padrão.",
        "Acompanhar o ticket médio mês a mês como termômetro de qualidade da carteira.",
    ]
    return fig, insights, recommendations


def _chart_abc_comissao(df_abc_com):
    """Pareto por COMISSÃO: concentração de quem de fato remunera a corretora."""
    if (
        df_abc_com is None
        or df_abc_com.empty
        or "TOTAL_COMISSAO" not in df_abc_com.columns
    ):
        return _no_data()

    df = df_abc_com.copy().sort_values("TOTAL_COMISSAO", ascending=False)
    top = df.head(30)
    cor_classe = {"Classe A": VERDE, "Classe B": VERDE_LIMA, "Classe C": LARANJA}
    bar_colors = [
        cor_classe.get(str(c).split(" (")[0], AZUL) for c in top["CURVA_ABC_COMISSAO"]
    ]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=top["CPF_LIMPO"].astype(str),
            y=top["TOTAL_COMISSAO"],
            marker_color=bar_colors,
            name="Comissão",
            hovertemplate="CPF %{x}<br>Comissão: R$ %{y:,.0f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=top["CPF_LIMPO"].astype(str),
            y=top["%_ACUMULADO"] * 100,
            mode="lines+markers",
            line=dict(color=AZUL, width=2),
            name="% acumulado",
            hovertemplate="Acumulado: %{y:.1f}%<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_hline(y=80, line_dash="dash", line_color=LARANJA, secondary_y=True)
    fig.update_xaxes(title_text="Cooperado (top 30 por comissão)", showticklabels=False)
    fig.update_yaxes(title_text="Comissão (R$)", secondary_y=False)
    fig.update_yaxes(
        title_text="% acumulado", secondary_y=True, range=[0, 105], showgrid=False
    )
    _style(fig, height=480)

    n_total = len(df)
    classe_a = df[df["CURVA_ABC_COMISSAO"].astype(str).str.startswith("Classe A")]
    n_a = len(classe_a)
    com_total = df["TOTAL_COMISSAO"].sum()
    insights = [
        f"<b>{_pct(n_a / n_total * 100 if n_total else 0)}</b> dos cooperados ({n_a}) "
        f"concentram ~80% da <b>comissão</b>.",
        f"Comissão total da carteira: <b>{_money(com_total)}</b>.",
        "A concentração por comissão pode diferir da por prêmio — as taxas variam por produto/seguradora.",
    ]
    recommendations = [
        "Priorizar quem mais gera <b>comissão</b> — é a receita real da corretora.",
        "Cruzar com a ABC por prêmio: cliente de alto prêmio e baixa comissão tem margem ruim.",
    ]
    return fig, insights, recommendations


def _chart_margem_comissao(df_partner_com):
    """Barras da taxa de comissão efetiva (comissão/prêmio) por seguradora."""
    if (
        df_partner_com is None
        or df_partner_com.empty
        or "TAXA_COMISSAO_EFETIVA_%" not in df_partner_com.columns
    ):
        return _no_data()

    df = df_partner_com.copy().sort_values("TAXA_COMISSAO_EFETIVA_%", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=df["TAXA_COMISSAO_EFETIVA_%"],
            y=df["SEGURADORA"].astype(str),
            orientation="h",
            marker=dict(
                color=df["TAXA_COMISSAO_EFETIVA_%"],
                colorscale=[[0, VERDE_LIMA], [1, VERDE]],
            ),
            text=[_pct(v) for v in df["TAXA_COMISSAO_EFETIVA_%"]],
            textposition="outside",
            customdata=np.stack(
                [df["TOTAL_COMISSAO"], df["TOTAL_PREMIO_LIQ"]], axis=-1
            ),
            hovertemplate=(
                "%{y}<br>Taxa efetiva: %{x:.1f}%"
                "<br>Comissão: R$ %{customdata[0]:,.0f}"
                "<br>Prêmio: R$ %{customdata[1]:,.0f}<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(autorange="reversed", title_text="")
    fig.update_xaxes(title_text="Taxa de comissão efetiva (%)")
    _style(fig, height=max(420, 32 * len(df)))

    melhor, pior = df.iloc[0], df.iloc[-1]
    soma_prem = df["TOTAL_PREMIO_LIQ"].sum()
    media = (df["TOTAL_COMISSAO"].sum() / soma_prem * 100) if soma_prem > 0 else 0
    insights = [
        f"Melhor margem: <b>{melhor['SEGURADORA']}</b> ({_pct(melhor['TAXA_COMISSAO_EFETIVA_%'])}).",
        f"Pior margem: <b>{pior['SEGURADORA']}</b> ({_pct(pior['TAXA_COMISSAO_EFETIVA_%'])}).",
        f"Taxa de comissão efetiva média da carteira: <b>{_pct(media)}</b>.",
    ]
    recommendations = [
        "Direcionar volume para as seguradoras de maior taxa efetiva.",
        "Renegociar comissionamento com as de menor margem.",
        "Cruzar com o market share por prêmio: parceiro grande em prêmio mas de baixa margem merece atenção.",
    ]
    return fig, insights, recommendations


def _chart_margem_seg_produto(df_sp):
    """
    Dispersão prêmio × taxa efetiva no grão seguradora×produto (bolha = comissão).
    Mostra se o prêmio concentrado numa seguradora vem de produto de alta margem.
    """
    if df_sp is None or df_sp.empty or "TAXA_COMISSAO_EFETIVA_%" not in df_sp.columns:
        return _no_data()

    df = df_sp[df_sp["TOTAL_PREMIO_LIQ"] > 0].copy()
    if df.empty:
        return _no_data()

    df["_label"] = df["SEGURADORA"].astype(str) + " · " + df["PRODUTO"].astype(str)
    max_com = df["TOTAL_COMISSAO"].max()
    sizeref = (2.0 * max_com / (55.0**2)) if max_com > 0 else 1

    fig = go.Figure(
        go.Scatter(
            x=df["TOTAL_PREMIO_LIQ"],
            y=df["TAXA_COMISSAO_EFETIVA_%"],
            mode="markers",
            marker=dict(
                size=df["TOTAL_COMISSAO"],
                sizemode="area",
                sizeref=sizeref,
                sizemin=4,
                color=df["TAXA_COMISSAO_EFETIVA_%"],
                colorscale=[[0, LARANJA], [1, VERDE]],
                showscale=True,
                colorbar=dict(title="Taxa ef. %"),
                line=dict(width=0.5, color="white"),
            ),
            text=df["_label"],
            customdata=np.stack(
                [df["TOTAL_COMISSAO"], df["TOTAL_PREMIO_LIQ"]], axis=-1
            ),
            hovertemplate=(
                "%{text}<br>Prêmio: R$ %{customdata[1]:,.0f}"
                "<br>Comissão: R$ %{customdata[0]:,.0f}"
                "<br>Taxa efetiva: %{y:.1f}%<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="Prêmio líquido — concentração (R$)")
    fig.update_yaxes(title_text="Taxa de comissão efetiva (%)")
    _style(fig, height=540)

    soma_prem = df["TOTAL_PREMIO_LIQ"].sum()
    media = (df["TOTAL_COMISSAO"].sum() / soma_prem * 100) if soma_prem > 0 else 0
    top_prem = df.sort_values("TOTAL_PREMIO_LIQ", ascending=False).iloc[0]
    top_taxa = df.sort_values("TAXA_COMISSAO_EFETIVA_%", ascending=False).iloc[0]
    n_excl = (
        int(df["PRODUTO_EXCLUSIVO_SEGURADORA"].sum())
        if "PRODUTO_EXCLUSIVO_SEGURADORA" in df.columns
        else 0
    )
    insights = [
        f"Maior bloco de prêmio: <b>{top_prem['SEGURADORA']} · {top_prem['PRODUTO']}</b> "
        f"({_money(top_prem['TOTAL_PREMIO_LIQ'])}, taxa {_pct(top_prem['TAXA_COMISSAO_EFETIVA_%'])}).",
        f"Maior taxa efetiva: <b>{top_taxa['SEGURADORA']} · {top_taxa['PRODUTO']}</b> "
        f"({_pct(top_taxa['TAXA_COMISSAO_EFETIVA_%'])}).",
        f"Taxa efetiva média da carteira: <b>{_pct(media)}</b>. "
        f"Combinações com produto exclusivo de uma seguradora: <b>{n_excl}</b>.",
    ]
    recommendations = [
        "Comparar combinações de prêmio parecido e taxa diferente — a de maior taxa é a venda mais rentável.",
        "Produto de alta margem concentrado numa só seguradora: avaliar dependência e poder de negociação.",
        "Direcionar o produto de maior margem (via Mix por Especialidade) a quem ainda não tem.",
    ]
    return fig, insights, recommendations


def _chart_completeness(df_completeness):
    """Diagnóstico de cadastro: % de preenchimento por campo, cor por confiabilidade."""
    if (
        df_completeness is None
        or df_completeness.empty
        or "PREENCHIMENTO_PCT" not in df_completeness.columns
    ):
        return _no_data()

    df = df_completeness.copy().sort_values("PREENCHIMENTO_PCT", ascending=True)
    cor = {
        "Alta": VERDE,
        "Média": VERDE_LIMA,
        "Baixa": LARANJA,
        "Inútil (constante)": "#B0B0B0",
    }
    fig = go.Figure(
        go.Bar(
            x=df["PREENCHIMENTO_PCT"],
            y=df["CAMPO"].astype(str),
            orientation="h",
            marker_color=[cor.get(c, AZUL) for c in df["CONFIABILIDADE"]],
            text=[f"{v:.0f}%" for v in df["PREENCHIMENTO_PCT"]],
            textposition="outside",
            customdata=df["CONFIABILIDADE"],
            hovertemplate="%{y}<br>Preenchimento: %{x:.1f}%<br>%{customdata}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Preenchimento (%)", range=[0, 108])
    fig.update_yaxes(title_text="")
    _style(fig, height=max(440, 26 * len(df)))

    alta = df[df["CONFIABILIDADE"] == "Alta"]["CAMPO"].tolist()
    frageis = df[df["CONFIABILIDADE"].isin(["Baixa", "Inútil (constante)"])][
        "CAMPO"
    ].tolist()
    insights = [
        f"<b>{len(alta)}</b> campos são 100%/alta confiabilidade — base segura para a análise qualitativa.",
        f"<b>{len(frageis)}</b> campos frágeis/inúteis: {', '.join(frageis[:5])}"
        + ("…" if len(frageis) > 5 else "")
        + ".",
        "A própria completude do cadastro já é um diagnóstico para o gerente.",
    ]
    recommendations = [
        "Concentrar a 1ª análise nos campos de alta confiabilidade (especialidade, produto, datas).",
        "Plano de saneamento para geografia e estado civil (preenchimento parcial).",
        "Revisar campos constantes (sem informação) — candidatos a remoção/recaptura.",
    ]
    return fig, insights, recommendations


def _chart_specialty_gaps(df_gaps):
    """Top oportunidades de cross-sell: especialidade × produto com maior lacuna."""
    if (
        df_gaps is None
        or df_gaps.empty
        or "COOPERADOS_SEM_PRODUTO" not in df_gaps.columns
    ):
        return _no_data()

    df = df_gaps.copy().sort_values("COOPERADOS_SEM_PRODUTO", ascending=False).head(20)
    df = df.iloc[::-1]
    rotulo = df["CARACTERÍSTICA"].astype(str) + " — " + df["PRODUTO"].astype(str)
    fig = go.Figure(
        go.Bar(
            x=df["COOPERADOS_SEM_PRODUTO"],
            y=rotulo,
            orientation="h",
            marker=dict(
                color=df["GAP_PCT"], colorscale=[[0, VERDE_LIMA], [1, LARANJA]]
            ),
            customdata=np.stack(
                [df["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"], df["PENETRACAO_PCT"]],
                axis=-1,
            ),
            hovertemplate=(
                "%{y}<br>Sem o produto: %{x}"
                "<br>Base da especialidade: %{customdata[0]}"
                "<br>Penetração atual: %{customdata[1]:.1f}%<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="Cooperados ativos sem o produto (oportunidade)")
    fig.update_yaxes(title_text="")
    _style(fig, height=560)

    top = df.iloc[-1]
    insights = [
        f"Maior lacuna: <b>{top['CARACTERÍSTICA']} — {top['PRODUTO']}</b> "
        f"({int(top['COOPERADOS_SEM_PRODUTO'])} cooperados sem o produto).",
        "Lacunas combinam base grande da especialidade com baixa penetração do produto.",
        "Tudo em contagem — independe de prêmio/comissão.",
    ]
    recommendations = [
        "Priorizar campanhas pelas maiores lacunas absolutas (eixo X).",
        "Cruzar com o rating do cooperado para ordenar a abordagem dentro de cada lacuna.",
    ]
    return fig, insights, recommendations


def _chart_producer(df_prod_perf):
    """
    Performance de produtor: barras de volume (itens) coloridas pela taxa de
    renovação. Quem produz mais × quem retém melhor, num só visual.
    """
    if (
        df_prod_perf is None
        or df_prod_perf.empty
        or "QTD_ITENS" not in df_prod_perf.columns
    ):
        return _no_data()

    # Produtores EXTERNOS (força de vendas real) no gráfico; interno/casa à parte
    if "EH_INTERNO" in df_prod_perf.columns:
        externos = df_prod_perf[~df_prod_perf["EH_INTERNO"]]
        internos = df_prod_perf[df_prod_perf["EH_INTERNO"]]
    else:
        externos, internos = df_prod_perf, df_prod_perf.iloc[0:0]
    if externos.empty:
        return _no_data()

    d = externos.sort_values("QTD_ITENS", ascending=True).copy()
    d["_lbl"] = d["PRODUTOR"].astype(str).str.slice(0, 34)
    # Cor = taxa de renovação JUSTA (só renováveis); cinza onde não há renovável
    taxa_just = (
        d["TAXA_RENOVACAO_RENOVAVEL_%"]
        if "TAXA_RENOVACAO_RENOVAVEL_%" in d.columns
        else d["TAXA_RENOVACAO_%"]
    ).fillna(0)
    fig = go.Figure(
        go.Bar(
            x=d["QTD_ITENS"],
            y=d["_lbl"],
            orientation="h",
            marker=dict(
                color=taxa_just,
                colorscale=[[0, LARANJA], [1, VERDE]],
                showscale=True,
                colorbar=dict(title="Renov.<br>renov. %"),
            ),
            customdata=np.stack(
                [d["QTD_CLIENTES"], taxa_just, d["N_NOVOS"], d["N_RENOVACOES"]], axis=-1
            ),
            hovertemplate=(
                "%{y}<br>Itens: %{x}<br>Clientes: %{customdata[0]}"
                "<br>Taxa renovação (renováveis): %{customdata[1]:.0f}%"
                "<br>Novos: %{customdata[2]} · Renovações: %{customdata[3]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="Itens produzidos")
    fig.update_yaxes(title_text="")
    _style(fig, height=max(440, 30 * len(d)))

    ext_sorted = externos.sort_values("QTD_ITENS", ascending=False)
    top = ext_sorted.iloc[0]
    top3_share = float(ext_sorted.head(3)["SHARE_ITENS_%"].sum())
    ret_col = (
        "TAXA_RENOVACAO_RENOVAVEL_%"
        if "TAXA_RENOVACAO_RENOVAVEL_%" in ext_sorted.columns
        else "TAXA_RENOVACAO_%"
    )
    rel = ext_sorted[
        (
            (
                ext_sorted["APOLICES_RENOVADAS_REN"]
                + ext_sorted["APOLICES_VENCIDAS_REN"]
                >= 10
            )
            if "APOLICES_RENOVADAS_REN" in ext_sorted.columns
            else (ext_sorted["N_RENOVACOES"] + ext_sorted["N_NOVOS"] >= 20)
        )
    ].dropna(subset=[ret_col])
    insights = [
        f"Maior produtor (externo): <b>{top['PRODUTOR']}</b> "
        f"({int(top['QTD_ITENS'])} itens, {int(top['QTD_CLIENTES'])} clientes, "
        f"{top['SHARE_ITENS_%']:.0f}% da produção externa).",
        f"Concentração entre externos: <b>top-3 = {top3_share:.0f}%</b>.",
    ]
    if not rel.empty:
        melhor = rel.sort_values(ret_col, ascending=False).iloc[0]
        pior = rel.sort_values(ret_col).iloc[0]
        insights.append(
            f"Retenção (só renováveis, base ≥10): melhor <b>{melhor['PRODUTOR']}</b> "
            f"({_pct(melhor[ret_col])}) · pior <b>{pior['PRODUTOR']}</b> ({_pct(pior[ret_col])})."
        )
    if not internos.empty:
        n_int = int(internos["QTD_ITENS"].sum())
        insights.append(
            f"Carteira interna (casa, sem produtor): <b>{n_int}</b> itens — avaliada à "
            "parte, fora do ranking (não é força de vendas)."
        )
    recommendations = [
        "Replicar a prática dos produtores de maior taxa de renovação nos demais.",
        "A taxa exibida é só de produtos RENOVÁVEIS (apples-to-apples) — não penaliza "
        "produtor focado em recorrente, cuja 'renovação' tem outra dinâmica.",
        "Cruzar com Acionabilidade por Produtor: baixa cobertura de contato derruba renovação.",
    ]
    return fig, insights, recommendations


# ── Gráficos do track OPERACIONAL / QUALIDADE ─────────────────────────────────
def _chart_dq_resumo(df_resumo):
    """
    Resumo executivo dos testes de qualidade (prêmio zerado, comissão > prêmio,
    inconsistência %, outliers, duplicatas): barras de ocorrências por regra,
    coloridas por severidade. O detalhe registro-a-registro fica no XLSX de DQ.
    """
    if (
        df_resumo is None
        or df_resumo.empty
        or "QTD_REGISTROS_FLAGADOS" not in df_resumo.columns
    ):
        return _no_data("Sem apontamentos de qualidade na base atual.")

    cor_sev = {"CRÍTICO": LARANJA, "ALERTA": "#E8B500", "INFORMATIVO": AZUL}
    d = df_resumo.sort_values("QTD_REGISTROS_FLAGADOS", ascending=True).copy()
    cores = [cor_sev.get(str(s).upper(), AZUL) for s in d.get("SEVERIDADE", "")]
    fig = go.Figure(
        go.Bar(
            x=d["QTD_REGISTROS_FLAGADOS"],
            y=d["REGRA_DQ"].astype(str),
            orientation="h",
            marker_color=cores,
            text=[
                f"{int(q)} ({p:.1f}%)"
                for q, p in zip(d["QTD_REGISTROS_FLAGADOS"], d["PCT_DA_BASE"])
            ],
            textposition="outside",
            customdata=d.get("SEVERIDADE", ""),
            hovertemplate="%{y}<br>Ocorrências: %{x}<br>Severidade: %{customdata}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Registros sinalizados")
    fig.update_yaxes(title_text="")
    _style(fig, height=max(420, 40 * len(d)))

    criticos = d[d.get("SEVERIDADE", "").astype(str).str.upper() == "CRÍTICO"]
    n_crit = int(criticos["QTD_REGISTROS_FLAGADOS"].sum())
    pior = d.sort_values("QTD_REGISTROS_FLAGADOS", ascending=False).iloc[0]
    insights = [
        f"<b>{n_crit}</b> registros em regras CRÍTICAS (prêmio zerado/negativo, "
        "comissão > prêmio, duplicatas) — corrigir na origem.",
        f"Maior volume: <b>{pior['REGRA_DQ']}</b> "
        f"({int(pior['QTD_REGISTROS_FLAGADOS'])} registros, {pior['PCT_DA_BASE']:.1f}% da base).",
        "O motor analítico NÃO corrige — só sinaliza; o saneamento é decisão do negócio.",
    ]
    recommendations = [
        "Priorizar as regras CRÍTICAS: distorcem prêmio/comissão de várias visões comerciais.",
        "Tratar na origem (sistema da corretora), não no relatório — evita reincidência.",
        "Acompanhar a tendência em dq_history.parquet (o nº de apontamentos deve cair).",
    ]
    return fig, insights, recommendations


def _chart_origem_cadastro(df):
    """Barras empilhadas migrado × orgânico por ano — viés de carga histórica."""
    if df is None or df.empty or "ANO_INICIO" not in df.columns:
        return _no_data()
    d = df.dropna(subset=["ANO_INICIO"]).copy()
    anos = d["ANO_INICIO"].astype(int).astype(str)
    fig = go.Figure()
    fig.add_bar(x=anos, y=d.get("Migrado", 0), name="Migrado", marker_color=LARANJA)
    fig.add_bar(x=anos, y=d.get("Orgânico", 0), name="Orgânico", marker_color=VERDE)
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Ano de início de vigência")
    fig.update_yaxes(title_text="Registros")
    _style(fig)

    tot_mig = int(d.get("Migrado", pd.Series(dtype=int)).sum())
    tot = int(d.get("TOTAL", pd.Series(dtype=int)).sum())
    pct = (tot_mig / tot * 100) if tot else 0
    insights = [
        f"<b>{pct:.0f}%</b> da base ({tot_mig:,} de {tot:,}) é carga migrada (USUÁRIO = MIGRACAO).",
        "Os anos iniciais concentram a migração — cohort/safra e somas desse período refletem "
        "migração, não originação real de venda.",
    ]
    recommendations = [
        "Ler cohort/sazonalidade e somas 2024 com ressalva (viés de migração).",
        "Para originação real, analisar só o subconjunto orgânico.",
        "Reduzir dependência de carga histórica padronizando o cadastro orgânico.",
    ]
    return fig, insights, recommendations


def _chart_status_situacao(df):
    """Mapa de calor STATUS_PRODUTO (motor) × SITUAÇÃO (nativa) — concordância."""
    if df is None or df.empty or "STATUS_PRODUTO" not in df.columns:
        return _no_data()
    piv = df.pivot_table(
        index="STATUS_PRODUTO",
        columns="SITUAÇÃO",
        values="QTD_PRODUTOS",
        aggfunc="sum",
        fill_value=0,
    )
    fig = go.Figure(
        go.Heatmap(
            z=piv.values,
            x=[str(c) for c in piv.columns],
            y=[str(i) for i in piv.index],
            colorscale=[[0, "#FFFFFF"], [1, AZUL]],
            text=piv.values,
            texttemplate="%{text}",
            showscale=False,
        )
    )
    fig.update_xaxes(title_text="SITUAÇÃO (status do documento)")
    fig.update_yaxes(title_text="STATUS_PRODUTO (motor de vigência)")
    _style(fig)

    total = df["QTD_PRODUTOS"].sum()
    conc = df[df["CONCORDA"]]["QTD_PRODUTOS"].sum() if "CONCORDA" in df.columns else 0
    pct = (conc / total * 100) if total else 0
    insights = [f"Concordância motor × situação nativa: <b>{pct:.0f}%</b>."]
    disc = (
        df[~df["CONCORDA"]].sort_values("QTD_PRODUTOS", ascending=False)
        if "CONCORDA" in df.columns
        else pd.DataFrame()
    )
    if not disc.empty:
        t = disc.iloc[0]
        insights.append(
            f"Maior divergência: motor <b>{t['STATUS_PRODUTO']}</b> × situação "
            f"<b>{t['SITUAÇÃO']}</b> ({int(t['QTD_PRODUTOS'])} produtos) — candidatos a "
            "problema de cadastro/processo."
        )
    recommendations = [
        "Investigar divergências: SITUAÇÃO Ativa com cancelamento efetivo (ver DQ1), "
        "ou Vencida que era renovação não-linkada (ver DQ2).",
        "Acompanhar a concordância como termômetro de qualidade de cadastro ao longo do tempo.",
    ]
    return fig, insights, recommendations


def _chart_contact_producer(df):
    """Barras de % contatável por produtor (corte b da acionabilidade)."""
    if df is None or df.empty or "PCT_CONTATAVEL" not in df.columns:
        return _no_data()
    d = df.sort_values("PCT_CONTATAVEL", ascending=True).copy()
    d["_lbl"] = d["PRODUTOR"].astype(str).str.slice(0, 34)
    fig = go.Figure(
        go.Bar(
            x=d["PCT_CONTATAVEL"],
            y=d["_lbl"],
            orientation="h",
            marker=dict(
                color=d["PCT_CONTATAVEL"], colorscale=[[0, LARANJA], [1, VERDE]]
            ),
            text=[f"{v:.0f}%" for v in d["PCT_CONTATAVEL"]],
            textposition="outside",
            customdata=np.stack(
                [d["QTD_CLIENTES"], d["PCT_TELEFONE"], d["PCT_EMAIL"]], axis=-1
            ),
            hovertemplate=(
                "%{y}<br>Contatável: %{x:.0f}%<br>Clientes: %{customdata[0]}"
                "<br>Telefone: %{customdata[1]:.0f}% · E-mail: %{customdata[2]:.0f}%<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title_text="% de clientes com telefone OU e-mail")
    fig.update_yaxes(title_text="")
    _style(fig, height=max(420, 30 * len(d)))

    media = (
        (d["CONTATAVEIS"].sum() / d["QTD_CLIENTES"].sum() * 100)
        if d["QTD_CLIENTES"].sum()
        else 0
    )
    rel = d[d["QTD_CLIENTES"] >= 20]  # produtores com carteira relevante
    pior = rel.sort_values("PCT_CONTATAVEL").iloc[0] if not rel.empty else d.iloc[0]
    insights = [
        f"Acionabilidade média da carteira: <b>{media:.0f}%</b> dos clientes têm algum canal.",
        f"Pior cobertura (carteira ≥20): <b>{pior['PRODUTOR']}</b> "
        f"({pior['PCT_CONTATAVEL']:.0f}% contatável, {int(pior['QTD_CLIENTES'])} clientes).",
    ]
    recommendations = [
        "Direcionar esforço de enriquecimento de cadastro aos produtores de menor cobertura.",
        "Para campanha de e-mail, usar EMAIL_ACIONAVEL (tem e-mail E consentimento), não só TEM_EMAIL.",
        "Cruzar com a Agenda de Renovações: baixa acionabilidade + renovação próxima = risco real.",
    ]
    return fig, insights, recommendations


# ── Gráficos do track MARKETING (base/mercado: cliente × prospect + demografia) ─
def _bar_cli_prospect(d, key, eixo, horizontal=False, top=None, height=460):
    """Barras empilhadas Clientes × Prospects por uma chave categórica."""
    d = d.copy()
    if top:
        d = d.sort_values("QTD_COOPERADOS", ascending=False).head(top)
    cats = d[key].astype(str)
    fig = go.Figure()
    if horizontal:
        fig.add_bar(
            y=cats,
            x=d["QTD_CLIENTES"],
            name="Clientes",
            orientation="h",
            marker_color=VERDE,
        )
        fig.add_bar(
            y=cats,
            x=d["QTD_PROSPECTS"],
            name="Prospects",
            orientation="h",
            marker_color=AZUL,
        )
        fig.update_yaxes(autorange="reversed", title_text="")
        fig.update_xaxes(title_text=eixo)
    else:
        fig.add_bar(x=cats, y=d["QTD_CLIENTES"], name="Clientes", marker_color=VERDE)
        fig.add_bar(x=cats, y=d["QTD_PROSPECTS"], name="Prospects", marker_color=AZUL)
        fig.update_xaxes(title_text=eixo)
        fig.update_yaxes(title_text="Cooperados")
    fig.update_layout(barmode="stack")
    _style(fig, height=height)
    return fig


def _chart_base_status(df):
    """Status comercial da base: ATIVO / INATIVO / PROSPECT (total e %)."""
    if df is None or df.empty or "STATUS" not in df.columns:
        return _no_data()
    cor = {"ATIVO": VERDE, "INATIVO": LARANJA, "PROSPECT": AZUL}
    d = df.copy()
    fig = go.Figure(
        go.Bar(
            x=d["STATUS"],
            y=d["QTD_COOPERADOS"],
            marker_color=[cor.get(s, AZUL) for s in d["STATUS"]],
            text=[
                f"{int(q)} ({p:.1f}%)"
                for q, p in zip(d["QTD_COOPERADOS"], d["PCT_DA_BASE"])
            ],
            textposition="outside",
        )
    )
    fig.update_xaxes(title_text="Status comercial")
    fig.update_yaxes(title_text="Cooperados")
    _style(fig)
    total = int(d["QTD_COOPERADOS"].sum())
    pro = d[d["STATUS"] == "PROSPECT"]
    pct_pro = float(pro["PCT_DA_BASE"].iloc[0]) if not pro.empty else 0
    insights = [
        f"Base total: <b>{total}</b> cooperados.",
        f"<b>{pct_pro:.0f}%</b> são PROSPECTS (nunca compraram) — o maior potencial de conversão.",
        "O Comercial (grão de produção) não enxerga os prospects — por isso este track.",
    ]
    recs = [
        "Separar a estratégia: aquisição (prospects) ≠ reativação (inativos).",
        "Direcionar a aquisição pelas distribuições de especialidade e idade ao lado.",
    ]
    return fig, insights, recs


def _chart_specialty_dist(df):
    """Distribuição por especialidade (cliente × prospect) — top 15."""
    if df is None or df.empty or "ESPECIALIDADE" not in df.columns:
        return _no_data()
    d = df[df["ESPECIALIDADE"] != "Não Informado"]
    if d.empty:
        d = df
    n = min(15, len(d))
    fig = _bar_cli_prospect(
        d,
        "ESPECIALIDADE",
        "Cooperados",
        horizontal=True,
        top=15,
        height=max(440, 30 * n),
    )
    top = d.sort_values("QTD_COOPERADOS", ascending=False).iloc[0]
    mais_pro = d.sort_values("QTD_PROSPECTS", ascending=False).iloc[0]
    insights = [
        f"Especialidade mais numerosa: <b>{top['ESPECIALIDADE']}</b> "
        f"({int(top['QTD_COOPERADOS'])} cooperados).",
        f"Maior bolsão de prospects: <b>{mais_pro['ESPECIALIDADE']}</b> "
        f"({int(mais_pro['QTD_PROSPECTS'])} prospects, "
        f"{mais_pro['PCT_PROSPECT_NO_GRUPO']:.0f}% do grupo) — alvo de campanha.",
    ]
    recs = [
        "Priorizar especialidades com muitos prospects E afinidade com a carteira atual.",
        "Cruzar com o Mix por Especialidade (Comercial) para saber qual produto ofertar.",
    ]
    return fig, insights, recs


def _chart_birth_decade(df):
    """Concentração por década de nascimento (cliente × prospect)."""
    if df is None or df.empty or "DECADA_NASCIMENTO" not in df.columns:
        return _no_data()
    d = df[df["DECADA_NASCIMENTO"] != "Não Informada"]
    if d.empty:
        return _no_data()
    fig = _bar_cli_prospect(d, "DECADA_NASCIMENTO", "Década de nascimento")
    top = d.sort_values("QTD_COOPERADOS", ascending=False).iloc[0]
    insights = [
        f"Maior concentração: nascidos nos anos <b>{top['DECADA_NASCIMENTO']}</b> "
        f"({int(top['QTD_COOPERADOS'])} cooperados, {top['PCT_DA_BASE']:.0f}% da base).",
        "A coorte de nascimento orienta tom e canal da comunicação.",
    ]
    recs = ["Adequar mensagem/canal por geração; cruzar com a faixa etária ao lado."]
    return fig, insights, recs


def _chart_age_bands(df):
    """Distribuição por faixa etária (Até 40 / 41 a 59 / 60+) — cliente × prospect."""
    if df is None or df.empty or "FAIXA_ETARIA_3" not in df.columns:
        return _no_data()
    d = df[df["FAIXA_ETARIA_3"] != "Não Informada"]
    if d.empty:
        d = df
    fig = _bar_cli_prospect(d, "FAIXA_ETARIA_3", "Faixa etária")
    top = d.sort_values("QTD_COOPERADOS", ascending=False).iloc[0]
    insights = [
        f"Faixa predominante: <b>{top['FAIXA_ETARIA_3']}</b> "
        f"({int(top['QTD_COOPERADOS'])} cooperados, {top['PCT_DA_BASE']:.0f}% da base).",
    ]
    pro60 = d[d["FAIXA_ETARIA_3"] == "60+"]
    if not pro60.empty:
        insights.append(
            f"Faixa 60+: <b>{int(pro60['QTD_PROSPECTS'].iloc[0])}</b> prospects — produtos "
            "de perfil (vida/previdência/saúde) podem ter aderência."
        )
    recs = ["Segmentar oferta por faixa: produto e abordagem mudam com a idade."]
    return fig, insights, recs


def _chart_age_histogram(df_base):
    """Histograma de idade da base, sobreposto Clientes × Prospects."""
    if df_base is None or df_base.empty or "IDADE" not in df_base.columns:
        return _no_data()
    d = df_base.dropna(subset=["IDADE"])
    if d.empty:
        return _no_data()
    cli = d[~d["EH_PROSPECT"]]["IDADE"]
    pro = d[d["EH_PROSPECT"]]["IDADE"]
    fig = go.Figure()
    fig.add_histogram(
        x=cli, name="Clientes", marker_color=VERDE, opacity=0.7, xbins=dict(size=5)
    )
    fig.add_histogram(
        x=pro, name="Prospects", marker_color=AZUL, opacity=0.6, xbins=dict(size=5)
    )
    fig.update_layout(barmode="overlay")
    fig.update_xaxes(title_text="Idade (anos)")
    fig.update_yaxes(title_text="Cooperados")
    _style(fig)
    idades = d["IDADE"]
    insights = [
        f"Idade média da base: <b>{idades.mean():.0f}</b> anos "
        f"(mediana {idades.median():.0f}).",
        f"Prospects: idade média <b>{pro.mean():.0f}</b> vs clientes <b>{cli.mean():.0f}</b> "
        "— se diferem, a comunicação de aquisição deve mirar a faixa dos prospects.",
    ]
    recs = ["Calibrar persona e canal pela distribuição etária real dos prospects."]
    return fig, insights, recs


def _chart_acquisition_targets(df):
    """Alvos de aquisição: prospects por especialidade + produto a ofertar (item 1)."""
    if df is None or df.empty or "QTD_PROSPECTS" not in df.columns:
        return _no_data()
    d = df[df["ESPECIALIDADE"] != "Não Informado"]
    if d.empty:
        d = df
    d = d.sort_values("QTD_PROSPECTS", ascending=False).head(15)
    customdata = list(zip(d["QTD_CLIENTES"], d.get("PRODUTOS_RECOMENDADOS", "")))
    fig = go.Figure(
        go.Bar(
            y=d["ESPECIALIDADE"].astype(str),
            x=d["QTD_PROSPECTS"],
            orientation="h",
            marker_color=AZUL,
            text=d["QTD_PROSPECTS"],
            textposition="outside",
            customdata=customdata,
            hovertemplate=(
                "<b>%{y}</b><br>Prospects: %{x}<br>"
                "Clientes atuais: %{customdata[0]}<br>"
                "Ofertar: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(autorange="reversed", title_text="")
    fig.update_xaxes(title_text="Prospects (mercado a conquistar)")
    _style(fig, height=max(440, 32 * len(d)))
    top = d.iloc[0]
    prod = str(top.get("PRODUTOS_RECOMENDADOS", "—"))
    insights = [
        f"Maior alvo de aquisição: <b>{top['ESPECIALIDADE']}</b> "
        f"({int(top['QTD_PROSPECTS'])} prospects).",
        f"Produto(s) com mais aderência nessa especialidade (entre clientes atuais): "
        f"<b>{prod}</b>.",
        "A penetração vem do Mix por Especialidade (Comercial): o que já vende ao perfil "
        "é a oferta natural para os prospects do mesmo perfil.",
    ]
    recs = [
        "Montar campanha por especialidade ofertando o produto de maior penetração da carteira.",
        "Priorizar especialidades que somam muitos prospects E alta aderência de produto.",
        "Cruzar com a audiência acionável (e-mail + consentimento) para dimensionar o alcance.",
    ]
    return fig, insights, recs


def _chart_reachable_audience(df):
    """Audiência de campanha: prospects vs alcançáveis por e-mail (item 2)."""
    if df is None or df.empty or "AUDIENCIA_EMAIL" not in df.columns:
        return _no_data()
    tot_pro = int(df["QTD_PROSPECTS"].sum())
    tot_aud = int(df["AUDIENCIA_EMAIL"].sum())
    pct = (tot_aud / tot_pro * 100) if tot_pro else 0

    d = df[df["ESPECIALIDADE"] != "Não Informado"]
    if d.empty:
        d = df
    d = d.sort_values("QTD_PROSPECTS", ascending=False).head(12)
    cats = d["ESPECIALIDADE"].astype(str)
    fig = go.Figure()
    fig.add_bar(
        y=cats,
        x=d["QTD_PROSPECTS"],
        name="Prospects",
        orientation="h",
        marker_color="#C9D6D7",
    )
    fig.add_bar(
        y=cats,
        x=d["AUDIENCIA_EMAIL"],
        name="Alcançáveis por e-mail",
        orientation="h",
        marker_color=VERDE,
    )
    fig.update_layout(barmode="overlay")
    fig.update_yaxes(autorange="reversed", title_text="")
    fig.update_xaxes(title_text="Prospects")
    _style(fig, height=max(440, 34 * len(d)))
    insights = [
        f"Audiência real de e-mail marketing: <b>{tot_aud}</b> prospects "
        f"(<b>{pct:.0f}%</b> dos {tot_pro}) têm e-mail E consentimento.",
        f"Os outros <b>{tot_pro - tot_aud}</b> prospects estão fora do alcance por e-mail "
        "(sem e-mail ou sem consentimento) — exigem outro canal ou enriquecimento de cadastro.",
    ]
    recs = [
        "Dimensionar a campanha de e-mail pela audiência acionável, não pela base bruta.",
        "Para os não-alcançáveis: priorizar coleta de e-mail/consentimento (LGPD) ou usar telefone.",
        "Concentrar o disparo nas especialidades com maior audiência absoluta.",
    ]
    return fig, insights, recs


def _chart_persona(df, key, eixo):
    """Distribuição de uma persona (sexo/estado civil/tipo) — cliente × prospect."""
    if df is None or df.empty or key not in df.columns:
        return _no_data()
    d = df[df[key] != "Não Informado"]
    informado = not d.empty
    if not informado:
        d = df
    fig = _bar_cli_prospect(
        d, key, eixo, horizontal=True, top=12, height=max(380, 40 * len(d))
    )
    top = d.sort_values("QTD_COOPERADOS", ascending=False).iloc[0]
    insights = [
        f"Grupo predominante: <b>{top[key]}</b> "
        f"({int(top['QTD_COOPERADOS'])} cooperados, {top['PCT_DA_BASE']:.0f}% da base)."
    ]
    ni = df[df[key] == "Não Informado"]
    if not ni.empty:
        insights.append(
            f"⚠ <b>{int(ni['QTD_COOPERADOS'].iloc[0])}</b> sem o campo preenchido "
            f"({ni['PCT_DA_BASE'].iloc[0]:.0f}%) — interpretar com cautela."
        )
    recs = [
        "Calibrar mensagem e oferta por segmento; tratar 'Não Informado' como gap de cadastro."
    ]
    return fig, insights, recs


# ── Item 4: roadmap de dados a coletar (página estática, sem builder de dados) ──
GROWTH_ROADMAP = [
    (
        "Origem do lead",
        "De onde veio cada prospect (indicação, evento, site, parceria).",
        "Capturar o canal de aquisição no cadastro/CRM.",
    ),
    (
        "Engajamento de campanha",
        "Aberturas, cliques e respostas por disparo.",
        "Integrar a ferramenta de e-mail marketing (eventos por contato).",
    ),
    (
        "Motivos de não-conversão",
        "Por que um prospect não fechou (preço, timing, concorrente).",
        "Registrar o motivo de perda no funil comercial.",
    ),
    (
        "Renda / porte real",
        "Capacidade de compra confiável (hoje RENDA/PROFISSÃO são lixo).",
        "Sanear ou recoletar renda; enriquecer com fonte externa.",
    ),
    (
        "Share of wallet externo",
        "Quais seguros o cooperado já tem fora da corretora.",
        "Pesquisa/declaração do cliente ou enriquecimento de mercado.",
    ),
    (
        "NPS / indicação",
        "Satisfação e propensão a indicar (motor de boca a boca).",
        "Rodar pesquisa NPS periódica e registrar indicações.",
    ),
]


def _render_growth_roadmap():
    """HTML estático (cards) do roadmap de dados a coletar — não há dado p/ calcular hoje."""
    cards = "".join(
        f'<div class="card"><span class="num">A COLETAR</span><h3>{t}</h3>'
        f'<p>{desc}</p><p class="how">▸ {how}</p></div>'
        for t, desc, how in GROWTH_ROADMAP
    )
    return ROADMAP_TEMPLATE.format(
        title="Growth — Dados a Coletar",
        subtitle="Roadmap de métricas futuras: não há dado para calcular hoje — é a lista do que capturar",
        cards=cards,
        accent=AZUL,
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


def _render_index(title, subtitle, cards, accent):
    """
    Monta o portal de navegação de um público. `cards` = lista de
    (filename, num, title, subtitle) — um card-link por HTML gerado.
    """
    cards_html = "".join(
        f'<a class="card" href="{fn}">'
        f'<span class="num">{num}</span><h3>{t}</h3><p>{s}</p>'
        f'<span class="go">Abrir →</span></a>'
        for fn, num, t, s in cards
    )
    return INDEX_TEMPLATE.format(
        title=title,
        subtitle=subtitle,
        cards=cards_html,
        accent=accent,
        timestamp=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


# ── Entry point ───────────────────────────────────────────────────────────────
def build_all_html_reports(
    df_abc,
    df_partner,
    df_specialty,
    df_prod_status,
    df_renewal,
    df_winback,
    df_snapshot,
    com_dir,
    oper_dir,
    df_abc_comissao=None,
    df_partner_comissao=None,
    df_completeness=None,
    df_specialty_gaps=None,
    df_margem_seg_produto=None,
    df_origem_cadastro=None,
    df_status_situacao=None,
    df_contact_producer=None,
    df_producer_perf=None,
    df_dq_resumo=None,
    mkt_dir=None,
    df_base_status=None,
    df_specialty_dist=None,
    df_birth_decade=None,
    df_age_bands=None,
    df_marketing_base=None,
    df_acquisition_targets=None,
    df_reachable_audience=None,
    df_sex_dist=None,
    df_marital_dist=None,
    df_client_type_dist=None,
    root_dir=None,
):
    """
    Orquestra a geração de todos os HTMLs de storytelling, **segmentados por público**:
    visuais comerciais vão para `com_dir`, operacionais/qualidade para `oper_dir`
    (último campo de cada tupla: "com" | "oper"). Cada visual roda em try/except
    isolado — erro em um não interrompe os demais. Retorna a lista de Paths gerados.
    """
    visuals = [
        (
            "01_curva_abc.html",
            "Curva ABC — Concentração de Receita",
            "Pareto dos cooperados por prêmio líquido acumulado",
            lambda: _chart_abc(df_abc),
            "Curva_ABC.xlsx",
            "com",
        ),
        (
            "02_market_share.html",
            "Market Share de Seguradoras",
            "Volume de prêmio e participação relativa por parceiro",
            lambda: _chart_partner(df_partner),
            "Market_Share.xlsx",
            "com",
        ),
        (
            "03_mix_especialidade.html",
            "Mix por Especialidade Médica",
            "Penetração de cada produto por grupo de especialidade",
            lambda: _chart_specialty(df_specialty),
            "Mix_Especialidade.xlsx",
            "com",
        ),
        (
            "04_cross_sell.html",
            "Oportunidades de Cross-sell",
            "Co-posse de produtos entre cooperados ativos",
            lambda: _chart_cross_sell(df_prod_status),
            "Calculadora_Produtos.xlsx",
            "com",
        ),
        (
            "05_agenda_renovacoes.html",
            "Agenda de Renovações — 90 dias",
            "Apólices renováveis vencendo por faixa de urgência",
            lambda: _chart_renewal(df_renewal),
            "Agenda_Renovacoes.xlsx",
            "com",
        ),
        (
            "06_winback.html",
            "Win-Back — Reativação de Inativos",
            "Top 20 ex-clientes por prêmio histórico e tempo inativo",
            lambda: _chart_winback(df_winback),
            "Win_Back.xlsx",
            "com",
        ),
        (
            "07_snapshot_mensal.html",
            "Snapshot Mensal da Carteira",
            "Evolução de clientes ativos e prêmio total mês a mês",
            lambda: _chart_snapshot(df_snapshot),
            "Snapshot_Mensal.xlsx",
            "com",
        ),
        (
            "08_curva_abc_comissao.html",
            "Curva ABC por Comissão",
            "Concentração da comissão — o que a corretora de fato recebe",
            lambda: _chart_abc_comissao(df_abc_comissao),
            "Curva_ABC_Comissao.xlsx",
            "com",
        ),
        (
            "09_margem_comissao.html",
            "Margem — Taxa de Comissão Efetiva",
            "Comissão / prêmio por seguradora (qual parceiro paga melhor)",
            lambda: _chart_margem_comissao(df_partner_comissao),
            "Margem_Comissao_Seguradora.xlsx",
            "com",
        ),
        (
            "12_margem_comissao_seg_produto.html",
            "Margem — Seguradora × Produto",
            "Prêmio × taxa efetiva por combinação (a concentração é de alta margem?)",
            lambda: _chart_margem_seg_produto(df_margem_seg_produto),
            "Margem_Comissao_Seg_Produto.xlsx",
            "com",
        ),
        (
            "16_performance_produtor.html",
            "Performance de Produtor",
            "Volume × retenção por produtor (quem produz mais e quem retém melhor)",
            lambda: _chart_producer(df_producer_perf),
            "Performance_Produtor.xlsx",
            "com",
        ),
        (
            "11_crosssell_gaps.html",
            "Cross-sell — Lacunas por Especialidade",
            "Cooperados ativos da especialidade sem o produto (oportunidade, sem valor)",
            lambda: _chart_specialty_gaps(df_specialty_gaps),
            "Mix_Especialidade.xlsx",
            "com",
        ),
        # ── Operacional / Qualidade ──
        (
            "10_completude_cadastro.html",
            "Completude do Cadastro",
            "Diagnóstico de preenchimento por campo (base da análise qualitativa)",
            lambda: _chart_completeness(df_completeness),
            "Completude_Cadastro.xlsx",
            "oper",
        ),
        (
            "13_origem_cadastro.html",
            "Origem do Cadastro — Migrado × Orgânico",
            "Quanto da base é carga histórica (e por que isso enviesa as séries)",
            lambda: _chart_origem_cadastro(df_origem_cadastro),
            "Origem_Cadastro.xlsx",
            "oper",
        ),
        (
            "14_status_vs_situacao.html",
            "Status do Motor × Situação Nativa",
            "Concordância entre o status calculado e a SITUAÇÃO do documento",
            lambda: _chart_status_situacao(df_status_situacao),
            "Status_vs_Situacao.xlsx",
            "oper",
        ),
        (
            "15_acionabilidade_produtor.html",
            "Acionabilidade por Produtor",
            "% de clientes com telefone/e-mail por produtor (qualidade de cadastro)",
            lambda: _chart_contact_producer(df_contact_producer),
            "Acionabilidade_Produtor.xlsx",
            "oper",
        ),
        (
            "16_qualidade_dados_dq.html",
            "Qualidade de Dados — Testes (DQ)",
            "Prêmio zerado, comissão > prêmio, inconsistência %, outliers, duplicatas",
            lambda: _chart_dq_resumo(df_dq_resumo),
            (
                "../DQ_Raio_X_Cooperados.xlsx",
                "DQ_Raio_X_Cooperados.xlsx",
                "Todas as ocorrências, registro a registro por regra, em",
            ),
            "oper",
        ),
        # ── Marketing (base/mercado: cliente × prospect + demografia) ──
        (
            "01_status_base.html",
            "Status Comercial da Base",
            "Composição da base de cadastro: ATIVO × INATIVO × PROSPECT",
            lambda: _chart_base_status(df_base_status),
            "Status_Base.xlsx",
            "mkt",
        ),
        (
            "02_especialidade.html",
            "Distribuição por Especialidade",
            "Cooperados por CARACTERÍSTICA, comparando clientes × prospects",
            lambda: _chart_specialty_dist(df_specialty_dist),
            "Distribuicao_Especialidade.xlsx",
            "mkt",
        ),
        (
            "03_decada_nascimento.html",
            "Concentração por Década de Nascimento",
            "Coortes geracionais da base (clientes × prospects)",
            lambda: _chart_birth_decade(df_birth_decade),
            "Decada_Nascimento.xlsx",
            "mkt",
        ),
        (
            "04_faixa_etaria.html",
            "Distribuição por Faixa Etária",
            "Até 40 · 41 a 59 · 60+ (clientes × prospects)",
            lambda: _chart_age_bands(df_age_bands),
            "Faixa_Etaria.xlsx",
            "mkt",
        ),
        (
            "05_histograma_idade.html",
            "Histograma de Idade",
            "Distribuição etária da base, sobreposto clientes × prospects",
            lambda: _chart_age_histogram(df_marketing_base),
            "Status_Base.xlsx",
            "mkt",
        ),
        (
            "06_alvos_aquisicao.html",
            "Alvos de Aquisição (Prospects × Produto)",
            "Por especialidade: prospects a conquistar + produto que mais "
            "pega no perfil",
            lambda: _chart_acquisition_targets(df_acquisition_targets),
            "Alvos_Aquisicao.xlsx",
            "mkt",
        ),
        (
            "07_audiencia_campanha.html",
            "Audiência de Campanha (E-mail Acionável)",
            "Prospects realmente alcançáveis: e-mail + consentimento",
            lambda: _chart_reachable_audience(df_reachable_audience),
            "Audiencia_Campanha.xlsx",
            "mkt",
        ),
        (
            "08_personas_sexo.html",
            "Personas — Sexo",
            "Distribuição por sexo (clientes × prospects)",
            lambda: _chart_persona(df_sex_dist, "SEXO_LABEL", "Cooperados"),
            "Personas_Sexo.xlsx",
            "mkt",
        ),
        (
            "09_personas_estado_civil.html",
            "Personas — Estado Civil",
            "Distribuição por estado civil (campo ~41% preenchido)",
            lambda: _chart_persona(df_marital_dist, "ESTADO_CIVIL", "Cooperados"),
            "Personas_Estado_Civil.xlsx",
            "mkt",
        ),
        (
            "10_personas_tipo.html",
            "Personas — Tipo de Cliente",
            "Distribuição por tipo de cliente (clientes × prospects)",
            lambda: _chart_persona(df_client_type_dist, "TIPO_CLIENTE", "Cooperados"),
            "Personas_Tipo.xlsx",
            "mkt",
        ),
    ]

    dirs = {"com": com_dir, "oper": oper_dir, "mkt": mkt_dir}
    saved = []
    index_cards = {"com": [], "oper": [], "mkt": []}
    for filename, title, subtitle, chart_fn, audit_ref, audience in visuals:
        if dirs.get(audience) is None:
            continue  # público não solicitado nesta execução
        try:
            fig, insights, recs = chart_fn()
            html = render_html_report(title, subtitle, fig, insights, recs, audit_ref)
            path = save_report(html, filename, dirs[audience])
            saved.append(path)
            num = filename.split("_", 1)[0]  # prefixo numérico do arquivo
            index_cards[audience].append((filename, num, title, subtitle))
            print(f"  ok {audience}/{filename}")
        except Exception as e:
            print(f"  falha {filename}: {e}")

    # Item 4: roadmap de growth (página estática, sem builder de dados) — só Marketing
    if mkt_dir is not None:
        try:
            roadmap_html = _render_growth_roadmap()
            fn = "11_growth_roadmap.html"
            saved.append(save_report(roadmap_html, fn, mkt_dir))
            index_cards["mkt"].append(
                (fn, "11", "Growth — Dados a Coletar", "Roadmap de métricas futuras")
            )
            print(f"  ok mkt/{fn} (roadmap estático)")
        except Exception as e:
            print(f"  falha 11_growth_roadmap.html: {e}")

    # Portais de navegação (índice) — um por público, consolidando seus HTMLs
    portais = {
        "com": (
            "Painel Comercial — Raio X Cooperados",
            "Vendas · CRM · Margens",
            VERDE,
        ),
        "oper": (
            "Painel Operacional / Qualidade — Raio X Cooperados",
            "Cadastro · Processo · Qualidade de dados",
            LARANJA,
        ),
        "mkt": (
            "Painel Marketing — Raio X Cooperados",
            "Base · Prospects · Demografia",
            AZUL,
        ),
    }
    for aud, cards in index_cards.items():
        if not cards:
            continue
        # ordena pelo prefixo numérico do arquivo
        cards_ord = sorted(cards, key=lambda c: int(c[1]) if c[1].isdigit() else 999)
        titulo, sub, accent = portais[aud]
        html = _render_index(titulo, sub, cards_ord, accent)
        saved.append(save_report(html, "index.html", dirs[aud]))
        print(f"  ok {aud}/index.html (portal de navegação)")

    # Índice CENTRAL na raiz: linka os painéis (mantém os individuais)
    if root_dir is not None:
        root_dir = Path(root_dir)
        portal_cards = []
        for aud in ("com", "oper", "mkt"):
            if not index_cards[aud] or dirs.get(aud) is None:
                continue
            href = (Path(dirs[aud]) / "index.html").relative_to(root_dir).as_posix()
            titulo, sub, _ = portais[aud]
            portal_cards.append((href, "PAINEL", titulo, sub))
        if portal_cards:
            html = _render_index(
                "Raio X Cooperados — Índice Central",
                "Escolha o painel: Comercial · Operacional/Qualidade · Marketing",
                portal_cards,
                AZUL,
            )
            saved.append(save_report(html, "index.html", root_dir))
            print("  ok index.html central (raiz)")

    return saved
