from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.utils import get_comissao_col


def format_produtos(serie):
    """Concatena os produtos distintos de um grupo em uma string ordenada."""
    return ", ".join(sorted(set(serie.dropna().astype(str))))


def build_serie_temporal(df, inicio_real_apolice, inicio_real_cliente, output_dir=None):
    """
    Gera um DataFrame indexado por mês cobrindo do menor INÍCIO DE VIGÊNCIA
    ao maior TÉRMINO DE VIGÊNCIA, com métricas ativas e novas.
    """
    df_valid = df.dropna(subset=["INÍCIO DE VIGÊNCIA", "TÉRMINO DE VIGÊNCIA"]).copy()
    if df_valid.empty:
        return pd.DataFrame()

    min_date = df_valid["INÍCIO DE VIGÊNCIA"].min()
    max_date = df_valid["TÉRMINO DE VIGÊNCIA"].max()

    comissao_col = get_comissao_col(df)

    months = pd.date_range(start=min_date.replace(day=1), end=max_date, freq="MS")

    results = []
    for month_start in months:
        month_end = month_start + pd.offsets.MonthEnd(1)

        # Ativos no mês
        mask_ativa = (df_valid["INÍCIO DE VIGÊNCIA"] <= month_end) & (
            df_valid["TÉRMINO DE VIGÊNCIA"] >= month_start
        )
        df_ativa = df_valid[mask_ativa]

        apolices_ativas = (
            df_ativa[["APÓLICE", "SEGURADORA (ABREVIADO)"]].drop_duplicates().shape[0]
            if not df_ativa.empty
            else 0
        )
        clientes_ativos = df_ativa["CPF/CNPJ"].nunique() if not df_ativa.empty else 0
        premio_liquido = (
            df_ativa["PRÊMIO LÍQ. DO SEGURO"].sum() if not df_ativa.empty else 0
        )
        comissao = df_ativa[comissao_col].sum() if not df_ativa.empty else 0

        # Novas no mês
        mask_nova_apolice = (inicio_real_apolice >= month_start) & (
            inicio_real_apolice <= month_end
        )
        apolices_novas = mask_nova_apolice.sum()

        mask_novo_cliente = (inicio_real_cliente >= month_start) & (
            inicio_real_cliente <= month_end
        )
        clientes_novos = mask_novo_cliente.sum()

        results.append(
            {
                "mes": month_start,
                "apolices_ativas": apolices_ativas,
                "clientes_ativos": clientes_ativos,
                "apolices_novas": apolices_novas,
                "clientes_novos": clientes_novos,
                "premio_liquido": premio_liquido,
                "comissao": comissao,
            }
        )

    df_res = pd.DataFrame(results).set_index("mes")

    # Plotting
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Contagem
    axes[0].plot(
        df_res.index, df_res["apolices_ativas"], label="Apólices Ativas", marker="o"
    )
    axes[0].plot(
        df_res.index, df_res["clientes_ativos"], label="Clientes Ativos", marker="s"
    )
    axes[0].plot(
        df_res.index, df_res["apolices_novas"], label="Apólices Novas", marker="^"
    )
    axes[0].plot(
        df_res.index, df_res["clientes_novos"], label="Clientes Novos", marker="d"
    )
    axes[0].set_title("Métricas de Contagem")
    axes[0].legend()
    axes[0].grid(True)

    # Financeiro
    axes[1].plot(
        df_res.index,
        df_res["premio_liquido"],
        label="Prêmio Líquido",
        color="green",
        marker="o",
    )
    axes[1].plot(
        df_res.index, df_res["comissao"], label="Comissão", color="purple", marker="s"
    )
    axes[1].set_title("Métricas Financeiras")
    axes[1].legend()
    axes[1].grid(True)

    plt.tight_layout()
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        # O prompt pediu '03_serie_temporal_vigencia.png', mas como é o nb 5, ajustei o nome se desejar, ou mantenho
        plt.savefig(
            out_path / "03_serie_temporal_vigencia.png", dpi=150, bbox_inches="tight"
        )
    plt.show()

    return df_res


def build_perfil_cliente(df):
    """
    Gera um DataFrame com uma linha por CPF/CNPJ contendo métricas sumarizadas.
    """
    comissao_col = get_comissao_col(df)

    grp = df.groupby("CPF/CNPJ")
    res = grp.agg(
        {
            "NOME ABREVIADO DO PRODUTO": ["nunique", format_produtos],
            "PRÊMIO LÍQ. DO SEGURO": "sum",
            comissao_col: "sum",
        }
    )

    res.columns = ["qtd_produtos", "produtos", "premio_liquido", "comissao"]

    # qtd_apolices: quantidade distinta de pares (APÓLICE, SEGURADORA (ABREVIADO))
    apolices_unicas = df.groupby("CPF/CNPJ").apply(
        lambda x: x[["APÓLICE", "SEGURADORA (ABREVIADO)"]].drop_duplicates().shape[0]
    )
    res["qtd_apolices"] = apolices_unicas

    return res


def build_mix_produto_mes(df):
    """
    Gera um DataFrame agrupado por (mês, CPF/CNPJ) focado no mix de produtos.
    """
    df_valid = df.dropna(subset=["INÍCIO DE VIGÊNCIA", "TÉRMINO DE VIGÊNCIA"]).copy()
    if df_valid.empty:
        return pd.DataFrame()

    min_date = df_valid["INÍCIO DE VIGÊNCIA"].min()
    max_date = df_valid["TÉRMINO DE VIGÊNCIA"].max()

    comissao_col = get_comissao_col(df)
    months = pd.date_range(start=min_date.replace(day=1), end=max_date, freq="MS")

    results = []
    for month_start in months:
        month_end = month_start + pd.offsets.MonthEnd(1)

        mask_ativa = (df_valid["INÍCIO DE VIGÊNCIA"] <= month_end) & (
            df_valid["TÉRMINO DE VIGÊNCIA"] >= month_start
        )
        df_ativa = df_valid[mask_ativa]

        if df_ativa.empty:
            continue

        grp = df_ativa.groupby("CPF/CNPJ")
        mes_res = grp.agg(
            {
                "NOME ABREVIADO DO PRODUTO": ["nunique", format_produtos],
                "PRÊMIO LÍQ. DO SEGURO": "sum",
                comissao_col: "sum",
            }
        )

        mes_res.columns = ["qtd_produtos", "produtos", "premio_liquido", "comissao"]
        mes_res["mes"] = month_start

        results.append(mes_res.reset_index())

    if not results:
        return pd.DataFrame()

    final_df = pd.concat(results, ignore_index=True)
    return final_df.set_index(["mes", "CPF/CNPJ"])
