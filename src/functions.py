import re

import numpy as np
import pandas as pd

from src.parameters import PRODUCT_TYPE_MAP
from src.utils import get_comissao_col


def clean_cpf_cnpj(val):
    """
    Limpa o CPF ou CNPJ removendo tudo que não for dígito e garantindo o padding correto (11 ou 14 dígitos).
    """
    if pd.isna(val):
        return ""
    cleaned = re.sub(r"\D", "", str(val))
    if len(cleaned) <= 11:
        return cleaned.zfill(11)
    else:
        return cleaned.zfill(14)


def prepare_demographics(df_cad):
    """
    Limpa e normaliza as colunas de Perfil oriundas do Cadastro.
    Padronização de string case e cálculo de Idade pelas datas de nascimento.
    """
    if df_cad.empty:
        return df_cad

    if "SEXO" in df_cad.columns:
        df_cad["SEXO"] = df_cad["SEXO"].fillna("NI").astype(str).str.upper().str.strip()

    for c in ["CIDADE", "BAIRRO", "ESTADO CIVIL", "CARACTERÍSTICA"]:
        if c in df_cad.columns:
            df_cad[c] = (
                df_cad[c].fillna("Não Informado").astype(str).str.title().str.strip()
            )

    dt_col = "DATA DE NASCIMENTO/DT. ABERTURA/FUNDAÇÃO"
    if dt_col in df_cad.columns:
        nasc = pd.to_datetime(df_cad[dt_col], errors="coerce")
        # Diferença em dias convertida para anos matemáticos (evitando o erro Unit Y is not supported do Numpy/Pandas novos)
        idade = (pd.Timestamp("today") - nasc).dt.days / 365.25
        # Floor vetorizado (Int64 nulável mantém inteiros e suporta <NA>)
        df_cad["IDADE"] = np.floor(idade).astype("Int64")

        # Bining Estatístico
        df_cad["FAIXA_ETARIA"] = (
            pd.cut(
                df_cad["IDADE"],
                bins=[-np.inf, 29, 39, 49, 59, 69, np.inf],
                labels=["Até 29", "30-39", "40-49", "50-59", "60-69", "70+"],
            )
            .astype(str)
            .replace("nan", "Não Calculada")
        )

    return df_cad


def extract_policy_root(policy):
    """
    Remove caracteres especiais (., -, /) e sufixos referentes a anos de uma apólice
    (ex: 2023, 2024), extraindo a sua raiz numérica.
    """
    if pd.isna(policy):
        return ""
    clean_pol = re.sub(r"[.\-/]", "", str(policy)).strip()

    # Remove um sufixo de ano (2000-2029) ao final, desde que haja algo antes
    # dele (o lookbehind impede que a raiz seja apenas o próprio ano).
    return re.sub(r"(?<=.)(?:20[0-2]\d)$", "", clean_pol)


