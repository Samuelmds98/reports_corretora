# Changelog — Raio X Cooperados

Registro das fases de implementação, decisões arquiteturais e desvios do plano original.
Ordenado do mais recente para o mais antigo.

---

## [3º track: MARKETING (base/mercado: cliente × prospect + demografia)] — Implementado ✓

**Motivação (dado real):** o Comercial é construído sobre o grão de PRODUÇÃO, então os
**68% da base que são prospects** (cooperados que nunca compraram) ficavam **invisíveis**.
O 3º track olha a base INTEIRA de cadastro.

**`src/marketing.py`** (não-monetário; 1 linha por cooperado): `build_marketing_base`
(lastro: status ATIVO/INATIVO/PROSPECT + demografia), `build_base_status`,
`build_specialty_distribution` (cliente × prospect), `build_birth_decade`,
`build_age_bands` (Até 40 / 41 a 59 / 60+).

**Saídas (`outputs/marketing/`):** `Marketing_RaioX.xlsx` (5 abas) + 5 HTML (status,
especialidade, década, faixa etária, **histograma de idade**) + portal + parquet + 4
workbooks de auditoria. `build_all_html_reports` roteia 3 públicos (`com`/`oper`/`mkt`);
o índice central linka os **3 painéis**. Warehouse DuckDB ganha o schema `marketing.*` +
`gold.oportunidade_especialidade`.

---

## [Report HTML de Qualidade (DQ) + rodapé de auditoria em todos os HTMLs] — Implementado ✓

- **Novo HTML `16_qualidade_dados_dq.html`** (track operacional): surfacing dos testes de
  qualidade que antes só existiam no Excel — prêmio zerado/negativo, comissão > prêmio,
  inconsistência %, outliers, duplicatas. Mostra a **visão agregada** (ocorrências e
  severidade por regra, vindas de `build_dq_summary`); o rodapé linka o registro-a-registro
  em `DQ_Raio_X_Cooperados.xlsx`.
- **Bloco de rodapé generalizado** (`_audit_block`): além do `../auditoria/<wb>.xlsx`
  (lastro das visões comerciais), aceita link customizado para o XLSX detalhado. Agora
  **todos os HTMLs têm rodapé de auditoria**: comerciais → workbook de lastro; operacionais
  → `Operacional_Qualidade_RaioX.xlsx`; DQ → `DQ_Raio_X_Cooperados.xlsx`. O único sem link
  antes (`04_cross_sell`) passou a apontar para `Calculadora_Produtos.xlsx`.

**Produtor:**
- **Conta interna/casa separada** (`parameters.PRODUTOR_INTERNO_KEYWORDS`, ex.: UNIMED) —
  flag `EH_INTERNO`; sai do ranking e da concentração (share recalculado só entre externos).
- **Merge de produtor duplicado** (`PRODUTOR_ALIASES` + `normalize_producer`, aplicado em
  `prepare_producao`): mesmo produtor com 2 cadastros (antigo×novo) vira um só (ex.:
  LIDUINA ROMERO → LIDUINA MARIA BELMINO ROMERO).
- **Taxa de renovação JUSTA** (`TAXA_RENOVACAO_RENOVAVEL_%`): só de produtos RENOVÁVEIS —
  tira o viés de mix (recorrente não "renova" como apólice anual). Vira a métrica de
  retenção exibida no HTML.

**MVP de plataforma — DuckDB** (`scripts/build_warehouse.py`): projeta `outputs/raio_x.duckdb`
com 1 view por Parquet (schemas `comercial.*`/`operacional.*`) + views `gold.*`
(`kpis`, `produtores_externos`, `renovacoes_por_urgencia`, `qualidade_resumo`,
`margem_seg_produto_top`). SQL ad-hoc via `--sql`. Cada gold view é isolada (fonte ausente
só pula aquela). `duckdb` adicionado ao `requirements.txt`. Monolito mantido; evolução
detalhada em `docs/EVOLUCAO_PLATAFORMA.md`.

---

## [Performance de Produtor + avaliação de evolução p/ plataforma] — Implementado ✓

**Performance de Produtor** (`analytics.build_producer_performance`) — dimensão de força
de vendas, antes inexistente. Por PRODUTOR: carteira (clientes/itens/produtos/seguradoras),
`PRODUTO_PRINCIPAL`, originação (novos × renovações), **taxa de renovação** (`Renovada` ÷
`Renovada`+`Vencida`) e concentração Pareto (`SHARE_ITENS_%`/`SHARE_ACUM_%`). Aba 18 do
workbook comercial + parquet `performance_produtor` + auditoria `Performance_Produtor.xlsx`
+ HTML `16_performance_produtor` (volume × retenção). Não-monetário (contagens).

