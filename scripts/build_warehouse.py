"""
build_warehouse.py — MVP da "camada de consulta única" (plataforma de inteligência).

Conceito (ver docs/EVOLUCAO_PLATAFORMA.md): o pipeline continua MONOLÍTICO; este script
apenas projeta um **DuckDB** sobre os Parquet que o `Main.py` já gera. Com isso, toda a
base (comercial + operacional) vira consultável por SQL num só lugar, sem servidor, sem
mudar o pipeline. As tabelas são VIEWS que leem os Parquet — regenerou o pipeline, o
warehouse reflete na hora.

Uso:
    python scripts/build_warehouse.py            # (re)constrói outputs/reports.duckdb + demo
    python scripts/build_warehouse.py --sql "SELECT ..."   # roda uma consulta ad-hoc

Esquemas criados:
    comercial.*   — uma view por Parquet de outputs/comercial/parquet
    operacional.* — uma view por Parquet de outputs/operacional/parquet
    marketing.*   — uma view por Parquet de outputs/marketing/parquet
    gold.*        — exemplos de visões de valor (cruzam os públicos)
"""

import argparse
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "outputs" / "reports.duckdb"


def _connect():
    """Conecta ao DuckDB falhando RÁPIDO e com mensagem clara se o arquivo estiver
    travado (aberto noutra ferramenta/conexão) — em vez de ficar pendurado."""
    try:
        return duckdb.connect(str(DB_PATH))
    except duckdb.Error as e:
        raise SystemExit(
            f"[ERRO] Não consegui abrir {DB_PATH.name}: {str(e).splitlines()[0]}\n"
            "Feche o arquivo .duckdb (DBeaver/Power BI/outra conexão) e rode novamente."
        )


TRACKS = {
    "comercial": ROOT / "outputs" / "comercial" / "parquet",
    "operacional": ROOT / "outputs" / "operacional" / "parquet",
    "marketing": ROOT / "outputs" / "marketing" / "parquet",
}


def _register_views(con):
    """Cria 1 view por Parquet, em schemas por público. Retorna o nº de views."""
    n = 0
    for schema, pdir in TRACKS.items():
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        if not pdir.exists():
            continue
        for pq in sorted(pdir.glob("*.parquet")):
            view = f'{schema}."{pq.stem}"'
            con.execute(
                f"CREATE OR REPLACE VIEW {view} AS "
                f"SELECT * FROM read_parquet('{pq.as_posix()}')"
            )
            n += 1
    return n


