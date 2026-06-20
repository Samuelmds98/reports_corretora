import numpy as np
import pandas as pd

from src.parameters import PRODUCT_TYPE_MAP, PRODUTOR_INTERNO_KEYWORDS
from src.utils import get_comissao_col


def _classifica_abc(pct):
    """Classe ABC pelo % acumulado de prêmio (Pareto 80/15/5)."""
    if pct <= 0.80:
        return "Classe A (Top 80%)"
    if pct <= 0.95:
        return "Classe B (Nicho Médio 15%)"
    return "Classe C (Cauda 5%)"


def build_demographics(df_cruzamento):
    """
    Visão 1: Perfil Demográfico
    Gera as taxas de conversão (Ativos/Inativos) para cada cluster de Médico por Idade, Sexo, Especialidade...
    """
    if df_cruzamento.empty:
        return pd.DataFrame()

    cols = []
    # Usando as colunas solicitadas, se existirem na base pós-cruzamento
    for c in [
        "CIDADE",
        "ESTADO",
        "SEXO",
        "ESTADO CIVIL",
        "FAIXA_ETARIA",
        "CARACTERÍSTICA",
    ]:
        if c in df_cruzamento.columns:
            cols.append(c)

    if not cols:
        return pd.DataFrame(
            {"ALERTA": ["Colunas demográficas ausentes do cruzamento."]}
        )

    # Grouping
    res = (
        df_cruzamento.groupby(cols)
        .agg(
            TOTAL_COOPERADOS=("CPF_LIMPO", "count"),
            COOPERADOS_ATIVOS=("STATUS_GLOBAL", lambda x: (x == "ATIVO").sum()),
            TICKET_MEDIO_ESTRELAS=("RATING_ESTRELAS", "mean"),
        )
        .reset_index()
    )

    res["TAXA_CONVERSAO_%"] = (res["COOPERADOS_ATIVOS"] / res["TOTAL_COOPERADOS"]) * 100
    res = res.sort_values(by="COOPERADOS_ATIVOS", ascending=False)
    return res


def build_abc_curve(df_prod_status):
    """
    Visão 2: Curva ABC / Share of Wallet
    Aplica o Pareto isolando os tubarões (Classe A) que mais compõem as receitas.

    Usa o valor vigente (`PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO`): a "carteira
    de hoje" por cliente, sem inflar com renovações de anos anteriores da mesma apólice.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    df_receita = (
        df_prod_status.groupby(["CPF_LIMPO"])
        .agg(
            PRODUTOS_COMPRADOS=("PRODUTO", "count"),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
        )
        .reset_index()
    )

    df_receita = df_receita.sort_values(by="TOTAL_PREMIO_LIQ", ascending=False)

    soma_total = df_receita["TOTAL_PREMIO_LIQ"].sum()
    if soma_total > 0:
        df_receita["%_ACUMULADO"] = df_receita["TOTAL_PREMIO_LIQ"].cumsum() / soma_total
    else:
        df_receita["%_ACUMULADO"] = 0

    df_receita["CURVA_ABC"] = df_receita["%_ACUMULADO"].apply(_classifica_abc)
    df_receita["TICKET_MEDIO_PREMIO_POR_PRODUTO"] = np.where(
        df_receita["PRODUTOS_COMPRADOS"] > 0,
        df_receita["TOTAL_PREMIO_LIQ"] / df_receita["PRODUTOS_COMPRADOS"],
        0,
    )

    return df_receita


def build_cross_sell_matrix(df_prod_status):
    """
    Visão 3: Matriz de Produtos para Oferta e Next Best Product
    Fazendo One-Hot Encoding explícito e rastreável CPF por CPF.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    # Consideramos as carteiras vigentes
    ativos = df_prod_status[df_prod_status["STATUS_PRODUTO"] == "ATIVO"].copy()
    if ativos.empty:
        return pd.DataFrame({"CPF_LIMPO": df_prod_status["CPF_LIMPO"].unique()})

    # Pivotando produtos nas colunas
    pivot = pd.crosstab(index=ativos["CPF_LIMPO"], columns=ativos["PRODUTO"])

    for c in pivot.columns:
        pivot[c] = np.where(pivot[c] > 0, "SIM (Ativo)", "NÃO")

    pivot = pivot.reset_index()
    return pivot


