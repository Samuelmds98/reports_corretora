"""
marketing.py

Builders do track MARKETING — olham a **base inteira de cadastro** (não a produção),
comparando **quem já é cliente × quem ainda é prospect** e a **composição demográfica**
do mercado endereçável. É a lente que falta nos outros tracks: o Comercial é construído
sobre o grão de produção, então os cooperados que nunca compraram (prospects) ficam
invisíveis lá — e eles são a maioria da base.

Sujeito de dados: 1 linha por cooperado (cadastro cruzado com o status comercial).
Status simplificado em ATIVO / INATIVO / PROSPECT (a partir de `STATUS_GLOBAL`).
Não-monetário (contagens e demografia) — robusto e acionável.
"""

import numpy as np
import pandas as pd

ORIGIN_COLS = ["ID_LINHA", "ARQUIVO_ORIGEM", "LINHA_ORIGEM"]
_STATUS_ORDER = ["ATIVO", "INATIVO", "PROSPECT"]
# Faixas etárias do recorte de marketing (mais grossas que a FAIXA_ETARIA do cadastro)
_AGE_BINS = [-np.inf, 40, 59, np.inf]
_AGE_LABELS = ["Até 40", "41 a 59", "60+"]


def _status_simples(serie_status_global):
    """ATIVO / INATIVO / PROSPECT a partir de STATUS_GLOBAL ('INATIVO (PROSPECT)')."""
    s = serie_status_global.astype(str).str.upper()
    return np.where(
        s.str.contains("PROSPECT"),
        "PROSPECT",
        np.where(s.eq("ATIVO"), "ATIVO", "INATIVO"),
    )


def build_marketing_base(df_cruzamento):
    """
    Base por cooperado (lastro do track): status comercial simplificado + flag de
    prospect + demografia (especialidade, idade, ano/década de nascimento, faixa
    etária do recorte). Carrega a âncora de origem (`ID_LINHA`...) do cadastro para
    auditoria. As demais visões de marketing agregam ESTA base.
    """
    if df_cruzamento is None or df_cruzamento.empty:
        return pd.DataFrame()

    d = df_cruzamento.copy()
    d["STATUS"] = _status_simples(d.get("STATUS_GLOBAL", pd.Series("", index=d.index)))
    d["EH_PROSPECT"] = d["STATUS"] == "PROSPECT"

    col_esp = "CARACTERÍSTICA"
    d["ESPECIALIDADE"] = (
        d[col_esp].fillna("Não Informado") if col_esp in d.columns else "Não Informado"
    )

    if "IDADE" in d.columns:
        idade = pd.to_numeric(d["IDADE"], errors="coerce")
        d["IDADE"] = idade
        ano_atual = pd.Timestamp("today").year
        d["ANO_NASCIMENTO"] = (ano_atual - idade).astype("Int64")
        decada = (d["ANO_NASCIMENTO"] // 10 * 10).astype("Int64")
        d["DECADA_NASCIMENTO"] = decada.astype(str).where(
            decada.notna(), "Não Informada"
        )
        d["FAIXA_ETARIA_3"] = pd.cut(idade, bins=_AGE_BINS, labels=_AGE_LABELS).astype(
            str
        )
        d.loc[idade.isna(), "FAIXA_ETARIA_3"] = "Não Informada"
    else:
        d["IDADE"] = np.nan
        d["ANO_NASCIMENTO"] = pd.NA
        d["DECADA_NASCIMENTO"] = "Não Informada"
        d["FAIXA_ETARIA_3"] = "Não Informada"

    cols = (
        [c for c in ORIGIN_COLS if c in d.columns]
        + ["CPF_LIMPO", "STATUS", "EH_PROSPECT", "ESPECIALIDADE"]
        + ["IDADE", "ANO_NASCIMENTO", "DECADA_NASCIMENTO", "FAIXA_ETARIA_3"]
    )
    return d[[c for c in cols if c in d.columns]].reset_index(drop=True)


def _distribuicao(base, chave):
    """Contagem por `chave` com quebra cliente × prospect e % da base."""
    res = (
        base.groupby(chave)
        .agg(QTD_COOPERADOS=("CPF_LIMPO", "size"), QTD_PROSPECTS=("EH_PROSPECT", "sum"))
        .reset_index()
    )
    res["QTD_CLIENTES"] = res["QTD_COOPERADOS"] - res["QTD_PROSPECTS"]
    total = res["QTD_COOPERADOS"].sum()
    res["PCT_DA_BASE"] = (res["QTD_COOPERADOS"] / total * 100).round(1) if total else 0
    res["PCT_PROSPECT_NO_GRUPO"] = np.where(
        res["QTD_COOPERADOS"] > 0,
        (res["QTD_PROSPECTS"] / res["QTD_COOPERADOS"] * 100).round(1),
        0,
    )
    return res


def build_base_status(base):
    """Status comercial da base: ATIVO / INATIVO / PROSPECT (total e %)."""
    if base is None or base.empty:
        return pd.DataFrame()
    res = base.groupby("STATUS").agg(QTD_COOPERADOS=("CPF_LIMPO", "size")).reset_index()
    total = res["QTD_COOPERADOS"].sum()
    res["PCT_DA_BASE"] = (res["QTD_COOPERADOS"] / total * 100).round(1) if total else 0
    res["_ord"] = res["STATUS"].map({s: i for i, s in enumerate(_STATUS_ORDER)})
    return res.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)


def build_specialty_distribution(base):
    """Distribuição por especialidade (CARACTERÍSTICA) + cliente × prospect."""
    if base is None or base.empty:
        return pd.DataFrame()
    return _distribuicao(base, "ESPECIALIDADE").sort_values(
        "QTD_COOPERADOS", ascending=False
    )


def build_birth_decade(base):
    """Concentração por década de nascimento + cliente × prospect."""
    if base is None or base.empty:
        return pd.DataFrame()
    return _distribuicao(base, "DECADA_NASCIMENTO").sort_values("DECADA_NASCIMENTO")


def build_age_bands(base):
    """Distribuição por faixa etária (Até 40 / 41 a 59 / 60+) + cliente × prospect."""
    if base is None or base.empty:
        return pd.DataFrame()
    res = _distribuicao(base, "FAIXA_ETARIA_3")
    ordem = {l: i for i, l in enumerate(_AGE_LABELS + ["Não Informada"])}
    res["_ord"] = res["FAIXA_ETARIA_3"].map(ordem).fillna(99)
    return res.sort_values("_ord").drop(columns="_ord").reset_index(drop=True)
