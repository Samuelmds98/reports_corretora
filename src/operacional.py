"""
operacional.py

Métricas do track OPERACIONAL/QUALIDADE — servem ao backoffice e à gestão de
processo (≠ comercial). O foco aqui não é vender, é **expor problemas de cadastro
e de processo** que distorcem as análises comerciais. Como o resto do projeto,
estas funções **só sinalizam, nunca corrigem**, e carregam a âncora de origem
(`ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`) sempre que listam linhas, para auditoria.

Contexto de domínio que motiva cada métrica (registrado no contrato de dados):
  - `SITUAÇÃO` é o status do **documento**, não da apólice efetiva: uma apólice pode
    estar `Ativa` e ter um endosso de cancelamento vigente que a cancela de fato sem
    mudar a `SITUAÇÃO`. → `build_active_with_cancellation`.
  - Renovação cadastrada como **negócio novo** sem linkar a apólice antiga: a antiga
    fica `Vencida` (em vez de `Renovada`) e a renovação entra como `N`, inflando
    "negócio novo" e subestimando a retenção. → `build_renewal_as_new`.
  - ~40% da base veio de `USUÁRIO DA INCLUSÃO = MIGRACAO`, o que enviesa qualquer
    série temporal de venda. → `build_origem_cadastro`.
  - O `STATUS_PRODUTO` calculado pelo motor pode divergir da `SITUAÇÃO` nativa — a
    divergência é o sinal. → `build_status_vs_situacao`.
  - `SITUAÇÃO = Ativa` com vigência já vencida = status de documento defasado (devia ser
    `Renovada`/`Vencida`). → `build_situacao_ativa_vencida`.

Semântica de `SITUAÇÃO` (confirmada com o negócio): só `Ativa` é vigente; `Renovada` =
linha substituída por uma renovação (inativa, há outro registro `Ativa` do negócio);
`Vencida`/`Cancelada`/`Perda total` são não-vigentes.
"""

import numpy as np
import pandas as pd

ORIGIN_COLS = ["ID_LINHA", "ARQUIVO_ORIGEM", "LINHA_ORIGEM"]
_CANCEL_NEG = ["CN", "CR"]  # TIPO DE NEGÓCIO de cancelamento
# Só `Ativa` aparenta vigência. `Renovada` = linha SUBSTITUÍDA por uma renovação
# (logo inativa; existe outro registro `Ativa` do mesmo negócio). `Vencida`/`Cancelada`/
# `Perda total` também são não-vigentes. (Semântica confirmada com o negócio.)
_ATIVA = ["ATIVA"]


def _ana_keys(df):
    """Aliases de SEGURADORA/PRODUTO alinhados às demais visões (sem mutar o input)."""
    out = df.copy()
    out["SEGURADORA"] = out["SEGURADORA (ABREVIADO)"]
    out["PRODUTO"] = out["NOME ABREVIADO DO PRODUTO"]
    return out


def _is_cancel_row(df):
    """Linha de cancelamento: TIPO DE NEGÓCIO CN/CR ou TIPO DOCUMENTO de cancelamento."""
    neg = df["TIPO DE NEGÓCIO"].isin(_CANCEL_NEG)
    doc = (
        df["TIPO DOCUMENTO"]
        .astype(str)
        .str.contains("Cancelamento", case=False, na=False)
        if "TIPO DOCUMENTO" in df.columns
        else False
    )
    return neg | doc


