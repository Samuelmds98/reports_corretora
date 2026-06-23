# Guia de Métricas — Definição, cálculo, dados e impactos de qualidade

> Para cada métrica: o que é, como é calculada, quais dados usa, em que situações
> usar e — **o mais importante para um cenário com problema de cadastro** — o que
> acontece com a métrica quando o dado de origem está errado, ruim ou ausente.

Índice:
1. [Conceitos-base](#1-conceitos-base) (alimentam quase tudo)
2. [Status do Produto](#2-status-do-produto)
3. [Tipo de Vigência](#3-tipo-de-vigência)
4. [Rating do Cliente (1–5★)](#4-rating-do-cliente-15)
5. [Status Global do Cliente](#5-status-global-do-cliente)
6. [Curva ABC](#6-curva-abc)
7. [Market Share](#7-market-share)
8. [Cohort / Sazonalidade](#8-cohort--sazonalidade)
9. [Demografia / Taxa de Conversão](#9-demografia--taxa-de-conversão)
10. [Calculadora de Produtos](#10-calculadora-de-produtos)
11. [Mix por Especialidade](#11-mix-por-especialidade)
12. [Agenda de Renovações](#12-agenda-de-renovações)
13. [Win-Back](#13-win-back)
14. [Snapshot Mensal Ativo](#14-snapshot-mensal-ativo)
15. [Curva ABC / Market Share 2025+ (janeladas)](#15-curva-abc--market-share-2025-janeladas)
16. [Métricas na ótica da Comissão](#16-métricas-na-ótica-da-comissão)
17. [Qualidade de Dados (DQ)](#17-qualidade-de-dados-dq)
18. [Tabela-resumo de impactos](#18-tabela-resumo-de-impactos)

---

## 1. Conceitos-base

Três campos da produção governam quase tudo:

- **`INÍCIO DE VIGÊNCIA` / `TÉRMINO DE VIGÊNCIA`** — período de cobertura do registro.
- **`TIPO DE NEGÓCIO`** — `N`/`R` = apólice (nova/renovação); `EN`/`ER` = endosso;
  `CN`/`CR` = cancelamento; faturas vêm marcadas em `TIPO DOCUMENTO = FATURA`.
- **`PRÊMIO LÍQ. DO SEGURO`** e **comissão** — os valores financeiros.

> ⚠️ **A janela de avaliação é definida por `INÍCIO DE VIGÊNCIA`.** A base atual foi
> cortada em **2024+**. Isso afeta toda métrica temporal e toda soma — ver impactos
> em cada seção e no `run_context.parquet`/guardrails.

---

## 2. Status do Produto

**O que é:** o estado de cada produto de cada cooperado — `ATIVO`, `INATIVO` ou `CANCELADO`.

**Como é calculado** (por `CPF_LIMPO × SEGURADORA × PRODUTO`):
- **Bloco A — tem apólice (`TIPO DE NEGÓCIO` ∈ {N, R}):** pega a apólice mais recente.
  É `ATIVO` se `INÍCIO ≤ hoje ≤ TÉRMINO` **e** não há cancelamento (`CN`/`CR`) dentro
  da vigência e até hoje. Se houver cancelamento → `CANCELADO`. Fora da vigência → `INATIVO`.
- **Bloco B — sem apólice, mas há fatura:** é `ATIVO` se a fatura mais recente começou
  **nos últimos 90 dias** e não há cancelamento; senão `INATIVO`.

**Dados utilizados:** `TIPO DE NEGÓCIO`, `TIPO DOCUMENTO`, `INÍCIO/TÉRMINO DE VIGÊNCIA`,
`APÓLICE`, `RAMO`, `SEGURADORA (ABREVIADO)`.

**Situações de uso:** base de tudo — define quem é ativo, alimenta rating, ABC, snapshot.

**Impactos de dados ruins:**
- **Datas ausentes/erradas** (`INÍCIO`/`TÉRMINO` nulos ou invertidos) → o produto não
  passa no teste de vigência e cai como **INATIVO** indevidamente. (A vigência invertida
  é sinalizada no `DQ`.)
- **Cancelamento (CN/CR) sem a apólice correspondente** na base (ex: apólice de 2023
  cortada pela janela) → o cancelamento não encontra o que cancelar e é ignorado.
- **Janela 2024+:** produtos cuja única apólice/renovação é anterior a 2024 somem;
  podem parecer "prospects" em vez de inativos.

---

## 3. Tipo de Vigência

**O que é:** classifica o produto em **RENOVÁVEL** (ciclo anual, ex. AUTO), **RECORRENTE**
(mensal/faturas, ex. SAÚDE/ODONTO/VIDA) ou **TRANSACIONAL** (pontual, ex. VIAGEM).

**Como é calculado:** lookup do `NOME ABREVIADO DO PRODUTO` no mapa `PRODUCT_TYPE_MAP`
(fonte de verdade em `parameters.py`, originada do Google Sheets `Página1.html`).

**Impactos de dados ruins:**
- **Produto não mapeado** (nome novo/divergente) → tipo `INDEFINIDO` → **não conta**
  como recorrente/renovável/transacional no rating, e pode distorcer o status. O `DQ`
  sinaliza "Produto não mapeado". **Toda vez que surge produto novo, atualizar o mapa.**

---

## 4. Rating do Cliente (1–5★)

**O que é:** nota de 1 a 5 estrelas por CPF, top-down, medindo profundidade de carteira.

**Como é calculado** (sobre os **produtos ATIVOS** do CPF):
- Conta `recorrentes`, `renováveis`, `transacionais_12m` (transacional ativo OU com
  vigência nos últimos 365 dias), `ativos_total` e `categorias_ativas` (tipos distintos).
- **5★:** recorrentes ≥ 1 **e** renováveis ≥ 2 **e** transacionais_12m ≥ 1
- **4★:** recorrentes ≥ 1 **e** renováveis ≥ 1 **e** transacionais_12m ≥ 1
- **3★:** categorias distintas ≥ 2
- **2★:** produtos ativos ≥ 2 **e** categorias == 1
- **1★:** produtos ativos == 1
- **0:** nenhum produto ativo

**Dados utilizados:** `STATUS_PRODUTO`, `PRODUTO` (→ tipo de vigência), `MAX_INICIO_VIGENCIA`.

**Situações de uso:** priorização comercial, segmentação, fila de contato.

**Impactos de dados ruins:**
- O rating depende 100% do **status do produto** → qualquer erro de data/produto que
  derrube um ATIVO para INATIVO **rebaixa** o rating.
- **Importante:** rating e status são calculados juntos a partir dos ativos atuais.
  Logo, **um cliente INATIVO sempre tem rating 0** (não existe "rating histórico").
- Produto `INDEFINIDO` não soma em nenhuma categoria → pode impedir o cliente de
  alcançar 3★+ mesmo tendo variedade real.

---

## 5. Status Global do Cliente

**O que é:** `ATIVO` ou `INATIVO` por CPF (no relatório, quem não tem produção vira
`INATIVO (PROSPECT)`).

**Como é calculado:** `ATIVO` se o CPF tem ≥ 1 recorrente OU renovável OU transacional_12m
ativo; senão `INATIVO`.

**Impactos de dados ruins:** mesmos do status do produto. CPF digitado errado na
produção **divide** o cliente em dois e pode deixar metade como prospect.

---

## 6. Curva ABC

**O que é:** Pareto da carteira — quais cooperados concentram a receita (Classe A = topo
80%, B = 15% seguintes, C = cauda 5%).

**Como é calculado:** por `CPF_LIMPO`, soma o prêmio de **todos** os produtos
(`TOTAL_PREMIO_LIQ`), ordena desc, calcula `%_ACUMULADO = soma acumulada / total`, e
classifica: ≤ 0,80 → A; ≤ 0,95 → B; senão C.

**Valor = carteira vigente (último ciclo).** Desde a correção multi-ciclo, a ABC soma
`PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO` (só o ciclo de vigência mais recente de
cada apólice), e **não** o histórico `SOMA_*`. Assim uma apólice renovada ano a ano não
infla o cliente. É um *share-of-wallet da carteira atual*. (Ver §12 e `flag_last_cycle`.)

**Dados utilizados:** `PREMIO_ULTIMO_CICLO` por produto (soma das linhas brutas do último
ciclo — `EH_ULTIMO_CICLO`) agregado por CPF.

**Situações de uso:** definir carteira de alto valor, esteira de retenção, share-of-wallet.

**Impactos de dados ruins:**
- **Prêmio errado/zerado** em poucos registros muda o ranking e a classe de vários CPFs
  (o `%_ACUMULADO` é relativo ao total). O `DQ` sinaliza prêmio zerado/negativo e
  comissão > prêmio.
- **Duplicatas** inflam o prêmio de um CPF e o sobem artificialmente para Classe A.
- **CPF dividido** (erro de digitação) reparte a receita de um cliente em dois,
  rebaixando ambos.
- **Carteira vigente, não vitalícia:** `TOTAL_PREMIO_LIQ` é o prêmio do **último ciclo**
  dos produtos do cliente (dentro da janela 2024–2026 carregada). Não leia a ABC como
  "share-of-wallet de todos os tempos" nem como soma de todas as renovações.

---

## 7. Market Share

**O que é:** participação de cada seguradora no prêmio total da carteira.

**Como é calculado:** por `SEGURADORA`, soma prêmio e comissão (do **último ciclo**),
conta CPFs distintos, conta itens ativos, e
`MARKET_SHARE_RECEITA_% = prêmio da seguradora / prêmio total × 100`.

**Valor = carteira vigente (último ciclo).** Igual à ABC, soma
`PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO` para não inflar parceiros com renováveis
multi-ciclo — mede a participação na carteira atual.

**Dados utilizados:** `SEGURADORA (ABREVIADO)`, `PRÊMIO LÍQ. DO SEGURO` (linhas do último
ciclo), comissão, status.

**Situações de uso:** negociação com parceiros, risco de concentração, mix de fornecedores.

**Impactos de dados ruins:**
- **Nome de seguradora inconsistente** (abreviação divergente) **fragmenta** uma mesma
  seguradora em várias linhas, subestimando o share real.
- Prêmio errado/duplicado distorce o share (é relativo ao total).
- Janela 2024+: share da janela, não vitalício.

---

## 8. Cohort / Sazonalidade

**O que é:** por mês de **safra** (mês do primeiro início de vigência do produto): quantos
clientes/produtos e quanto prêmio entraram.

**Como é calculado:** agrupa por `SAFRA_MES_VIGENCIA` (= `PRIMEIRO_INICIO` formatado
`AAAA-MM`): clientes distintos, produtos distintos, soma de prêmio/comissão, tickets.

**Dados utilizados:** `PRIMEIRO_INICIO` (mínimo de início do grupo do produto), prêmio, comissão.

**Situações de uso:** aquisição por período, sazonalidade de vendas.

**Impactos de dados ruins:**
- **`PRIMEIRO_INICIO` é o mínimo do grupo** → se a base foi cortada, um produto antigo
  é "achatado" para o primeiro mês disponível. **A 1ª safra (2024-01) fica inflada**
  por contratos que começaram antes do corte.
- Por isso a janela 2024+ foi feita para avaliar **2025-2026** e descartar a 1ª safra.
- Datas ausentes → o produto sai da cohort.

---

## 9. Demografia / Taxa de Conversão

**O que é:** por célula demográfica (Cidade, Estado, Sexo, Estado Civil, Faixa Etária,
Especialidade): total de cooperados, ativos e taxa de conversão.

**Como é calculado:** agrupa o **cadastro cruzado** por essas colunas:
`TOTAL_COOPERADOS = contagem de CPF`, `COOPERADOS_ATIVOS = contagem de STATUS_GLOBAL == ATIVO`,
`TAXA_CONVERSAO_% = ativos / total × 100`, `TICKET_MEDIO_ESTRELAS = média do rating`.

**Dados utilizados:** colunas de perfil do **cadastro** (`CIDADE`, `ESTADO`, `SEXO`,
`ESTADO CIVIL`, `FAIXA_ETARIA`, `CARACTERÍSTICA`) + `STATUS_GLOBAL`/`RATING`.

**Situações de uso:** segmentação por perfil, onde converter mais, abordagem por especialidade.

**Impactos de dados ruins:**
- **É a métrica mais sensível a cadastro.** Perfil ausente vira célula "Não Informado".
- **Cadastro filtrado por categoria:** a demografia cobre só esse recorte; a taxa de
  conversão fica relativa ao subconjunto. Se o cadastro é um subconjunto e a produção
  é ampla, há **descasamento de população** (a produção tem CPFs que nem aparecem aqui).
  O guardrail alerta quando a taxa de órfãos passa de 15%.
- `IDADE`/`FAIXA_ETARIA` dependem de `DATA DE NASCIMENTO` válida; data ruim → "Não Calculada".

---

## 10. Calculadora de Produtos

**O que é:** a tabela-mãe no grão de **produto** (um por `CPF × SEGURADORA × PRODUTO`),
com status e totais. É a fonte de quase todas as outras visões.

**Como é calculado:** agrupa as linhas brutas por `CPF_LIMPO × SEGURADORA (ABREVIADO) ×
NOME ABREVIADO DO PRODUTO`: `STATUS_PRODUTO`, `PRIMEIRO_INICIO` (mín. início),
`ULTIMO_TERMINO` (máx. término), `SOMA_PREMIO_LIQ`, `SOMA_COMISSAO`, `MEDIA_PORCENTAGEM`.

**Situações de uso:** ponte de auditoria para a linha bruta; base de ABC, snapshot, mix.

**Impactos de dados ruins:** herda tudo do status do produto e dos valores brutos. É aqui
que se vê, por produto, a soma exata de prêmio/comissão das linhas que o compõem.

---

## 11. Mix por Especialidade

**O que é:** penetração de cada produto dentro de cada especialidade médica.

**Como é calculado:** entre os **produtos ATIVOS**, agrupa por `CARACTERÍSTICA × PRODUTO`:
`QTD_COOPERADOS_COM_PRODUTO = CPFs distintos`; `TOTAL_COOPERADOS_ATIVOS_ESPECIALIDADE =
CPFs ativos distintos na especialidade`; `PENETRACAO_PCT = qtd / total × 100`.

**Dados utilizados:** produtos ativos (produção) + `CARACTERÍSTICA` (cadastro).

**Situações de uso:** cross-sell segmentado por perfil profissional.

**Impactos de dados ruins:**
- Depende do cruzamento produção × cadastro: **CPF órfão** entra como especialidade
  "Não Informado" e some das especialidades reais.
- Sensível à **inconsistência de acento** entre as bases: produção usa
  `CARACTERISTICA` (sem acento) e cadastro `CARACTERÍSTICA` (com acento) — aqui vale a
  do cadastro.

---

## 12. Agenda de Renovações

**O que é:** apólices **renováveis ativas** vencendo nos próximos 30/60/90 dias, com
urgência e rating — a fila de contato do corretor.

**Como é calculado:** filtra produtos ATIVOS do tipo RENOVÁVEL com
`0 ≤ (ULTIMO_TERMINO − hoje) ≤ 90`; classifica urgência (🔴 ≤30, 🟡 ≤60, 🟢 ≤90);
junta o rating do cliente.

**Prêmio/comissão = só o último ciclo de vigência.** A agenda usa
`PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO`, **não** o histórico `SOMA_*`. Uma
apólice renovada ano a ano (ex.: vigente 2024→2025 e renovada 2025→2026) tem várias
linhas N/R para a MESMA apólice; somar todos os anos inflaria o "prêmio em risco". A
flag `EH_ULTIMO_CICLO` (ver `flag_last_cycle`) marca, por
`(CPF, SEGURADORA, PRODUTO, RAIZ_APÓLICE)`, as linhas cujo `INÍCIO DE VIGÊNCIA` é
`>=` o maior início entre as linhas N/R do grupo — ou seja, a renovação vigente e
seus endossos. `RAIZ_APÓLICE` mantém apólices distintas (ex.: dois carros) como
ciclos separados, cada uma somando o seu último ciclo. (Produtos só-FATURA/recorrentes
não entram aqui, mas para eles a flag conta todas as linhas: cada fatura é um pagamento
distinto — é por isso que `PRIMEIRO_INICIO`/`ULTIMO_TERMINO` seguem mín./máx.)

**Situações de uso:** priorização de renovação por urgência e valor.

**Impactos de dados ruins:**
- **`ULTIMO_TERMINO` errado** tira a apólice da janela (some da agenda) ou a coloca na
  urgência errada.
- Produto mal classificado (não-RENOVÁVEL) → não aparece, mesmo devendo renovar.
- **Renovação com número de apólice totalmente diferente** (sem raiz comum) é vista como
  apólice nova → os ciclos não se ligam e o prêmio do ciclo anterior pode reaparecer.
  Aparece no `Log_Apolices_Conflito_Reports` quando a raiz colide; quando nem a raiz bate,
  só dá para detectar no cruzamento manual.

---

## 13. Win-Back

**O que é:** clientes **inativos** cujo último produto venceu nos últimos 12 meses —
candidatos a reativação, ordenados por prêmio histórico.

**Como é calculado:** CPFs com `STATUS_GLOBAL = INATIVO` cujo `ULTIMO_TERMINO` está nos
últimos 12 meses; `DIAS_INATIVO = hoje − ULTIMO_TERMINO`;
`TOTAL_PREMIO_HISTORICO = soma do prêmio de todos os produtos do CPF`.

> Nota: o filtro original do plano (rating ≥ 2) era impossível (inativo ⇒ rating 0), então
> usa-se apenas status + janela de 12 meses, ordenando por prêmio histórico.

**Situações de uso:** campanha de reativação priorizada por valor.

**Impactos de dados ruins:**
- **Janela 2024+:** churned antes de 2024 **não aparecem** (saíram da base). O universo
  de win-back está limitado ao que iniciou vigência a partir de 2024.
- `ULTIMO_TERMINO` errado tira/inclui CPFs indevidamente.

---

## 14. Snapshot Mensal Ativo

**O que é:** quantos clientes/produtos ativos e quanto prêmio havia **em cada mês**.

**Como é calculado:** explode o **grão de ciclo** (`build_cycle_grain`) — uma linha por
**ciclo de vigência** de cada apólice — em uma linha por mês (janela do ciclo); por
`MES_REFERENCIA`: clientes distintos, produtos (contagem), prêmio e comissão. O prêmio
de **cada ciclo** é atribuído aos **seus** meses (o do ciclo 2025→2026 só nos meses de
2025-2026; o do ciclo anterior nos meses dele).

**Por que grão de ciclo (correção multi-ciclo):** antes o snapshot usava a soma histórica
do produto (`SOMA_*`) repetida em **todos** os meses de **todas** as vigências, inflando o
prêmio das renováveis renovadas. O grão de ciclo conserta o prêmio **sem perder a contagem
histórica** — um cliente ativo em 2024 continua ativo em 2024 (cada ciclo conta na sua
própria janela). Difere de `flag_last_cycle`, que mantém só o último ciclo (usado nas
visões de carteira vigente).

**Situações de uso:** "quantos ativos tínhamos em mar/2025?", tendência e sazonalidade.

**Impactos de dados ruins:**
- **Efeito de borda:** os primeiros meses da janela (início de 2024) ainda ficam parciais
  por contratos cujo ciclo anterior começou antes do corte (a 1ª safra não tem o ciclo
  completo na base).
- As contagens de **2025-2026 são confiáveis** (ativo é ativo). O prêmio mensal é "prêmio
  do ciclo atribuído ao mês", não receita reconhecida no mês.
- Datas ausentes → ciclo fora do snapshot.

---

## 15. Curva ABC / Market Share 2025+ (janeladas)

**O que é:** as mesmas ABC e Market Share, mas **só com registros cuja `INÍCIO DE VIGÊNCIA`
≥ 2025** — para isolar o período de avaliação real, sem o prêmio de 2024.

**Como é calculado:** filtra as **linhas brutas** por `INÍCIO DE VIGÊNCIA ≥ 2025-01-01` e
reagrupa (por CPF para ABC; por seguradora para share). A coluna `JANELA_INICIO` carimba o corte.

**Ressalva de semântica (importante):** como o filtro é por `INÍCIO DE VIGÊNCIA`, isto é
**"originação no período"**, não "receita reconhecida":
- faturas mensais (recorrente): cada fatura tem início próprio → ≈ receita do período;
- apólices anuais (renovável): captura negócio **novo/renovado** em 2025+, e **exclui a
  cauda** de contratos iniciados em 2024 que seguem vigentes.

**Situações de uso:** avaliar a concentração/originação **do período sob análise** sem
arrastar a 1ª safra.

**Impactos de dados ruins:** os mesmos da ABC/Market Share, mais a dependência de
`INÍCIO DE VIGÊNCIA` correto (é o parâmetro de recorte).

---

## 16. Métricas na ótica da Comissão

> Prêmio é o volume que passa pela corretora; **comissão é o que ela de fato recebe**.
> Como a taxa varia por produto/seguradora, a foto por comissão difere da por prêmio.

### 16.1 Curva ABC por Comissão
**O que é:** Pareto dos cooperados por **comissão** gerada (não por prêmio).
**Como é calculado:** por `CPF_LIMPO`, soma `SOMA_COMISSAO`, ordena desc, `%_ACUMULADO`
e classe A/B/C (mesma regra 80/15/5). Colunas: `TOTAL_COMISSAO`, `CURVA_ABC_COMISSAO`,
`TICKET_MEDIO_COMISSAO_POR_PRODUTO`.
**Uso:** priorizar quem realmente remunera a corretora. Cruzar com a ABC por prêmio:
cliente de alto prêmio e baixa comissão tem **margem ruim**.

### 16.2 Margem / Market Share por Comissão (seguradora)
**O que é:** participação de cada seguradora na comissão **e** a `TAXA_COMISSAO_EFETIVA_%`
(= comissão ÷ prêmio) — qual parceiro paga melhor.
**Como é calculado:** por `SEGURADORA`, `TOTAL_COMISSAO`, `TOTAL_PREMIO_LIQ`,
`MARKET_SHARE_COMISSAO_% = comissão/comissão total × 100`,
`TAXA_COMISSAO_EFETIVA_% = comissão/prêmio × 100`.
**Uso:** direcionar volume para parceiros de maior taxa; renegociar os de baixa margem.

### 16.3 Margem por Comissão (produto)
**O que é:** `TAXA_COMISSAO_EFETIVA_%` por produto — quais produtos pagam melhor.
**Como é calculado:** por `PRODUTO`, soma comissão e prêmio, taxa efetiva = razão; ordena desc.
**Uso:** mix de produto orientado à rentabilidade, não só ao volume.

### 16.4 Margem por Comissão (SEGURADORA × PRODUTO)
**O que é:** a `TAXA_COMISSAO_EFETIVA_%` no grão **seguradora × produto** — a comparação
justa. A visão por seguradora (16.2) sozinha engana: uma seguradora pode liderar o prêmio
só porque **concentra um produto de alta margem** (e há produtos que só existem nela).
**Como é calculado:** por `(SEGURADORA, PRODUTO)`: `QTD_CLIENTES`, `QTD_ITENS`,
`TOTAL_COMISSAO`, `TOTAL_PREMIO_LIQ`, `TAXA_COMISSAO_EFETIVA_%` (= comissão/prêmio),
`SHARE_PREMIO_%` e `SHARE_COMISSAO_%` (concentração da combinação no total), e
`N_SEGURADORAS_DO_PRODUTO` + `PRODUTO_EXCLUSIVO_SEGURADORA` (se aquele produto só é
vendido por aquela seguradora). Ordena por prêmio desc (blocos maiores no topo).
**Uso:** ver se a concentração de prêmio numa seguradora é de **alta margem** ou apesar de
baixa; identificar produto rentável exclusivo de um parceiro (dependência + negociação).
Visual: dispersão prêmio × taxa efetiva (bolha = comissão) em `12_margem_comissao_seg_produto.html`.

**Todas as visões de comissão usam o valor vigente (último ciclo)** —
`COMISSAO_ULTIMO_CICLO`/`PREMIO_ULTIMO_CICLO`, consistente com ABC e Market Share.

**Impactos de dados ruins (todas):**
- A **taxa efetiva** é uma razão: prêmio zerado/errado a explode ou zera; comissão > prêmio
  gera margem > 100% (o `DQ` já sinaliza esses casos). Some por grupo (não por linha) reduz
  o efeito de uma linha isolada, mas grupos pequenos ficam sensíveis — no grão
  seguradora×produto há mais células pequenas, leia a taxa junto de `QTD_ITENS`.
- Comissão usa a coluna **`COMISSÃO`** (não a `COMISSÃO TOTAL...`); divergência entre as
  duas afeta o número (fonte única em `get_comissao_col`).
- Nome de seguradora/produto inconsistente fragmenta a célula (mesma ressalva do Market Share).

---

## 17. Qualidade de Dados (DQ)

Arquivo `DQ_Reports.xlsx` — **só sinaliza, nunca corrige**. Regras:
- **Prêmio zerado/negativo** em apólice (CRÍTICO).
- **Comissão > prêmio** (CRÍTICO — operacionalmente impossível).
- **Inconsistência percentual:** comissão real diverge > 1% de `prêmio × %` (ALERTA).
- **Outliers de prêmio / de %** por (produto, seguradora), fora de média ± 3 desvios (ALERTA).
- **Grupos com amostra < 5** isolados (INFORMATIVO).
- **Duplicatas exatas** pela chave da linha (CRÍTICO).
- Aba `0_RESUMO_DQ` com contagem e severidade por regra; histórico acumulado em
  `dq_history.parquet` (tendência ao longo do tempo).

**Situações de uso:** fila de correção do back-office; medir se a qualidade melhora.

---

## 18. Tabela-resumo de impactos

| Problema na origem | Quem distorce | Como se manifesta | Onde detectar |
|---|---|---|---|
| CPF digitado errado | Rating, ABC, Status, Demografia | cliente dividido em dois; órfão | `DQ` (órfão), guardrail |
| Datas de vigência ausentes/invertidas | Status, Cohort, Snapshot, Renovações | produto cai como INATIVO; some das séries | `DQ` (vigência invertida) |
| Prêmio zerado/negativo/errado | ABC, Market Share, Cohort, Snapshot | ranking e classes mudam | `DQ` (prêmio, comissão > prêmio) |
| Duplicata de linha | ABC, Market Share, somas | prêmio inflado | `DQ` (duplicatas) |
| Produto não mapeado | Tipo de vigência, Rating | tipo INDEFINIDO; rating menor | `DQ` (produto não mapeado) |
| Seguradora com nome inconsistente | Market Share | share fragmentado | inspeção do lastro |
| Cadastro filtrado por categoria | Demografia, Mix, Conversão | população descasada; órfãos altos | guardrail (taxa de órfãos) |
| Janela por `INÍCIO DE VIGÊNCIA` (2024+) | Cohort, Snapshot, somas, Win-Back | 1ª safra inflada; somas da janela | guardrail (janela), `run_context` |
| Acento `CARACTERISTICA`/`CARACTERÍSTICA` | Mix, Demografia | join falha entre bases | inspeção do cruzamento (vale o do cadastro) |
| Comissão errada / coluna trocada | ABC Comissão, Margem, Market Share Comissão | taxa efetiva e ranking de margem distorcidos | `DQ` (comissão > prêmio, inconsistência %) |

> Para **conferir** qualquer um desses números registro a registro, use o `GUIA_AUDITORIA.md`.
