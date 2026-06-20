"""
data_quality_advanced.py

Detecções estatísticas e estruturais de qualidade de dados (Fase 4).

Princípio: **nenhuma correção de valor é feita**. Todas as funções apenas detectam
e sinalizam registros que precisam de revisão humana, em colunas de diagnóstico
(`MOTIVO_FLAG`). Nenhuma função modifica o DataFrame original — sempre opera em
`.copy()` ou subsets filtrados.

Convenção de robustez: se uma coluna obrigatória estiver ausente, a função retorna
um DataFrame com a coluna `MOTIVO_FLAG` descrevendo o erro, em vez de lançar exceção.
"""

import numpy as np
import pandas as pd

PREMIO_COL = "PRÊMIO LÍQ. DO SEGURO"

# Colunas de identificação reaproveitadas nos subsets de saída
_ID_COLS = [
    "CPF_LIMPO",
    "SEGURADORA (ABREVIADO)",
    "NOME ABREVIADO DO PRODUTO",
    "APÓLICE",
    "TIPO DE NEGÓCIO",
    "INÍCIO DE VIGÊNCIA",
]


def _missing_cols_df(missing):
    """DataFrame de erro padronizado quando faltam colunas obrigatórias."""
    return pd.DataFrame(
        {"MOTIVO_FLAG": [f"Colunas obrigatórias ausentes: {', '.join(missing)}"]}
    )


def _subset(df, cols):
    """Retorna apenas as colunas que existem, preservando a ordem pedida."""
    return df[[c for c in cols if c in df.columns]].copy()


def detect_zero_negative_premio(df_prod):
    """
    Detecta registros com prêmio líquido zerado ou negativo em apólices (N/R).
    Faturas e endossos são excluídos pois podem ter valores de ajuste negativos.
    """
    req = ["TIPO DE NEGÓCIO", PREMIO_COL]
    missing = [c for c in req if c not in df_prod.columns]
    if missing:
        return _missing_cols_df(missing)

    df = df_prod[df_prod["TIPO DE NEGÓCIO"].isin(["N", "R"])].copy()
    premio = pd.to_numeric(df[PREMIO_COL], errors="coerce")
    mask = premio.isna() | (premio <= 0)

    flagged = df[mask].copy()
    flagged["MOTIVO_FLAG"] = "Prêmio zerado ou negativo em apólice"

    cols = _ID_COLS + [PREMIO_COL, "MOTIVO_FLAG"]
    return _subset(flagged, cols)


def detect_commission_exceeds_premio(df_prod, comissao_col):
    """
    Detecta registros onde a comissão é maior que o prêmio líquido.
    Operacionalmente impossível — comissão é percentual do prêmio.
    """
    req = [PREMIO_COL, comissao_col]
    missing = [c for c in req if c not in df_prod.columns]
    if missing:
        return _missing_cols_df(missing)

    df = df_prod.copy()
    premio = pd.to_numeric(df[PREMIO_COL], errors="coerce")
    comissao = pd.to_numeric(df[comissao_col], errors="coerce")

    # premio > 0 evita dupla contagem com a regra de prêmio zerado/negativo
    mask = (comissao > premio) & (premio > 0)

    flagged = df[mask].copy()
    flagged["DIFERENCA"] = comissao[mask] - premio[mask]
    flagged["MOTIVO_FLAG"] = "Comissão maior que prêmio"

    cols = _ID_COLS + [PREMIO_COL, comissao_col, "DIFERENCA", "MOTIVO_FLAG"]
    return _subset(flagged, cols)