**Avaliação de evolução para plataforma de inteligência de dados** (`docs/EVOLUCAO_PLATAFORMA.md`):
roadmap MVP/POC reaproveitando os builders como transforms — DuckDB (camada de query única),
Prefect (orquestração), pandera (contratos na ingestão), Streamlit (consumo interativo por
público), camada semântica única de métricas. Sem acesso/segurança/performance (escopo POC).

---

## [Acionabilidade (2 cortes) + portais de navegação + limpeza] — Implementado ✓

**Acionabilidade / contatabilidade** (`src/operacional.py`):
- `build_contact_lookup` — flags por CPF do cadastro: `TEM_TELEFONE`, `TEM_EMAIL`,
  `ACEITA_EMAIL` (consentimento), `CONTATAVEL` (telefone OU e-mail), `EMAIL_ACIONAVEL`
  (e-mail E consentimento).
- **Corte (a) — por cliente na lista de ação** (`add_contact_flags`): a Agenda de
  Renovações e o Win-Back ganham as flags → lista *executável* (separa quem dá pra
  contatar de quem está bloqueado por cadastro). O HTML da agenda passa a dizer quantas
  estão sem canal (e quantas já nos 30 dias).
- **Corte (b) — agregado por produtor** (`build_contactability_by_producer`): % de
  clientes com contato por PRODUTOR (cliente atribuído ao produtor da apólice N/R mais
  recente). Aba `7_Acionabilidade_Produtor` + parquet + HTML `15_acionabilidade_produtor`.

**Portais de navegação (HTML):** índice por público (`comercial/visuals/index.html`,
`operacional/visuals/index.html`) em cards + **índice central** `outputs/index.html`
linkando os dois painéis (gerados da mesma lista de visuais, se mantêm sozinhos).

**Limpeza:** removidas as pastas superseded `outputs/{reports,visuals,parquet,auditoria}`;
`utils.py` não recria mais `outputs/reports`. Arquitetura atualizada no `CLAUDE.md`.

---

## [Marco: segmentação Comercial × Operacional + métricas de qualidade/processo] — Implementado ✓

Após a apresentação inicial, o gerente pediu **separação clara** entre artefatos
comerciais e operacionais/qualidade — o projeto passa a servir **2 públicos**.

**Segmentação física dos outputs (2 árvores):**
- `outputs/comercial/` — `Comercial_RaioX.xlsx` (21 abas) + `visuals/` + `parquet/` +
  `auditoria/`. Vendas/CRM/margens.
- `outputs/operacional/` — `Operacional_Qualidade_RaioX.xlsx` (7 abas) + `visuals/` +
  `parquet/` + `DQ_Raio_X_Cooperados.xlsx` + `Log_Apolices_Conflito` + `dq_history`.
- `build_all_html_reports` agora roteia cada HTML por público (campo `com`/`oper`);
  parquet e auditoria também segmentados. Substitui o antigo `Mapping_Comercial_*` +
  `Raio_X_Qualitativo` (cujas abas foram redistribuídas).

**Novas métricas operacionais/qualidade (`src/operacional.py`):**
- `build_origem_cadastro` — migrado × orgânico por ano (`USUÁRIO DA INCLUSÃO = MIGRACAO`);
  ~40% da base é carga histórica e enviesa as séries de venda.
- `build_status_vs_situacao` — matriz de concordância `STATUS_PRODUTO` (motor) ×
  `SITUAÇÃO` (nativa). Divergências = candidatos a problema de cadastro.
- `build_active_with_cancellation` (DQ1) — apólices `Ativa`/`Renovada` com endosso de
  cancelamento vigente (o status do documento esconde o cancelamento efetivo).
- `build_renewal_as_new` (DQ2) — provável renovação cadastrada como `N` sem linkar a
  antiga (vira `Vencida`); heurística por proximidade de datas + raiz de apólice diferente.
  9 casos nos dados reais.
- `build_situacao_ativa_vencida` (DQ3) — apólice `SITUAÇÃO = Ativa` com `TÉRMINO < hoje`
  (status defasado). 220 casos nos dados reais. Semântica de `SITUAÇÃO` confirmada com o
  negócio: só `Ativa` é vigente; `Renovada` = linha substituída (inativa) → concordância
  motor×situação subiu de 78,8% para 89,4%.
- HTMLs operacionais: `13_origem_cadastro`, `14_status_vs_situacao` (+ completude movida).

**Aba Conferência removida dos workbooks de auditoria.** Decisão do negócio: Agregado +
Lastro já atendem (a conferência checava o próprio caminho). O check de fechamento entre
motor e auditoria virou um **aviso de console** (só fala se houver divergência) — mantém
a rede de segurança sem poluir o artefato.

