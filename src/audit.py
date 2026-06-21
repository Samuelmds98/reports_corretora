"""
audit.py

Workbooks de auditoria por análise (rastreabilidade total).

Cada análise vira um `.xlsx` autocontido com 2 abas:
  1. **Agregado** — os números (cópia da visão agregada).
  2. **Lastro**   — TODOS os registros de origem que alimentam aqueles números,
     cada um com a âncora (`ID_LINHA`, `ARQUIVO_ORIGEM`, `LINHA_ORIGEM`) e as
     colunas-chave que dizem a qual linha agregada ele pertence (o "tag de métrica").

A antiga aba **Conferência** foi removida (por decisão do negócio: Agregado + Lastro já
atendem). O fechamento lastro→número virou um **check de consistência no console** (via
o parâmetro `checks`), que só avisa se algum número não bater — rede de segurança
silenciosa entre os dois caminhos de código.

Objetivo: para quem tem problema de cadastro/qualidade, poder pegar QUALQUER
número, filtrar o lastro pela chave e ver exatamente os registros — e de qual
arquivo/linha de origem cada um veio.

Nenhuma função modifica os DataFrames recebidos.
"""

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from src.excel_report import AZUL, VERDE, format_sheet
from src.operacional import build_contact_by_client, build_status_situacao_base
from src.utils import get_comissao_col

ORIGIN_COLS = ["ID_LINHA", "ARQUIVO_ORIGEM", "LINHA_ORIGEM"]
TOLERANCIA = 0.01  # diferença absoluta aceitável na conferência (float)
SKIPPED = "n/a"  # builder não aplicável (≠ None, que sinaliza arquivo bloqueado)


def _raw_product_keys(df_prod):
    """Cópia das linhas brutas com SEGURADORA/PRODUTO alinhadas ao df_prod_status."""
    raw = df_prod.copy()
    raw["SEGURADORA"] = raw["SEGURADORA (ABREVIADO)"]
    raw["PRODUTO"] = raw["NOME ABREVIADO DO PRODUTO"]
    return raw


def _only_last_cycle(df):
    """
    Mantém só as linhas do último ciclo de vigência (flag `EH_ULTIMO_CICLO`), se
    presente. As visões de carteira vigente (ABC, Market Share, Margens) somam o
    último ciclo; o lastro precisa do mesmo recorte para a conferência fechar.
    """
    if "EH_ULTIMO_CICLO" in df.columns:
        return df[df["EH_ULTIMO_CICLO"]].copy()
    return df


def _origin_first(df, group_keys):
    """Reordena para a âncora de origem e as chaves de tag virem primeiro."""
    origin = [c for c in ORIGIN_COLS if c in df.columns]
    keys = [c for c in group_keys if c in df.columns and c not in origin]
    rest = [c for c in df.columns if c not in origin + keys]
    return df[origin + keys + rest]


def _build_conferencia(agg_df, lastro_df, group_keys, checks):
    """
    Re-agrega o lastro por group_keys e compara com o agregado, por métrica.
    Retorna uma tabela longa com DIFERENCA e CONFERE (divergências no topo).
    """
    linhas = []
    for chk in checks:
        if chk["func"] == "size":
            rec = (
                lastro_df.groupby(group_keys, dropna=False)
                .size()
                .reset_index(name="VALOR_LASTRO")
            )
        else:
            rec = (
                lastro_df.groupby(group_keys, dropna=False)[chk["lastro_col"]]
                .agg(chk["func"])
                .reset_index()
                .rename(columns={chk["lastro_col"]: "VALOR_LASTRO"})
            )

        merged = agg_df[group_keys + [chk["agg_col"]]].merge(
            rec, on=group_keys, how="left"
        )
        merged = merged.rename(columns={chk["agg_col"]: "VALOR_AGREGADO"})
        merged["VALOR_LASTRO"] = merged["VALOR_LASTRO"].fillna(0)
        merged["METRICA"] = chk["label"]
        merged["DIFERENCA"] = merged["VALOR_AGREGADO"] - merged["VALOR_LASTRO"]
        merged["CONFERE"] = merged["DIFERENCA"].abs() < TOLERANCIA
        linhas.append(
            merged[
                group_keys
                + ["METRICA", "VALOR_AGREGADO", "VALOR_LASTRO", "DIFERENCA", "CONFERE"]
            ]
        )

    if not linhas:
        return pd.DataFrame()

    out = pd.concat(linhas, ignore_index=True)
    # Divergências primeiro, para o auditor ver o que não fecha logo de cara
    return out.sort_values(["CONFERE", "METRICA"], ascending=[True, True]).reset_index(
        drop=True
    )