def detect_percentage_inconsistency(df_prod, comissao_col):
    """
    Detecta registros onde a comissão real diverge mais de 1% da comissão esperada
    calculada por: prêmio × (percentual / 100). Usa tolerância relativa para tratar
    corretamente prêmios de magnitudes diferentes.
    """
    req = [PREMIO_COL, comissao_col, "PORCENTAGEM"]
    missing = [c for c in req if c not in df_prod.columns]
    if missing:
        return _missing_cols_df(missing)

    df = df_prod.copy()
    premio = pd.to_numeric(df[PREMIO_COL], errors="coerce")
    comissao = pd.to_numeric(df[comissao_col], errors="coerce")
    porcentagem = pd.to_numeric(df["PORCENTAGEM"], errors="coerce")

    comissao_esperada = premio * (porcentagem / 100.0)
    tolerancia = comissao_esperada * 0.01  # 1% do valor esperado

    divergencia_abs = (comissao_esperada - comissao).abs()
    mask = (divergencia_abs > tolerancia) & (comissao_esperada > 0)

    flagged = df[mask].copy()
    flagged["COMISSAO_ESPERADA"] = comissao_esperada[mask]
    flagged["COMISSAO_REAL"] = comissao[mask]
    flagged["DIVERGENCIA_ABS"] = divergencia_abs[mask]
    flagged["DIVERGENCIA_PCT"] = (
        flagged["DIVERGENCIA_ABS"] / flagged["COMISSAO_ESPERADA"]
    ) * 100
    flagged["MOTIVO_FLAG"] = "Inconsistência entre % e comissão cadastrada"

    flagged = flagged.sort_values("DIVERGENCIA_PCT", ascending=False)

    cols = _ID_COLS + [
        PREMIO_COL,
        "PORCENTAGEM",
        "COMISSAO_ESPERADA",
        "COMISSAO_REAL",
        "DIVERGENCIA_ABS",
        "DIVERGENCIA_PCT",
        "MOTIVO_FLAG",
    ]
    return _subset(flagged, cols)


def _detect_numeric_outliers(df_prod, value_col, motivo):
    """
    Detecção de outliers por média ± 3 desvios padrão, agrupada por
    (PRODUTO, SEGURADORA). Lógica compartilhada entre prêmio e percentual.
    Retorna (df_outliers_grandes, df_grupos_pequenos).
    """
    req = [
        "TIPO DE NEGÓCIO",
        value_col,
        "NOME ABREVIADO DO PRODUTO",
        "SEGURADORA (ABREVIADO)",
    ]
    missing = [c for c in req if c not in df_prod.columns]
    if missing:
        err = _missing_cols_df(missing)
        return err, err.copy()

    df = df_prod.copy()
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df[df["TIPO DE NEGÓCIO"].isin(["N", "R"]) & (df[value_col] > 0)].copy()
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    grp = df.groupby(["NOME ABREVIADO DO PRODUTO", "SEGURADORA (ABREVIADO)"])[value_col]
    df["MEDIA_GRUPO"] = grp.transform("mean")
    df["DESVIO_GRUPO"] = grp.transform("std")
    df["N_REGISTROS_GRUPO"] = grp.transform("count")
    df["LIMITE_INF"] = df["MEDIA_GRUPO"] - 3 * df["DESVIO_GRUPO"]
    df["LIMITE_SUP"] = df["MEDIA_GRUPO"] + 3 * df["DESVIO_GRUPO"]

    pequenos = df[df["N_REGISTROS_GRUPO"] < 5].copy()
    grandes = df[df["N_REGISTROS_GRUPO"] >= 5].copy()

    mask_out = (grandes[value_col] < grandes["LIMITE_INF"]) | (
        grandes[value_col] > grandes["LIMITE_SUP"]
    )
    outliers = grandes[mask_out].copy()
    outliers["MOTIVO_FLAG"] = motivo

    pequenos["MOTIVO_FLAG"] = (
        "Grupo com amostra insuficiente (<5 registros) para análise estatística"
    )

    cols = [
        "CPF_LIMPO",
        "SEGURADORA (ABREVIADO)",
        "NOME ABREVIADO DO PRODUTO",
        "APÓLICE",
        "TIPO DE NEGÓCIO",
        value_col,
        "MEDIA_GRUPO",
        "DESVIO_GRUPO",
        "LIMITE_INF",
        "LIMITE_SUP",
        "N_REGISTROS_GRUPO",
        "MOTIVO_FLAG",
    ]
    return _subset(outliers, cols), _subset(pequenos, cols)


