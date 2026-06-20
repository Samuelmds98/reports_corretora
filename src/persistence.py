"""
persistence.py

Camada de persistência para consumo no Power BI (Fase 6).

Duas responsabilidades:
1. `export_parquet_tables` — grava as tabelas de negócio em Parquet, sobrescrevendo
   a cada execução (representa o estado atual da carteira).
2. `append_dq_history` — acumula o resumo de qualidade de cada execução num único
   Parquet que nunca é sobrescrito, só cresce (rastreabilidade da tendência de DQ).

Nenhuma função modifica os DataFrames recebidos. Colunas com tipos incompatíveis
com Parquet (listas, dicts, objetos mistos) são convertidas para `str` em vez de
lançar exceção.
"""

from pathlib import Path

import pandas as pd

PARQUET_ENGINE = "pyarrow"


def _stringify_problematic_columns(df):
    """
    Retorna uma cópia do DataFrame com colunas `object` que contenham objetos
    Python complexos (listas/dicts/sets/tuplas) convertidas para string.
    Valores nulos e strings simples são preservados.
    """
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == "object":
            tem_complexo = (
                out[col].apply(lambda v: isinstance(v, (list, dict, set, tuple))).any()
            )
            if tem_complexo:
                out[col] = out[col].apply(
                    lambda v: str(v) if isinstance(v, (list, dict, set, tuple)) else v
                )
    return out


def _write_parquet(df, path):
    """
    Escreve um DataFrame em Parquet de forma resiliente: tenta direto e, se algum
    tipo for incompatível, serializa as colunas `object` para str e tenta de novo.
    """
    safe = _stringify_problematic_columns(df)
    try:
        safe.to_parquet(path, index=False, engine=PARQUET_ENGINE)
    except Exception:
        # Última linha de defesa: serializa object -> str preservando os nulos
        fallback = safe.copy()
        for col in fallback.columns:
            if fallback[col].dtype == "object":
                fallback[col] = fallback[col].apply(
                    lambda v: (
                        None
                        if v is None or (isinstance(v, float) and pd.isna(v))
                        else str(v)
                    )
                )
        fallback.to_parquet(path, index=False, engine=PARQUET_ENGINE)


def export_parquet_tables(tables, output_dir):
    """
    Exporta um dicionário {nome_arquivo: DataFrame} como arquivos Parquet.
    Sobrescreve a cada execução — representa o estado atual da carteira.
    DataFrames vazios são pulados (não geram arquivo). Retorna lista de Paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for name, df in tables.items():
        if df is None or df.empty:
            print(f"  aviso: tabela '{name}' vazia — Parquet não gerado.")
            continue
        path = output_dir / f"{name}.parquet"
        _write_parquet(df, path)
        saved.append(path)
    return saved


def append_dq_history(df_resumo, history_path):
    """
    Acumula o resumo DQ de cada execução do pipeline em um Parquet histórico.
    Lê o arquivo existente, adiciona RUN_DATE, concatena e regrava. Se rodado mais
    de uma vez no mesmo dia, mantém apenas a execução mais recente daquele dia.
    Nunca sobrescreve execuções de dias anteriores. Retorna o Path do histórico.
    """
    history_path = Path(history_path)

    df_run = df_resumo.copy()
    df_run["RUN_DATE"] = pd.Timestamp("today").normalize().date()

    if history_path.exists():
        df_hist = pd.read_parquet(history_path, engine=PARQUET_ENGINE)
        df_combined = pd.concat([df_hist, df_run], ignore_index=True)
        # Mesma regra no mesmo dia: mantém a execução mais recente
        df_combined = df_combined.drop_duplicates(
            subset=["RUN_DATE", "REGRA_DQ"], keep="last"
        ).reset_index(drop=True)
    else:
        df_combined = df_run

    df_combined.to_parquet(history_path, index=False, engine=PARQUET_ENGINE)
    print(
        f"Histórico DQ atualizado: {len(df_combined)} registros em {history_path.name}"
    )
    return history_path