**Caveats de domínio registrados** em `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md`:
`SITUAÇÃO` = status do documento (≠ apólice efetiva); renovação-como-novo quebra o link.

---

## [Último ciclo em todas as visões de carteira + Margem Seguradora×Produto] — Implementado ✓

Extensão da correção multi-ciclo (abaixo) para as demais visões de valor + nova visão 19.

**Último ciclo nas visões de carteira vigente** (antes somavam `SOMA_*` histórico):
- ABC (3), Market Share (6), ABC-Comissão (16), Margem-Seguradora (17) e Margem-Produto
  (18) passam a somar `PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO`. Nomes de saída
  inalterados (`TOTAL_PREMIO_LIQ`/`TOTAL_COMISSAO`) → HTML/Power BI seguem iguais.
- Cohort (5) e Originação (14/15) **mantidos** (janelados por `INÍCIO DE VIGÊNCIA` de
  propósito); `Calculadora` (7) mantém `SOMA_*` + colunas de último ciclo.
- Auditorias afetadas filtram `EH_ULTIMO_CICLO` (helper `_only_last_cycle`) para fechar.

**Snapshot Mensal (13) — grão de ciclo (`functions.build_cycle_grain`):** o snapshot
inflava o prêmio repetindo `SOMA_*` em todos os meses de todas as vigências. Agora explode
um **grão de ciclo** (uma linha por ciclo de vigência, com a janela e o valor daquele
ciclo). Conserta o prêmio **sem perder a contagem histórica** (cada ciclo conta nos seus
meses; cliente ativo em 2024 segue ativo em 2024). Alimenta `build_monthly_active_snapshot`
e `build_snapshot_grain` sem alterá-las (mesmas colunas, várias linhas por produto).

**Nova Visão 19 — Margem por SEGURADORA × PRODUTO**
(`analytics.build_commission_margin_seguradora_produto`): taxa de comissão efetiva no grão
seguradora×produto + `SHARE_PREMIO_%`/`SHARE_COMISSAO_%` e
`N_SEGURADORAS_DO_PRODUTO`/`PRODUTO_EXCLUSIVO_SEGURADORA`. Responde "a seguradora é grande
em prêmio por concentrar produto de alta margem?". Inclui aba 19, parquet
`margem_comissao_seg_produto`, workbook `Margem_Comissao_Seg_Produto.xlsx` (auditoria) e
HTML `12_margem_comissao_seg_produto.html` (dispersão prêmio × taxa efetiva, bolha = comissão).

---

## [Correção: prêmio/comissão da Agenda de Renovações] — Implementado ✓

**Problema:** a Agenda de Renovações somava prêmio/comissão de **todos os ciclos** de
uma apólice renovável. Para uma apólice vigente 2024→2025 e renovada 2025→2026, o
"prêmio em risco" vinha inflado (somava os dois anos), pois `process_product_status`
agrega por `(CPF, SEGURADORA, PRODUTO)` e usa `.sum()` sobre todas as linhas N/R.

**Correção (valor vigente = só o último ciclo):**
- **`functions.flag_last_cycle`** — marca em cada linha bruta `EH_ULTIMO_CICLO`. Por
  `(CPF, SEGURADORA, PRODUTO, RAIZ_APÓLICE)`, o ciclo vigente começa no MAIOR
  `INÍCIO DE VIGÊNCIA` entre as linhas N/R; linhas com início `>=` esse valor (renovação
  vigente + endossos EN/ER) entram, ciclos anteriores ficam de fora. `RAIZ_APÓLICE`
  mantém apólices distintas (ex.: 2 carros) como ciclos independentes. Produtos só-FATURA
  (recorrente) contam todas as linhas — cada fatura é um pagamento distinto.
- **`process_product_status`** ganha `PREMIO_ULTIMO_CICLO`, `COMISSAO_ULTIMO_CICLO` e
  `INICIO_ULTIMO_CICLO`. `SOMA_PREMIO_LIQ`/`SOMA_COMISSAO` (histórico) **permanecem**
  para ABC/Market Share/Snapshot (que não foram alterados).
- **`build_renewal_agenda`** passa a exibir os valores do último ciclo; HTML
  `_chart_renewal` e `audit_renovacoes` (lastro filtrado por `EH_ULTIMO_CICLO`) ajustados
  para a conferência fechar. `Main` carimba a flag em `df_prod` (auditoria + Parquet).

**Escopo inicial (estendido depois):** ABC, Market Share e Snapshot ainda usavam `SOMA_*`
histórico — corrigidos na entrada acima (último ciclo / grão de ciclo). Doc nova:
`docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md` (regras por produto + contratos de dados).

