"""
gerar_dados_exemplo.py

Gera uma cópia ANONIMIZADA e RANDOMIZADA dos dois Excel de origem, com a MESMA
estrutura de colunas, para uso em apresentação/TCC (sem expor dados reais).

- Dados qualitativos (nomes, CPFs, e-mails, telefones, endereços) são fictícios.
- Dados quantitativos (prêmio, comissão, %, datas, parcelas) são aleatórios.
- O vocabulário estrutural que o pipeline precisa (produtos do PRODUCT_TYPE_MAP,
  tipos de negócio/documento) é preservado, para o motor rodar igual.
- **Furos de qualidade são injetados de propósito** (prêmio zerado, comissão >
  prêmio, inconsistência %, duplicatas, CPF órfão, produto não mapeado, idade
  implausível, vigência invertida) para reproduzir o cenário real e alimentar o DQ.

Reprodutível por seed. Saída em `data/exemplo/` com os mesmos nomes de arquivo.
Uso:  python scripts/gerar_dados_exemplo.py
"""

import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.parameters import PRODUCT_TYPE_MAP

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

OUT_DIR = ROOT / "data" / "exemplo"
HOJE = pd.Timestamp("2026-06-16")

N_COOPERADOS = 700
N_ORFAOS = 12  # CPFs que aparecem na produção mas não no cadastro

# ── Vocabulários sintéticos (genéricos, não identificáveis) ───────────────────
PRODUTOS = list(PRODUCT_TYPE_MAP.keys())
PRODUTO_NAO_MAPEADO = "PRODUTO TESTE NAO MAPEADO"
SEGURADORAS = [
    f"Seguradora {l}" for l in "Alfa Beta Gama Delta Épsilon Zeta Eta Teta".split()
]
SEG_ABREV = {s: s.split()[1][:4].upper() for s in SEGURADORAS}
RAMOS = ["VIDA", "AUTO", "SAÚDE", "PATRIMONIAL", "PREVIDÊNCIA", "RC", "VIAGEM"]
ESPECIALIDADES = [
    "Pediatria",
    "Anestesiologia",
    "Ginecologia e Obstetrícia",
    "Oftalmologia",
    "Cirurgia Geral",
    "Ortopedia e Traumatologia",
    "Cardiologia",
    "Clínica Médica",
    "Otorrinolaringologia",
    "Radiologia",
    "Dermatologia",
    "Urologia",
    "Psiquiatria",
    "Neurologia",
    "Endocrinologia",
]
CIDADES = [
    "Fortaleza",
    "Caucaia",
    "Maracanaú",
    "Sobral",
    "Juazeiro do Norte",
    "Eusébio",
]
ESTADOS_CIVIS = ["Solteiro", "Casado", "Divorciado", "Viúvo", "União Estável"]
SEXOS = ["M", "F"]
# Variedade p/ a base de exemplo refletir múltiplos rótulos (evita campos "constantes"
# que apareceriam como cinza/"Inútil" na Completude e gráficos de 1 só barra).
ESTADOS = [
    "CE",
    "CE",
    "CE",
    "PE",
    "RN",
    "PB",
    "BA",
]  # majoritariamente CE (coop regional)
PROFISSOES = [
    "Médico",
    "Médico",
    "Cirurgião",
    "Anestesista",
    "Clínico Geral",
    "Pediatra",
]
TIPOS_PESSOA = ["Pessoa Física"] * 6 + ["Pessoa Jurídica"]  # ~15% PJ (clínicas)
PRODUTORES = [
    "Ana Vendas",
    "Bruno Corretor",
    "Carla Seguros",
    "Diego Comercial",
    "Equipe Digital",
]
NOMES = [
    "Ana",
    "Bruno",
    "Carla",
    "Daniel",
    "Eduardo",
    "Fernanda",
    "Gabriel",
    "Helena",
    "Igor",
    "Júlia",
    "Lucas",
    "Mariana",
    "Nelson",
    "Olívia",
    "Paulo",
    "Rafaela",
    "Sérgio",
    "Tatiana",
    "Vitor",
    "Yara",
]
SOBRENOMES = [
    "Silva",
    "Souza",
    "Costa",
    "Oliveira",
    "Lima",
    "Pereira",
    "Almeida",
    "Ferreira",
    "Rodrigues",
    "Gomes",
    "Martins",
    "Araújo",
    "Barbosa",
]


def cpf_aleatorio():
    """CPF fictício de 11 dígitos (sem validação de dígito verificador)."""
    return "".join(str(random.randint(0, 9)) for _ in range(11))