def build_time_series_growth(df_prod_status):
    """
    Visão 6 e 8: Sazonalidade (Safra) por Início Vigência (Cohorts Temporal)
    Exibe Clientes, Produtos, Premínio, Comissão e Ticket agrupados por Data.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    df_ts = df_prod_status.copy()
    df_ts = df_ts[pd.notnull(df_ts["PRIMEIRO_INICIO"])]
    if df_ts.empty:
        return pd.DataFrame()

    # Cria o Safra Ano/Mês (YYYY-MM)
    df_ts["SAFRA_MES_VIGENCIA"] = pd.to_datetime(
        df_ts["PRIMEIRO_INICIO"], errors="coerce"
    ).dt.strftime("%Y-%m")

    res = (
        df_ts.groupby("SAFRA_MES_VIGENCIA")
        .agg(
            CLIENTES_DISTINTOS_Safra=("CPF_LIMPO", "nunique"),
            PRODUTOS_VENDIDOS_Safra=("PRODUTO", "nunique"),
            VALOR_PREMIO=("SOMA_PREMIO_LIQ", "sum"),
            VALOR_COMISSAO=("SOMA_COMISSAO", "sum"),
        )
        .reset_index()
    )

    res["TICKET_MEDIO_CLIENTE_NO_MES"] = np.where(
        res["CLIENTES_DISTINTOS_Safra"] > 0,
        res["VALOR_PREMIO"] / res["CLIENTES_DISTINTOS_Safra"],
        0,
    )
    res["TICKET_MEDIO_PRODUTO_NO_MES"] = np.where(
        res["PRODUTOS_VENDIDOS_Safra"] > 0,
        res["VALOR_PREMIO"] / res["PRODUTOS_VENDIDOS_Safra"],
        0,
    )

    res = res.sort_values("SAFRA_MES_VIGENCIA", ascending=True)
    return res


def build_partner_performance(df_prod_status):
    """
    Visão 5: Market Share de Seguradoras (Soma Volume, Receita e Comissões).

    Usa o valor vigente (último ciclo) para não inflar o prêmio das renováveis
    multi-ciclo — mede a participação na carteira atual de cada parceiro.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    res = (
        df_prod_status.groupby("SEGURADORA")
        .agg(
            QTD_CLIENTES_DISTINTOS=("CPF_LIMPO", "nunique"),
            QTD_ITENS_ATIVOS=("STATUS_PRODUTO", lambda x: (x == "ATIVO").sum()),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
            MEDIA_TAXA_PORCENTAGEM_DE_COMISSAO=("MEDIA_PORCENTAGEM", "mean"),
        )
        .reset_index()
    )

    res = res.sort_values("TOTAL_PREMIO_LIQ", ascending=False)

    soma_total = res["TOTAL_PREMIO_LIQ"].sum()
    if soma_total > 0:
        res["MARKET_SHARE_RECEITA_%"] = (res["TOTAL_PREMIO_LIQ"] / soma_total) * 100

    return res


def build_specialty_mix(df_cruzamento, df_prod_status):
    """
    Visão 10: Cruza a especialidade (CARACTERÍSTICA) do cooperado com os produtos
    ativos, calculando a penetração de cada produto por grupo de especialidade.
    Útil para abordagem comercial segmentada por perfil profissional.
    """
    if df_cruzamento.empty or df_prod_status.empty:
        return pd.DataFrame()

    # Especialidade por cooperado (trata nulos)
    col_esp = "CARACTERÍSTICA"
    if col_esp not in df_cruzamento.columns:
        return pd.DataFrame(
            {"ALERTA": ["Coluna CARACTERÍSTICA ausente do cruzamento."]}
        )

    df_esp = df_cruzamento[["CPF_LIMPO", col_esp]].copy()
    df_esp[col_esp] = df_esp[col_esp].fillna("Não Informado")

    # Apenas produtos ativos
    ativos = df_prod_status[df_prod_status["STATUS_PRODUTO"] == "ATIVO"][
        ["CPF_LIMPO", "PRODUTO"]
    ].copy()
    if ativos.empty:
        return pd.DataFrame()

    merged = pd.merge(ativos, df_esp, on="CPF_LIMPO", how="left")
    merged[col_esp] = merged[col_esp].fillna("Não Informado")

    # Cooperados distintos com cada produto, por especialidade
    res = (
        merged.groupby([col_esp, "PRODUTO"])["CPF_LIMPO"]
        .nunique()
        .reset_index(name="QTD_COOPERADOS_COM_PRODUTO")
    )

    # Total de cooperados ativos distintos por especialidade
    total_esp = (
        merged.groupby(col_esp)["CPF_LIMPO"]
        .nunique()
        .reset_index(name="TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE")
    )

    res = pd.merge(res, total_esp, on=col_esp, how="left")
    res["PENETRACAO_PCT"] = np.where(
        res["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"] > 0,
        res["QTD_COOPERADOS_COM_PRODUTO"]
        / res["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"]
        * 100,
        0,
    )

    res = res.sort_values([col_esp, "PENETRACAO_PCT"], ascending=[True, False])
    return res


