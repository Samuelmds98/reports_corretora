"""
app/lib/registry.py

Registry das visões do app (decisão D1=A): a "lista de quais gráficos por track"
vive aqui, no app, importando os `_chart_*` de `src.report_html` sem tocá-los. A
lógica de cada gráfico permanece de fonte única (report_html); só a orquestração
de qual parquet alimenta qual gráfico é declarada aqui.

Cada visão: key, título, subtítulo, track, `loader` (-> DataFrame), `chart`
(DataFrame -> (fig, insights, recs)) e `audit` (Path do workbook de lastro, ou None).
"""

import sys
from pathlib import Path

# Garante que `src` seja importável quando o Streamlit roda um script de página.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.lib.data import OUTPUTS, audit_file, load_dq_resumo, load_parquet
from src.report_html import (  # noqa: E402  (após ajuste de sys.path)
    _chart_abc, _chart_abc_comissao, _chart_acquisition_targets,
    _chart_age_bands, _chart_age_histogram, _chart_base_status,
    _chart_birth_decade, _chart_completeness, _chart_contact_producer,
    _chart_cross_sell, _chart_dq_resumo, _chart_margem_comissao,
    _chart_margem_seg_produto, _chart_origem_cadastro, _chart_partner,
    _chart_persona, _chart_producer, _chart_reachable_audience, _chart_renewal,
    _chart_snapshot, _chart_specialty, _chart_specialty_dist,
    _chart_specialty_gaps, _chart_status_situacao, _chart_winback)


def _pq(track, name):
    """Loader de uma tabela parquet (lazy)."""
    return lambda: load_parquet(track, name)


def _visao(key, title, subtitle, track, chart, loader, audit):
    return {
        "key": key,
        "title": title,
        "subtitle": subtitle,
        "track": track,
        "chart": chart,
        "loader": loader,
        "audit": audit,
    }


# ── Comercial ─────────────────────────────────────────────────────────────────
_COMERCIAL = [
    _visao(
        "com_abc",
        "Curva ABC — Concentração de Receita",
        "Pareto dos cooperados por prêmio líquido acumulado",
        "comercial",
        _chart_abc,
        _pq("comercial", "curva_abc"),
        audit_file("comercial", "Curva_ABC.xlsx"),
    ),
    _visao(
        "com_share",
        "Market Share de Seguradoras",
        "Volume de prêmio e participação relativa por parceiro",
        "comercial",
        _chart_partner,
        _pq("comercial", "market_share"),
        audit_file("comercial", "Market_Share.xlsx"),
    ),
    _visao(
        "com_mix",
        "Mix por Especialidade Médica",
        "Penetração de cada produto por grupo de especialidade",
        "comercial",
        _chart_specialty,
        _pq("comercial", "mix_especialidade"),
        audit_file("comercial", "Mix_Especialidade.xlsx"),
    ),
    _visao(
        "com_cross",
        "Oportunidades de Cross-sell",
        "Co-posse de produtos entre cooperados ativos",
        "comercial",
        _chart_cross_sell,
        _pq("comercial", "producao_status"),
        audit_file("comercial", "Calculadora_Produtos.xlsx"),
    ),
    _visao(
        "com_renov",
        "Agenda de Renovações — 90 dias",
        "Apólices renováveis vencendo por faixa de urgência",
        "comercial",
        _chart_renewal,
        _pq("comercial", "agenda_renovacoes"),
        audit_file("comercial", "Agenda_Renovacoes.xlsx"),
    ),
    _visao(
        "com_winback",
        "Win-Back — Reativação de Inativos",
        "Top ex-clientes por prêmio histórico e tempo inativo",
        "comercial",
        _chart_winback,
        _pq("comercial", "winback"),
        audit_file("comercial", "Win_Back.xlsx"),
    ),
    _visao(
        "com_snap",
        "Snapshot Mensal da Carteira",
        "Evolução de clientes ativos e prêmio total mês a mês",
        "comercial",
        _chart_snapshot,
        _pq("comercial", "snapshot_mensal"),
        audit_file("comercial", "Snapshot_Mensal.xlsx"),
    ),
    _visao(
        "com_abc_com",
        "Curva ABC por Comissão",
        "Concentração da comissão — o que a corretora de fato recebe",
        "comercial",
        _chart_abc_comissao,
        _pq("comercial", "curva_abc_comissao"),
        audit_file("comercial", "Curva_ABC_Comissao.xlsx"),
    ),
    _visao(
        "com_margem",
        "Margem — Taxa de Comissão Efetiva",
        "Comissão / prêmio por seguradora (qual parceiro paga melhor)",
        "comercial",
        _chart_margem_comissao,
        _pq("comercial", "margem_comissao_seguradora"),
        audit_file("comercial", "Margem_Comissao_Seguradora.xlsx"),
    ),
    _visao(
        "com_margem_sp",
        "Margem — Seguradora × Produto",
        "Prêmio × taxa efetiva por combinação",
        "comercial",
        _chart_margem_seg_produto,
        _pq("comercial", "margem_comissao_seg_produto"),
        audit_file("comercial", "Margem_Comissao_Seg_Produto.xlsx"),
    ),
    _visao(
        "com_prod",
        "Performance de Produtor",
        "Volume × retenção por produtor",
        "comercial",
        _chart_producer,
        _pq("comercial", "performance_produtor"),
        audit_file("comercial", "Performance_Produtor.xlsx"),
    ),
    _visao(
        "com_gaps",
        "Cross-sell — Lacunas por Especialidade",
        "Cooperados ativos da especialidade sem o produto (oportunidade)",
        "comercial",
        _chart_specialty_gaps,
        _pq("comercial", "crosssell_gaps"),
        audit_file("comercial", "Mix_Especialidade.xlsx"),
    ),
]