def identify_root_conflicts(df):
    """
    Identifica registros conflitantes: Apólices cujo NÚMERO é diferente, mas a Raiz é a mesma,
    considerando a chave (CPF/CNPJ, SEGURADORA, RAMO).

    Retorna dois elementos:
     1) df atualizado (com a nova coluna de raiz)
     2) log_conflitos (Dataframe só com os problemas para auditoria)
    """
    if "CPF_LIMPO" not in df.columns:
        df["CPF_LIMPO"] = df["CPF/CNPJ"].apply(clean_cpf_cnpj)

    df["RAIZ_APÓLICE"] = df["APÓLICE"].apply(extract_policy_root)

    group_cols = ["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "RAMO", "RAIZ_APÓLICE"]

    # Contagem de apólices distintas por chave raiz
    agg_df = df.groupby(group_cols)["APÓLICE"].nunique().reset_index()
    agg_df = agg_df[agg_df["APÓLICE"] > 1]

    if len(agg_df) > 0:
        log_conflitos = pd.merge(df, agg_df[group_cols], on=group_cols, how="inner")
    else:
        log_conflitos = pd.DataFrame(columns=df.columns)

    return df, log_conflitos


def build_cancellation_index(df):
    """
    Pré-indexa, de uma só vez, as datas de início dos registros de cancelamento
    (TIPO DE NEGÓCIO CN/CR) por chave (CPF, SEGURADORA, RAMO, APÓLICE).

    Antes, cada produto varria a base inteira (`all_records`) atrás dos seus
    cancelamentos — comportamento O(n²). Com este índice o lookup vira O(1).
    """
    cancel_df = df[df["TIPO DE NEGÓCIO"].isin(["CN", "CR"])]
    key_cols = ["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "RAMO", "APÓLICE"]
    return {
        key: grp["INÍCIO DE VIGÊNCIA"].dropna().tolist()
        for key, grp in cancel_df.groupby(key_cols)
    }


def _is_cancelled(cancel_dates, lower, upper, today):
    """
    Há cancelamento se existe uma data de início CN/CR dentro da janela
    [lower, upper] (upper opcional) e não posterior a hoje.
    """
    for cn_inicio in cancel_dates:
        if pd.isna(cn_inicio):
            continue
        if cn_inicio > today or cn_inicio < lower:
            continue
        if upper is not None and cn_inicio > upper:
            continue
        return True
    return False


def get_product_status(group, cancel_index, today):
    """
    Aplica a hierarquia do Bloco A (Apólices) e Bloco B (Faturas) para definir o STATUS do produto.
    Recebe um subgrupo de linhas correspondente a (CPF_LIMPO, SEGURADORA, PRODUTO)
    e o índice de cancelamentos pré-computado por `build_cancellation_index`.
    """
    bloco_a = group[group["TIPO DE NEGÓCIO"].isin(["N", "R"])]

    if not bloco_a.empty:
        # Pega a mais recente
        base = bloco_a.sort_values("INÍCIO DE VIGÊNCIA", ascending=False).iloc[0]

        inicio = base["INÍCIO DE VIGÊNCIA"]
        termino = base["TÉRMINO DE VIGÊNCIA"]

        if (
            pd.notnull(inicio)
            and pd.notnull(termino)
            and inicio <= today
            and termino >= today
        ):
            key = (
                base["CPF_LIMPO"],
                base["SEGURADORA (ABREVIADO)"],
                base["RAMO"],
                base["APÓLICE"],
            )
            cancel_dates = cancel_index.get(key, ())
            return (
                "CANCELADO"
                if _is_cancelled(cancel_dates, inicio, termino, today)
                else "ATIVO"
            )
        else:
            return "INATIVO"

    # Bloco B (Caso sem N ou R, verificar se há FATURA)
    bloco_b = group[group["TIPO DOCUMENTO"] == "FATURA"]
    if not bloco_b.empty:
        base = bloco_b.sort_values("INÍCIO DE VIGÊNCIA", ascending=False).iloc[0]
        max_inicio = base["INÍCIO DE VIGÊNCIA"]

        if pd.notnull(max_inicio):
            dias_diff = (today - max_inicio).days
            if 0 <= dias_diff <= 90:
                key = (
                    base["CPF_LIMPO"],
                    base["SEGURADORA (ABREVIADO)"],
                    base["RAMO"],
                    base["APÓLICE"],
                )
                cancel_dates = cancel_index.get(key, ())
                if not _is_cancelled(cancel_dates, max_inicio, None, today):
                    return "ATIVO"

        return "INATIVO"

    return "INATIVO"


def flag_last_cycle(df):
    """
    Marca em cada linha BRUTA de produção se ela pertence ao ÚLTIMO ciclo de
    vigência da sua apólice, na coluna booleana `EH_ULTIMO_CICLO`.

    **Motivação:** uma apólice RENOVÁVEL renovada ano a ano (ex.: vigente
    2024→2025 e renovada 2025→2026) gera várias linhas N/R para a MESMA apólice.
    Somar prêmio/comissão de todos os anos infla o valor. Para visões de "valor
    vigente" (ex.: Agenda de Renovações) interessa apenas o ciclo mais recente.

    **Regra por chave (CPF_LIMPO, SEGURADORA, PRODUTO, RAIZ_APÓLICE):**
      - Há linhas N/R (apólice nova/renovação — Bloco A): o ciclo vigente começa no
        MAIOR `INÍCIO DE VIGÊNCIA` entre as linhas N/R. Entram as linhas com início
        ``>=`` esse valor (a renovação vigente + seus endossos EN/ER); os ciclos
        anteriores ficam de fora.
      - Sem N/R (só FATURA — recorrente): TODAS as linhas contam, pois cada fatura
        é um pagamento distinto e a soma total é a semântica correta (é por isso
        que `PRIMEIRO_INICIO`/`ULTIMO_TERMINO` continuam sendo mín./máx.).

    `RAIZ_APÓLICE` isola renovações da MESMA apólice (sufixo de ano removido em
    `extract_policy_root`), preservando apólices DISTINTAS (ex.: dois automóveis na
    mesma seguradora) como ciclos independentes — cada uma contribui com o seu
    último ciclo. Só sinaliza: não remove linhas nem altera valores.
    """
    df = df.copy()
    if "RAIZ_APÓLICE" not in df.columns:
        df["RAIZ_APÓLICE"] = df["APÓLICE"].apply(extract_policy_root)

    inicio = pd.to_datetime(df["INÍCIO DE VIGÊNCIA"], errors="coerce")
    is_nr = df["TIPO DE NEGÓCIO"].isin(["N", "R"])
    grp_keys = [
        df["CPF_LIMPO"],
        df["SEGURADORA (ABREVIADO)"],
        df["NOME ABREVIADO DO PRODUTO"],
        df["RAIZ_APÓLICE"],
    ]

    # Início do ciclo vigente por chave = maior início entre as linhas N/R do grupo.
    # Grupos sem N/R (só fatura) ficam com NaT e, por isso, contam todas as linhas.
    ciclo_inicio = inicio.where(is_nr).groupby(grp_keys).transform("max")

    df["EH_ULTIMO_CICLO"] = (ciclo_inicio.isna() | (inicio >= ciclo_inicio)).astype(
        bool
    )
    return df


def calculate_rating(client_products, today):
    """
    Analisa os produtos previamente statusificados de um mesmo cliente (agrupados),
    aplicando a regra Top-Down de pontuação de estrelas e de status global.
    """
    recorrentes = 0
    renovaveis = 0
    transacionais_12m = 0
    ativos_total = 0
    categorias_ativas = set()
    produtos_ativos = []

    for _, row in client_products.iterrows():
        prod_name = row["PRODUTO"]
        status = row["STATUS_PRODUTO"]
        # Lookup na tabela de mapeamento
        cat = (
            PRODUCT_TYPE_MAP.get(str(prod_name).strip(), "INDEFINIDO").upper()
            if pd.notnull(prod_name)
            else "INDEFINIDO"
        )

        is_ativo = status == "ATIVO"
        max_inicio = row["MAX_INICIO_VIGENCIA"]

        # TRANSACIONAL: Ativo OU vigência nos últimos 12 meses
        if cat == "TRANSACIONAL":
            if is_ativo:
                transacionais_12m += 1
                ativos_total += 1
                categorias_ativas.add(cat)
                produtos_ativos.append(prod_name)
            elif pd.notnull(max_inicio):
                days_diff = (today - max_inicio).days
                if 0 <= days_diff <= 365:
                    transacionais_12m += 1
                    ativos_total += 1
                    categorias_ativas.add(cat)
                    produtos_ativos.append(prod_name)
        else:
            # RENOVÁVEL ou RECORRENTE
            if is_ativo:
                if cat == "RECORRENTE":
                    recorrentes += 1
                elif cat == "RENOVÁVEL":
                    renovaveis += 1
                ativos_total += 1
                categorias_ativas.add(cat)
                produtos_ativos.append(prod_name)

    # Determinação do Status Global do Cliente
    status_global = (
        "ATIVO"
        if (recorrentes > 0 or renovaveis > 0 or transacionais_12m > 0)
        else "INATIVO"
    )

    qtd_categorias = len(categorias_ativas)

    # Motor de Rating Top-Down
    rating = 0
    if recorrentes >= 1 and renovaveis >= 2 and transacionais_12m >= 1:
        rating = 5
    elif recorrentes >= 1 and renovaveis >= 1 and transacionais_12m >= 1:
        rating = 4
    elif qtd_categorias >= 2:
        rating = 3
    elif ativos_total >= 2 and qtd_categorias == 1:
        rating = 2
    elif ativos_total == 1:
        rating = 1

    lista_prods = (
        ", ".join(sorted(set([str(p) for p in produtos_ativos])))
        if produtos_ativos
        else "Nenhum"
    )

    return pd.Series(
        {
            "STATUS_GLOBAL": status_global,
            "RATING_ESTRELAS": rating,
            "LISTA_PRODUTOS_ATIVOS": lista_prods,
        }
    )


def process_product_status(df):
    """
    Itera grupo a grupo (CPF_LIMPO, SEGURADORA, NOME ABREVIADO DO PRODUTO)
    para consolidar o status de vigência de cada produto e somar indicadores de receita.
    """
    today = pd.Timestamp("today").normalize()
    if "CPF_LIMPO" not in df.columns:
        df["CPF_LIMPO"] = df["CPF/CNPJ"].apply(clean_cpf_cnpj)

    # Âncora do "valor vigente": marca as linhas do último ciclo de cada apólice
    # (idempotente — só recalcula se o pipeline ainda não tiver marcado).
    if "EH_ULTIMO_CICLO" not in df.columns:
        df = flag_last_cycle(df)

    df["INÍCIO DE VIGÊNCIA"] = pd.to_datetime(
        df["INÍCIO DE VIGÊNCIA"], errors="coerce"
    ).dt.normalize()
    df["TÉRMINO DE VIGÊNCIA"] = pd.to_datetime(
        df["TÉRMINO DE VIGÊNCIA"], errors="coerce"
    ).dt.normalize()

    group_cols = ["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "NOME ABREVIADO DO PRODUTO"]
    grouped = df.groupby(group_cols)

    results = []

    # Identificar a coluna exata de comissão da base
    comissao_col = get_comissao_col(df)

    # Índice de cancelamentos construído uma única vez (evita varrer a base por grupo)
    cancel_index = build_cancellation_index(df)

    for name, group in grouped:
        # Pega o Status usando as regras do Bloco A e Bloco B
        status = get_product_status(group, cancel_index, today)
        max_inicio = group["INÍCIO DE VIGÊNCIA"].max()

        # Agregações comerciais solicitadas
        min_inicio = group["INÍCIO DE VIGÊNCIA"].min()
        max_termino = group["TÉRMINO DE VIGÊNCIA"].max()
        soma_premio = (
            group["PRÊMIO LÍQ. DO SEGURO"].sum()
            if "PRÊMIO LÍQ. DO SEGURO" in group.columns
            else 0
        )
        soma_comissao = (
            group[comissao_col].sum() if comissao_col in group.columns else 0
        )
        media_pct = group["PORCENTAGEM"].mean() if "PORCENTAGEM" in group.columns else 0

        # "Valor vigente": soma apenas as linhas do último ciclo de cada apólice
        # (ver flag_last_cycle). Evita inflar prêmio/comissão somando renovações
        # de anos anteriores da MESMA apólice. SOMA_* acima permanece histórico.
        ciclo = group[group["EH_ULTIMO_CICLO"]]
        premio_ultimo_ciclo = (
            ciclo["PRÊMIO LÍQ. DO SEGURO"].sum()
            if "PRÊMIO LÍQ. DO SEGURO" in ciclo.columns
            else 0
        )
        comissao_ultimo_ciclo = (
            ciclo[comissao_col].sum() if comissao_col in ciclo.columns else 0
        )
        inicio_ultimo_ciclo = ciclo["INÍCIO DE VIGÊNCIA"].min()

        results.append(
            {
                "CPF_LIMPO": name[0],
                "SEGURADORA": name[1],
                "PRODUTO": name[2],
                "STATUS_PRODUTO": status,
                "PRIMEIRO_INICIO": min_inicio,
                "ULTIMO_TERMINO": max_termino,
                "INICIO_ULTIMO_CICLO": inicio_ultimo_ciclo,
                "SOMA_PREMIO_LIQ": soma_premio,
                "SOMA_COMISSAO": soma_comissao,
                "PREMIO_ULTIMO_CICLO": premio_ultimo_ciclo,
                "COMISSAO_ULTIMO_CICLO": comissao_ultimo_ciclo,
                "MEDIA_PORCENTAGEM": media_pct,
                "MAX_INICIO_VIGENCIA": max_inicio,  # Usado depois internamente no cálculo de Rating
            }
        )

    return pd.DataFrame(results)


def build_cycle_grain(df_prod):
    """
    Grão de CICLO de vigência: uma linha por ciclo de cada apólice, com a janela
    [PRIMEIRO_INICIO, ULTIMO_TERMINO] e o prêmio/comissão DAQUELE ciclo.

    Resolve a inflação multi-ciclo do Snapshot Mensal: em vez de repetir a soma
    histórica do produto em TODOS os meses de TODAS as vigências, cada renovação
    passa a contar apenas nos SEUS meses, com o SEU valor. Diferente de
    `flag_last_cycle` (que mantém só o último ciclo), aqui TODOS os ciclos são
    preservados — cada um na sua janela — para que a contagem histórica de ativos
    por mês não regrida (um cliente ativo em 2024 continua ativo em 2024).

    Devolve as MESMAS colunas que o `df_prod_status` expõe às funções de snapshot
    (`CPF_LIMPO`, `SEGURADORA`, `PRODUTO`, `PRIMEIRO_INICIO`, `ULTIMO_TERMINO`,
    `SOMA_PREMIO_LIQ`, `SOMA_COMISSAO`), para alimentá-las sem alterá-las — só que
    agora com várias linhas por produto (uma por ciclo).

    Regra por (CPF, SEGURADORA, PRODUTO, RAIZ_APÓLICE):
      - Bloco A (linhas N/R): cada N/R é um ciclo, com a janela [início, término] da
        própria linha. O valor do ciclo soma a N/R + os movimentos (endossos EN/ER)
        cujo início cai entre este ciclo e o início do próximo. Cancelamentos
        (CN/CR) ficam de fora do valor.
      - Recorrente (só FATURA, sem N/R): um único "ciclo" cobrindo
        [mín. início, máx. término] do produto, somando as faturas (fluxo recorrente).
    """
    df = df_prod.copy()
    if "RAIZ_APÓLICE" not in df.columns:
        df["RAIZ_APÓLICE"] = df["APÓLICE"].apply(extract_policy_root)
    df["INÍCIO DE VIGÊNCIA"] = pd.to_datetime(df["INÍCIO DE VIGÊNCIA"], errors="coerce")
    df["TÉRMINO DE VIGÊNCIA"] = pd.to_datetime(
        df["TÉRMINO DE VIGÊNCIA"], errors="coerce"
    )

    comissao_col = get_comissao_col(df)
    has_premio = "PRÊMIO LÍQ. DO SEGURO" in df.columns
    has_comissao = comissao_col in df.columns

    def _premio(sub):
        return sub["PRÊMIO LÍQ. DO SEGURO"].sum() if has_premio else 0

    def _comissao(sub):
        return sub[comissao_col].sum() if has_comissao else 0

    keys = [
        "CPF_LIMPO",
        "SEGURADORA (ABREVIADO)",
        "NOME ABREVIADO DO PRODUTO",
        "RAIZ_APÓLICE",
    ]
    rows = []
    for (cpf, seg, prod, _raiz), g in df.groupby(keys, dropna=False):
        nr = g[g["TIPO DE NEGÓCIO"].isin(["N", "R"])].sort_values("INÍCIO DE VIGÊNCIA")
        # Movimentos que compõem valor (exclui cancelamentos)
        mov = g[~g["TIPO DE NEGÓCIO"].isin(["CN", "CR"])]

        if not nr.empty:
            inicios = nr["INÍCIO DE VIGÊNCIA"].tolist()
            for i, (_, base) in enumerate(nr.iterrows()):
                ci = base["INÍCIO DE VIGÊNCIA"]
                ct = base["TÉRMINO DE VIGÊNCIA"]
                # Limite superior do ciclo = início do próximo N/R (renovação seguinte)
                nxt = inicios[i + 1] if i + 1 < len(inicios) else pd.Timestamp.max
                in_cycle = mov[
                    (mov["INÍCIO DE VIGÊNCIA"] >= ci)
                    & (mov["INÍCIO DE VIGÊNCIA"] < nxt)
                ]
                rows.append(
                    {
                        "CPF_LIMPO": cpf,
                        "SEGURADORA": seg,
                        "PRODUTO": prod,
                        "PRIMEIRO_INICIO": ci,
                        "ULTIMO_TERMINO": ct,
                        "SOMA_PREMIO_LIQ": _premio(in_cycle),
                        "SOMA_COMISSAO": _comissao(in_cycle),
                    }
                )
        else:
            rows.append(
                {
                    "CPF_LIMPO": cpf,
                    "SEGURADORA": seg,
                    "PRODUTO": prod,
                    "PRIMEIRO_INICIO": g["INÍCIO DE VIGÊNCIA"].min(),
                    "ULTIMO_TERMINO": g["TÉRMINO DE VIGÊNCIA"].max(),
                    "SOMA_PREMIO_LIQ": _premio(mov),
                    "SOMA_COMISSAO": _comissao(mov),
                }
            )
    return pd.DataFrame(rows)


def generate_client_insights(df_prod):
    """
    Roda todo o funil desde os produtos até os ratings por CPF.
    Agora retorna DOIS dataframes: o resumo de clientes e a base analítica de produtos.
    """
    today = pd.Timestamp("today").normalize()

    # 1. Base detalhada: processa agrupado por produto/seguradora
    df_prod_status = process_product_status(df_prod)

    # 2. Resumo de Cliente: processa o Rating da base detalhada por CPF
    df_client_rating = (
        df_prod_status.groupby("CPF_LIMPO")
        .apply(lambda g: calculate_rating(g, today))
        .reset_index()
    )

    return df_client_rating, df_prod_status