def build_renewal_agenda(df_prod_status, df_client_insights):
    """
    Visão 11: Filtra produtos RENOVÁVEIS ativos com ULTIMO_TERMINO nos próximos
    90 dias, enriquece com o rating do cliente e classifica por urgência.
    É a fila de ligações do corretor, ordenada por proximidade do vencimento.

    Valor exibido = `PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO` (apenas o ciclo
    de vigência mais recente da apólice), e NÃO o histórico `SOMA_*`. Para uma
    apólice renovada ano a ano, somar todos os ciclos inflaria o prêmio em risco.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    today = pd.Timestamp("today").normalize()

    df = df_prod_status[df_prod_status["STATUS_PRODUTO"] == "ATIVO"].copy()
    df["TIPO_VIGENCIA"] = df["PRODUTO"].map(PRODUCT_TYPE_MAP)
    df = df[df["TIPO_VIGENCIA"] == "RENOVÁVEL"].copy()
    if df.empty:
        return pd.DataFrame()

    df["ULTIMO_TERMINO"] = pd.to_datetime(df["ULTIMO_TERMINO"], errors="coerce")
    df["DIAS_ATE_VENCIMENTO"] = (df["ULTIMO_TERMINO"] - today).dt.days
    df = df[(df["DIAS_ATE_VENCIMENTO"] >= 0) & (df["DIAS_ATE_VENCIMENTO"] <= 90)].copy()
    if df.empty:
        return pd.DataFrame()

    # Classificação de urgência por faixa de dias
    df["URGENCIA"] = np.select(
        [
            df["DIAS_ATE_VENCIMENTO"] <= 30,
            df["DIAS_ATE_VENCIMENTO"] <= 60,
            df["DIAS_ATE_VENCIMENTO"] <= 90,
        ],
        ["🔴 Até 30 dias", "🟡 31 a 60 dias", "🟢 61 a 90 dias"],
        default="",
    )

    df = pd.merge(
        df,
        df_client_insights[["CPF_LIMPO", "RATING_ESTRELAS", "STATUS_GLOBAL"]],
        on="CPF_LIMPO",
        how="left",
    )

    df = df.sort_values(
        ["DIAS_ATE_VENCIMENTO", "RATING_ESTRELAS"], ascending=[True, False]
    )

    cols = [
        "CPF_LIMPO",
        "SEGURADORA",
        "PRODUTO",
        "INICIO_ULTIMO_CICLO",
        "ULTIMO_TERMINO",
        "DIAS_ATE_VENCIMENTO",
        "URGENCIA",
        "PREMIO_ULTIMO_CICLO",
        "COMISSAO_ULTIMO_CICLO",
        "RATING_ESTRELAS",
    ]
    return df[[c for c in cols if c in df.columns]]


def build_winback_candidates(df_prod_status, df_client_insights):
    """
    Visão 12: Identifica clientes inativos cujo último produto venceu nos últimos
    12 meses. Candidatos prioritários para reativação, pois já conhecem a corretora.
    Ordenados por prêmio histórico (maior valor demonstrado primeiro).

    Obs.: o filtro original do plano (rating >= 2) seria sempre vazio — no motor
    atual o rating é derivado dos produtos ativos, logo todo cliente INATIVO tem
    rating 0. Por isso o recorte usa apenas o status + janela de 12 meses.
    """
    if df_prod_status.empty or df_client_insights.empty:
        return pd.DataFrame()

    today = pd.Timestamp("today").normalize()
    cutoff_12m = today - pd.DateOffset(months=12)

    # Clientes inativos (já tiveram produtos, hoje sem nada ativo)
    inativos = df_client_insights[df_client_insights["STATUS_GLOBAL"] == "INATIVO"]
    cpfs_inativos = inativos["CPF_LIMPO"].unique()
    if len(cpfs_inativos) == 0:
        return pd.DataFrame()

    base = df_prod_status[df_prod_status["CPF_LIMPO"].isin(cpfs_inativos)].copy()
    base["ULTIMO_TERMINO"] = pd.to_datetime(base["ULTIMO_TERMINO"], errors="coerce")

    # Último vencimento e prêmio histórico total por CPF
    df_ultimo = (
        base.groupby("CPF_LIMPO")
        .agg(
            ULTIMO_TERMINO=("ULTIMO_TERMINO", "max"),
            TOTAL_PREMIO_HISTORICO=("SOMA_PREMIO_LIQ", "sum"),
        )
        .reset_index()
    )

    # Venceu nos últimos 12 meses
    df_ultimo = df_ultimo[
        (df_ultimo["ULTIMO_TERMINO"] >= cutoff_12m)
        & (df_ultimo["ULTIMO_TERMINO"] < today)
    ].copy()
    if df_ultimo.empty:
        return pd.DataFrame()

    df_ultimo["DIAS_INATIVO"] = (today - df_ultimo["ULTIMO_TERMINO"]).dt.days

    # Enriquecer com rating e últimos produtos
    df_ultimo = pd.merge(
        df_ultimo,
        df_client_insights[["CPF_LIMPO", "RATING_ESTRELAS", "LISTA_PRODUTOS_ATIVOS"]],
        on="CPF_LIMPO",
        how="left",
    )

    df_ultimo = df_ultimo.sort_values(
        ["TOTAL_PREMIO_HISTORICO", "DIAS_INATIVO"], ascending=[False, True]
    )

    cols = [
        "CPF_LIMPO",
        "RATING_ESTRELAS",
        "ULTIMO_TERMINO",
        "DIAS_INATIVO",
        "LISTA_PRODUTOS_ATIVOS",
        "TOTAL_PREMIO_HISTORICO",
    ]
    return df_ultimo[[c for c in cols if c in df_ultimo.columns]]


def build_monthly_active_snapshot(df_prod_status):
    """
    Visão 13: Explode cada produto em uma linha por mês de vigência (M-to-N
    explosion) e agrega quantos clientes e produtos estavam ativos a cada mês.
    Responde 'Quantos clientes ativos tínhamos em março de 2023?'.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    df = df_prod_status.dropna(subset=["PRIMEIRO_INICIO", "ULTIMO_TERMINO"]).copy()
    if df.empty:
        return pd.DataFrame()

    df["PRIMEIRO_INICIO"] = pd.to_datetime(df["PRIMEIRO_INICIO"], errors="coerce")
    df["ULTIMO_TERMINO"] = pd.to_datetime(df["ULTIMO_TERMINO"], errors="coerce")
    df = df.dropna(subset=["PRIMEIRO_INICIO", "ULTIMO_TERMINO"])

    # Lista de meses vigentes por produto (vetorizado, sem iterrows)
    df["MES_REFERENCIA"] = df.apply(
        lambda r: pd.date_range(
            start=r["PRIMEIRO_INICIO"].replace(day=1),
            end=r["ULTIMO_TERMINO"],
            freq="MS",
        ),
        axis=1,
    )

    exploded = df.explode("MES_REFERENCIA").dropna(subset=["MES_REFERENCIA"])
    if exploded.empty:
        return pd.DataFrame()

    exploded["MES_REFERENCIA"] = exploded["MES_REFERENCIA"].dt.strftime("%Y-%m")

    res = (
        exploded.groupby("MES_REFERENCIA")
        .agg(
            CLIENTES_ATIVOS=("CPF_LIMPO", "nunique"),
            PRODUTOS_ATIVOS=("PRODUTO", "count"),
            PRODUTOS_DISTINTOS=("PRODUTO", "nunique"),
            PREMIO_TOTAL=("SOMA_PREMIO_LIQ", "sum"),
            COMISSAO_TOTAL=("SOMA_COMISSAO", "sum"),
        )
        .reset_index()
    )

    res["TICKET_MEDIO_CLIENTE"] = np.where(
        res["CLIENTES_ATIVOS"] > 0,
        res["PREMIO_TOTAL"] / res["CLIENTES_ATIVOS"],
        0,
    )

    res = res.sort_values("MES_REFERENCIA", ascending=True)
    return res