def detect_premio_outliers(df_prod):
    """
    Detecta prêmios estatisticamente anômalos usando média ± 3 desvios padrão,
    agrupado por (NOME ABREVIADO DO PRODUTO, SEGURADORA (ABREVIADO)). Grupos com
    menos de 5 registros são isolados em flag separada por amostra insuficiente.
    Retorna (df_outliers_grandes, df_grupos_pequenos).
    """
    return _detect_numeric_outliers(
        df_prod, PREMIO_COL, "Prêmio outlier (fora de média ± 3 desvios padrão)"
    )


def detect_percentage_outliers(df_prod):
    """
    Detecta percentuais de comissão estatisticamente anômalos por
    (PRODUTO, SEGURADORA). Mesma lógica de outlier que detect_premio_outliers,
    aplicada sobre a coluna PORCENTAGEM.
    Retorna (df_outliers_pct, df_grupos_pequenos_pct).
    """
    return _detect_numeric_outliers(
        df_prod,
        "PORCENTAGEM",
        "% de comissão outlier (fora de média ± 3 desvios padrão)",
    )


def detect_exact_duplicates(df_prod):
    """
    Detecta linhas duplicadas pela chave (CPF_LIMPO, APÓLICE, TIPO DE NEGÓCIO,
    INÍCIO DE VIGÊNCIA, TÉRMINO DE VIGÊNCIA, PRÊMIO LÍQ. DO SEGURO).
    Provável importação dupla da fonte.
    """
    key_cols = [
        "CPF_LIMPO",
        "APÓLICE",
        "TIPO DE NEGÓCIO",
        "INÍCIO DE VIGÊNCIA",
        "TÉRMINO DE VIGÊNCIA",
        PREMIO_COL,
    ]
    missing = [c for c in key_cols if c not in df_prod.columns]
    if missing:
        return _missing_cols_df(missing)

    df = df_prod.copy()
    mask = df.duplicated(subset=key_cols, keep=False)

    df_dup = df[mask].copy()
    if df_dup.empty:
        cols = key_cols + ["GRUPO_DUPLICATA", "MOTIVO_FLAG"]
        return pd.DataFrame(columns=cols)

    df_dup["GRUPO_DUPLICATA"] = df_dup.groupby(key_cols).ngroup() + 1
    df_dup["MOTIVO_FLAG"] = "Duplicata exata detectada"
    df_dup = df_dup.sort_values("GRUPO_DUPLICATA", ascending=True)

    cols = key_cols + ["GRUPO_DUPLICATA", "MOTIVO_FLAG"]
    return _subset(df_dup, cols)


def build_dq_summary(dict_resultados, total_registros):
    """
    Gera a aba de resumo executivo do DQ: uma linha por tipo de problema com
    contagem de registros, percentual da base e severidade.
    Recebe um dict {nome_regra: dataframe_flagado} e o total da base original.
    """

    def _severidade(regra):
        nome = regra.lower()
        if "amostra" in nome or "insuf" in nome:
            return "INFORMATIVO"
        # CRÍTICO: prêmio zerado/negativo, comissão > prêmio (símbolo ou texto), duplicatas
        comissao_maior = (
            "comiss" in nome and ">" in nome
        ) or "maior que prêmio" in nome
        if (
            "zerado" in nome
            or "negativ" in nome
            or comissao_maior
            or "duplicat" in nome
        ):
            return "CRÍTICO"
        if "inconsist" in nome or "outlier" in nome:
            return "ALERTA"
        return "INFORMATIVO"

    linhas = []
    for regra, df in dict_resultados.items():
        qtd = len(df) if df is not None else 0
        pct = (qtd / total_registros * 100) if total_registros else 0
        linhas.append(
            {
                "REGRA_DQ": regra,
                "QTD_REGISTROS_FLAGADOS": qtd,
                "PCT_DA_BASE": round(pct, 2),
                "SEVERIDADE": _severidade(regra),
            }
        )

    return pd.DataFrame(
        linhas,
        columns=["REGRA_DQ", "QTD_REGISTROS_FLAGADOS", "PCT_DA_BASE", "SEVERIDADE"],
    )
