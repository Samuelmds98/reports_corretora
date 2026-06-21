"""
Main.py — Pipeline principal "Raio X Cooperados".

Substitui o antigo notebook `06_cruzamento_cadastro_producao.ipynb`: lê os dois
Excel brutos, roda o motor de saneamento + rating, cruza cadastro × produção,
integra a auditoria de qualidade e exporta o data warehouse multi-abas formatado.

Uso:
    python Main.py
"""

import argparse
import hashlib
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.analytics import (
    build_abc_curve,
    build_abc_curve_comissao,
    build_cadastro_completeness,
    build_cancellation_rate,
    build_commission_margin_produto,
    build_commission_margin_seguradora_produto,
    build_cross_sell_matrix,
    build_demographics,
    build_monthly_active_snapshot,
    build_origination_sums,
    build_partner_performance,
    build_partner_performance_comissao,
    build_partner_share_by_count,
    build_portfolio_depth,
    build_producao_enriquecida,
    build_producer_performance,
    build_product_distribution,
    build_renewal_agenda,
    build_snapshot_grain,
    build_specialty_gaps,
    build_specialty_mix,
    build_time_series_growth,
    build_winback_candidates,
)
from src.audit import (
    audit_abc,
    audit_abc_comissao,
    audit_acionabilidade,
    audit_calculadora,
    audit_cohort,
    audit_completude,
    audit_demografia,
    audit_margem_produto,
    audit_margem_seg_produto,
    audit_margem_seguradora,
    audit_market_share,
    audit_marketing,
    audit_mix,
    audit_origem_cadastro,
    audit_origination,
    audit_partner_count,
    audit_portfolio_depth,
    audit_producer,
    audit_product_distribution,
    audit_renovacoes,
    audit_snapshot,
    audit_status_situacao,
    audit_winback,
)
from src.data_quality_advanced import (
    build_dq_summary,
    detect_commission_exceeds_premio,
    detect_exact_duplicates,
    detect_percentage_inconsistency,
    detect_percentage_outliers,
    detect_premio_outliers,
    detect_zero_negative_premio,
)
from src.excel_report import export_formatted_workbook
from src.functions import (
    build_cycle_grain,
    clean_cpf_cnpj,
    flag_last_cycle,
    generate_client_insights,
    identify_root_conflicts,
    prepare_demographics,
)
from src.guardrails import build_run_context
from src.marketing import (
    build_acquisition_targets,
    build_age_bands,
    build_base_status,
    build_birth_decade,
    build_client_type_distribution,
    build_marital_distribution,
    build_marketing_base,
    build_reachable_audience,
    build_sex_distribution,
    build_specialty_distribution,
)
from src.operacional import (
    add_contact_flags,
    build_active_with_cancellation,
    build_contact_lookup,
    build_contactability_by_producer,
    build_origem_cadastro,
    build_renewal_as_new,
    build_situacao_ativa_vencida,
    build_status_vs_situacao,
)
from src.parameters import PRODUCT_TYPE_MAP, normalize_producer
from src.persistence import append_dq_history, export_parquet_tables
from src.quality import run_full_audit
from src.report_html import build_all_html_reports
from src.utils import DATA_RAW, OUTPUTS, get_comissao_col, load_excel

warnings.filterwarnings("ignore")

# ── Saídas segmentadas por público (marco: Comercial × Operacional/Qualidade) ──
# O gerente pediu separação clara entre os artefatos comerciais (vendas/CRM) e os
# operacionais/qualidade (backoffice/processo). Cada público tem sua própria árvore:
# workbook + visuais HTML + parquet + workbooks de auditoria.
COMERCIAL_DIR = OUTPUTS / "comercial"
OPERACIONAL_DIR = OUTPUTS / "operacional"
MARKETING_DIR = OUTPUTS / "marketing"

# Track COMERCIAL
COM_REPORT_FILE = COMERCIAL_DIR / "Comercial_RaioX.xlsx"
COM_VISUALS_DIR = COMERCIAL_DIR / "visuals"
COM_PARQUET_DIR = COMERCIAL_DIR / "parquet"
COM_AUDIT_DIR = COMERCIAL_DIR / "auditoria"