def build_origination_sums(df_prod, start_date="2025-01-01"):
    """
    Versões 14/15: somas JANELADAS de Curva ABC e Market Share, filtrando as linhas
    BRUTAS de produção por INÍCIO DE VIGÊNCIA >= start_date. Retorna (df_abc, df_share).

    RESSALVA DE SEMÂNTICA — o parâmetro de janela é `INÍCIO DE VIGÊNCIA`. Portanto
    isto mede o prêmio de itens cuja **vigência iniciou** no período ("originação no
    período"), e NÃO a receita reconhecida no período:
      - faturas mensais (recorrente): cada fatura tem início próprio → ≈ receita do período;
      - apólices anuais (renovável): captura negócio novo/renovado em start_date+, mas
        **exclui a cauda** de contratos iniciados antes do corte que seguem vigentes.

    Filtra as linhas brutas (não o `df_prod_status`), pois o `PRIMEIRO_INICIO` agregado
    é o mínimo do grupo e descartaria um recorrente iniciado antes do corte que ainda
    fatura dentro da janela.
    """
    if df_prod is None or df_prod.empty:
        return pd.DataFrame(), pd.DataFrame()

    prod_col = "NOME ABREVIADO DO PRODUTO"
    seg_col = "SEGURADORA (ABREVIADO)"
    premio_col = "PRÊMIO LÍQ. DO SEGURO"
    comissao_col = get_comissao_col(df_prod)
    janela = pd.Timestamp(start_date)

    ini = pd.to_datetime(df_prod["INÍCIO DE VIGÊNCIA"], errors="coerce")
    sub = df_prod[ini >= janela].copy()
    if sub.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Curva ABC janelada (por CPF)
    df_abc = (
        sub.groupby("CPF_LIMPO")
        .agg(
            PRODUTOS_DISTINTOS=(prod_col, "nunique"),
            TOTAL_PREMIO_LIQ=(premio_col, "sum"),
            TOTAL_COMISSAO=(comissao_col, "sum"),
        )
        .reset_index()
        .sort_values("TOTAL_PREMIO_LIQ", ascending=False)
    )
    soma_abc = df_abc["TOTAL_PREMIO_LIQ"].sum()
    df_abc["%_ACUMULADO"] = (
        df_abc["TOTAL_PREMIO_LIQ"].cumsum() / soma_abc if soma_abc > 0 else 0
    )
    df_abc["CURVA_ABC"] = df_abc["%_ACUMULADO"].apply(_classifica_abc)
    df_abc["JANELA_INICIO"] = janela.date()

    # Market Share janelado (por seguradora)
    df_share = (
        sub.groupby(seg_col)
        .agg(
            QTD_CLIENTES_DISTINTOS=("CPF_LIMPO", "nunique"),
            TOTAL_PREMIO_LIQ=(premio_col, "sum"),
            TOTAL_COMISSAO=(comissao_col, "sum"),
        )
        .reset_index()
        .rename(columns={seg_col: "SEGURADORA"})
        .sort_values("TOTAL_PREMIO_LIQ", ascending=False)
    )
    soma_share = df_share["TOTAL_PREMIO_LIQ"].sum()
    if soma_share > 0:
        df_share["MARKET_SHARE_RECEITA_%"] = (
            df_share["TOTAL_PREMIO_LIQ"] / soma_share * 100
        )
    df_share["JANELA_INICIO"] = janela.date()

    return df_abc, df_share


def build_snapshot_grain(df_prod_status):
    """
    Grão do snapshot mensal: explode cada produto nas suas parcelas mensais de
    vigência (uma linha por CPF×SEGURADORA×PRODUTO×MÊS). Espelha exatamente a
    explosão de `build_monthly_active_snapshot`, servindo de lastro auditável e
    de tabela granular para o Power BI reconstruir o snapshot.
    """
    if df_prod_status is None or df_prod_status.empty:
        return pd.DataFrame()

    df = df_prod_status.dropna(subset=["PRIMEIRO_INICIO", "ULTIMO_TERMINO"]).copy()
    if df.empty:
        return pd.DataFrame()

    df["PRIMEIRO_INICIO"] = pd.to_datetime(df["PRIMEIRO_INICIO"], errors="coerce")
    df["ULTIMO_TERMINO"] = pd.to_datetime(df["ULTIMO_TERMINO"], errors="coerce")
    df = df.dropna(subset=["PRIMEIRO_INICIO", "ULTIMO_TERMINO"])

    df["MES_REFERENCIA"] = df.apply(
        lambda r: pd.date_range(
            start=r["PRIMEIRO_INICIO"].replace(day=1),
            end=r["ULTIMO_TERMINO"],
            freq="MS",
        ),
        axis=1,
    )
    exploded = df.explode("MES_REFERENCIA").dropna(subset=["MES_REFERENCIA"])
    if exploded.empty:
        return pd.DataFrame()

    exploded["MES_REFERENCIA"] = exploded["MES_REFERENCIA"].dt.strftime("%Y-%m")
    cols = [
        "CPF_LIMPO",
        "SEGURADORA",
        "PRODUTO",
        "STATUS_PRODUTO",
        "MES_REFERENCIA",
        "SOMA_PREMIO_LIQ",
        "SOMA_COMISSAO",
    ]
    return exploded[[c for c in cols if c in exploded.columns]].reset_index(drop=True)