def nome_aleatorio():
    return f"{random.choice(NOMES)} {random.choice(SOBRENOMES)}"


def data_aleatoria(ini, fim):
    """Timestamp aleatório entre duas datas."""
    delta = (fim - ini).days
    return ini + pd.Timedelta(days=random.randint(0, max(delta, 1)))


# ── Cadastro ──────────────────────────────────────────────────────────────────
def gerar_cadastro():
    cpfs = [cpf_aleatorio() for _ in range(N_COOPERADOS)]
    linhas = []
    for i, cpf in enumerate(cpfs):
        nasc = data_aleatoria(pd.Timestamp("1955-01-01"), pd.Timestamp("1998-12-31"))
        # Furo: idade implausível em alguns registros
        if i < 3:
            nasc = pd.Timestamp("2010-06-01")  # < 22 anos
        elif i < 6:
            nasc = pd.Timestamp("1915-01-01")  # > 100 anos

        nome = nome_aleatorio()
        linhas.append(
            {
                "NIVEL": "Cooperado",
                "DIVISAO": random.choice(["Divisão A", "Divisão B", "Divisão C"]),
                "NOME": nome,
                "TIPO": random.choice(TIPOS_PESSOA),
                "CLIENTE DESDE": data_aleatoria(
                    pd.Timestamp("2015-01-01"), HOJE
                ).strftime("%d/%m/%Y"),
                "TIPO PESSOA": "F",
                "CGC/CPF": cpf,
                "DATA DE NASCIMENTO/DT. ABERTURA/FUNDAÇÃO": nasc,
                "TELEFONE": f"(85) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                "EMAIL": f"{nome.lower().replace(' ', '.')}{i}@exemplo.com",
                "CLIENTE": 10000 + i,
                "SEXO": random.choice(SEXOS),
                "DATA DE INCLUSÃO": data_aleatoria(
                    pd.Timestamp("2015-01-01"), HOJE
                ).strftime("%d/%m/%Y"),
                "SITUAÇÃO": "Ativo",
                "NOME PREFERENCIAL": nome.split()[0],
                "GRUPO DE PRODUÇÃO": random.choice(["Grupo 1", "Grupo 2", "Grupo 3"]),
                "E-MAIL SECUNDÁRIO": "",
                "ACEITA RECEBER E-MAILS PROMOCIONAIS": random.choice(["Sim", "Não"]),
                "DATA ALTERAÇÃO": data_aleatoria(
                    pd.Timestamp("2023-01-01"), HOJE
                ).strftime("%d/%m/%Y"),
                "Nº DA MATRICULA": float(20000 + i),
                "TIPO CARACTERÍSTICA": "Especialidade",
                "CARACTERÍSTICA": random.choice(ESPECIALIDADES),
                "CEP": f"60{random.randint(100,999)}-{random.randint(100,999)}",
                "NUMERO DO ENDEREÇO": str(random.randint(1, 2000)),
                "COMPLEMENTO DO ENDEREÇO": random.choice(
                    ["", "Apto 101", "Casa", "Bloco B"]
                ),
                "BAIRRO": random.choice(
                    ["Centro", "Aldeota", "Meireles", "Messejana", "Parquelândia"]
                ),
                "CIDADE": random.choice(CIDADES),
                "ESTADO": random.choice(ESTADOS),
                "PROFISSÃO": random.choice(PROFISSOES),
                "ESTADO CIVIL": random.choice(ESTADOS_CIVIS),
                "RENDA FAMILIAR/FATURAMENTO MÉDIO": random.randint(8000, 60000),
                "QTDE FILHOS/QTDE FUNCIONÁRIOS": random.randint(0, 4),
                "QTDE VEICS": random.randint(0, 3),
            }
        )
    return pd.DataFrame(linhas), cpfs