# Track OPERACIONAL / QUALIDADE
OPER_REPORT_FILE = OPERACIONAL_DIR / "Operacional_Qualidade_RaioX.xlsx"
DQ_FILE = OPERACIONAL_DIR / "DQ_Raio_X_Cooperados.xlsx"
CONFLICT_LOG_FILE = OPERACIONAL_DIR / "Log_Apolices_Conflito_RaioX.xlsx"
OPER_VISUALS_DIR = OPERACIONAL_DIR / "visuals"
OPER_PARQUET_DIR = OPERACIONAL_DIR / "parquet"
OPER_AUDIT_DIR = OPERACIONAL_DIR / "auditoria"
DQ_HIST_FILE = OPERACIONAL_DIR / "dq_history.parquet"

# Track MARKETING (base/mercado: cliente × prospect + demografia)
MKT_REPORT_FILE = MARKETING_DIR / "Marketing_RaioX.xlsx"
MKT_VISUALS_DIR = MARKETING_DIR / "visuals"
MKT_PARQUET_DIR = MARKETING_DIR / "parquet"
MKT_AUDIT_DIR = MARKETING_DIR / "auditoria"

INPUT_HASH_FILE = OUTPUTS / ".last_input_hash"

# Garante a árvore de saída dos dois públicos (export functions também criam, mas o
# log de conflito grava direto com to_excel e precisa do diretório já existente).
for _d in (
    COM_VISUALS_DIR,
    COM_PARQUET_DIR,
    COM_AUDIT_DIR,
    OPER_VISUALS_DIR,
    OPER_PARQUET_DIR,
    OPER_AUDIT_DIR,
    MKT_VISUALS_DIR,
    MKT_PARQUET_DIR,
    MKT_AUDIT_DIR,
):
    _d.mkdir(parents=True, exist_ok=True)

# Janela de avaliação para as somas janeladas (origem por INÍCIO DE VIGÊNCIA).
# O 1º corte da produção foi em 2024; 2025+ isola o período sob avaliação.
WINDOW_EVAL_START = "2025-01-01"

# Nomes fixos dos Excel de entrada (o diretório é parametrizável via --input-dir)
PROD_FILENAME = "RptAnaliseProducao.xlsx"
CAD_FILENAME = "RptClienteLista.xlsx"


def _input_files(input_dir):
    """Caminhos dos 2 Excel de entrada dentro do diretório informado."""
    return [Path(input_dir) / PROD_FILENAME, Path(input_dir) / CAD_FILENAME]


def _input_hash(input_dir):
    """Hash SHA-256 do conteúdo dos Excel de entrada (guard de idempotência)."""
    h = hashlib.sha256()
    for f in _input_files(input_dir):
        h.update(f.read_bytes())
    return h.hexdigest()


# ── Etapas do pipeline ────────────────────────────────────────────────────────
def _stamp_origin(df, prefix, filename):
    """
    Carimba a âncora de rastreabilidade em cada linha: arquivo e linha de origem
    no Excel bruto. Feito na LEITURA (antes de qualquer filtro/dedup) para que o
    ID acompanhe o registro até o fim do pipeline. LINHA_ORIGEM começa em 2
    (linha 1 do Excel é o cabeçalho).
    """
    df = df.copy()
    df["ARQUIVO_ORIGEM"] = filename
    df["LINHA_ORIGEM"] = range(2, len(df) + 2)
    df["ID_LINHA"] = [f"{prefix}-{n:06d}" for n in df["LINHA_ORIGEM"]]
    return df


def load_data(input_dir):
    """Lê as bases brutas de produção e cadastro (já com âncora de origem)."""
    print(f"Carregando bases de {input_dir} ...")
    prod_path, cad_path = _input_files(input_dir)
    df_prod = load_excel(prod_path)
    df_cad = load_excel(cad_path)
    df_prod = _stamp_origin(df_prod, "PROD", PROD_FILENAME)
    df_cad = _stamp_origin(df_cad, "CAD", CAD_FILENAME)
    print(f"Produção: {len(df_prod):,} linhas. | Cadastro: {len(df_cad):,} linhas.")
    return df_prod, df_cad


def prepare_cadastro(df_cad):
    """Limpa documento, calcula demografia (idade/geografia/sexo) e deduplica por CPF."""
    cpf_cols = [c for c in df_cad.columns if "CPF" in c.upper() or "CNPJ" in c.upper()]
    if cpf_cols:
        df_cad["CPF_LIMPO"] = df_cad[cpf_cols[0]].apply(clean_cpf_cnpj)

    print("Higienizando dados de Perfil (Idade, Geografia, Gêneros)...")
    df_cad = prepare_demographics(df_cad)
    df_cad = df_cad.drop_duplicates(subset=["CPF_LIMPO"])
    print(f"Cadastro unificado: {len(df_cad):,} cooperados.")
    return df_cad