def build_producao_enriquecida(df_prod_status, df_cruzamento):
    """
    Grão central produto × cooperado para o Power BI: cada produto por cooperado
    enriquecido com perfil (especialidade, faixa etária, sexo, cidade, rating) e
    o tipo de vigência (RENOVÁVEL/RECORRENTE/TRANSACIONAL). Tabela-fato pronta
    para replicar métricas comerciais em DAX.
    """
    client_cols = [
        "CPF_LIMPO",
        "CARACTERÍSTICA",
        "FAIXA_ETARIA",
        "IDADE",
        "SEXO",
        "CIDADE",
        "RATING_ESTRELAS",
        "STATUS_GLOBAL",
        "LISTA_PRODUTOS_ATIVOS",
    ]
    available = [c for c in client_cols if c in df_cruzamento.columns]
    df_client = df_cruzamento[available].drop_duplicates("CPF_LIMPO")

    df = df_prod_status.copy()
    df["TIPO_PRODUTO"] = df["PRODUTO"].map(PRODUCT_TYPE_MAP).fillna("INDEFINIDO")
    return df.merge(df_client, on="CPF_LIMPO", how="left")


# ── Visões na ótica da COMISSÃO (o que a corretora de fato recebe) ────────────
def build_abc_curve_comissao(df_prod_status):
    """
    Visão 16: Curva ABC por COMISSÃO — concentração de quem mais gera comissão
    (≠ ABC por prêmio, pois a taxa varia por produto/seguradora). Pareto por CPF.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    df = (
        df_prod_status.groupby("CPF_LIMPO")
        .agg(
            PRODUTOS_COMPRADOS=("PRODUTO", "count"),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
        )
        .reset_index()
        .sort_values("TOTAL_COMISSAO", ascending=False)
    )
    soma = df["TOTAL_COMISSAO"].sum()
    df["%_ACUMULADO"] = df["TOTAL_COMISSAO"].cumsum() / soma if soma > 0 else 0
    df["CURVA_ABC_COMISSAO"] = df["%_ACUMULADO"].apply(_classifica_abc)
    df["TICKET_MEDIO_COMISSAO_POR_PRODUTO"] = np.where(
        df["PRODUTOS_COMPRADOS"] > 0, df["TOTAL_COMISSAO"] / df["PRODUTOS_COMPRADOS"], 0
    )
    return df


def build_partner_performance_comissao(df_prod_status):
    """
    Visão 17: Market Share por COMISSÃO + Margem por seguradora.
    Mostra a participação de cada seguradora na comissão recebida e a
    TAXA DE COMISSÃO EFETIVA (comissão / prêmio) — qual parceiro paga melhor.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    res = (
        df_prod_status.groupby("SEGURADORA")
        .agg(
            QTD_CLIENTES_DISTINTOS=("CPF_LIMPO", "nunique"),
            QTD_ITENS_ATIVOS=("STATUS_PRODUTO", lambda x: (x == "ATIVO").sum()),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
        )
        .reset_index()
        .sort_values("TOTAL_COMISSAO", ascending=False)
    )
    soma = res["TOTAL_COMISSAO"].sum()
    if soma > 0:
        res["MARKET_SHARE_COMISSAO_%"] = res["TOTAL_COMISSAO"] / soma * 100
    res["TAXA_COMISSAO_EFETIVA_%"] = np.where(
        res["TOTAL_PREMIO_LIQ"] > 0,
        res["TOTAL_COMISSAO"] / res["TOTAL_PREMIO_LIQ"] * 100,
        0,
    )
    return res