---

## [Sessão de Refatoração + TCC] — Implementado ✓

Bloco consolidado do que foi efetivamente construído nesta sessão. Ajusta o status
das Fases 5–8 abaixo (5 e 6 foram implementadas; 7 e 8 foram **substituídas** pela
abordagem de auditoria em Excel descrita aqui).

### Refatoração e otimização (base)
- **`get_product_status` O(n²) → O(1)** via `build_cancellation_index` (índice de
  cancelamentos CN/CR pré-computado) + helper `_is_cancelled`. Engine caiu de ~4s para ~2s.
- **DRY**: `get_comissao_col` e `load_excel` centralizados em `src/utils.py`;
  `_classifica_abc` e `format_produtos` extraídos; `extract_policy_root` com regex única.
- `src/excel_report.py` extraído do notebook; ambiente `.venv`; `t.py` descartado;
  `quality.py` integrado ao pipeline (DQ na aba 8 + log na 9, depois migradas p/ arquivo DQ).

### Guardrails, idempotência e janelamento
- **`src/guardrails.py`** (`build_run_context`): mede janela temporal (por `INÍCIO DE
  VIGÊNCIA`), taxa de órfãos e nº de categorias; só alerta + persiste `run_context.parquet`.
- **Guard de idempotência por hash** do input (pula execução se nada mudou; `--force` força).
- **`build_origination_sums`**: ABC e Market Share janelados por `INÍCIO DE VIGÊNCIA ≥ 2025`
  ("originação no período", não receita reconhecida) → abas 14/15.

### Rastreabilidade total (substitui Fases 7 e 8 planejadas)
- **Âncora `ID_LINHA`** carimbada na **leitura** (`_stamp_origin` em `load_data`), não em
  `prepare_producao` — assim sobrevive ao dedup/saneamento. Inclui `ARQUIVO_ORIGEM` e
  `LINHA_ORIGEM` (linha exata no Excel bruto), tanto para produção quanto cadastro.
- **`src/audit.py`** — workbooks de auditoria por análise em `outputs/auditoria/` (14 arquivos),
  cada um com abas **Agregado | Lastro | Conferência** (prova de fechamento: soma do lastro
  == número agregado, zero divergências). Objetivo: auditoria em Excel para o usuário final.
- **Parquets granulares** para Power BI: `producao_grain` (bruto com `ID_LINHA`),
  `producao_enriquecida` (produto × cooperado × perfil + tipo), `snapshot_grain` (produto × mês).
- **Ref de auditoria embutida nos HTML** (seção linkando o workbook de lastro).
- **Resiliência a arquivo aberto**: gravações Excel pulam com aviso `[BLOQUEADO]` e a execução
  não é marcada como concluída (próxima rodada regenera sem `--force`).

### Métricas na ótica da COMISSÃO (abas 16–18)
- `build_abc_curve_comissao` (ABC por comissão), `build_partner_performance_comissao`
  (market share por comissão + **taxa de comissão efetiva** = comissão/prêmio por seguradora),
  `build_commission_margin_produto` (margem por produto).
- Cada uma com aba, parquet, workbook de auditoria e HTML (08/09).
- **Insight:** a concentração/margem por comissão diverge da de prêmio (as taxas variam) —
  expõe parceiros/produtos de alto volume e baixa margem.

### Raio X Qualitativo (não-monetário — abordagem inicial ao gerente)
Motivação: confiabilidade dos valores (prêmio/comissão) é baixa; a 1ª entrega ao gerente
usa só dados confiáveis (especialidade, produto, datas, contagens). O Rating e o Status já
são não-monetários (contagens), então também entram.
- **6 funções em `src/analytics.py`** → arquivo separado `outputs/reports/Raio_X_Qualitativo.xlsx`:
  `build_cadastro_completeness` (diagnóstico de preenchimento por campo + tier de confiabilidade),
  `build_product_distribution` (mix por contagem), `build_partner_share_by_count` (market share
  por contagem, sem prêmio), `build_portfolio_depth` (profundidade + mono-produto + gaps de
  cobertura), `build_cancellation_rate` (churn estrutural CN/CR ÷ apólices),
  `build_specialty_gaps` (cross-sell gaps por especialidade).
- 6 Parquets `qual_*`, 3 workbooks de auditoria (`Qual_*`), 2 HTMLs (10 completude / 11 gaps).
- Completude calculada sobre o cadastro **bruto** (antes do preenchimento de nulos).
- Achados (base real): ~70% dos produtores são mono-produto; `QTDE FILHOS`/`QTDE VEICS` são
  constantes (inúteis); geografia/estado civil ~40–54% preenchidos.