def prepare_producao(df_prod):
    """Limpa documento e sinaliza conflitos de raiz de apólice (exporta log se houver)."""
    df_prod["CPF_LIMPO"] = df_prod["CPF/CNPJ"].apply(clean_cpf_cnpj)

    # Unifica produtores com cadastro duplicado (mesmo produtor, nomes diferentes)
    if "PRODUTOR" in df_prod.columns:
        df_prod["PRODUTOR"] = df_prod["PRODUTOR"].apply(normalize_producer)

    print("Buscando anomalias contratuais de Root...")
    df_prod, log_conflitos = identify_root_conflicts(df_prod)

    # Marca as linhas do último ciclo de cada apólice (valor vigente vs. histórico).
    # Feito aqui para que a flag acompanhe df_prod até a auditoria e o Parquet.
    df_prod = flag_last_cycle(df_prod)
    if len(log_conflitos) > 0:
        try:
            log_conflitos.to_excel(CONFLICT_LOG_FILE, index=False, engine="openpyxl")
            print(
                f"-> {len(log_conflitos):,} linhas em conflito exportadas: {CONFLICT_LOG_FILE.name}"
            )
        except PermissionError:
            print(
                f"  [BLOQUEADO] {CONFLICT_LOG_FILE.name} aberto — log de conflitos não regravado."
            )
    else:
        print("Zero anomalias de raiz na geração atual.")
    return df_prod


def build_cruzamento(df_cad, df_client_insights):
    """Left join Cadastro -> Insights (base central do CRM), tratando prospects."""
    df_cruzamento = pd.merge(df_cad, df_client_insights, on="CPF_LIMPO", how="left")
    df_cruzamento["STATUS_GLOBAL"] = df_cruzamento["STATUS_GLOBAL"].fillna(
        "INATIVO (PROSPECT)"
    )
    df_cruzamento["RATING_ESTRELAS"] = df_cruzamento["RATING_ESTRELAS"].fillna(0)
    df_cruzamento["LISTA_PRODUTOS_ATIVOS"] = df_cruzamento[
        "LISTA_PRODUTOS_ATIVOS"
    ].fillna("Nenhum")
    return df_cruzamento


def coerce_dates(df, columns=None):
    """Converte colunas de data para `date` puro (Excel mais limpo)."""
    if columns is None:
        columns = [
            c for c in df.columns if "DATA" in c.upper() or "NASCIMENTO" in c.upper()
        ]
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
    return df


def build_audit_base(df_prod, df_prod_status, df_client_insights, df_cad):
    """
    Monta a base transacional auditável (aba 8) e o log isolado de qualidade (aba 9).
    Cada linha de produção recebe o status do produto, o rating do cliente e o
    DIAGNOSTICO_QUALIDADE consolidado pelo motor de auditoria.
    """
    df_prod_auditavel = df_prod.copy()

    base_status = df_prod_status[
        ["CPF_LIMPO", "SEGURADORA", "PRODUTO", "STATUS_PRODUTO"]
    ].rename(
        columns={
            "SEGURADORA": "SEGURADORA (ABREVIADO)",
            "PRODUTO": "NOME ABREVIADO DO PRODUTO",
        }
    )
    df_prod_auditavel = pd.merge(
        df_prod_auditavel,
        base_status,
        on=["CPF_LIMPO", "SEGURADORA (ABREVIADO)", "NOME ABREVIADO DO PRODUTO"],
        how="left",
    )
    df_prod_auditavel = pd.merge(
        df_prod_auditavel,
        df_client_insights[["CPF_LIMPO", "STATUS_GLOBAL", "RATING_ESTRELAS"]],
        on="CPF_LIMPO",
        how="left",
    )

    # Motor de auditoria: agrega DIAGNOSTICO_QUALIDADE e isola o log do backoffice
    df_prod_auditavel, df_log_master = run_full_audit(
        df_cad, df_prod_auditavel, PRODUCT_TYPE_MAP
    )
    return df_prod_auditavel, df_log_master


