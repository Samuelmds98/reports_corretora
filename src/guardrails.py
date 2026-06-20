"""
guardrails.py

Sanidade do contexto de ingestão (Fase 7). Não corrige dados — apenas mede a
"forma" do input e alerta quando ele pode distorcer as análises.

Motivação: as bases são fatias filtradas (produção com corte temporal a partir de
2024; cadastro podendo ser recortado por categoria). Como as visões agregam um
snapshot, um input janelado/filtrado gera distorções silenciosas:
- somas (ABC, prêmio histórico do winback) viram totais da janela, não vitalícios;
- cohort/safra e snapshot mensal começam artificialmente no corte (a 1ª safra
  fica inflada por contratos iniciados antes da janela);
- se o cadastro for um subconjunto, a taxa de órfãos explode e as visões
  cadastro-side passam a cobrir uma população diferente da produção.

Este módulo torna isso **visível** (banner + parquet de contexto), que é a resposta
correta de engenharia para um input incompleto — não dá para "consertar" dado ausente.
"""

import pandas as pd

# Limiares de alerta (conservadores; ajustáveis conforme o negócio)
ORPHAN_PCT_ALERTA = 15.0  # acima disso, cadastro provavelmente é um subconjunto
N_CATEGORIAS_ALERTA = 2  # cadastro com <= isto sugere recorte por categoria


def build_run_context(
    df_prod,
    df_cad,
    inicio_col="INÍCIO DE VIGÊNCIA",
    carac_col="CARACTERÍSTICA",
):
    """
    Mede a janela temporal da produção e a cobertura produção × cadastro.
    Retorna (df_contexto: 1 linha, warnings: list[str]). Não muta os DataFrames.
    """
    ini = pd.to_datetime(df_prod.get(inicio_col), errors="coerce")
    janela_ini = ini.min()
    janela_fim = ini.max()
    n_meses = int(ini.dt.to_period("M").nunique()) if ini.notna().any() else 0

    cpfs_prod = set(df_prod["CPF_LIMPO"]) if "CPF_LIMPO" in df_prod.columns else set()
    cpfs_cad = set(df_cad["CPF_LIMPO"]) if "CPF_LIMPO" in df_cad.columns else set()
    orfaos = cpfs_prod - cpfs_cad
    pct_orfaos = (len(orfaos) / len(cpfs_prod) * 100) if cpfs_prod else 0.0

    n_categorias = df_cad[carac_col].nunique() if carac_col in df_cad.columns else 0

    contexto = {
        "JANELA_INICIO": janela_ini.date() if pd.notnull(janela_ini) else None,
        "JANELA_FIM": janela_fim.date() if pd.notnull(janela_fim) else None,
        "MESES_NA_JANELA": n_meses,
        "N_LINHAS_PRODUCAO": len(df_prod),
        "N_CPF_PRODUTORES": len(cpfs_prod),
        "N_CADASTRO": len(cpfs_cad),
        "N_CATEGORIAS_CADASTRO": int(n_categorias),
        "CPF_ORFAOS": len(orfaos),
        "PCT_ORFAOS": round(pct_orfaos, 1),
        "RUN_DATE": pd.Timestamp("today").normalize().date(),
    }

    warnings = []
    if pd.notnull(janela_ini):
        primeira_safra = janela_ini.strftime("%Y-%m")
        warnings.append(
            f"Produção janelada em {contexto['JANELA_INICIO']}..{contexto['JANELA_FIM']} "
            f"({n_meses} meses): cohort/safra, snapshot mensal e somas (curva ABC, prêmio "
            f"histórico do winback) refletem só esta janela — não são valores vitalícios. "
            f"A 1ª safra ({primeira_safra}) tende a estar inflada por contratos iniciados "
            f"antes do corte."
        )
    if pct_orfaos > ORPHAN_PCT_ALERTA:
        warnings.append(
            f"Taxa de órfãos alta ({pct_orfaos:.1f}% dos CPF produtores sem cadastro): o "
            f"cadastro é provavelmente um subconjunto filtrado. As visões cadastro-side "
            f"(demografia, CRM) cobrem população diferente das visões produção-side (ABC, "
            f"market share, snapshot), e o flag de órfão no DQ está inflado por design."
        )
    if 0 < n_categorias <= N_CATEGORIAS_ALERTA:
        warnings.append(
            f"Cadastro restrito a {n_categorias} categoria(s) de CARACTERÍSTICA: a demografia "
            f"e a taxa de conversão valem só para esse recorte — não interpretar como base completa."
        )

    contexto["WARNINGS"] = " | ".join(warnings) if warnings else "OK"
    return pd.DataFrame([contexto]), warnings