### Documentação e TCC
- **Guias em `docs/`** (movidos de `outputs/`, que é ignorado pelo git): `GUIA_AUDITORIA.md`,
  `GUIA_METRICAS.md`, `GUIA_IMPLEMENTACAO_POWERBI.md`, `GUIA_METRICAS_QUALITATIVAS.md`,
  `ANALISES_NAO_MONETARIAS.md` (levantamento), `ARTEFATOS_TCC.md`. (O próprio `CHANGELOG.md`
  também foi para `docs/`.)
- **`scripts/gerar_dados_exemplo.py`** → `data/exemplo/`: cópia anonimizada/randomizada dos 2
  Excel (mesma estrutura), reprodutível por seed, com **furos de qualidade propositais** para
  exercitar o DQ (prêmio zerado, comissão>prêmio, inconsistência %, outliers, duplicatas,
  órfãos, produto não mapeado, idade implausível, vigência invertida).
- **`Main.py --input-dir`**: roda sobre qualquer diretório de entrada (ex.: `data/exemplo`)
  sem sobrescrever `data/raw`; checagem amigável se os arquivos não existirem.

### Inventário de saídas (estado atual)
- Relatório principal: **16 abas** (1–7, 10–18) · `DQ_Raio_X_Cooperados.xlsx` (10 abas) ·
  `Raio_X_Qualitativo.xlsx` (6 abas)
- **17** workbooks de auditoria · **11** HTMLs · **26** Parquets · histórico `dq_history.parquet`

---

## [Fase 8] Grain Tables para Power BI — Substituído ⤳

> **Status real:** o plano original (grain `producao_bruta` + `sequencia_pares` para replicar
> métricas em DAX) foi **substituído** pela abordagem de **auditoria em Excel** (ver bloco no
> topo): o objetivo do usuário era rastreabilidade fácil para o usuário final, não DAX.
> **Implementado de fato:** `producao_grain`, `producao_enriquecida` e `snapshot_grain` em
> Parquet (granularidade para o Power BI), mas **sem** `producao_bruta`/`sequencia_pares`
> (estes dependiam da Fase 7, também substituída).

**Plano:** `outputs/PLANO_IMPLEMENTACAO_GRAIN_POWERBI.md`

### O que será feito
- `build_producao_enriquecida` → `producao_enriquecida.parquet`: grain central
  (produto × cooperado + atributos de perfil + TIPO_PRODUTO). Fonte para ~90% das métricas em DAX.
- `build_snapshot_grain` → `snapshot_grain.parquet`: explosão M-to-N pré-computada para
  o snapshot mensal — PBI não consegue replicar essa lógica de data range em DAX.
- `producao_bruta.parquet`: `df_prod_auditavel` exportado como Parquet (grain transacional com ID_LINHA).
- `sequencia_pares.parquet`: pares de transição antes do crosstab — permite auditar
  quais cooperados fizeram a transição A → B.
- `build_product_transition_matrix` passa a retornar `(matrix_counts, matrix_pct, df_pairs)`.

### Decisões tomadas
- **Agregados Python mantidos** — os Parquets `curva_abc`, `market_share` etc. continuam existindo
  para alimentar os visuais HTML Python. As grains são adicionais, não substitutas.
- **`snapshot_grain` pré-computado em Python** — a explosão M-to-N por data range não tem
  equivalente simples em DAX/Power Query. Exportar pré-processado é mais seguro.
- **Sem star schema no PBI** — cada Parquet é uma flat table independente. Joins e relações
  são feitos via filtros e slicers, não via modelagem de dados.
- **Cadeia de auditoria**: visual agregado → `producao_enriquecida` (produto×cooperado) →
  `producao_bruta` (transações com ID_LINHA) → linha exata no Excel bruto.

---

## [Fase 7] Analytics RevOps — Substituído ⤳

> **Status real:** `build_product_survival` e `build_product_transition_matrix` (sobrevivência
> e matriz de transição) **não foram implementados**. O `ID_LINHA` foi implementado, porém na
> **leitura** (`_stamp_origin` em `load_data`) e não em `prepare_producao` — colocá-lo na leitura
> garante que sobreviva ao dedup do cadastro e ao saneamento de raízes. O esforço foi redirecionado
> para a **rastreabilidade total via workbooks de auditoria** (ver bloco no topo).

**Plano:** `outputs/PLANO_IMPLEMENTACAO_REVOPS_ANALYTICS.md`