def build_dq_report(df_prod, df_prod_auditavel, df_log_master):
    """
    Orquestra todas as detecções de qualidade avançada e exporta o arquivo DQ
    separado do relatório de negócio. Nenhuma correção é feita — só sinalização.
    """
    comissao_col = get_comissao_col(df_prod)

    df_zero_premio = detect_zero_negative_premio(df_prod)
    df_com_maior = detect_commission_exceeds_premio(df_prod, comissao_col)
    df_pct_incons = detect_percentage_inconsistency(df_prod, comissao_col)
    df_out_premio, df_out_premio_pequenos = detect_premio_outliers(df_prod)
    df_out_pct, df_out_pct_pequenos = detect_percentage_outliers(df_prod)
    df_duplicatas = detect_exact_duplicates(df_prod)

    total = len(df_prod)
    dict_resultados = {
        "Prêmio Zerado/Negativo": df_zero_premio,
        "Comissão > Prêmio": df_com_maior,
        "Inconsistência Percentual": df_pct_incons,
        "Outlier Prêmio (grupo ≥5)": df_out_premio,
        "Outlier % Comissão (grupo ≥5)": df_out_pct,
        "Duplicatas Exatas": df_duplicatas,
    }
    df_resumo = build_dq_summary(dict_resultados, total)

    dq_exports = [
        ("0_RESUMO_DQ", df_resumo),
        ("1_PREMIO_ZERADO_NEGATIVO", df_zero_premio),
        ("2_COMISSAO_MAIOR_PREMIO", df_com_maior),
        ("3_INCONSISTENCIA_PERCENTUAL", df_pct_incons),
        ("4_OUTLIER_PREMIO", df_out_premio),
        ("5_OUTLIER_PCT_COMISSAO", df_out_pct),
        (
            "6_GRUPOS_AMOSTRA_INSUF",
            pd.concat([df_out_premio_pequenos, df_out_pct_pequenos], ignore_index=True),
        ),
        ("7_DUPLICATAS_EXATAS", df_duplicatas),
        ("8_LOG_QUALIDADE_GERAL", df_log_master),  # migrado da aba 9
        ("9_AUDITORIA_BRUTA_LASTRO", df_prod_auditavel),  # migrado da aba 8
    ]

    export_formatted_workbook(dq_exports, DQ_FILE)
    print(f"Relatório de Qualidade DQ gerado: {DQ_FILE.name}")
    return DQ_FILE, df_resumo