def export_audit_workbook(path, agg_df, lastro_df, group_keys, checks=None):
    """
    Escreve o workbook de auditoria de uma análise: **Agregado | Lastro**.

    O Agregado é o número; o Lastro são TODOS os registros de origem que o compõem,
    cada um com a âncora (`ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`) e as chaves de
    grupo — quem audita filtra o lastro pela chave e vê exatamente as linhas brutas.

    `checks` (opcional) NÃO é mais publicado como aba. Ele alimenta apenas um
    **check de consistência no console**: a auditoria re-agrega o lastro por um
    caminho de código independente e avisa se algum número não fechar com o agregado
    — rede de segurança contra os dois caminhos divergirem (ex.: filtro de último
    ciclo). O artefato entregue ao negócio fica enxuto (Agregado|Lastro).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    checks = checks or []

    lastro_out = _origin_first(lastro_df, group_keys)
    conf = _build_conferencia(agg_df, lastro_df, group_keys, checks)
    n_div = int((~conf["CONFERE"]).sum()) if not conf.empty else 0

    try:
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            agg_df.to_excel(writer, sheet_name="1_Agregado", index=False)
            lastro_out.to_excel(writer, sheet_name="2_Lastro", index=False)

        wb = load_workbook(path)
        format_sheet(wb["1_Agregado"], VERDE)
        format_sheet(wb["2_Lastro"], AZUL)
        wb.save(path)
    except PermissionError:
        print(
            f"  [BLOQUEADO] {path.name} está aberto/protegido — pulei a gravação. "
            f"Feche o arquivo e rode novamente."
        )
        return None

    # Check silencioso: só fala se houver divergência (não polui o caso normal).
    alerta = "" if n_div == 0 else f" — ⚠ {n_div} divergência(s) interna(s)!"
    print(f"  auditoria: {path.name} ({len(lastro_out):,} linhas de lastro){alerta}")
    return path


# ── Builders por análise ──────────────────────────────────────────────────────
def audit_abc(out_dir, df_abc, df_prod):
    """Curva ABC: lastro = linhas brutas de produção, taggeadas por CPF e classe ABC."""
    classe = df_abc[["CPF_LIMPO", "CURVA_ABC"]]
    lastro = _only_last_cycle(df_prod).merge(classe, on="CPF_LIMPO", how="inner")
    checks = [
        {
            "label": "Prêmio líquido (último ciclo) por CPF",
            "agg_col": "TOTAL_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Curva_ABC.xlsx", df_abc, lastro, ["CPF_LIMPO"], checks
    )


def audit_market_share(out_dir, df_partner, df_prod):
    """Market Share: lastro = linhas brutas de produção, taggeadas por seguradora."""
    lastro = _only_last_cycle(df_prod)
    lastro["SEGURADORA"] = lastro["SEGURADORA (ABREVIADO)"]
    checks = [
        {
            "label": "Prêmio líquido (último ciclo) por seguradora",
            "agg_col": "TOTAL_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Market_Share.xlsx", df_partner, lastro, ["SEGURADORA"], checks
    )


def audit_cohort(out_dir, df_ts_growth, df_prod, df_prod_status):
    """
    Cohort/Sazonalidade: lastro = linhas brutas, taggeadas pela SAFRA do produto
    (mês do PRIMEIRO_INICIO do grupo CPF×SEGURADORA×PRODUTO). Cada linha bruta
    herda a safra do seu grupo, então o prêmio reconcilia por safra.
    """
    ps = df_prod_status[
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO", "PRIMEIRO_INICIO"]
    ].copy()
    ps["SAFRA_MES_VIGENCIA"] = pd.to_datetime(
        ps["PRIMEIRO_INICIO"], errors="coerce"
    ).dt.strftime("%Y-%m")
    ps = ps.rename(
        columns={
            "SEGURADORA": "SEGURADORA (ABREVIADO)",
            "PRODUTO": "NOME ABREVIADO DO PRODUTO",
        }
    )[
        [
            "CPF_LIMPO",
            "SEGURADORA (ABREVIADO)",
            "NOME ABREVIADO DO PRODUTO",
            "SAFRA_MES_VIGENCIA",
        ]
    ]

    lastro = df_prod.merge(
        ps,
        on=["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "NOME ABREVIADO DO PRODUTO"],
        how="left",
    )
    checks = [
        {
            "label": "Prêmio líquido por safra",
            "agg_col": "VALOR_PREMIO",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Cohort_Sazonalidade.xlsx",
        df_ts_growth,
        lastro,
        ["SAFRA_MES_VIGENCIA"],
        checks,
    )


def audit_demografia(out_dir, df_demographics, df_cruzamento):
    """
    Demografia: lastro = cadastro (1 linha por cooperado), taggeado pela célula
    demográfica. Reconcilia a contagem total e a de ativos por célula.
    """
    demo_cols = [
        "CIDADE",
        "ESTADO",
        "SEXO",
        "ESTADO CIVIL",
        "FAIXA_ETARIA",
        "CARACTERÍSTICA",
    ]
    group_keys = [c for c in demo_cols if c in df_demographics.columns]

    lastro = df_cruzamento.copy()
    lastro["_ATIVO"] = (lastro.get("STATUS_GLOBAL") == "ATIVO").astype(int)

    checks = [
        {
            "label": "Total de cooperados na célula",
            "agg_col": "TOTAL_COOPERADOS",
            "lastro_col": "_ATIVO",
            "func": "size",
        },
        {
            "label": "Cooperados ativos na célula",
            "agg_col": "COOPERADOS_ATIVOS",
            "lastro_col": "_ATIVO",
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Demografia.xlsx",
        df_demographics,
        lastro,
        group_keys,
        checks,
    )


def audit_calculadora(out_dir, df_prod_status, df_prod):
    """
    Calculadora de Produtos (df_prod_status): a ponte canônica produto → linhas
    brutas. Lastro = todas as linhas de produção, taggeadas por CPF×SEGURADORA×PRODUTO.
    """
    lastro = _raw_product_keys(df_prod)
    comissao_col = get_comissao_col(df_prod)
    checks = [
        {
            "label": "Prêmio líquido por produto",
            "agg_col": "SOMA_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        },
        {
            "label": "Comissão por produto",
            "agg_col": "SOMA_COMISSAO",
            "lastro_col": comissao_col,
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Calculadora_Produtos.xlsx",
        df_prod_status,
        lastro,
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO"],
        checks,
    )


def audit_mix(out_dir, df_specialty, df_prod_status, df_cruzamento, df_prod):
    """Mix por Especialidade: lastro = linhas brutas dos produtos ATIVOS + especialidade."""
    if df_specialty is None or "PRODUTO" not in df_specialty.columns:
        return SKIPPED

    ativos = df_prod_status[df_prod_status["STATUS_PRODUTO"] == "ATIVO"][
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO"]
    ]
    lastro = _raw_product_keys(df_prod).merge(
        ativos, on=["CPF_LIMPO", "SEGURADORA", "PRODUTO"], how="inner"
    )
    esp = df_cruzamento[["CPF_LIMPO", "CARACTERÍSTICA"]].drop_duplicates("CPF_LIMPO")
    lastro = lastro.merge(esp, on="CPF_LIMPO", how="left")
    lastro["CARACTERÍSTICA"] = lastro["CARACTERÍSTICA"].fillna("Não Informado")

    checks = [
        {
            "label": "Cooperados distintos com o produto",
            "agg_col": "QTD_COOPERADOS_COM_PRODUTO",
            "lastro_col": "CPF_LIMPO",
            "func": "nunique",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Mix_Especialidade.xlsx",
        df_specialty,
        lastro,
        ["CARACTERÍSTICA", "PRODUTO"],
        checks,
    )


def audit_renovacoes(out_dir, df_renewal, df_prod):
    """
    Agenda de Renovações: lastro = linhas brutas do ÚLTIMO CICLO dos produtos
    renováveis listados. O valor exibido (`PREMIO_ULTIMO_CICLO`) considera apenas
    o ciclo de vigência mais recente da apólice (flag `EH_ULTIMO_CICLO`), então o
    lastro é filtrado pela mesma flag para que a conferência feche.
    """
    if df_renewal is None or df_renewal.empty:
        return SKIPPED

    keys = df_renewal[["CPF_LIMPO", "SEGURADORA", "PRODUTO"]].drop_duplicates()
    lastro = _only_last_cycle(_raw_product_keys(df_prod)).merge(
        keys, on=["CPF_LIMPO", "SEGURADORA", "PRODUTO"], how="inner"
    )
    checks = [
        {
            "label": "Prêmio do último ciclo por produto",
            "agg_col": "PREMIO_ULTIMO_CICLO",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Agenda_Renovacoes.xlsx",
        df_renewal,
        lastro,
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO"],
        checks,
    )


def audit_winback(out_dir, df_winback, df_prod):
    """Win-Back: lastro = linhas brutas de produção dos CPFs inativos candidatos."""
    if df_winback is None or df_winback.empty:
        return SKIPPED

    lastro = df_prod.merge(df_winback[["CPF_LIMPO"]], on="CPF_LIMPO", how="inner")
    checks = [
        {
            "label": "Prêmio histórico por CPF",
            "agg_col": "TOTAL_PREMIO_HISTORICO",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Win_Back.xlsx", df_winback, lastro, ["CPF_LIMPO"], checks
    )


def audit_snapshot(out_dir, df_snapshot, df_snapshot_grain):
    """Snapshot Mensal: lastro = grão produto×mês (de build_snapshot_grain)."""
    if df_snapshot_grain is None or df_snapshot_grain.empty:
        return SKIPPED

    checks = [
        {
            "label": "Prêmio total por mês",
            "agg_col": "PREMIO_TOTAL",
            "lastro_col": "SOMA_PREMIO_LIQ",
            "func": "sum",
        },
        {
            "label": "Clientes ativos por mês",
            "agg_col": "CLIENTES_ATIVOS",
            "lastro_col": "CPF_LIMPO",
            "func": "nunique",
        },
        {
            "label": "Produtos ativos por mês",
            "agg_col": "PRODUTOS_ATIVOS",
            "lastro_col": "PRODUTO",
            "func": "size",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Snapshot_Mensal.xlsx",
        df_snapshot,
        df_snapshot_grain,
        ["MES_REFERENCIA"],
        checks,
    )


def audit_abc_comissao(out_dir, df_abc_com, df_prod):
    """Curva ABC por Comissão: lastro = linhas brutas, taggeadas por CPF e classe."""
    if df_abc_com is None or df_abc_com.empty:
        return SKIPPED
    classe = df_abc_com[["CPF_LIMPO", "CURVA_ABC_COMISSAO"]]
    lastro = _only_last_cycle(df_prod).merge(classe, on="CPF_LIMPO", how="inner")
    comissao_col = get_comissao_col(df_prod)
    checks = [
        {
            "label": "Comissão (último ciclo) por CPF",
            "agg_col": "TOTAL_COMISSAO",
            "lastro_col": comissao_col,
            "func": "sum",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Curva_ABC_Comissao.xlsx",
        df_abc_com,
        lastro,
        ["CPF_LIMPO"],
        checks,
    )


def audit_margem_seguradora(out_dir, df_partner_com, df_prod):
    """Margem/Share por Comissão (seguradora): reconcilia comissão e prêmio por seguradora."""
    if df_partner_com is None or df_partner_com.empty:
        return SKIPPED
    lastro = _only_last_cycle(df_prod)
    lastro["SEGURADORA"] = lastro["SEGURADORA (ABREVIADO)"]
    comissao_col = get_comissao_col(df_prod)
    checks = [
        {
            "label": "Comissão (último ciclo) por seguradora",
            "agg_col": "TOTAL_COMISSAO",
            "lastro_col": comissao_col,
            "func": "sum",
        },
        {
            "label": "Prêmio (último ciclo) por seguradora",
            "agg_col": "TOTAL_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Margem_Comissao_Seguradora.xlsx",
        df_partner_com,
        lastro,
        ["SEGURADORA"],
        checks,
    )


def audit_margem_produto(out_dir, df_margem_prod, df_prod):
    """Margem por Comissão (produto): reconcilia comissão e prêmio por produto."""
    if df_margem_prod is None or df_margem_prod.empty:
        return SKIPPED
    lastro = _only_last_cycle(_raw_product_keys(df_prod))
    comissao_col = get_comissao_col(df_prod)
    checks = [
        {
            "label": "Comissão (último ciclo) por produto",
            "agg_col": "TOTAL_COMISSAO",
            "lastro_col": comissao_col,
            "func": "sum",
        },
        {
            "label": "Prêmio (último ciclo) por produto",
            "agg_col": "TOTAL_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Margem_Comissao_Produto.xlsx",
        df_margem_prod,
        lastro,
        ["PRODUTO"],
        checks,
    )


def audit_margem_seg_produto(out_dir, df_margem_sp, df_prod):
    """
    Margem por SEGURADORA × PRODUTO: reconcilia comissão e prêmio (último ciclo) no
    grão seguradora×produto. Lastro = linhas brutas do último ciclo taggeadas pelas
    duas chaves.
    """
    if df_margem_sp is None or df_margem_sp.empty:
        return SKIPPED
    lastro = _only_last_cycle(_raw_product_keys(df_prod))
    comissao_col = get_comissao_col(df_prod)
    checks = [
        {
            "label": "Comissão (último ciclo) por seguradora×produto",
            "agg_col": "TOTAL_COMISSAO",
            "lastro_col": comissao_col,
            "func": "sum",
        },
        {
            "label": "Prêmio (último ciclo) por seguradora×produto",
            "agg_col": "TOTAL_PREMIO_LIQ",
            "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Margem_Comissao_Seg_Produto.xlsx",
        df_margem_sp,
        lastro,
        ["SEGURADORA", "PRODUTO"],
        checks,
    )


def audit_producer(out_dir, df_producer, df_prod):
    """Performance de Produtor: lastro = linhas brutas taggeadas por PRODUTOR."""
    if df_producer is None or df_producer.empty or "PRODUTOR" not in df_prod.columns:
        return SKIPPED
    lastro = df_prod.copy()
    checks = [
        {
            "label": "Itens por produtor",
            "agg_col": "QTD_ITENS",
            "lastro_col": "PRODUTOR",
            "func": "size",
        },
        {
            "label": "Clientes distintos por produtor",
            "agg_col": "QTD_CLIENTES",
            "lastro_col": "CPF_LIMPO",
            "func": "nunique",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Performance_Produtor.xlsx",
        df_producer,
        lastro,
        ["PRODUTOR"],
        checks,
    )


def audit_product_distribution(out_dir, df_dist, df_prod):
    """Mix de Produtos (contagem): reconcilia cooperados distintos por produto."""
    if df_dist is None or df_dist.empty:
        return SKIPPED
    lastro = _raw_product_keys(df_prod)
    checks = [
        {
            "label": "Cooperados distintos por produto",
            "agg_col": "QTD_COOPERADOS",
            "lastro_col": "CPF_LIMPO",
            "func": "nunique",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Qual_Mix_Produtos.xlsx", df_dist, lastro, ["PRODUTO"], checks
    )


def audit_partner_count(out_dir, df_partner_count, df_prod):
    """Market Share por contagem: reconcilia clientes distintos por seguradora."""
    if df_partner_count is None or df_partner_count.empty:
        return SKIPPED
    lastro = df_prod.copy()
    lastro["SEGURADORA"] = lastro["SEGURADORA (ABREVIADO)"]
    checks = [
        {
            "label": "Clientes distintos por seguradora",
            "agg_col": "QTD_CLIENTES_DISTINTOS",
            "lastro_col": "CPF_LIMPO",
            "func": "nunique",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Qual_Market_Share_Contagem.xlsx",
        df_partner_count,
        lastro,
        ["SEGURADORA"],
        checks,
    )


def audit_portfolio_depth(out_dir, df_portfolio, df_prod):
    """Profundidade de carteira: reconcilia o nº de produtos distintos por cooperado."""
    if df_portfolio is None or df_portfolio.empty:
        return SKIPPED
    lastro = _raw_product_keys(df_prod)
    checks = [
        {
            "label": "Produtos distintos por cooperado",
            "agg_col": "N_PRODUTOS",
            "lastro_col": "PRODUTO",
            "func": "nunique",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Qual_Profundidade_Carteira.xlsx",
        df_portfolio,
        lastro,
        ["CPF_LIMPO"],
        checks,
    )


# ── Auditoria do track OPERACIONAL / QUALIDADE (Agregado | Lastro) ────────────
def audit_origem_cadastro(out_dir, df_origem, df_prod):
    """Origem (migrado×orgânico): lastro = linhas brutas com ORIGEM_CADASTRO + ANO."""
    if (
        df_origem is None
        or df_origem.empty
        or "USUÁRIO DA INCLUSÃO" not in df_prod.columns
    ):
        return SKIPPED
    lastro = df_prod.copy()
    upper = lastro["USUÁRIO DA INCLUSÃO"].astype(str).str.upper()
    lastro["ORIGEM_CADASTRO"] = upper.str.contains("MIGRA", na=False).map(
        {True: "Migrado", False: "Orgânico"}
    )
    lastro["ANO_INICIO"] = pd.to_datetime(
        lastro["INÍCIO DE VIGÊNCIA"], errors="coerce"
    ).dt.year
    return export_audit_workbook(
        Path(out_dir) / "Origem_Cadastro.xlsx", df_origem, lastro, ["ANO_INICIO"], []
    )


def audit_status_situacao(out_dir, df_status_sit, df_prod, df_prod_status):
    """Status×Situação: lastro = base por produto (status + situação + concorda)."""
    if df_status_sit is None or df_status_sit.empty:
        return SKIPPED
    base = build_status_situacao_base(df_prod, df_prod_status)
    if base is None or base.empty:
        return SKIPPED
    checks = [
        {
            "label": "Produtos por célula status×situação",
            "agg_col": "QTD_PRODUTOS",
            "lastro_col": "STATUS_PRODUTO",
            "func": "size",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / "Status_vs_Situacao.xlsx",
        df_status_sit,
        base,
        ["STATUS_PRODUTO", "SITUAÇÃO"],
        checks,
    )


def audit_acionabilidade(out_dir, df_contact_prod, df_prod, df_cad):
    """Acionabilidade por produtor: lastro = clientes com produtor + flags de contato."""
    if df_contact_prod is None or df_contact_prod.empty:
        return SKIPPED
    base = build_contact_by_client(df_prod, df_cad)
    if base is None or base.empty:
        return SKIPPED
    checks = [
        {
            "label": "Clientes por produtor",
            "agg_col": "QTD_CLIENTES",
            "lastro_col": "CPF_LIMPO",
            "func": "size",
        },
        {
            "label": "Contatáveis por produtor",
            "agg_col": "CONTATAVEIS",
            "lastro_col": "CONTATAVEL",
            "func": "sum",
        },
    ]
    return export_audit_workbook(
        Path(out_dir) / "Acionabilidade_Produtor.xlsx",
        df_contact_prod,
        base,
        ["PRODUTOR"],
        checks,
    )


def audit_completude(out_dir, df_completeness, df_cad_raw):
    """Completude do cadastro: lastro = registros de cadastro (origem das taxas)."""
    if df_completeness is None or df_completeness.empty:
        return SKIPPED
    return export_audit_workbook(
        Path(out_dir) / "Completude_Cadastro.xlsx",
        df_completeness,
        df_cad_raw.copy(),
        [],
        [],
    )


def audit_marketing(
    out_dir,
    fname,
    agg_df,
    base_df,
    group_keys,
    agg_col="QTD_COOPERADOS",
    base_filter=None,
):
    """
    Auditoria genérica das visões de MARKETING: lastro = base por cooperado
    (`build_marketing_base`), com a âncora do cadastro. Reconcilia a contagem por
    chave (status, especialidade, década, faixa etária, personas).

    `agg_col`/`base_filter` permitem auditar recortes que contam apenas um subconjunto
    da base — ex.: alvos de aquisição e audiência de campanha contam só PROSPECTS
    (`agg_col="QTD_PROSPECTS"`, `base_filter=lambda b: b["EH_PROSPECT"]`).
    """
    if agg_df is None or agg_df.empty or base_df is None or base_df.empty:
        return SKIPPED
    lastro = base_df[base_filter(base_df)] if base_filter is not None else base_df
    checks = [
        {
            "label": agg_col + " por " + "/".join(group_keys),
            "agg_col": agg_col,
            "lastro_col": "CPF_LIMPO",
            "func": "size",
        }
    ]
    return export_audit_workbook(
        Path(out_dir) / fname, agg_df, lastro, group_keys, checks
    )


def audit_origination(out_dir, df_abc_win, df_share_win, df_prod, start_date):
    """Somas janeladas 2025+: lastro = linhas brutas com INÍCIO DE VIGÊNCIA >= corte."""
    ini = pd.to_datetime(df_prod["INÍCIO DE VIGÊNCIA"], errors="coerce")
    sub = df_prod[ini >= pd.Timestamp(start_date)].copy()

    resultados = []
    if df_abc_win is not None and not df_abc_win.empty:
        lastro_abc = sub.merge(
            df_abc_win[["CPF_LIMPO", "CURVA_ABC"]], on="CPF_LIMPO", how="inner"
        )
        resultados.append(
            export_audit_workbook(
                Path(out_dir) / "Curva_ABC_2025plus.xlsx",
                df_abc_win,
                lastro_abc,
                ["CPF_LIMPO"],
                [
                    {
                        "label": "Prêmio líquido por CPF (originação 2025+)",
                        "agg_col": "TOTAL_PREMIO_LIQ",
                        "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
                        "func": "sum",
                    }
                ],
            )
        )
    else:
        resultados.append(SKIPPED)

    if df_share_win is not None and not df_share_win.empty:
        lastro_share = _raw_product_keys(sub)
        resultados.append(
            export_audit_workbook(
                Path(out_dir) / "Market_Share_2025plus.xlsx",
                df_share_win,
                lastro_share,
                ["SEGURADORA"],
                [
                    {
                        "label": "Prêmio líquido por seguradora (originação 2025+)",
                        "agg_col": "TOTAL_PREMIO_LIQ",
                        "lastro_col": "PRÊMIO LÍQ. DO SEGURO",
                        "func": "sum",
                    }
                ],
            )
        )
    else:
        resultados.append(SKIPPED)

    return resultados
