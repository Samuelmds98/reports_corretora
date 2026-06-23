# Guia de Métricas Qualitativas (Raio X Qualitativo)

> Métricas **não-monetárias** — não dependem de prêmio nem de comissão. Pensadas para a
> abordagem inicial ao gerente enquanto a confiabilidade dos valores é baixa, usando só
> os campos confiáveis (especialidade, produto, ramo, seguradora, datas, contagens).
>
> Estas visões estão **distribuídas pelos tracks** segmentados (não há mais um workbook
> "Qualitativo" único): apoio comercial não-monetário em `outputs/comercial/`
> (Mix, Market Share por contagem, Profundidade, Cross-sell Gaps) e qualidade de
> cadastro/processo em `outputs/operacional/` (Completude, Taxa de Cancelamento). Cada
> "Onde:" abaixo aponta a aba/parquet/HTML do track correspondente.

Para cada métrica: o que é, como é calculada, dados usados, granularidade, onde encontrar,
situações de uso e o que acontece com dados ruins.

Índice:
1. [Por que qualitativo](#1-por-que-qualitativo)
2. [Completude do Cadastro](#2-completude-do-cadastro)
3. [Mix de Produtos](#3-mix-de-produtos)
4. [Market Share por Contagem](#4-market-share-por-contagem)
5. [Profundidade de Carteira](#5-profundidade-de-carteira)
6. [Taxa de Cancelamento Estrutural](#6-taxa-de-cancelamento-estrutural)
7. [Cross-sell Gaps por Especialidade](#7-cross-sell-gaps-por-especialidade)
8. [Métricas do relatório principal que também são não-monetárias](#8-métricas-do-relatório-principal-que-também-são-não-monetárias)
9. [Roteiro sugerido para o gerente](#9-roteiro-sugerido-para-o-gerente)

---

## 1. Por que qualitativo

A confiabilidade dos valores (prêmio/comissão) hoje é baixa. Estas métricas usam apenas
**contagens, categorias e datas** — campos com preenchimento alto e confiável. Importante:
o **Rating** e o **Status** do motor **já são não-monetários** (derivam de contagens de
produtos ativos e categorias), então também entram nesta abordagem.

Tiers de confiabilidade (base real): 🟢 Alta = especialidade, produto, ramo, seguradora,
datas de vigência, nascimento, tipo de negócio/documento · 🟡 Média = sexo, tempo de casa,
profissão · 🟠 Baixa = cidade/estado/bairro (~54%), estado civil (41%) · 🔴 Inútil =
`QTDE FILHOS`, `QTDE VEICS` (constantes).

---

## 2. Completude do Cadastro

**Pergunta:** em que estado está o nosso cadastro? Quais campos dá para confiar?

**Como é calculada:** para cada campo (do cadastro e da produção), `PREENCHIMENTO_PCT`
(% de não-nulos) e `VALORES_DISTINTOS` (cardinalidade). Classificação `CONFIABILIDADE`:
- `Inútil (constante)` se distintos ≤ 1;
- `Alta` se preenchimento ≥ 95%;
- `Média` se ≥ 70%;
- `Baixa` caso contrário.

> Calculada sobre o cadastro **bruto** (antes de `prepare_demographics` preencher nulos com
> "Não Informado"), senão tudo apareceria 100%.

**Dados:** todos os campos categóricos/qualitativos das duas bases. **Granularidade:** 1 linha por campo.

**Onde** (track Operacional): aba `1_Completude_Cadastro` · parquet
`operacional/parquet/completude_cadastro` · HTML `operacional/visuals/10_completude_cadastro.html`.
Sem workbook de auditoria (é um diagnóstico de metadados, não agrega registros).

**Situações de uso:** abre a conversa com o gerente; fundamenta o foco em dados confiáveis;
vira um **plano de saneamento** (priorizar os campos 🟠/🔴).

**Impactos:** é a própria meta-métrica de qualidade. Reflete o estado real do cadastro —
quanto pior o preenchimento, mais valiosa a visão.

---

## 3. Mix de Produtos

**Pergunta:** qual a composição da carteira por produto (em número de cooperados)?

**Como é calculada:** por `PRODUTO`: `QTD_COOPERADOS` (CPFs distintos), `QTD_ITENS`
(registros de produto), `QTD_ATIVOS` (status ATIVO), `TIPO_PRODUTO` (RENOVÁVEL/RECORRENTE/
TRANSACIONAL via `PRODUCT_TYPE_MAP`) e `PCT_COOPERADOS` (= QTD_COOPERADOS ÷ total de CPFs
produtores × 100). Ordena por `QTD_COOPERADOS` desc.

**Dados:** `df_prod_status` (PRODUTO, CPF, STATUS). **Granularidade:** 1 linha por produto.

**Onde** (track Comercial): aba `19_Mix_Produtos` · parquet `comercial/parquet/mix_produtos` ·
auditoria `comercial/auditoria/Qual_Mix_Produtos.xlsx` (reconciliação: CPFs distintos por
produto). **Não usa valor.**

**Situações de uso:** entender concentração de portfólio; produtos "carro-chefe" vs nicho;
base para campanhas.

**Impactos:** produto não mapeado vira `TIPO_PRODUTO = INDEFINIDO` (sinalizado no DQ);
nome de produto inconsistente fragmenta a contagem.

---

## 4. Market Share por Contagem

**Pergunta:** qual a dependência de cada seguradora — **sem** usar prêmio?

**Como é calculada:** por `SEGURADORA`: `QTD_CLIENTES_DISTINTOS`, `QTD_ITENS`, `QTD_ATIVOS`
e `SHARE_ITENS_PCT` (= QTD_ITENS ÷ total de itens × 100, soma 100%). Ordena por `QTD_ITENS` desc.

**Dados:** `df_prod_status`. **Granularidade:** 1 linha por seguradora.

**Onde** (track Comercial): aba `20_Market_Share_Contagem` · parquet
`comercial/parquet/market_share_contagem` · auditoria
`comercial/auditoria/Qual_Market_Share_Contagem.xlsx`.

**Situações de uso:** risco de concentração de parceiros e negociação — medido por volume de
contratos/clientes, não por receita (que é o dado frágil).

**Impactos:** nome de seguradora inconsistente fragmenta o share. `QTD_CLIENTES_DISTINTOS`
pode somar > total de clientes (um cliente pode ter várias seguradoras) — é penetração, não partição.

---

## 5. Profundidade de Carteira

**Pergunta:** quão "fundo" é o relacionamento de cada cooperado? Quem é mono-produto?

**Como é calculada:** por `CPF_LIMPO`: `N_PRODUTOS` (produtos distintos), `N_SEGURADORAS`,
`N_ITENS`; entre os **ativos**: `N_CATEGORIAS_ATIVAS` e flags `TEM_RECORRENTE` /
`TEM_RENOVAVEL` / `TEM_TRANSACIONAL`; `CLASSE_PROFUNDIDADE` (Mono-produto / 2 produtos /
3+ produtos). Enriquecida com `RATING_ESTRELAS` e `STATUS_GLOBAL`. Ordena por `N_PRODUTOS`
asc e `RATING_ESTRELAS` desc (mono-produto de alto rating primeiro = melhor alvo de expansão).

**Dados:** `df_prod_status` + insights do cliente. **Granularidade:** 1 linha por cooperado.

**Onde** (track Comercial): aba `21_Profundidade_Carteira` · parquet
`comercial/parquet/profundidade_carteira` · auditoria
`comercial/auditoria/Qual_Profundidade_Carteira.xlsx` (reconciliação: produtos distintos por CPF).

**Situações de uso:** **pipeline de expansão/cross-sell** — mono-produto = maior potencial;
`TEM_RECORRENTE == Falso` entre ativos = gap de produto de recorrência.

**Impactos:** depende do status do produto (datas) e do `PRODUCT_TYPE_MAP`. CPF digitado
errado divide um cooperado em dois e subestima a profundidade.

---

## 6. Taxa de Cancelamento Estrutural

**Pergunta:** quais produtos têm mais cancelamento — **sem** olhar valor?

**Como é calculada:** por `PRODUTO`: `N_APOLICES` (registros com `TIPO DE NEGÓCIO` ∈ {N, R}),
`N_CANCELAMENTOS` (∈ {CN, CR}) e `TAXA_CANCELAMENTO_PCT` (= cancelamentos ÷ apólices × 100).
Considera só produtos com `N_APOLICES > 0`; ordena pela taxa desc.

**Dados:** produção bruta (`TIPO DE NEGÓCIO`). **Granularidade:** 1 linha por produto.

**Onde** (track Operacional): aba `8_Taxa_Cancelamento` · parquet
`operacional/parquet/taxa_cancelamento`. Sem workbook de auditoria próprio (é uma razão
entre contagens; rastreável via `comercial/auditoria/Calculadora_Produtos.xlsx`).

**Situações de uso:** churn estrutural por produto; priorizar retenção e revisar produtos
com cancelamento alto.

**Impactos:** cancelamento (CN/CR) sem a apólice correspondente na base (ex.: apólice anterior
ao corte de 2024) distorce a razão. É contagem, então independe da qualidade dos valores.

---

## 7. Cross-sell Gaps por Especialidade

**Pergunta:** onde há mais oportunidade de oferta por perfil profissional?

**Como é calculada:** deriva do Mix por Especialidade. Por `(CARACTERÍSTICA, PRODUTO)`:
`COOPERADOS_SEM_PRODUTO` (= total de cooperados ativos da especialidade − os que já têm o
produto) e `GAP_PCT` (= 100 − `PENETRACAO_PCT`). Considera só especialidades com base ≥ 5
cooperados ativos; ordena por `COOPERADOS_SEM_PRODUTO` desc (maior lacuna absoluta primeiro).

**Dados:** `df_specialty` (produtos ativos × especialidade do cadastro).
**Granularidade:** 1 linha por (especialidade, produto).

**Onde** (track Comercial): aba `22_CrossSell_Gaps_Especialidade` · parquet
`comercial/parquet/crosssell_gaps` · HTML `comercial/visuals/11_crosssell_gaps.html`.
Lastro herdado de `comercial/auditoria/Mix_Especialidade.xlsx`.

**Situações de uso:** **fila de campanhas** — especialidade de base grande e baixa penetração
de um produto = alvo natural. Ex.: muitos pediatras sem VIAGEM/AP.

**Impactos:** depende do cruzamento produção × cadastro (CPF órfão entra como "Não Informado")
e usa a `CARACTERÍSTICA` do **cadastro** (com acento), não a da produção.

---

## 8. Métricas do relatório principal que também são não-monetárias

Já existem no pipeline e podem ser apresentadas omitindo as colunas de valor (detalhe em
`docs/GUIA_METRICAS.md`):

| Métrica | Por que é não-monetária |
|---|---|
| **Rating (1–5★)** | Baseado em contagens de produtos ativos e categorias, não em valor. |
| **Status do Produto / Global** | Regras de vigência e cancelamento (datas), sem valor. |
| **Demografia / Taxa de Conversão** | Contagens de cooperados e ativos por célula. |
| **Mix por Especialidade** | Penetração = contagem de cooperados. |
| **Cross-sell (co-posse)** | Contagem de clientes com pares de produtos. |
| **Cohort / Sazonalidade** | Use as colunas de **clientes/produtos** (não as de prêmio). |
| **Snapshot Mensal** | Use **clientes/produtos ativos** por mês (não o prêmio). |
| **Agenda de Renovações** | Datas + urgência + rating (sem depender de valor). |

---

## 9. Roteiro sugerido para o gerente

1. **Completude do Cadastro** (§2) — mostra o estado do cadastro e justifica a abordagem.
2. **Raio X por Especialidade** — Mix por especialidade + conversão + rating (especialidade
   é 100% confiável).
3. **Profundidade / Mono-produto** (§5) — "~70% dos produtores têm só 1 produto" → pipeline
   de expansão priorizado por rating.
4. **Cross-sell Gaps** (§7) — onde a próxima campanha rende mais.
5. **Agenda de Renovações** — fila acionável imediata.

> Todos os números são **auditáveis** (`outputs/<público>/auditoria/`) e **rastreáveis** até
> a linha de origem — sustentam a conversa mesmo com o cadastro imperfeito. Quando os valores
> forem saneados, as visões de prêmio/comissão entram numa 2ª fase (ver `docs/GUIA_METRICAS.md`).