### O que será feito
- **`ID_LINHA` em `prepare_producao`** (1 linha) → propaga para `df_prod_auditavel` automaticamente.
  Permite rastrear da métrica agregada → aba 7 (produto status) → aba 9 DQ (transacional) →
  linha exata no Excel bruto `RptAnaliseProducao.xlsx`. Verificado: **não estava implementado**.
- `build_product_survival(df_prod_status)` → aba `14_Sobrevivencia_Produto` (LARANJA)
  - Taxa de cancelamento, tempo mediano de vida e classificação de risco por (PRODUTO, SEGURADORA)
  - Identifica combos com alto churn e cancamento precoce para ação de retenção
- `build_product_transition_matrix(df_prod_status)` → aba `15_Sequencia_Produto` (VERDE)
  - Matriz de transição temporal: dado que o cliente tem produto A, qual produto adquire em seguida?
  - Apenas pares com intervalo > 30 dias (evita aquisições simultâneas)
  - Normalizada por linha (%) para leitura direta como probabilidade de cross-sell
- 2 novos visuais HTML: `08_sobrevivencia_produto.html` e `09_sequencia_produtos.html`
- 2 novos Parquets: `sobrevivencia_produto.parquet` e `sequencia_produto.parquet`

### Decisões tomadas
- **`ID_LINHA` adicionado em `prepare_producao`** via `df_prod.insert(0, "ID_LINHA", df_prod.index)`.
  Propaga automaticamente para `df_prod_auditavel` (cópia de `df_prod`). Não propaga para
  `df_prod_status` (é um agregado por produto — não tem rastreabilidade linha a linha por design).
  Cadeia de auditoria: métrica → aba 7 → ID_LINHA na aba 9 DQ → Excel bruto.
- **Sem biblioteca externa de sobrevivência (sem lifelines)** — implementado com pandas puro.
  Kaplan-Meier formal seria mais preciso com right-censoring, mas percentis + taxa de cancelamento
  respondem a pergunta de negócio sem adicionar dependência.
- **Threshold de 30 dias para transição** — pares com `DIAS_ATE_PROXIMO < 30` são tratados
  como aquisição simultânea (não contam como sequência). Reduzir para 7 dias se a base
  tiver poucos clientes multi-produto com datas distintas.
- **Aba 15 exporta apenas `matrix_pct`** — a matriz de contagens brutas vai para Parquet
  mas não para o Excel, mantendo o relatório principal legível para gestão.

---

## [Fase 6] Persistência Parquet + Histórico DQ — Implementado ✓

> **Status real:** implementado conforme o plano. `pyarrow` adicionado ao `requirements.txt`.
> O conjunto de Parquets cresceu além das 11 tabelas originais (hoje 20, incluindo as visões
> janeladas, de comissão e os grãos granulares).

**Plano:** `outputs/PLANO_IMPLEMENTACAO_PERSISTENCIA.md`

### O que será feito
- Novo módulo `src/persistence.py` com duas funções:
  - `export_parquet_tables` — exporta 11 tabelas analíticas para `outputs/parquet/`
    (sobrescritas a cada execução, representam o estado atual)
  - `append_dq_history` — acumula o resumo de qualidade de cada execução em
    `outputs/dq_history.parquet` (nunca sobrescrito, cresce com o tempo)
- Power BI consome os Parquets via Get Data nativo (sem driver adicional)

### Decisões tomadas
- **Parquet em vez de SQLite/DuckDB** — Power BI lê Parquet nativamente sem
  instalação de driver ODBC. DuckDB fica como upgrade opcional no futuro caso
  seja necessária capacidade de SQL direto no Power BI.
- **Acumulação de histórico por `read → concat → write`** — padrão simples sem
  dependência de banco de dados. Deduplicação por `(RUN_DATE, REGRA_DQ)` com
  `keep="last"` garante que múltiplas execuções no mesmo dia não inflam o histórico.
- **`build_dq_report` passa a retornar `(DQ_FILE, df_resumo)`** — mudança mínima
  na assinatura para expor o DataFrame de resumo ao `run_pipeline()` sem duplicar lógica.

---

## [Fase 5] Visuais HTML com Storytelling — Implementado ✓

> **Status real:** implementado. Hoje são **9** HTMLs (os 7 originais + `08_curva_abc_comissao`
> e `09_margem_comissao`). **Desvio importante:** a versão do Plotly.js no CDN deixou de ser
> fixa em `2.27` e passou a ser derivada de `get_plotlyjs_version()` — a 2.27 não decodifica os
> typed arrays (base64) gerados pelo Plotly 6.x, o que corrompia os valores de prêmio no hover.

**Plano:** `outputs/PLANO_IMPLEMENTACAO_VISUALS_HTML.md`