def build_commission_margin_produto(df_prod_status):
    """
    Visão 18: Margem (Taxa de Comissão Efetiva) por PRODUTO = comissão / prêmio.
    Revela quais produtos pagam melhor à corretora, independentemente do volume
    de prêmio. Ordenado pela taxa efetiva desc.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    res = (
        df_prod_status.groupby("PRODUTO")
        .agg(
            QTD_ITENS=("CPF_LIMPO", "count"),
            QTD_CLIENTES=("CPF_LIMPO", "nunique"),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
        )
        .reset_index()
    )
    res["TAXA_COMISSAO_EFETIVA_%"] = np.where(
        res["TOTAL_PREMIO_LIQ"] > 0,
        res["TOTAL_COMISSAO"] / res["TOTAL_PREMIO_LIQ"] * 100,
        0,
    )
    return res.sort_values("TAXA_COMISSAO_EFETIVA_%", ascending=False)


def build_commission_margin_seguradora_produto(df_prod_status):
    """
    Visão 19: Margem (Taxa de Comissão Efetiva) por SEGURADORA × PRODUTO.

    **Por que este grão:** o prêmio costuma se CONCENTRAR numa seguradora, mas a taxa
    efetiva (comissão/prêmio) varia por PRODUTO — e há produtos que só existem em
    seguradoras específicas. A visão por seguradora (17) sozinha esconde isso: uma
    seguradora pode liderar o prêmio só porque concentra um produto de alta margem.
    Cruzar seguradora × produto permite a comparação justa.

    Colunas-chave:
      - `TAXA_COMISSAO_EFETIVA_%` = comissão / prêmio (a margem real da combinação);
      - `SHARE_PREMIO_%` / `SHARE_COMISSAO_%` = concentração de cada combinação no total;
      - `N_SEGURADORAS_DO_PRODUTO` e `PRODUTO_EXCLUSIVO_SEGURADORA` = se o produto só
        é vendido por aquela seguradora (explica concentração + poder de negociação).

    Usa o valor vigente (último ciclo), igual às demais visões de carteira.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    res = (
        df_prod_status.groupby(["SEGURADORA", "PRODUTO"])
        .agg(
            QTD_CLIENTES=("CPF_LIMPO", "nunique"),
            QTD_ITENS=("CPF_LIMPO", "count"),
            TOTAL_COMISSAO=("COMISSAO_ULTIMO_CICLO", "sum"),
            TOTAL_PREMIO_LIQ=("PREMIO_ULTIMO_CICLO", "sum"),
        )
        .reset_index()
    )

    res["TAXA_COMISSAO_EFETIVA_%"] = np.where(
        res["TOTAL_PREMIO_LIQ"] > 0,
        res["TOTAL_COMISSAO"] / res["TOTAL_PREMIO_LIQ"] * 100,
        0,
    )

    soma_prem = res["TOTAL_PREMIO_LIQ"].sum()
    soma_com = res["TOTAL_COMISSAO"].sum()
    res["SHARE_PREMIO_%"] = np.where(
        soma_prem > 0, res["TOTAL_PREMIO_LIQ"] / soma_prem * 100, 0
    )
    res["SHARE_COMISSAO_%"] = np.where(
        soma_com > 0, res["TOTAL_COMISSAO"] / soma_com * 100, 0
    )

    # Exclusividade: em quantas seguradoras cada produto aparece (no dado atual)
    n_seg = res.groupby("PRODUTO")["SEGURADORA"].transform("nunique")
    res["N_SEGURADORAS_DO_PRODUTO"] = n_seg
    res["PRODUTO_EXCLUSIVO_SEGURADORA"] = n_seg == 1

    return res.sort_values(
        ["TOTAL_PREMIO_LIQ", "TAXA_COMISSAO_EFETIVA_%"], ascending=[False, False]
    )


# ── Raio X Qualitativo: análises NÃO-MONETÁRIAS (sem prêmio/comissão) ──────────
def build_cadastro_completeness(df_cad_raw, df_prod):
    """
    Diagnóstico de qualidade do cadastro: % de preenchimento e cardinalidade por
    campo (categórico/qualitativo). Abre a conversa mostrando o estado do cadastro.
    Usa o cadastro BRUTO (antes do preenchimento de nulos por prepare_demographics).
    """
    fontes = [
        (
            "Cadastro",
            df_cad_raw,
            [
                "SEXO",
                "ESTADO CIVIL",
                "CIDADE",
                "ESTADO",
                "BAIRRO",
                "CARACTERÍSTICA",
                "DATA DE NASCIMENTO/DT. ABERTURA/FUNDAÇÃO",
                "CLIENTE DESDE",
                "PROFISSÃO",
                "QTDE FILHOS/QTDE FUNCIONÁRIOS",
                "QTDE VEICS",
            ],
        ),
        (
            "Produção",
            df_prod,
            [
                "NOME ABREVIADO DO PRODUTO",
                "RAMO",
                "SEGURADORA (ABREVIADO)",
                "TIPO DE NEGÓCIO",
                "TIPO DOCUMENTO",
                "INÍCIO DE VIGÊNCIA",
                "TÉRMINO DE VIGÊNCIA",
                "CARACTERISTICA",
                "QUANTIDADE DE PARCELAS",
            ],
        ),
    ]
    linhas = []
    for origem, df, cols in fontes:
        n = len(df)
        for c in cols:
            if c not in df.columns:
                continue
            preench = (df[c].notna().mean() * 100) if n else 0
            distintos = int(df[c].nunique(dropna=True))
            if distintos <= 1:
                classe = "Inútil (constante)"
            elif preench >= 95:
                classe = "Alta"
            elif preench >= 70:
                classe = "Média"
            else:
                classe = "Baixa"
            linhas.append(
                {
                    "ORIGEM": origem,
                    "CAMPO": c,
                    "PREENCHIMENTO_PCT": round(preench, 1),
                    "VALORES_DISTINTOS": distintos,
                    "CONFIABILIDADE": classe,
                }
            )
    return pd.DataFrame(linhas).sort_values(
        ["ORIGEM", "PREENCHIMENTO_PCT"], ascending=[True, False]
    )


def build_product_distribution(df_prod_status):
    """Mix de produtos por CONTAGEM: cooperados, itens e ativos por produto."""
    if df_prod_status.empty:
        return pd.DataFrame()
    total_cpf = df_prod_status["CPF_LIMPO"].nunique()
    res = (
        df_prod_status.groupby("PRODUTO")
        .agg(
            QTD_COOPERADOS=("CPF_LIMPO", "nunique"),
            QTD_ITENS=("CPF_LIMPO", "count"),
            QTD_ATIVOS=("STATUS_PRODUTO", lambda x: (x == "ATIVO").sum()),
        )
        .reset_index()
    )
    res["TIPO_PRODUTO"] = res["PRODUTO"].map(PRODUCT_TYPE_MAP).fillna("INDEFINIDO")
    res["PCT_COOPERADOS"] = np.where(
        total_cpf > 0, res["QTD_COOPERADOS"] / total_cpf * 100, 0
    )
    return res.sort_values("QTD_COOPERADOS", ascending=False)