def build_origem_cadastro(df_prod):
    """
    Migrado × Orgânico por ano de início de vigência. `USUÁRIO DA INCLUSÃO = MIGRACAO`
    marca carga histórica; o resto é cadastro orgânico. Como ~40% da base é migrada
    (e com datas de proposta achatadas), as séries de venda/safra dos primeiros anos
    refletem migração, não originação real — esta tabela quantifica esse viés.
    """
    if df_prod.empty or "USUÁRIO DA INCLUSÃO" not in df_prod.columns:
        return pd.DataFrame()

    df = df_prod.copy()
    df["ORIGEM_CADASTRO"] = np.where(
        df["USUÁRIO DA INCLUSÃO"]
        .astype(str)
        .str.upper()
        .str.contains("MIGRA", na=False),
        "Migrado",
        "Orgânico",
    )
    df["ANO_INICIO"] = pd.to_datetime(df["INÍCIO DE VIGÊNCIA"], errors="coerce").dt.year

    res = (
        df.groupby("ANO_INICIO")["ORIGEM_CADASTRO"]
        .value_counts()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ("Migrado", "Orgânico"):
        if col not in res.columns:
            res[col] = 0
    res["TOTAL"] = res["Migrado"] + res["Orgânico"]
    res["PCT_MIGRADO"] = np.where(
        res["TOTAL"] > 0, res["Migrado"] / res["TOTAL"] * 100, 0
    ).round(1)
    return res.sort_values("ANO_INICIO")


def _concorda_status_situacao(status_produto, situacao):
    """Motor ATIVO ↔ SITUAÇÃO `Ativa`; INATIVO/CANCELADO ↔ qualquer não-`Ativa`."""
    s = str(situacao).upper()
    return s in _ATIVA if status_produto == "ATIVO" else s not in _ATIVA


def build_status_situacao_base(df_prod, df_prod_status):
    """
    Lastro do Status×Situação: uma linha por produto (CPF×SEGURADORA×PRODUTO) com o
    `STATUS_PRODUTO` (motor) e a `SITUAÇÃO` da apólice N/R mais recente do grupo +
    `CONCORDA`. É a base que a matriz agrega — serve de lastro auditável.
    """
    if df_prod.empty or df_prod_status.empty or "SITUAÇÃO" not in df_prod.columns:
        return pd.DataFrame()

    keys = ["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "NOME ABREVIADO DO PRODUTO"]
    prod = df_prod.copy()
    prod["_INI"] = pd.to_datetime(prod["INÍCIO DE VIGÊNCIA"], errors="coerce")
    ap = prod[prod["TIPO DE NEGÓCIO"].isin(["N", "R"])].sort_values("_INI")
    if ap.empty:
        return pd.DataFrame()
    last = ap.groupby(keys, dropna=False).tail(1)[keys + ["SITUAÇÃO"]]
    last = last.rename(
        columns={
            "SEGURADORA (ABREVIADO)": "SEGURADORA",
            "NOME ABREVIADO DO PRODUTO": "PRODUTO",
        }
    )
    base = df_prod_status[
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO", "STATUS_PRODUTO"]
    ].merge(last, on=["CPF_LIMPO", "SEGURADORA", "PRODUTO"], how="inner")
    if base.empty:
        return base
    base["CONCORDA"] = base.apply(
        lambda r: _concorda_status_situacao(r["STATUS_PRODUTO"], r["SITUAÇÃO"]), axis=1
    )
    return base


def build_status_vs_situacao(df_prod, df_prod_status):
    """
    Concordância entre o `STATUS_PRODUTO` (calculado pelo motor de vigência) e a
    `SITUAÇÃO` nativa (status do documento) — matriz de contingência. Cada divergência
    é candidata a problema de cadastro/processo (ex.: SITUAÇÃO `Ativa` com cancelamento
    efetivo; ou `Vencida` que era renovação não-linkada). Lastro em
    `build_status_situacao_base`.
    """
    base = build_status_situacao_base(df_prod, df_prod_status)
    if base.empty:
        return pd.DataFrame()

    mat = (
        base.groupby(["STATUS_PRODUTO", "SITUAÇÃO"])
        .size()
        .reset_index(name="QTD_PRODUTOS")
        .sort_values("QTD_PRODUTOS", ascending=False)
    )
    total = mat["QTD_PRODUTOS"].sum()
    mat["PCT"] = np.where(total > 0, mat["QTD_PRODUTOS"] / total * 100, 0).round(1)
    mat["CONCORDA"] = mat.apply(
        lambda r: _concorda_status_situacao(r["STATUS_PRODUTO"], r["SITUAÇÃO"]), axis=1
    )
    return mat


def build_situacao_ativa_vencida(df_prod):
    """
    DQ3 — apólices com `SITUAÇÃO = Ativa` mas **vigência já vencida** (`TÉRMINO` < hoje).
    Pela regra do negócio, uma apólice cujo prazo passou deveria estar `Renovada` ou
    `Vencida` — `Ativa` aqui é status de documento não atualizado (cadastro defasado).

    Restrito a **apólices** (linhas N/R); endossos ficam de fora porque o comportamento
    de vigência deles ainda será confirmado com o backoffice. Lista uma linha por
    apólice sinalizada, com a âncora de origem e os dias de atraso.
    """
    if df_prod.empty or "SITUAÇÃO" not in df_prod.columns:
        return pd.DataFrame()

    today = pd.Timestamp("today").normalize()
    df = _ana_keys(df_prod)
    df = df[df["TIPO DE NEGÓCIO"].isin(["N", "R"])].copy()
    df["_TER"] = pd.to_datetime(df["TÉRMINO DE VIGÊNCIA"], errors="coerce")

    ativa = df["SITUAÇÃO"].astype(str).str.upper().isin(_ATIVA)
    vencida = df["_TER"].notna() & (df["_TER"] < today)
    flag = df[ativa & vencida].copy()
    if flag.empty:
        return pd.DataFrame()

    flag["DIAS_VENCIDA"] = (today - flag["_TER"]).dt.days
    cols = (
        [c for c in ORIGIN_COLS if c in flag.columns]
        + ["CPF_LIMPO", "SEGURADORA", "PRODUTO", "RAMO", "APÓLICE"]
        + ["SITUAÇÃO", "INÍCIO DE VIGÊNCIA", "TÉRMINO DE VIGÊNCIA", "DIAS_VENCIDA"]
    )
    out = flag[[c for c in cols if c in flag.columns]]
    return out.sort_values("DIAS_VENCIDA", ascending=False)


def build_active_with_cancellation(df_prod):
    """
    DQ1 — apólices que **aparentam vigência** (`SITUAÇÃO = Ativa` na linha N/R)
    mas têm um **endosso/registro de cancelamento** na mesma apólice. O documento
    segue "ativo", mas o cancelamento pode já ter efetivado a baixa — caso clássico de
    status enganoso. Lista uma linha por apólice sinalizada, com a âncora de origem do
    registro de cancelamento para conferência.
    """
    if df_prod.empty or "SITUAÇÃO" not in df_prod.columns:
        return pd.DataFrame()

    df = _ana_keys(df_prod)
    key = ["CPF_LIMPO", "SEGURADORA", "PRODUTO", "RAMO", "APÓLICE"]
    df["_CANCEL"] = _is_cancel_row(df)
    df["_APOL_ATIVA"] = df["TIPO DE NEGÓCIO"].isin(["N", "R"]) & df["SITUAÇÃO"].astype(
        str
    ).str.upper().isin(_ATIVA)

    flags = df.groupby(key, dropna=False).agg(
        TEM_CANCELAMENTO=("_CANCEL", "any"),
        APOLICE_APARENTE_ATIVA=("_APOL_ATIVA", "any"),
    )
    suspeitas = flags[flags["TEM_CANCELAMENTO"] & flags["APOLICE_APARENTE_ATIVA"]]
    if suspeitas.empty:
        return pd.DataFrame()

    suspeitas = suspeitas.reset_index()[key]
    # Anexa as linhas de cancelamento dessas apólices (com âncora de origem)
    cancel_rows = df[df["_CANCEL"]].merge(suspeitas, on=key, how="inner")
    cols = (
        [c for c in ORIGIN_COLS if c in cancel_rows.columns]
        + key
        + ["TIPO DE NEGÓCIO", "TIPO DOCUMENTO", "SITUAÇÃO", "INÍCIO DE VIGÊNCIA"]
    )
    out = cancel_rows[[c for c in cols if c in cancel_rows.columns]].copy()
    return out.sort_values(key)


def build_renewal_as_new(df_prod, janela_dias=120):
    """
    DQ2 — provável **renovação cadastrada como negócio novo** sem linkar a apólice
    anterior. Heurística: um registro `N` (novo) cujo início cai perto (±`janela_dias`)
    do término de uma apólice `Vencida` do mesmo `(CPF, SEGURADORA, RAMO)`, com **raiz
    de apólice diferente** (logo não foi pega pelo `Log_Apolices_Conflito`, que exige
    mesma raiz). Quando isso ocorre, a antiga vira `Vencida` em vez de `Renovada` e a
    renovação infla o "negócio novo" — distorce retenção e originação.
    """
    if df_prod.empty or "SITUAÇÃO" not in df_prod.columns:
        return pd.DataFrame()

    df = _ana_keys(df_prod)
    df["_INI"] = pd.to_datetime(df["INÍCIO DE VIGÊNCIA"], errors="coerce")
    df["_TER"] = pd.to_datetime(df["TÉRMINO DE VIGÊNCIA"], errors="coerce")
    if "RAIZ_APÓLICE" not in df.columns:
        return pd.DataFrame()

    on = ["CPF_LIMPO", "SEGURADORA", "RAMO"]
    novos = df[df["TIPO DE NEGÓCIO"] == "N"]
    vencidas = df[df["SITUAÇÃO"].astype(str).str.upper() == "VENCIDA"]
    if novos.empty or vencidas.empty:
        return pd.DataFrame()

    m = novos.merge(vencidas, on=on, suffixes=("_NOVO", "_VENC"))
    m["GAP_DIAS"] = (m["_INI_NOVO"] - m["_TER_VENC"]).dt.days
    m = m[
        (m["GAP_DIAS"].abs() <= janela_dias)
        & (m["RAIZ_APÓLICE_NOVO"] != m["RAIZ_APÓLICE_VENC"])
    ]
    if m.empty:
        return pd.DataFrame()

    out = pd.DataFrame(
        {
            "CPF_LIMPO": m["CPF_LIMPO"],
            "SEGURADORA": m["SEGURADORA"],
            "RAMO": m["RAMO"],
            "PRODUTO_NOVO": m["PRODUTO_NOVO"],
            "APOLICE_NOVA": m["APÓLICE_NOVO"],
            "INICIO_NOVO": m["_INI_NOVO"],
            "APOLICE_VENCIDA": m["APÓLICE_VENC"],
            "TERMINO_VENCIDA": m["_TER_VENC"],
            "GAP_DIAS": m["GAP_DIAS"],
            "ID_LINHA_NOVO": m.get("ID_LINHA_NOVO"),
            "ID_LINHA_VENCIDA": m.get("ID_LINHA_VENC"),
        }
    )
    return out.drop_duplicates().sort_values(["CPF_LIMPO", "SEGURADORA", "INICIO_NOVO"])


# ── Acionabilidade / contatabilidade (telefone, e-mail, consentimento) ─────────
_CONSENT_COL = "ACEITA RECEBER E-MAILS PROMOCIONAIS"


def _has_value(s):
    """True onde a string tem conteúdo útil (não nula, não vazia, não 'nan')."""
    t = s.astype(str).str.strip()
    return t.notna() & (t != "") & (t.str.upper() != "NAN")


def build_contact_lookup(df_cad):
    """
    Por `CPF_LIMPO`, flags de contatabilidade vindas do cadastro:
      - `TEM_TELEFONE` / `TEM_EMAIL` — há um canal preenchido;
      - `ACEITA_EMAIL` — consentimento de marketing (`ACEITA RECEBER E-MAILS...`);
      - `CONTATAVEL` — tem ao menos um canal (telefone OU e-mail);
      - `EMAIL_ACIONAVEL` — tem e-mail E consentimento (universo de e-mail marketing).
    Base para os dois cortes de acionabilidade (por cliente na lista de ação e
    agregado por produtor).
    """
    cols = [
        "CPF_LIMPO",
        "TEM_TELEFONE",
        "TEM_EMAIL",
        "ACEITA_EMAIL",
        "CONTATAVEL",
        "EMAIL_ACIONAVEL",
    ]
    if df_cad is None or df_cad.empty or "CPF_LIMPO" not in df_cad.columns:
        return pd.DataFrame(columns=cols)

    df = df_cad.drop_duplicates("CPF_LIMPO")
    falso = pd.Series(False, index=df.index)  # default alinhado ao índice

    tem_tel = _has_value(df["TELEFONE"]) if "TELEFONE" in df.columns else falso
    tem_mail = _has_value(df["EMAIL"]) if "EMAIL" in df.columns else falso
    consent = (
        df[_CONSENT_COL].astype(str).str.strip().str.upper().str.startswith("S")
        if _CONSENT_COL in df.columns
        else falso
    )
    out = pd.DataFrame({"CPF_LIMPO": df["CPF_LIMPO"].values})
    out["TEM_TELEFONE"] = tem_tel.fillna(False).astype(bool).values
    out["TEM_EMAIL"] = tem_mail.fillna(False).astype(bool).values
    out["ACEITA_EMAIL"] = consent.fillna(False).astype(bool).values
    out["CONTATAVEL"] = out["TEM_TELEFONE"] | out["TEM_EMAIL"]
    out["EMAIL_ACIONAVEL"] = out["TEM_EMAIL"] & out["ACEITA_EMAIL"]
    return out


def add_contact_flags(df_action, contact_lookup):
    """
    CORTE (a) — anexa as flags de contatabilidade a uma lista de ação (Agenda de
    Renovações, Win-Back) por `CPF_LIMPO`. Transforma a lista priorizada em lista
    *executável*: separa quem dá pra contatar de quem está bloqueado por cadastro.
    CPFs sem cadastro ficam como não-contatáveis (False).
    """
    flags = [
        "TEM_TELEFONE",
        "TEM_EMAIL",
        "ACEITA_EMAIL",
        "CONTATAVEL",
        "EMAIL_ACIONAVEL",
    ]
    if df_action is None or df_action.empty:
        return df_action
    if contact_lookup is None or contact_lookup.empty:
        for f in flags:
            df_action[f] = False
        return df_action
    out = df_action.merge(contact_lookup, on="CPF_LIMPO", how="left")
    for f in flags:
        if f in out.columns:
            out[f] = out[f].fillna(False).astype(bool)
    return out


def build_contact_by_client(df_prod, df_cad):
    """
    Lastro da acionabilidade por produtor: uma linha por cliente com o PRODUTOR
    atribuído (apólice N/R mais recente) e as flags de contato. A agregação por
    produtor soma isto — serve de lastro auditável.
    """
    if df_prod.empty or "PRODUTOR" not in df_prod.columns:
        return pd.DataFrame()

    contacts = build_contact_lookup(df_cad)
    df = df_prod.copy()
    df["_INI"] = pd.to_datetime(df["INÍCIO DE VIGÊNCIA"], errors="coerce")

    # Produtor da apólice (N/R) mais recente de cada cliente; fallback p/ qualquer linha
    ap = df[df["TIPO DE NEGÓCIO"].isin(["N", "R"])]
    base = ap if not ap.empty else df
    prod_por_cpf = (
        base.sort_values("_INI").groupby("CPF_LIMPO").tail(1)[["CPF_LIMPO", "PRODUTOR"]]
    )

    m = prod_por_cpf.merge(contacts, on="CPF_LIMPO", how="left")
    for f in [
        "TEM_TELEFONE",
        "TEM_EMAIL",
        "CONTATAVEL",
        "EMAIL_ACIONAVEL",
        "ACEITA_EMAIL",
    ]:
        if f in m.columns:
            m[f] = m[f].fillna(False).astype(bool)
        else:
            m[f] = False
    return m


def build_contactability_by_producer(df_prod, df_cad):
    """
    CORTE (b) — % de clientes com contato por PRODUTOR (métrica de qualidade de
    cadastro). Como um cliente pode ter apólices de produtores diferentes, atribui
    cada cliente ao produtor da sua apólice (N/R) **mais recente**. Mostra onde estão
    os buracos de contato e qual produtor precisa enriquecer o cadastro. Lastro em
    `build_contact_by_client`.
    """
    m = build_contact_by_client(df_prod, df_cad)
    if m.empty:
        return pd.DataFrame()
    for f in ["TEM_TELEFONE", "TEM_EMAIL", "CONTATAVEL", "EMAIL_ACIONAVEL"]:
        m[f] = m[f].astype(int)

    res = (
        m.groupby("PRODUTOR")
        .agg(
            QTD_CLIENTES=("CPF_LIMPO", "nunique"),
            COM_TELEFONE=("TEM_TELEFONE", "sum"),
            COM_EMAIL=("TEM_EMAIL", "sum"),
            CONTATAVEIS=("CONTATAVEL", "sum"),
            EMAIL_ACIONAVEL=("EMAIL_ACIONAVEL", "sum"),
        )
        .reset_index()
    )
    res["PCT_CONTATAVEL"] = (res["CONTATAVEIS"] / res["QTD_CLIENTES"] * 100).round(1)
    res["PCT_TELEFONE"] = (res["COM_TELEFONE"] / res["QTD_CLIENTES"] * 100).round(1)
    res["PCT_EMAIL"] = (res["COM_EMAIL"] / res["QTD_CLIENTES"] * 100).round(1)
    return res.sort_values("QTD_CLIENTES", ascending=False)