_GOLD_VIEWS = {
    # Ranking de produtores EXTERNOS (exclui a conta interna/casa); retenção JUSTA
    "produtores_externos": """
        SELECT PRODUTOR, QTD_CLIENTES, QTD_ITENS,
               "TAXA_RENOVACAO_RENOVAVEL_%" AS taxa_renov_renovavel_pct,
               "SHARE_ITENS_%", "SHARE_ACUM_%"
        FROM comercial."performance_produtor"
        WHERE EH_INTERNO = FALSE
        ORDER BY QTD_ITENS DESC
    """,
    # KPIs de uma olhada (cruza comercial + operacional)
    "kpis": """
        SELECT
          (SELECT COUNT(*) FROM comercial."clientes_crm")              AS cooperados,
          (SELECT COUNT(*) FROM comercial."agenda_renovacoes")         AS renovacoes_90d,
          (SELECT ROUND(100.0*AVG(CASE WHEN CONTATAVEL THEN 1 ELSE 0 END),1)
                  FROM comercial."agenda_renovacoes")                  AS pct_agenda_contatavel,
          (SELECT COUNT(*) FROM operacional."situacao_ativa_vencida")  AS apolices_ativa_vencida,
          (SELECT COUNT(*) FROM operacional."renovacao_como_novo")     AS renovacao_como_novo
    """,
    # Agenda de renovações por urgência + acionabilidade (fila de trabalho)
    "renovacoes_por_urgencia": """
        SELECT URGENCIA,
               COUNT(*)                                        AS apolices,
               SUM(CASE WHEN CONTATAVEL THEN 1 ELSE 0 END)     AS contataveis,
               SUM(CASE WHEN NOT CONTATAVEL THEN 1 ELSE 0 END) AS sem_canal,
               ROUND(SUM("PREMIO_ULTIMO_CICLO"), 0)            AS premio_em_risco
        FROM comercial."agenda_renovacoes"
        GROUP BY URGENCIA
        ORDER BY MIN(DIAS_ATE_VENCIMENTO)
    """,
    # Scorecard de qualidade (DQ2/DQ3; DQ1 fica de fora quando vem vazio)
    "qualidade_resumo": """
        SELECT 'Apolices Ativa-vencida (DQ3)' AS indicador,
               (SELECT COUNT(*) FROM operacional."situacao_ativa_vencida") AS qtd
        UNION ALL SELECT 'Renovacao cadastrada como novo (DQ2)',
               (SELECT COUNT(*) FROM operacional."renovacao_como_novo")
    """,
    # Marketing: maiores bolsões de prospects por especialidade (alvos de aquisição)
    "oportunidade_especialidade": """
        SELECT ESPECIALIDADE,
               QTD_COOPERADOS,
               QTD_PROSPECTS,
               "PCT_PROSPECT_NO_GRUPO" AS pct_prospect
        FROM marketing."distribuicao_especialidade"
        WHERE QTD_COOPERADOS >= 30
        ORDER BY QTD_PROSPECTS DESC
    """,
    # Margem seguradora×produto: combinações de alta taxa com prêmio relevante
    "margem_seg_produto_top": """
        SELECT SEGURADORA, PRODUTO,
               "TAXA_COMISSAO_EFETIVA_%" AS taxa_efetiva_pct,
               "SHARE_PREMIO_%"          AS share_premio_pct,
               PRODUTO_EXCLUSIVO_SEGURADORA
        FROM comercial."margem_comissao_seg_produto"
        WHERE "SHARE_PREMIO_%" >= 1
        ORDER BY "TAXA_COMISSAO_EFETIVA_%" DESC
    """,
}


def _register_gold(con):
    """Cria as views 'gold' (cada uma isolada — fonte ausente só pula aquela view)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    ok = 0
    for nome, sql in _GOLD_VIEWS.items():
        try:
            con.execute(f"CREATE OR REPLACE VIEW gold.{nome} AS {sql}")
            ok += 1
        except duckdb.Error as e:
            print(
                f"  [aviso] gold.{nome} pulada (fonte ausente?): {str(e).splitlines()[0]}"
            )
    return ok


def build():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = _connect()
    n = _register_views(con)
    g = _register_gold(con)

    print(
        f"Warehouse: {DB_PATH.relative_to(ROOT)}  |  {n} views base + {g} views gold "
        "(schemas comercial / operacional / gold)"
    )
    if g and _view_exists(con, "gold", "kpis"):
        print("\nKPIs (gold.kpis):")
        print(con.sql("SELECT * FROM gold.kpis").to_df().to_string(index=False))
        print("\nTop 5 produtores externos (gold.produtores_externos):")
        print(
            con.sql("SELECT * FROM gold.produtores_externos LIMIT 5")
            .to_df()
            .to_string(index=False)
        )
    con.close()


def _view_exists(con, schema, name):
    q = (
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = ? AND table_name = ?"
    )
    return con.execute(q, [schema, name]).fetchone() is not None


def run_sql(sql):
    con = _connect()
    print(con.sql(sql).to_df().to_string(index=False))
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Constrói/consulta o warehouse DuckDB."
    )
    parser.add_argument("--sql", help="Roda uma consulta SQL ad-hoc no warehouse.")
    args = parser.parse_args()
    if args.sql:
        run_sql(args.sql)
    else:
        build()