def build_partner_share_by_count(df_prod_status):
    """Market share por CONTAGEM (sem prêmio): clientes, itens e share de itens por seguradora."""
    if df_prod_status.empty:
        return pd.DataFrame()
    total_itens = len(df_prod_status)
    res = (
        df_prod_status.groupby("SEGURADORA")
        .agg(
            QTD_CLIENTES_DISTINTOS=("CPF_LIMPO", "nunique"),
            QTD_ITENS=("CPF_LIMPO", "count"),
            QTD_ATIVOS=("STATUS_PRODUTO", lambda x: (x == "ATIVO").sum()),
        )
        .reset_index()
    )
    res["SHARE_ITENS_PCT"] = np.where(
        total_itens > 0, res["QTD_ITENS"] / total_itens * 100, 0
    )
    return res.sort_values("QTD_ITENS", ascending=False)


def build_portfolio_depth(df_prod_status, df_client_insights):
    """
    Profundidade de carteira por cooperado (contagens): nº de produtos, categorias
    e seguradoras; classe (mono-produto / 2 / 3+) e gaps de cobertura
    (sem recorrente / sem renovável). Base para campanha de expansão sem usar valor.
    """
    if df_prod_status.empty:
        return pd.DataFrame()

    df = df_prod_status.copy()
    df["TIPO"] = df["PRODUTO"].map(PRODUCT_TYPE_MAP).fillna("INDEFINIDO")

    base = (
        df.groupby("CPF_LIMPO")
        .agg(
            N_PRODUTOS=("PRODUTO", "nunique"),
            N_SEGURADORAS=("SEGURADORA", "nunique"),
            N_ITENS=("PRODUTO", "count"),
        )
        .reset_index()
    )

    ativos = df[df["STATUS_PRODUTO"] == "ATIVO"]
    tipos = ativos.groupby("CPF_LIMPO")["TIPO"].agg(lambda s: set(s)).reset_index()
    tipos = tipos.rename(columns={"TIPO": "_TIPOS_ATIVOS"})
    base = base.merge(tipos, on="CPF_LIMPO", how="left")

    def _tem(s, t):
        return bool(isinstance(s, set) and t in s)

    base["TEM_RECORRENTE"] = base["_TIPOS_ATIVOS"].apply(
        lambda s: _tem(s, "RECORRENTE")
    )
    base["TEM_RENOVAVEL"] = base["_TIPOS_ATIVOS"].apply(lambda s: _tem(s, "RENOVÁVEL"))
    base["TEM_TRANSACIONAL"] = base["_TIPOS_ATIVOS"].apply(
        lambda s: _tem(s, "TRANSACIONAL")
    )
    base["N_CATEGORIAS_ATIVAS"] = base["_TIPOS_ATIVOS"].apply(
        lambda s: len(s) if isinstance(s, set) else 0
    )
    base = base.drop(columns=["_TIPOS_ATIVOS"])

    base["CLASSE_PROFUNDIDADE"] = np.where(
        base["N_PRODUTOS"] == 1,
        "Mono-produto",
        np.where(base["N_PRODUTOS"] == 2, "2 produtos", "3+ produtos"),
    )

    base = base.merge(
        df_client_insights[["CPF_LIMPO", "RATING_ESTRELAS", "STATUS_GLOBAL"]],
        on="CPF_LIMPO",
        how="left",
    )
    return base.sort_values(["N_PRODUTOS", "RATING_ESTRELAS"], ascending=[True, False])


def build_cancellation_rate(df_prod):
    """
    Taxa de cancelamento ESTRUTURAL por produto (sem valor): cancelamentos (CN/CR)
    sobre apólices (N/R). Mede churn usando só contagens de TIPO DE NEGÓCIO.
    """
    col = "NOME ABREVIADO DO PRODUTO"
    if col not in df_prod.columns or "TIPO DE NEGÓCIO" not in df_prod.columns:
        return pd.DataFrame()

    df = df_prod.copy()
    df["_APOLICE"] = df["TIPO DE NEGÓCIO"].isin(["N", "R"]).astype(int)
    df["_CANCEL"] = df["TIPO DE NEGÓCIO"].isin(["CN", "CR"]).astype(int)
    res = (
        df.groupby(col)
        .agg(N_APOLICES=("_APOLICE", "sum"), N_CANCELAMENTOS=("_CANCEL", "sum"))
        .reset_index()
        .rename(columns={col: "PRODUTO"})
    )
    res["TAXA_CANCELAMENTO_PCT"] = np.where(
        res["N_APOLICES"] > 0, res["N_CANCELAMENTOS"] / res["N_APOLICES"] * 100, 0
    )
    res = res[res["N_APOLICES"] > 0]
    return res.sort_values("TAXA_CANCELAMENTO_PCT", ascending=False)


def build_specialty_gaps(df_specialty, min_base=5):
    """
    Cross-sell gaps por especialidade: cooperados ativos da especialidade que NÃO
    têm o produto (oportunidade absoluta). Deriva do Mix; ordena pela maior lacuna.
    """
    if (
        df_specialty is None
        or df_specialty.empty
        or "PENETRACAO_PCT" not in df_specialty.columns
    ):
        return pd.DataFrame()

    df = df_specialty[
        df_specialty["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"] >= min_base
    ].copy()
    df["COOPERADOS_SEM_PRODUTO"] = (
        df["TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE"] - df["QTD_COOPERADOS_COM_PRODUTO"]
    )
    df["GAP_PCT"] = 100 - df["PENETRACAO_PCT"]
    return df.sort_values("COOPERADOS_SEM_PRODUTO", ascending=False)