def run_pipeline(force=False, input_dir=DATA_RAW):
    """Orquestra o fluxo completo e gera o relatório multi-abas.

    input_dir: diretório com os 2 Excel de entrada (padrão: data/raw).
    Guard de idempotência: se os Excel de entrada forem byte-idênticos à última
    execução bem-sucedida, o pipeline é pulado (use force=True para reprocessar).
    """
    faltando = [str(f) for f in _input_files(input_dir) if not f.exists()]
    if faltando:
        print("[ERRO] Arquivo(s) de entrada não encontrado(s):")
        for f in faltando:
            print(f"  - {f}")
        print(f"Esperado em {input_dir}: {PROD_FILENAME} e {CAD_FILENAME}.")
        return None

    current_hash = _input_hash(input_dir)
    if (
        not force
        and INPUT_HASH_FILE.exists()
        and INPUT_HASH_FILE.read_text().strip() == current_hash
    ):
        print(
            "Input inalterado desde a última execução — nada a reprocessar "
            "(use --force para forçar)."
        )
        return None

    df_prod, df_cad = load_data(input_dir)

    # Cadastro bruto (antes do preenchimento de nulos) p/ o diagnóstico de completude
    df_cad_raw = df_cad.copy()

    df_cad = prepare_cadastro(df_cad)
    df_prod = prepare_producao(df_prod)

    # Guardrails: alerta sobre janela temporal e cobertura cadastro × produção
    df_run_context, ctx_warnings = build_run_context(df_prod, df_cad)
    for w in ctx_warnings:
        print(f"  [GUARDRAIL] {w}")

    print("Processando hierarquia de Rating e Valores...")
    df_client_insights, df_prod_status = generate_client_insights(df_prod)

    df_cruzamento = build_cruzamento(df_cad, df_client_insights)

    print("Cruzando visões para Relatórios Analíticos...")
    df_demographics = build_demographics(df_cruzamento)
    df_abc = build_abc_curve(df_prod_status)
    df_cross = build_cross_sell_matrix(df_prod_status)
    df_ts_growth = build_time_series_growth(df_prod_status)
    df_partner = build_partner_performance(df_prod_status)
    df_specialty = build_specialty_mix(df_cruzamento, df_prod_status)
    df_renewal = build_renewal_agenda(df_prod_status, df_client_insights)
    df_winback = build_winback_candidates(df_prod_status, df_client_insights)

    # Acionabilidade — corte (a): flags de contato (telefone/e-mail/consentimento)
    # nas listas de ação, tornando-as executáveis. Enriquecidas antes dos consumidores.
    contact_lookup = build_contact_lookup(df_cad)
    df_renewal = add_contact_flags(df_renewal, contact_lookup)
    df_winback = add_contact_flags(df_winback, contact_lookup)

    # Snapshot mensal a partir do grão de CICLO (cada renovação nos seus meses, com
    # o seu valor) — evita inflar o prêmio repetindo a soma histórica em todo mês.
    df_cycle = build_cycle_grain(df_prod)
    df_snapshot = build_monthly_active_snapshot(df_cycle)

    # Somas janeladas (originação por INÍCIO DE VIGÊNCIA >= janela de avaliação)
    df_abc_win, df_share_win = build_origination_sums(df_prod, WINDOW_EVAL_START)

    # Visões na ótica da comissão (receita real da corretora)
    df_abc_com = build_abc_curve_comissao(df_prod_status)
    df_partner_com = build_partner_performance_comissao(df_prod_status)
    df_margem_prod = build_commission_margin_produto(df_prod_status)
    df_margem_seg_prod = build_commission_margin_seguradora_produto(df_prod_status)

    # Análises não-monetárias de apoio COMERCIAL (contagens, especialidade)
    df_prod_dist = build_product_distribution(df_prod_status)
    df_partner_count = build_partner_share_by_count(df_prod_status)
    df_portfolio = build_portfolio_depth(df_prod_status, df_client_insights)
    df_spec_gaps = build_specialty_gaps(df_specialty)
    df_producer = build_producer_performance(df_prod)

    # Track OPERACIONAL / QUALIDADE (qualidade de cadastro e processo)
    df_completeness = build_cadastro_completeness(df_cad_raw, df_prod)
    df_cancel = build_cancellation_rate(df_prod)
    df_origem = build_origem_cadastro(df_prod)
    df_status_sit = build_status_vs_situacao(df_prod, df_prod_status)
    df_ativa_cancel = build_active_with_cancellation(df_prod)
    df_renov_novo = build_renewal_as_new(df_prod)
    df_ativa_vencida = build_situacao_ativa_vencida(df_prod)
    df_contact_prod = build_contactability_by_producer(df_prod, df_cad)

    # Track MARKETING (base inteira: cliente × prospect + demografia + personas)
    # contact_lookup (calculado acima) anexa e-mail/consentimento → audiência de campanha.
    df_mkt_base = build_marketing_base(df_cruzamento, contact_lookup)
    df_base_status = build_base_status(df_mkt_base)
    df_spec_dist = build_specialty_distribution(df_mkt_base)
    df_birth_decade = build_birth_decade(df_mkt_base)
    df_age_bands = build_age_bands(df_mkt_base)
    # Personas (item 3) + alvos de aquisição (item 1) + audiência acionável (item 2)
    df_sex_dist = build_sex_distribution(df_mkt_base)
    df_marital_dist = build_marital_distribution(df_mkt_base)
    df_client_type_dist = build_client_type_distribution(df_mkt_base)
    df_acq_targets = build_acquisition_targets(df_mkt_base, df_specialty)
    df_audience = build_reachable_audience(df_mkt_base)

    # Grãos granulares (lastro de auditoria + tabelas para Power BI)
    df_snapshot_grain = build_snapshot_grain(df_cycle)
    df_prod_enriquecida = build_producao_enriquecida(df_prod_status, df_cruzamento)

    # Tratamento de datas para exportação
    df_cruzamento = coerce_dates(df_cruzamento)
    df_prod_status = coerce_dates(
        df_prod_status,
        [
            "PRIMEIRO_INICIO",
            "ULTIMO_TERMINO",
            "INICIO_ULTIMO_CICLO",
            "MAX_INICIO_VIGENCIA",
        ],
    )
    df_export_clientes = df_cruzamento.sort_values(
        by=["RATING_ESTRELAS", "STATUS_GLOBAL"], ascending=[False, True]
    )

    # Base de auditoria (aba 8) + log isolado (aba 9)
    print("Auditando qualidade linha a linha...")
    df_prod_auditavel, df_log_master = build_audit_base(
        df_prod, df_prod_status, df_client_insights, df_cad
    )
    n_problemas = (df_prod_auditavel["DIAGNOSTICO_QUALIDADE"] != "OK").sum()
    print(f"-> {n_problemas:,} linhas com apontamento de qualidade.")

    # Relatório de qualidade DQ (arquivo separado; abas de auditoria migradas para cá)
    print("Gerando relatório de qualidade DQ...")
    _, df_dq_resumo = build_dq_report(df_prod, df_prod_auditavel, df_log_master)

    # ── Workbook COMERCIAL (vendas/CRM) ──
    print(f"Gerando {COM_REPORT_FILE.name} ...")
    com_exports = [
        ("1_Visao_Clientes_CRM", df_export_clientes),
        ("2_Demografia_E_Taxas", df_demographics),
        ("3_CurvaABC_Rentabilidade", df_abc),
        ("4_Matriz_CrossSell", df_cross),
        ("5_Cohort_Sazonalidade", df_ts_growth),
        ("6_Market_Share_Fornecedor", df_partner),
        ("7_Calculadora_Produtos", df_prod_status),
        ("8_Mix_Por_Especialidade", df_specialty),
        ("9_Agenda_Renovacoes_90d", df_renewal),
        ("10_Win_Back_Reativacao", df_winback),
        ("11_Snapshot_Mensal_Ativo", df_snapshot),
        ("12_CurvaABC_2025plus", df_abc_win),
        ("13_Market_Share_2025plus", df_share_win),
        ("14_CurvaABC_Comissao", df_abc_com),
        ("15_Margem_Comissao_Seguradora", df_partner_com),
        ("16_Margem_Comissao_Produto", df_margem_prod),
        ("17_Margem_Comissao_Seg_Produto", df_margem_seg_prod),
        # Apoio comercial não-monetário (contagens)
        ("18_Performance_Produtor", df_producer),
        ("19_Mix_Produtos", df_prod_dist),
        ("20_Market_Share_Contagem", df_partner_count),
        ("21_Profundidade_Carteira", df_portfolio),
        ("22_CrossSell_Gaps_Especialidade", df_spec_gaps),
    ]
    main_ok = export_formatted_workbook(com_exports, COM_REPORT_FILE)
    if main_ok:
        print("Relatório Comercial gerado com sucesso!")

    # ── Workbook OPERACIONAL / QUALIDADE (backoffice/processo) ──
    print(f"Gerando {OPER_REPORT_FILE.name} ...")
    oper_exports = [
        ("1_Completude_Cadastro", df_completeness),
        ("2_Origem_Cadastro_Migrado", df_origem),
        ("3_Status_vs_Situacao", df_status_sit),
        ("4_Apolices_Ativas_c_Cancelamento", df_ativa_cancel),
        ("5_Renovacao_Como_Novo", df_renov_novo),
        ("6_Situacao_Ativa_Vencida", df_ativa_vencida),
        ("7_Acionabilidade_Produtor", df_contact_prod),
        ("8_Taxa_Cancelamento", df_cancel),
        ("9_Run_Context_Guardrails", df_run_context),
    ]
    qual_ok = export_formatted_workbook(oper_exports, OPER_REPORT_FILE)

    # ── Workbook MARKETING (base/mercado: cliente × prospect + demografia) ──
    print(f"Gerando {MKT_REPORT_FILE.name} ...")
    mkt_exports = [
        ("1_Status_Base", df_base_status),
        ("2_Distribuicao_Especialidade", df_spec_dist),
        ("3_Decada_Nascimento", df_birth_decade),
        ("4_Faixa_Etaria", df_age_bands),
        ("5_Alvos_Aquisicao", df_acq_targets),
        ("6_Audiencia_Campanha", df_audience),
        ("7_Personas_Sexo", df_sex_dist),
        ("8_Personas_Estado_Civil", df_marital_dist),
        ("9_Personas_Tipo", df_client_type_dist),
        ("10_Base_Cooperados", df_mkt_base),
    ]
    mkt_ok = export_formatted_workbook(mkt_exports, MKT_REPORT_FILE)

    # Visuais HTML com storytelling, segmentados por público (com | oper | mkt)
    print("\nGerando visuais HTML...")
    build_all_html_reports(
        df_abc=df_abc,
        df_partner=df_partner,
        df_specialty=df_specialty,
        df_prod_status=df_prod_status,
        df_renewal=df_renewal,
        df_winback=df_winback,
        df_snapshot=df_snapshot,
        com_dir=COM_VISUALS_DIR,
        oper_dir=OPER_VISUALS_DIR,
        df_abc_comissao=df_abc_com,
        df_partner_comissao=df_partner_com,
        df_completeness=df_completeness,
        df_specialty_gaps=df_spec_gaps,
        df_margem_seg_produto=df_margem_seg_prod,
        df_origem_cadastro=df_origem,
        df_status_situacao=df_status_sit,
        df_contact_producer=df_contact_prod,
        df_producer_perf=df_producer,
        df_dq_resumo=df_dq_resumo,
        mkt_dir=MKT_VISUALS_DIR,
        df_base_status=df_base_status,
        df_specialty_dist=df_spec_dist,
        df_birth_decade=df_birth_decade,
        df_age_bands=df_age_bands,
        df_marketing_base=df_mkt_base,
        df_acquisition_targets=df_acq_targets,
        df_reachable_audience=df_audience,
        df_sex_dist=df_sex_dist,
        df_marital_dist=df_marital_dist,
        df_client_type_dist=df_client_type_dist,
        root_dir=OUTPUTS,
    )

    # Persistência Parquet — segmentada por público (estado atual) + histórico DQ
    print("\nExportando tabelas para Parquet...")
    com_parquet = {
        "clientes_crm": df_export_clientes,
        "producao_status": df_prod_status,
        "curva_abc": df_abc,
        "demografico": df_demographics,
        "cross_sell": df_cross,
        "cohort_sazonalidade": df_ts_growth,
        "market_share": df_partner,
        "mix_especialidade": df_specialty,
        "agenda_renovacoes": df_renewal,
        "winback": df_winback,
        "snapshot_mensal": df_snapshot,
        "curva_abc_2025plus": df_abc_win,
        "market_share_2025plus": df_share_win,
        "curva_abc_comissao": df_abc_com,
        "margem_comissao_seguradora": df_partner_com,
        "margem_comissao_produto": df_margem_prod,
        "margem_comissao_seg_produto": df_margem_seg_prod,
        "performance_produtor": df_producer,
        "mix_produtos": df_prod_dist,
        "market_share_contagem": df_partner_count,
        "profundidade_carteira": df_portfolio,
        "crosssell_gaps": df_spec_gaps,
        # Grão granular para reconstruir as análises comerciais no Power BI
        "producao_grain": df_prod,  # linha bruta atômica (com ID_LINHA)
        "producao_enriquecida": df_prod_enriquecida,  # produto × cooperado × perfil
        "snapshot_grain": df_snapshot_grain,  # ciclo × mês explodido
    }
    oper_parquet = {
        "completude_cadastro": df_completeness,
        "taxa_cancelamento": df_cancel,
        "origem_cadastro": df_origem,
        "status_vs_situacao": df_status_sit,
        "apolices_ativas_cancelamento": df_ativa_cancel,
        "renovacao_como_novo": df_renov_novo,
        "situacao_ativa_vencida": df_ativa_vencida,
        "acionabilidade_produtor": df_contact_prod,
        "run_context": df_run_context,
    }
    mkt_parquet = {
        "base_cooperados": df_mkt_base,
        "status_base": df_base_status,
        "distribuicao_especialidade": df_spec_dist,
        "decada_nascimento": df_birth_decade,
        "faixa_etaria": df_age_bands,
        "alvos_aquisicao": df_acq_targets,
        "audiencia_campanha": df_audience,
        "personas_sexo": df_sex_dist,
        "personas_estado_civil": df_marital_dist,
        "personas_tipo": df_client_type_dist,
    }
    export_parquet_tables(com_parquet, COM_PARQUET_DIR)
    export_parquet_tables(oper_parquet, OPER_PARQUET_DIR)
    export_parquet_tables(mkt_parquet, MKT_PARQUET_DIR)
    print(
        f"  {len(com_parquet)} comerciais + {len(oper_parquet)} operacionais + "
        f"{len(mkt_parquet)} marketing exportadas para outputs/*/parquet/"
    )

    append_dq_history(df_dq_resumo, DQ_HIST_FILE)

    # Workbooks de auditoria (Agregado|Lastro) — análises comerciais → track comercial
    print("\nGerando workbooks de auditoria...")
    audit_results = [
        audit_abc(COM_AUDIT_DIR, df_abc, df_prod),
        audit_market_share(COM_AUDIT_DIR, df_partner, df_prod),
        audit_cohort(COM_AUDIT_DIR, df_ts_growth, df_prod, df_prod_status),
        audit_demografia(COM_AUDIT_DIR, df_demographics, df_cruzamento),
        audit_calculadora(COM_AUDIT_DIR, df_prod_status, df_prod),
        audit_mix(COM_AUDIT_DIR, df_specialty, df_prod_status, df_cruzamento, df_prod),
        audit_renovacoes(COM_AUDIT_DIR, df_renewal, df_prod),
        audit_winback(COM_AUDIT_DIR, df_winback, df_prod),
        audit_snapshot(COM_AUDIT_DIR, df_snapshot, df_snapshot_grain),
    ]
    audit_results += audit_origination(
        COM_AUDIT_DIR, df_abc_win, df_share_win, df_prod, WINDOW_EVAL_START
    )
    audit_results += [
        audit_abc_comissao(COM_AUDIT_DIR, df_abc_com, df_prod),
        audit_margem_seguradora(COM_AUDIT_DIR, df_partner_com, df_prod),
        audit_margem_produto(COM_AUDIT_DIR, df_margem_prod, df_prod),
        audit_margem_seg_produto(COM_AUDIT_DIR, df_margem_seg_prod, df_prod),
        audit_producer(COM_AUDIT_DIR, df_producer, df_prod),
        audit_product_distribution(COM_AUDIT_DIR, df_prod_dist, df_prod),
        audit_partner_count(COM_AUDIT_DIR, df_partner_count, df_prod),
        audit_portfolio_depth(COM_AUDIT_DIR, df_portfolio, df_prod),
    ]
    # Auditoria do track operacional/qualidade → outputs/operacional/auditoria/
    audit_results += [
        audit_completude(OPER_AUDIT_DIR, df_completeness, df_cad_raw),
        audit_origem_cadastro(OPER_AUDIT_DIR, df_origem, df_prod),
        audit_status_situacao(OPER_AUDIT_DIR, df_status_sit, df_prod, df_prod_status),
        audit_acionabilidade(OPER_AUDIT_DIR, df_contact_prod, df_prod, df_cad),
    ]
    # Auditoria do track marketing → outputs/marketing/auditoria/ (lastro = base por cooperado)
    audit_results += [
        audit_marketing(
            MKT_AUDIT_DIR, "Status_Base.xlsx", df_base_status, df_mkt_base, ["STATUS"]
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Distribuicao_Especialidade.xlsx",
            df_spec_dist,
            df_mkt_base,
            ["ESPECIALIDADE"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Decada_Nascimento.xlsx",
            df_birth_decade,
            df_mkt_base,
            ["DECADA_NASCIMENTO"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Faixa_Etaria.xlsx",
            df_age_bands,
            df_mkt_base,
            ["FAIXA_ETARIA_3"],
        ),
        # Alvos de aquisição e audiência contam só PROSPECTS → lastro filtrado
        audit_marketing(
            MKT_AUDIT_DIR,
            "Alvos_Aquisicao.xlsx",
            df_acq_targets,
            df_mkt_base,
            ["ESPECIALIDADE"],
            agg_col="QTD_PROSPECTS",
            base_filter=lambda b: b["EH_PROSPECT"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Audiencia_Campanha.xlsx",
            df_audience,
            df_mkt_base,
            ["ESPECIALIDADE"],
            agg_col="QTD_PROSPECTS",
            base_filter=lambda b: b["EH_PROSPECT"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Personas_Sexo.xlsx",
            df_sex_dist,
            df_mkt_base,
            ["SEXO_LABEL"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Personas_Estado_Civil.xlsx",
            df_marital_dist,
            df_mkt_base,
            ["ESTADO_CIVIL"],
        ),
        audit_marketing(
            MKT_AUDIT_DIR,
            "Personas_Tipo.xlsx",
            df_client_type_dist,
            df_mkt_base,
            ["TIPO_CLIENTE"],
        ),
    ]

    # Só marca como concluído se nenhum Excel essencial foi pulado (arquivo aberto).
    # Assim, com um arquivo travado, a próxima execução regenera sem precisar de --force.
    todos_ok = (
        main_ok is not None
        and qual_ok is not None
        and mkt_ok is not None
        and all(r is not None for r in audit_results)
    )
    if todos_ok:
        INPUT_HASH_FILE.write_text(current_hash)
    else:
        print(
            "\n[ATENÇÃO] Alguns arquivos estavam abertos e foram pulados — execução "
            "NÃO marcada como concluída. Feche-os e rode novamente (sem --force)."
        )
    return COM_REPORT_FILE


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Raio X Cooperados.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocessa mesmo se os Excel de entrada não mudaram.",
    )
    parser.add_argument(
        "--input-dir",
        default=None,
        help="Diretório com os 2 Excel de entrada (padrão: data/raw). "
        "Ex.: --input-dir data/exemplo para rodar com os dados de exemplo.",
    )
    args = parser.parse_args()
    input_dir = Path(args.input_dir) if args.input_dir else DATA_RAW
    run_pipeline(force=args.force, input_dir=input_dir)