### O que será feito
- Novo módulo `src/report_html.py`
- 7 arquivos HTML auto-contidos em `outputs/visuals/`, um por análise:
  Curva ABC, Market Share, Mix por Especialidade, Cross-sell, Agenda de Renovações,
  Win-Back e Snapshot Mensal
- Cada HTML: gráfico Plotly interativo + seções de Insights e Recomendações
  geradas dinamicamente dos dados reais
- Consumo direto dos DataFrames já em memória — zero I/O extra

### Decisões tomadas
- **Visuais separados por análise, não um dashboard único** — o usuário abre
  um por um para contar o storytelling, não precisa de uma aplicação monolítica.
- **Plotly em vez de Altair** — interatividade nativa (hover/zoom) é valiosa
  numa apresentação executiva; Plotly + template Jinja2 oferece controle total
  do layout sem diferença de esforço em relação ao Altair para esse formato.
- **Plotly.js via CDN (não embutido)** — `include_plotlyjs=False` mantém
  arquivos leves; CDN fixa versão 2.27 para estabilidade.
- **Quarto descartado** — aesthetic avaliado como acadêmico, não adequado
  para apresentações executivas.
- **Observable Framework descartado** — solução mais visualmente polida, mas
  requer JavaScript e gera uma pasta `dist/` (não arquivo único). Mantido como
  referência para upgrade futuro se necessário.
- **Cada função `_chart_*` encapsulada em `try/except`** — erro em um visual
  não interrompe a geração dos demais nem o pipeline principal.

---

## [Fase 4] Módulo de Qualidade Avançada (DQ) — Implementado ✓

**Plano:** `outputs/PLANO_IMPLEMENTACAO_QUALIDADE_DQ.md`

### O que foi feito
- Novo módulo `src/data_quality_advanced.py` com 7 funções de detecção:
  - `detect_zero_negative_premio` — prêmio zerado ou negativo em apólices N/R
  - `detect_commission_exceeds_premio` — comissão maior que o prêmio (impossível)
  - `detect_percentage_inconsistency` — divergência entre percentual e comissão cadastrada
  - `detect_premio_outliers` — outliers de prêmio por (PRODUTO, SEGURADORA) via ±3σ
  - `detect_percentage_outliers` — outliers de percentual de comissão (mesma lógica)
  - `detect_exact_duplicates` — duplicatas exatas pela chave transacional
  - `build_dq_summary` — resumo executivo com severidade por regra
- Novo arquivo de saída: `outputs/reports/DQ_Raio_X_Cooperados.xlsx` (10 abas)
- Abas 8 e 9 migradas do relatório principal para o arquivo DQ
- Relatório principal passa a ser exclusivamente de negócio (abas 1–7 + 10–13)

### Decisões tomadas
- **Nenhuma correção de valor** — o pipeline apenas detecta e sinaliza.
  Toda coluna gerada é diagnóstico; nunca substitui o dado original.
- **Tolerância relativa de 1%** para inconsistência de percentual — evita
  falsos positivos em prêmios de magnitudes muito diferentes (1% de R$1.200
  ≠ 1% de R$50.000).
- **Grupos com menos de 5 registros isolados** em aba separada
  (`6_GRUPOS_AMOSTRA_INSUF`) — análise estatística com n < 5 é não confiável;
  não gerar flags de outlier nesses grupos.
- **Detecção de parcelamento removida** do escopo — não é possível distinguir
  de forma confiável "12 parcelas de R$100" de "12 registros de R$1.200"
  sem um âncora externo (o valor anual da apólice mãe). Registros desse tipo
  precisam de revisão humana com base em outros sinais.
- **Duas colunas de comissão** no dataset (`COMISSÃO` e
  `COMISSÃO TOTAL (CORRET + CO-CORRET)`): prioridade para `COMISSÃO` via
  `get_comissao_col` de `src/utils.py`. Pendente confirmação do negócio.

---

## [Fase 3] Novas Análises (Abas 10–13) — Implementado ✓

**Plano:** `outputs/PLANO_IMPLEMENTACAO_NOVAS_ANALISES.md`

### O que foi feito
- 4 novas funções adicionadas ao final de `src/analytics.py`
- 4 novas abas no relatório principal (10 a 13)

| Aba | Função | Descrição |
|---|---|---|
| 10 | `build_specialty_mix` | Penetração de produto por especialidade médica |
| 11 | `build_renewal_agenda` | Apólices renováveis vencendo em 90 dias |
| 12 | `build_winback_candidates` | Clientes inativos nos últimos 12 meses |
| 13 | `build_monthly_active_snapshot` | Snapshot M-to-N de clientes e prêmio por mês |