# ── Produção ──────────────────────────────────────────────────────────────────
def _base_row_producao():
    """Template com todas as 39 colunas (defaults)."""
    return {
        "RAMO": "",
        "NOME ABREVIADO DO PRODUTO": "",
        "DATA PROPOSTA": pd.NaT,
        "PROPOSTA": 0,
        "INÍCIO DE VIGÊNCIA": pd.NaT,
        "TÉRMINO DE VIGÊNCIA": pd.NaT,
        "SEGURADORA (ABREVIADO)": "",
        "SITUAÇÃO": "Ativa",
        "GRUPO DE PRODUÇÃO": "Grupo 1",
        "CAMPANHA": "",
        "TIPO DE NEGÓCIO": "",
        "TIPO DOCUMENTO": "",
        "SUB-TIPO DE DOCUMENTO": "",
        "CLIENTE": "",
        "CPF/CNPJ": "",
        "APÓLICE": "",
        "ENDOSSO": 0.0,
        "PRÊMIO LÍQ. DO SEGURO": 0.0,
        "PORCENTAGEM": 0.0,
        "COMISSÃO TOTAL (CORRET + CO-CORRET)": 0.0,
        "PRODUTOR": "Corretor Exemplo",
        "DATA EMISSÃO": pd.NaT,
        "DATA ENTRADA": pd.NaT,
        "COMISSÃO": 0.0,
        "USUÁRIO DA INCLUSÃO": "usuario.exemplo",
        "QTDEENDOSSO": 0,
        "SEGURADORA": "",
        "QUANTIDADE DE PARCELAS": 1,
        "MOTIVO CANCELAMENTO": "",
        "DATA CANCELAMENTO": pd.NaT,
        "CÓDIGO DO DOCUMENTO": float(random.randint(100000, 999999)),
        "DATA PAGAMENTO": np.nan,
        "DATA REFERÊNCIA": pd.NaT,
        "VENCIMENTO": np.nan,
        "DATA INCLUSÃO": pd.NaT,
        "PARCELA INICIAL": 1,
        "DIA PRÓX. PARCELA": random.randint(1, 28),
        "CARACTERISTICA": "",
        "NOME COMPLETO DO PRODUTO": "",
    }


def _row(
    cpf,
    nome,
    esp,
    produto,
    seg,
    ramo,
    tipo_negocio,
    tipo_doc,
    inicio,
    termino,
    premio,
    pct,
    apolice,
):
    r = _base_row_producao()
    comissao = round(premio * pct / 100.0, 2)
    r.update(
        {
            "RAMO": ramo,
            "NOME ABREVIADO DO PRODUTO": produto,
            "NOME COMPLETO DO PRODUTO": f"{produto} - Plano Exemplo",
            "DATA PROPOSTA": inicio,
            "PROPOSTA": random.randint(100000, 999999),
            "INÍCIO DE VIGÊNCIA": inicio,
            "TÉRMINO DE VIGÊNCIA": termino,
            "SEGURADORA (ABREVIADO)": SEG_ABREV.get(seg, seg[:4].upper()),
            "SEGURADORA": seg,
            "TIPO DE NEGÓCIO": tipo_negocio,
            "TIPO DOCUMENTO": tipo_doc,
            "CLIENTE": nome,
            "CPF/CNPJ": cpf,
            "APÓLICE": apolice,
            "PRÊMIO LÍQ. DO SEGURO": round(premio, 2),
            "PORCENTAGEM": pct,
            "COMISSÃO": comissao,
            "COMISSÃO TOTAL (CORRET + CO-CORRET)": comissao,
            "DATA EMISSÃO": inicio,
            "DATA ENTRADA": inicio,
            "DATA REFERÊNCIA": inicio,
            "DATA INCLUSÃO": inicio,
            "QUANTIDADE DE PARCELAS": random.choice([1, 6, 12]),
            "CARACTERISTICA": esp,
        }
    )
    return r