# ── Operacional / Qualidade ───────────────────────────────────────────────────
_OPERACIONAL = [
    _visao(
        "op_compl",
        "Completude do Cadastro",
        "Diagnóstico de preenchimento por campo",
        "operacional",
        _chart_completeness,
        _pq("operacional", "completude_cadastro"),
        audit_file("operacional", "Completude_Cadastro.xlsx"),
    ),
    _visao(
        "op_origem",
        "Origem do Cadastro — Migrado × Orgânico",
        "Quanto da base é carga histórica (e por que enviesa as séries)",
        "operacional",
        _chart_origem_cadastro,
        _pq("operacional", "origem_cadastro"),
        audit_file("operacional", "Origem_Cadastro.xlsx"),
    ),
    _visao(
        "op_status_sit",
        "Status do Motor × Situação Nativa",
        "Concordância entre o status calculado e a SITUAÇÃO do documento",
        "operacional",
        _chart_status_situacao,
        _pq("operacional", "status_vs_situacao"),
        audit_file("operacional", "Status_vs_Situacao.xlsx"),
    ),
    _visao(
        "op_acion",
        "Acionabilidade por Produtor",
        "% de clientes com telefone/e-mail por produtor",
        "operacional",
        _chart_contact_producer,
        _pq("operacional", "acionabilidade_produtor"),
        audit_file("operacional", "Acionabilidade_Produtor.xlsx"),
    ),
    _visao(
        "op_dq",
        "Qualidade de Dados — Testes (DQ)",
        "Prêmio zerado, comissão > prêmio, inconsistência %, outliers, duplicatas",
        "operacional",
        _chart_dq_resumo,
        load_dq_resumo,
        OUTPUTS / "operacional" / "DQ_Reports.xlsx",
    ),
]

# ── Marketing (base/mercado: cliente × prospect + demografia + personas) ──────
_MARKETING = [
    _visao(
        "mkt_status",
        "Status Comercial da Base",
        "Composição da base: ATIVO × INATIVO × PROSPECT",
        "marketing",
        _chart_base_status,
        _pq("marketing", "status_base"),
        audit_file("marketing", "Status_Base.xlsx"),
    ),
    _visao(
        "mkt_esp",
        "Distribuição por Especialidade",
        "Cooperados por CARACTERÍSTICA, clientes × prospects",
        "marketing",
        _chart_specialty_dist,
        _pq("marketing", "distribuicao_especialidade"),
        audit_file("marketing", "Distribuicao_Especialidade.xlsx"),
    ),
    _visao(
        "mkt_decada",
        "Concentração por Década de Nascimento",
        "Coortes geracionais da base (clientes × prospects)",
        "marketing",
        _chart_birth_decade,
        _pq("marketing", "decada_nascimento"),
        audit_file("marketing", "Decada_Nascimento.xlsx"),
    ),
    _visao(
        "mkt_faixa",
        "Distribuição por Faixa Etária",
        "Até 40 · 41 a 59 · 60+ (clientes × prospects)",
        "marketing",
        _chart_age_bands,
        _pq("marketing", "faixa_etaria"),
        audit_file("marketing", "Faixa_Etaria.xlsx"),
    ),
    _visao(
        "mkt_hist",
        "Histograma de Idade",
        "Distribuição etária da base, sobreposto clientes × prospects",
        "marketing",
        _chart_age_histogram,
        _pq("marketing", "base_cooperados"),
        audit_file("marketing", "Status_Base.xlsx"),
    ),
    _visao(
        "mkt_alvos",
        "Alvos de Aquisição (Prospects × Produto)",
        "Por especialidade: prospects a conquistar + produto que mais pega",
        "marketing",
        _chart_acquisition_targets,
        _pq("marketing", "alvos_aquisicao"),
        audit_file("marketing", "Alvos_Aquisicao.xlsx"),
    ),
    _visao(
        "mkt_aud",
        "Audiência de Campanha (E-mail Acionável)",
        "Prospects realmente alcançáveis: e-mail + consentimento",
        "marketing",
        _chart_reachable_audience,
        _pq("marketing", "audiencia_campanha"),
        audit_file("marketing", "Audiencia_Campanha.xlsx"),
    ),
    _visao(
        "mkt_sexo",
        "Personas — Sexo",
        "Distribuição por sexo (clientes × prospects)",
        "marketing",
        lambda df: _chart_persona(df, "SEXO_LABEL", "Cooperados"),
        _pq("marketing", "personas_sexo"),
        audit_file("marketing", "Personas_Sexo.xlsx"),
    ),
    _visao(
        "mkt_civil",
        "Personas — Estado Civil",
        "Distribuição por estado civil (~41% preenchido)",
        "marketing",
        lambda df: _chart_persona(df, "ESTADO_CIVIL", "Cooperados"),
        _pq("marketing", "personas_estado_civil"),
        audit_file("marketing", "Personas_Estado_Civil.xlsx"),
    ),
    _visao(
        "mkt_tipo",
        "Personas — Tipo de Cliente",
        "Distribuição por tipo de cliente (clientes × prospects)",
        "marketing",
        lambda df: _chart_persona(df, "TIPO_CLIENTE", "Cooperados"),
        _pq("marketing", "personas_tipo"),
        audit_file("marketing", "Personas_Tipo.xlsx"),
    ),
]

VISOES = _COMERCIAL + _OPERACIONAL + _MARKETING


def visoes_do_track(track: str):
    """Lista de visões de um track, na ordem de exibição."""
    return [v for v in VISOES if v["track"] == track]
