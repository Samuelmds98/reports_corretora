import numpy as np
import pandas as pd

from src.utils import get_comissao_col


def audit_production_row(row, comissao_col, parameters_map):
    """
    Rastreia anomalias na geração da linha de produção individualmente.
    """
    errors = []

    # 1. Divergência Financeira de Comissionamento
    try:
        premio = pd.to_numeric(row.get("PRÊMIO LÍQ. DO SEGURO", 0), errors="coerce")
        comissao = pd.to_numeric(row.get(comissao_col, 0), errors="coerce")
        porcentagem = pd.to_numeric(row.get("PORCENTAGEM", 0), errors="coerce")

        if pd.notnull(premio) and pd.notnull(comissao) and pd.notnull(porcentagem):
            expected = premio * (porcentagem / 100.0)
            if abs(expected - comissao) > 0.03:
                errors.append(
                    f"Divergência Financeira: Esperado {expected:.2f}, Real {comissao:.2f}"
                )
    except:
        pass

    # 2. Inconsistência Temporal (Viagem no tempo)
    inicio = pd.to_datetime(row.get("INÍCIO DE VIGÊNCIA"), errors="coerce")
    fim = pd.to_datetime(row.get("TÉRMINO DE VIGÊNCIA"), errors="coerce")
    if pd.notnull(inicio) and pd.notnull(fim) and fim < inicio:
        errors.append("Vigência Invertida (Fim < Início)")

    # 3. Produto não classificado nas regras do Motor
    produto = str(row.get("NOME ABREVIADO DO PRODUTO", "")).strip()
    if produto not in parameters_map and produto != "nan" and produto != "":
        # Ignora string vazia, mas alerta se tiver produto fantasma
        errors.append(f"Produto '{produto}' não mapeado no DICIONARIO")

    return " | ".join(errors) if errors else "OK"


def audit_registration_row(row):
    """
    Rastreia anomalias a nível de paciente no cadastro base.
    """
    errors = []
    idade = row.get("IDADE")
    if pd.notnull(idade):
        if idade < 22:
            errors.append(f"Idade Implausível P/ Medico ({int(idade)} anos)")
        elif idade > 100:
            errors.append(f"Idade Implausível ({int(idade)} anos)")

    # Arquitetura básica do CPF
    cpf = str(row.get("CPF_LIMPO", ""))
    if len(cpf) != 11 and len(cpf) != 14:
        errors.append("CPF/CNPJ fora do padrão numérico (11 ou 14 dígitos)")

    return " | ".join(errors) if errors else "OK"


def run_full_audit(df_cad_limpo, df_prod_auditavel, parameters_map):
    """
    Orquestrador master para gerar as colunas na Aba 8 e devolver a Aba 9 Isolada.
    """
    # Identificar a coluna exata de comissão da base de produção
    comissao_col = get_comissao_col(df_prod_auditavel)

    # Aplicar rastreadores por dataframe
    df_prod_auditavel["AUDIT_PRODUCAO"] = df_prod_auditavel.apply(
        lambda r: audit_production_row(r, comissao_col, parameters_map), axis=1
    )

    df_cad_audit = df_cad_limpo.copy()
    df_cad_audit["AUDIT_CADASTRO"] = df_cad_audit.apply(audit_registration_row, axis=1)

    # Traz o log do cadastro para a base mestra
    df_prod_auditavel = pd.merge(
        df_prod_auditavel,
        df_cad_audit[["CPF_LIMPO", "AUDIT_CADASTRO"]],
        on="CPF_LIMPO",
        how="left",
    )

    # Identificação de fantasmas transacionais
    df_prod_auditavel["AUDIT_ORFAO"] = np.where(
        pd.isnull(df_prod_auditavel["AUDIT_CADASTRO"]),
        "CPF Produtivo inexistente na Tabela de Cadastro Principal",
        "OK",
    )

    # Concatenar as verificações numa única celula do excel para leitura humana fluida
    def consolidar_erros(row):
        erros = []
        if row.get("AUDIT_PRODUCAO") != "OK":
            erros.append(row["AUDIT_PRODUCAO"])
        if pd.notnull(row.get("AUDIT_CADASTRO")) and row.get("AUDIT_CADASTRO") != "OK":
            erros.append(row["AUDIT_CADASTRO"])
        if row.get("AUDIT_ORFAO") != "OK":
            erros.append(row["AUDIT_ORFAO"])

        return " | ".join(erros) if erros else "OK"

    df_prod_auditavel["DIAGNOSTICO_QUALIDADE"] = df_prod_auditavel.apply(
        consolidar_erros, axis=1
    )

    # Limpa as sujeiras técnicas de colunas da memoria
    df_prod_auditavel.drop(
        columns=["AUDIT_PRODUCAO", "AUDIT_CADASTRO", "AUDIT_ORFAO"],
        errors="ignore",
        inplace=True,
    )

    # Isolar a Aba 9 (Log Master) contendo APENAS a linha que necessita tratamento pelo Backoffice
    df_log_master = df_prod_auditavel[
        df_prod_auditavel["DIAGNOSTICO_QUALIDADE"] != "OK"
    ].copy()

    # Filtra colunas criticas para não carregar muito o relatório
    cols_selecionadas = [
        c
        for c in [
            "CPF_LIMPO",
            "SEGURADORA (ABREVIADO)",
            "NOME ABREVIADO DO PRODUTO",
            "APÓLICE",
            "TIPO DOCUMENTO",
            "TIPO DE NEGÓCIO",
            "PRÊMIO LÍQ. DO SEGURO",
            "PORCENTAGEM",
            comissao_col,
            "DIAGNOSTICO_QUALIDADE",
        ]
        if c in df_log_master.columns
    ]

    if "DIAGNOSTICO_QUALIDADE" not in cols_selecionadas:
        cols_selecionadas.append("DIAGNOSTICO_QUALIDADE")

    df_log_master = df_log_master[cols_selecionadas]
    return df_prod_auditavel, df_log_master