def gerar_producao(df_cad, cpfs_cad):
    # Universo de CPFs produtores: subset do cadastro + órfãos
    cpfs_produtores = random.sample(cpfs_cad, k=int(N_COOPERADOS * 0.6))
    cpfs_orfaos = [cpf_aleatorio() for _ in range(N_ORFAOS)]
    perfil = df_cad.set_index("CGC/CPF")[["NOME", "CARACTERÍSTICA"]].to_dict("index")

    linhas = []
    for cpf in cpfs_produtores + cpfs_orfaos:
        info = perfil.get(
            cpf,
            {"NOME": nome_aleatorio(), "CARACTERÍSTICA": random.choice(ESPECIALIDADES)},
        )
        nome, esp = info["NOME"], info["CARACTERÍSTICA"]
        n_produtos = random.randint(1, 4)
        for _ in range(n_produtos):
            produto = random.choice(PRODUTOS)
            tipo_vig = PRODUCT_TYPE_MAP[produto]
            seg = random.choice(SEGURADORAS)
            ramo = random.choice(RAMOS)
            pct = float(random.choice([10, 12, 15, 18, 20, 25, 30]))
            premio = round(random.uniform(300, 9000), 2)
            apolice = str(random.randint(1000000, 9999999))

            if tipo_vig == "RECORRENTE":
                # Faturas mensais (Bloco B): última fatura ativa ou não
                ativo = random.random() < 0.55
                ult = (
                    HOJE - pd.Timedelta(days=random.randint(5, 80))
                    if ativo
                    else HOJE - pd.Timedelta(days=random.randint(120, 600))
                )
                n_faturas = random.randint(2, 8)
                for k in range(n_faturas):
                    ini_f = ult - pd.DateOffset(months=k)
                    if ini_f < pd.Timestamp("2024-01-01"):
                        continue
                    linhas.append(
                        _row(
                            cpf,
                            nome,
                            esp,
                            produto,
                            seg,
                            ramo,
                            "ER",
                            "FATURA",
                            ini_f,
                            ini_f + pd.DateOffset(months=1),
                            premio / n_faturas,
                            pct,
                            apolice,
                        )
                    )
            else:
                # RENOVÁVEL/TRANSACIONAL: apólice (Bloco A)
                meses_termo = (
                    12 if tipo_vig == "RENOVÁVEL" else random.choice([1, 2, 3])
                )
                cenario = random.random()
                if cenario < 0.45:  # ativo hoje
                    inicio = HOJE - pd.Timedelta(days=random.randint(10, 330))
                elif cenario < 0.65:  # renovação vencendo nos próximos 90 dias
                    inicio = HOJE - pd.Timedelta(days=random.randint(275, 360))
                else:  # já vencido (inativo / win-back)
                    inicio = HOJE - pd.Timedelta(days=random.randint(400, 800))
                if inicio < pd.Timestamp("2024-01-01"):
                    inicio = pd.Timestamp("2024-01-01") + pd.Timedelta(
                        days=random.randint(0, 60)
                    )
                termino = inicio + pd.DateOffset(months=meses_termo)
                tneg = random.choice(["N", "R"])
                linhas.append(
                    _row(
                        cpf,
                        nome,
                        esp,
                        produto,
                        seg,
                        ramo,
                        tneg,
                        "APÓLICE",
                        inicio,
                        termino,
                        premio,
                        pct,
                        apolice,
                    )
                )

                # Renovação no ano seguinte (mesma raiz + sufixo de ano) p/ rating alto e log de raiz
                if tipo_vig == "RENOVÁVEL" and random.random() < 0.3:
                    linhas.append(
                        _row(
                            cpf,
                            nome,
                            esp,
                            produto,
                            seg,
                            ramo,
                            "R",
                            "APÓLICE",
                            inicio + pd.DateOffset(months=12),
                            termino + pd.DateOffset(months=12),
                            premio,
                            pct,
                            apolice + "2025",
                        )
                    )

                # Cancelamento (CN/CR) em alguns
                if random.random() < 0.05:
                    linhas.append(
                        _row(
                            cpf,
                            nome,
                            esp,
                            produto,
                            seg,
                            ramo,
                            "CN",
                            "ENDOSSO Cancelamento",
                            inicio + pd.Timedelta(days=20),
                            termino,
                            0.0,
                            pct,
                            apolice,
                        )
                    )
                    linhas[-1]["MOTIVO CANCELAMENTO"] = "Inadimplência"
                    linhas[-1]["DATA CANCELAMENTO"] = inicio + pd.Timedelta(days=20)

    # Grupo coeso dedicado para a regra de OUTLIER de prêmio disparar
    # (precisa de base grande e homogênea por produto×seguradora).
    for cpf in random.sample(cpfs_produtores, 50):
        info = perfil.get(
            cpf,
            {"NOME": nome_aleatorio(), "CARACTERÍSTICA": random.choice(ESPECIALIDADES)},
        )
        inicio = HOJE - pd.Timedelta(days=random.randint(30, 300))
        linhas.append(
            _row(
                cpf,
                info["NOME"],
                info["CARACTERÍSTICA"],
                "AUTOMÓVEL",
                "Seguradora Alfa",
                "AUTO",
                "R",
                "APÓLICE",
                inicio,
                inicio + pd.DateOffset(months=12),
                round(random.uniform(3500, 4500), 2),
                20.0,
                str(random.randint(1000000, 9999999)),
            )
        )

    df = pd.DataFrame(linhas)

    # Produtor por CPF (carteira de cada produtor) — múltiplos rótulos na acionabilidade.
    cpf_produtor = {c: random.choice(PRODUTORES) for c in df["CPF/CNPJ"].unique()}
    df["PRODUTOR"] = df["CPF/CNPJ"].map(cpf_produtor)

    # Produto não mapeado (furo)
    for idx in df.sample(5, random_state=SEED).index:
        df.loc[idx, "NOME ABREVIADO DO PRODUTO"] = PRODUTO_NAO_MAPEADO

    return df