def build_producer_performance(df_prod):
    """
    Visão comercial: desempenho por PRODUTOR (força de vendas). Responde quem produz
    quanto, com qual mix, qual concentração e quem retém melhor — dimensão até então
    inexistente no projeto.

    Por PRODUTOR:
      - carteira: `QTD_CLIENTES`, `QTD_ITENS`, `QTD_PRODUTOS`, `QTD_SEGURADORAS`;
      - mix: `PRODUTO_PRINCIPAL` (produto mais frequente);
      - originação: `N_NOVOS` vs `N_RENOVACOES` (TIPO DE NEGÓCIO N/R);
      - **retenção**: `TAXA_RENOVACAO_%` = `Renovada` ÷ (`Renovada` + `Vencida`) pela
        `SITUAÇÃO` nativa (só Ativa é vigente; Renovada = continuou, Vencida = caiu);
      - concentração (Pareto): `SHARE_ITENS_%` e `SHARE_ACUM_%`.

    Usa contagens (não-monetário) — robusto à baixa confiabilidade dos valores.
    """
    col = "PRODUTOR"
    prod_col = "NOME ABREVIADO DO PRODUTO"
    if df_prod is None or df_prod.empty or col not in df_prod.columns:
        return pd.DataFrame()

    df = df_prod.copy()
    neg = df.get("TIPO DE NEGÓCIO", pd.Series("", index=df.index)).astype(str)
    sit = df.get("SITUAÇÃO", pd.Series("", index=df.index)).astype(str).str.upper()
    # Tipo de vigência do produto (para a taxa de renovação JUSTA, só de renováveis)
    eh_renovavel = df[prod_col].map(PRODUCT_TYPE_MAP).eq("RENOVÁVEL")
    df["_NOVO"] = (neg == "N").astype(int)
    df["_RENOV"] = (neg == "R").astype(int)
    df["_RENOVADA"] = (sit == "RENOVADA").astype(int)
    df["_VENCIDA"] = (sit == "VENCIDA").astype(int)
    # Mesmas contagens restritas a produtos RENOVÁVEIS (comparação apples-to-apples)
    df["_RENOVADA_REN"] = ((sit == "RENOVADA") & eh_renovavel).astype(int)
    df["_VENCIDA_REN"] = ((sit == "VENCIDA") & eh_renovavel).astype(int)

    res = (
        df.groupby(col)
        .agg(
            QTD_CLIENTES=("CPF_LIMPO", "nunique"),
            QTD_ITENS=("CPF_LIMPO", "count"),
            QTD_PRODUTOS=(prod_col, "nunique"),
            QTD_SEGURADORAS=("SEGURADORA (ABREVIADO)", "nunique"),
            N_NOVOS=("_NOVO", "sum"),
            N_RENOVACOES=("_RENOV", "sum"),
            APOLICES_RENOVADAS=("_RENOVADA", "sum"),
            APOLICES_VENCIDAS=("_VENCIDA", "sum"),
            APOLICES_RENOVADAS_REN=("_RENOVADA_REN", "sum"),
            APOLICES_VENCIDAS_REN=("_VENCIDA_REN", "sum"),
        )
        .reset_index()
    )

    principal = (
        df.groupby(col)[prod_col]
        .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "—")
        .reset_index()
        .rename(columns={prod_col: "PRODUTO_PRINCIPAL"})
    )
    res = res.merge(principal, on=col, how="left")

    base_renov = res["APOLICES_RENOVADAS"] + res["APOLICES_VENCIDAS"]
    res["TAXA_RENOVACAO_%"] = np.where(
        base_renov > 0, (res["APOLICES_RENOVADAS"] / base_renov * 100).round(1), np.nan
    )
    # Taxa JUSTA: só produtos RENOVÁVEIS (tira o viés de mix — recorrente não "renova"
    # como apólice anual). É a métrica de retenção comparável entre produtores.
    base_ren = res["APOLICES_RENOVADAS_REN"] + res["APOLICES_VENCIDAS_REN"]
    res["TAXA_RENOVACAO_RENOVAVEL_%"] = np.where(
        base_ren > 0, (res["APOLICES_RENOVADAS_REN"] / base_ren * 100).round(1), np.nan
    )

    # Produtor interno/casa (sem repasse) avaliado à parte: fora do ranking e da
    # concentração — senão ele domina e mascara a força de vendas real.
    upper = res["PRODUTOR"].astype(str).str.upper()
    res["EH_INTERNO"] = upper.apply(
        lambda n: any(k in n for k in PRODUTOR_INTERNO_KEYWORDS)
    )

    # Externos primeiro (por volume); internos ao final. Share/Pareto só entre externos.
    res = res.sort_values(["EH_INTERNO", "QTD_ITENS"], ascending=[True, False])
    ext = ~res["EH_INTERNO"]
    total_ext = res.loc[ext, "QTD_ITENS"].sum()
    res["SHARE_ITENS_%"] = np.where(
        ext & (total_ext > 0), (res["QTD_ITENS"] / total_ext * 100).round(1), np.nan
    )
    res["SHARE_ACUM_%"] = res.loc[ext, "SHARE_ITENS_%"].cumsum().round(1)
    return res