### Decisões tomadas e desvios
- **Aba 10 (Mix Especialidade) substituiu LTV** como primeira prioridade —
  LTV com dados de prêmio sem série histórica completa seria impreciso.
- **Aba 12 (Win-Back): filtro de rating removido** — o filtro original do plano
  (`RATING_ESTRELAS >= 2` para inativos) é logicamente impossível: `calculate_rating`
  deriva o rating dos produtos **ativos**, logo todo cliente INATIVO tem rating 0.
  A aba ficaria sempre vazia. Decisão: win-back agora é todo cliente inativo cujo
  último produto venceu nos últimos 12 meses, ordenado por `TOTAL_PREMIO_HISTORICO` desc.
- **Aba 13 (Snapshot Mensal): abordagem vetorizada** — o loop com `iterrows`
  seria lento para bases grandes. Implementado com `df.apply + pd.date_range + explode`
  para gerar a explosão M-to-N de forma vetorizada.

---

## [Fase 2] Expansão BI — Analytics Layer — Implementado ✓

**Plano original:** `outputs/implementation_plan.md`

### O que foi feito
- Criação de `src/analytics.py` com 5 funções de BI:
  - `build_demographics` — perfil demográfico com taxa de conversão por cluster
  - `build_abc_curve` — curva ABC/Pareto por prêmio líquido acumulado
  - `build_cross_sell_matrix` — matriz de co-posse de produtos (one-hot encoding)
  - `build_time_series_growth` — sazonalidade por safra de início de vigência
  - `build_partner_performance` — market share de seguradoras
- Substituição do notebook `06_cruzamento_cadastro_producao.ipynb` pelo `Main.py`
- Exportação multi-abas formatada via `src/excel_report.py`

### Decisões tomadas
- **Notebook 06 mantido apenas como referência histórica** — `Main.py` é o
  ponto de entrada oficial do pipeline.
- **`src/analytics.py` como camada separada** — funções puras de BI isoladas
  das regras de negócio em `functions.py`, seguindo o princípio de separação
  de responsabilidades.

---

## [Fase 1] Pipeline Principal — Implementado ✓

### O que foi feito
- `Main.py` como orquestrador central do pipeline
- Módulos core em `src/`:
  - `functions.py` — saneamento de CPF, extração de raiz de apólice, motor de
    status (`get_product_status`), rating 1–5★ (`calculate_rating`), demographics
  - `parameters.py` — `PRODUCT_TYPE_MAP` (28 produtos → RENOVÁVEL/RECORRENTE/TRANSACIONAL)
  - `quality.py` — auditoria linha a linha (`run_full_audit`)
  - `excel_report.py` — paleta corporativa e exportação formatada multi-abas
  - `utils.py` — paths, loaders, helpers
- Entrada: `data/raw/RptAnaliseProducao.xlsx` e `data/raw/RptClienteLista.xlsx`
- Saída: `outputs/reports/Mapping_Comercial_Cruzamento_Cadastro_Producao.xlsx`

### Regras de negócio centrais implementadas
- **Produto ativo**: RENOVÁVEL/TRANSACIONAL: `Início <= hoje <= Término` sem CN/CR;
  RECORRENTE: fatura nos últimos 90 dias
- **Cliente ativo**: ≥1 produto Renovável/Recorrente ativo, OU ≥1 Transacional
  ativo ou com vigência nos últimos 12 meses
- **Rating top-down** (5★ → 1★):
  - 5★ — recorrentes≥1 E renováveis≥2 E transacionais_12m≥1
  - 4★ — recorrentes≥1 E renováveis≥1 E transacionais_12m≥1
  - 3★ — categorias_distintas≥2
  - 2★ — produtos_ativos≥2 E categorias_distintas==1
  - 1★ — produtos_ativos==1

---

## Dívidas técnicas conhecidas

- **Duas colunas de comissão** (`COMISSÃO` vs `COMISSÃO TOTAL (CORRET + CO-CORRET)`) —
  centralizado em `get_comissao_col` com prioridade para `COMISSÃO`. Pendente
  confirmação de qual coluna é a correta para o negócio.
- **Inconsistência de acento** — `CARACTERISTICA` na produção (sem acento) vs
  `CARACTERÍSTICA` no cadastro (com acento). Tratar com cuidado em joins.
- **Sem testes automatizados** — candidatos a `pytest`: funções de rating,
  status de produto, extração de raiz, e as novas detecções de DQ.
- **`src/analise_temporal.py`** — usado apenas no notebook 05, não integrado
  ao `Main.py`. A lógica de série temporal foi reimplementada de forma simplificada
  em `build_time_series_growth` e `build_monthly_active_snapshot`.
- **Pasta `backup/`** — ignorar completamente. Não é contexto válido.