# ── Injeção de furos financeiros ──────────────────────────────────────────────
def injetar_furos(df):
    rng = np.random.default_rng(SEED)
    apolices = df.index[df["TIPO DOCUMENTO"] == "APÓLICE"].to_numpy()

    def amostra(n):
        return rng.choice(apolices, size=min(n, len(apolices)), replace=False)

    # Prêmio zerado/negativo
    for idx in amostra(15):
        df.loc[idx, "PRÊMIO LÍQ. DO SEGURO"] = rng.choice(
            [0.0, -abs(rng.uniform(50, 500))]
        )
    # Comissão > prêmio
    for idx in amostra(8):
        p = max(df.loc[idx, "PRÊMIO LÍQ. DO SEGURO"], 100)
        df.loc[idx, "PRÊMIO LÍQ. DO SEGURO"] = round(p, 2)
        df.loc[idx, "COMISSÃO"] = round(p * rng.uniform(1.2, 2.0), 2)
        df.loc[idx, "COMISSÃO TOTAL (CORRET + CO-CORRET)"] = df.loc[idx, "COMISSÃO"]
    # Inconsistência percentual (comissão != prêmio*%/100)
    for idx in amostra(20):
        df.loc[idx, "COMISSÃO"] = round(
            df.loc[idx, "COMISSÃO"] * rng.uniform(1.3, 2.5), 2
        )
        df.loc[idx, "COMISSÃO TOTAL (CORRET + CO-CORRET)"] = df.loc[idx, "COMISSÃO"]
    # Outliers de prêmio: 2 valores extremos no grupo coeso AUTOMÓVEL×ALFA. Magnitude
    # moderada (≈10× o normal de ~3-4k do grupo): dispara o detector de outlier (±3σ)
    # sem dominar o eixo da Curva ABC e deixá-la ilegível.
    alvo = df.index[
        (df["NOME ABREVIADO DO PRODUTO"] == "AUTOMÓVEL")
        & (df["SEGURADORA (ABREVIADO)"] == SEG_ABREV["Seguradora Alfa"])
    ].to_numpy()
    for idx in alvo[:2]:
        df.loc[idx, "PRÊMIO LÍQ. DO SEGURO"] = round(rng.uniform(40000, 55000), 2)
    # Vigência invertida (término < início)
    for idx in amostra(5):
        ini = df.loc[idx, "INÍCIO DE VIGÊNCIA"]
        if pd.notnull(ini):
            df.loc[idx, "TÉRMINO DE VIGÊNCIA"] = ini - pd.Timedelta(days=30)
    # Duplicatas exatas
    dups = df.loc[amostra(6)].copy()
    df = pd.concat([df, dups], ignore_index=True)
    return df


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Gerando cadastro de exemplo...")
    df_cad, cpfs_cad = gerar_cadastro()
    print(f"  {len(df_cad)} cooperados.")

    print("Gerando produção de exemplo...")
    df_prod = gerar_producao(df_cad, cpfs_cad)
    df_prod = injetar_furos(df_prod)
    print(f"  {len(df_prod)} linhas de produção.")

    cad_path = OUT_DIR / "RptClienteLista.xlsx"
    prod_path = OUT_DIR / "RptAnaliseProducao.xlsx"
    df_cad.to_excel(cad_path, index=False, engine="openpyxl")
    df_prod.to_excel(prod_path, index=False, engine="openpyxl")

    print(f"\nArquivos gerados em {OUT_DIR}:")
    print(f"  - {cad_path.name} ({df_cad.shape[0]} x {df_cad.shape[1]})")
    print(f"  - {prod_path.name} ({df_prod.shape[0]} x {df_prod.shape[1]})")
    print(
        "\nFuros de qualidade injetados de propósito: prêmio zerado/negativo, "
        "comissão > prêmio, inconsistência %, outliers, vigência invertida, "
        "duplicatas, produto não mapeado, idade implausível e CPFs órfãos."
    )
    print(
        "\nPara usar no pipeline: copie os 2 arquivos para data/raw/ e rode "
        "`python Main.py --force`."
    )


if __name__ == "__main__":
    main()
