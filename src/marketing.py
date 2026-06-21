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
# Personas (item 3): rótulos legíveis e flags de contato vindas de build_contact_lookup
_SEX_LABELS = {"M": "Masculino", "F": "Feminino"}
_CONTACT_FLAGS = ["TEM_EMAIL", "ACEITA_EMAIL", "CONTATAVEL", "EMAIL_ACIONAVEL"]


def _norm_categoria(serie, default="Não Informado"):
    """Normaliza uma coluna categórica de cadastro: trata nulos, vazios e 'nan'."""
    s = serie.astype(str).str.strip()
    return s.mask(s.eq("") | s.str.lower().eq("nan") | serie.isna(), default)


def _status_simples(serie_status_global):
    """ATIVO / INATIVO / PROSPECT a partir de STATUS_GLOBAL ('INATIVO (PROSPECT)')."""
    s = serie_status_global.astype(str).str.upper()
    return np.where(
        s.str.contains("PROSPECT"),
        "PROSPECT",
        np.where(s.eq("ATIVO"), "ATIVO", "INATIVO"),
    )


def build_marketing_base(df_cruzamento, contact_lookup=None):
    """
    Base por cooperado (lastro do track): status comercial simplificado + flag de
    prospect + demografia (especialidade, idade, ano/década de nascimento, faixa
    etária do recorte) + personas (sexo, estado civil, tipo de cliente). Carrega a
    âncora de origem (`ID_LINHA`...) do cadastro para auditoria. Quando `contact_lookup`
    (de `operacional.build_contact_lookup`) é passado, anexa as flags de
    contatabilidade/consentimento por CPF — base da audiência de campanha (item 2).
    As demais visões de marketing agregam ESTA base.
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

    # Personas extras (item 3): sexo, estado civil e tipo de cliente. Campos de
    # cadastro de qualidade desigual (ESTADO CIVIL ~41% preenchido) → "Não Informado".
    if "SEXO" in d.columns:
        sexo = d["SEXO"].astype(str).str.upper().str.strip()
        d["SEXO_LABEL"] = sexo.map(_SEX_LABELS).fillna("Não Informado")
    else:
        d["SEXO_LABEL"] = "Não Informado"
    d["ESTADO_CIVIL"] = (
        _norm_categoria(d["ESTADO CIVIL"])
        if "ESTADO CIVIL" in d.columns
        else "Não Informado"
    )
    d["TIPO_CLIENTE"] = (
        _norm_categoria(d["TIPO"]) if "TIPO" in d.columns else "Não Informado"
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

    # Flags de contatabilidade/consentimento por CPF (audiência de campanha — item 2)
    if contact_lookup is not None and not contact_lookup.empty:
        d = d.merge(contact_lookup, on="CPF_LIMPO", how="left")
    for f in _CONTACT_FLAGS:
        if f in d.columns:
            d[f] = d[f].fillna(False).astype(bool)
        else:
            d[f] = False

    cols = (
        [c for c in ORIGIN_COLS if c in d.columns]
        + ["CPF_LIMPO", "STATUS", "EH_PROSPECT", "ESPECIALIDADE"]
        + ["SEXO_LABEL", "ESTADO_CIVIL", "TIPO_CLIENTE"]
        + ["IDADE", "ANO_NASCIMENTO", "DECADA_NASCIMENTO", "FAIXA_ETARIA_3"]
        + _CONTACT_FLAGS
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


# ── Item 3: personas (sexo, estado civil, tipo de cliente) ────────────────────
def build_sex_distribution(base):
    """Distribuição por sexo (cliente × prospect)."""
    if base is None or base.empty:
        return pd.DataFrame()
    return _distribuicao(base, "SEXO_LABEL").sort_values(
        "QTD_COOPERADOS", ascending=False
    )


def build_marital_distribution(base):
    """Distribuição por estado civil (cliente × prospect). Campo ~41% preenchido."""
    if base is None or base.empty:
        return pd.DataFrame()
    return _distribuicao(base, "ESTADO_CIVIL").sort_values(
        "QTD_COOPERADOS", ascending=False
    )


def build_client_type_distribution(base):
    """Distribuição por tipo de cliente (E/P/S) — cliente × prospect."""
    if base is None or base.empty:
        return pd.DataFrame()
    return _distribuicao(base, "TIPO_CLIENTE").sort_values(
        "QTD_COOPERADOS", ascending=False
    )


# ── Item 1: alvos de aquisição (prospects × mix da especialidade) ─────────────
def build_acquisition_targets(base, df_specialty_mix, top_n=3):
    """
    Campanhas acionáveis: para cada especialidade, cruza o nº de PROSPECTS (mercado a
    conquistar, da base de marketing) com os produtos que os CLIENTES daquela
    especialidade mais possuem — a penetração por especialidade vem de
    `analytics.build_specialty_mix` (track Comercial). Resultado: alvos de aquisição
    = especialidade → prospects → produto(s) a ofertar (o que já "pega" no perfil).
    """
    if base is None or base.empty:
        return pd.DataFrame()

    prospects = (
        base[base["EH_PROSPECT"]]
        .groupby("ESPECIALIDADE")
        .agg(QTD_PROSPECTS=("CPF_LIMPO", "size"))
        .reset_index()
    )
    if prospects.empty:
        return pd.DataFrame()

    clientes = (
        base[~base["EH_PROSPECT"]]
        .groupby("ESPECIALIDADE")
        .agg(QTD_CLIENTES=("CPF_LIMPO", "size"))
        .reset_index()
    )
    alvo = prospects.merge(clientes, on="ESPECIALIDADE", how="left")
    alvo["QTD_CLIENTES"] = alvo["QTD_CLIENTES"].fillna(0).astype(int)

    # Top produtos por especialidade (penetração entre clientes ativos) — do mix comercial
    top_prod = pd.DataFrame()
    if (
        df_specialty_mix is not None
        and not df_specialty_mix.empty
        and "PRODUTO" in df_specialty_mix.columns
    ):
        mix = df_specialty_mix.rename(
            columns={"CARACTERÍSTICA": "ESPECIALIDADE"}
        ).copy()
        mix = mix.sort_values(
            ["ESPECIALIDADE", "PENETRACAO_PCT"], ascending=[True, False]
        )
        mix["_rk"] = mix.groupby("ESPECIALIDADE").cumcount() + 1
        mix_top = mix[mix["_rk"] <= top_n].assign(
            _label=lambda x: x["PRODUTO"].astype(str)
            + " ("
            + x["PENETRACAO_PCT"].round(0).astype(int).astype(str)
            + "%)"
        )
        top_prod = (
            mix_top.groupby("ESPECIALIDADE")["_label"]
            .apply("; ".join)
            .reset_index(name="PRODUTOS_RECOMENDADOS")
        )
        primeiro = mix_top[mix_top["_rk"] == 1][
            ["ESPECIALIDADE", "PRODUTO", "PENETRACAO_PCT"]
        ].rename(
            columns={
                "PRODUTO": "TOP_PRODUTO",
                "PENETRACAO_PCT": "TOP_PENETRACAO_PCT",
            }
        )
        top_prod = top_prod.merge(primeiro, on="ESPECIALIDADE", how="left")

    if not top_prod.empty:
        alvo = alvo.merge(top_prod, on="ESPECIALIDADE", how="left")
    else:
        alvo["PRODUTOS_RECOMENDADOS"] = pd.NA
        alvo["TOP_PRODUTO"] = pd.NA
        alvo["TOP_PENETRACAO_PCT"] = pd.NA

    alvo["PRODUTOS_RECOMENDADOS"] = alvo["PRODUTOS_RECOMENDADOS"].fillna(
        "Sem histórico de clientes na especialidade"
    )
    alvo["TOP_PENETRACAO_PCT"] = pd.to_numeric(
        alvo["TOP_PENETRACAO_PCT"], errors="coerce"
    ).round(1)
    return alvo.sort_values("QTD_PROSPECTS", ascending=False).reset_index(drop=True)


# ── Item 2: universo realmente acionável (audiência de e-mail marketing) ──────
def build_reachable_audience(base):
    """
    Audiência de campanha: dentre os PROSPECTS, quantos são realmente alcançáveis por
    e-mail marketing — têm e-mail E consentimento (`EMAIL_ACIONAVEL`, calculado por
    `operacional.build_contact_lookup`). Quebra por especialidade com total de
    prospects, com e-mail, que consentem e a audiência acionável (n e %). É o tamanho
    real da audiência endereçável hoje — quase sempre muito menor que a base bruta.
    """
    if base is None or base.empty or "EMAIL_ACIONAVEL" not in base.columns:
        return pd.DataFrame()
    pro = base[base["EH_PROSPECT"]]
    if pro.empty:
        return pd.DataFrame()

    res = (
        pro.groupby("ESPECIALIDADE")
        .agg(
            QTD_PROSPECTS=("CPF_LIMPO", "size"),
            COM_EMAIL=("TEM_EMAIL", "sum"),
            CONSENTEM=("ACEITA_EMAIL", "sum"),
            CONTATAVEIS=("CONTATAVEL", "sum"),
            AUDIENCIA_EMAIL=("EMAIL_ACIONAVEL", "sum"),
        )
        .reset_index()
    )
    for c in ["COM_EMAIL", "CONSENTEM", "CONTATAVEIS", "AUDIENCIA_EMAIL"]:
        res[c] = res[c].astype(int)
    res["PCT_AUDIENCIA"] = np.where(
        res["QTD_PROSPECTS"] > 0,
        (res["AUDIENCIA_EMAIL"] / res["QTD_PROSPECTS"] * 100).round(1),
        0,
    )
    return res.sort_values("QTD_PROSPECTS", ascending=False).reset_index(drop=True)
