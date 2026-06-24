# ARCHITECTURE — reports_corretora

> Arquitetura resumida + **avaliação do motor de recomendações** (seção 3). Nomes de
> código em inglês; explicações em português. Para o roadmap de evolução (DuckDB,
> orquestração, app), ver `docs/EVOLUCAO_PLATAFORMA.md`.

## 1. Fluxo do pipeline (monolítico — `Main.py`)

```
data/raw/ (2 Excel) → load_data (carimba ID_LINHA) → prepare_cadastro / prepare_producao
  → generate_client_insights (motor: status do produto, ciclo de vigência, rating)
  → build_run_context (guardrails) → builders (analytics / operacional / marketing)
  → DQ + auditoria → exporta SEGMENTADO por público
        → outputs/{comercial,operacional,marketing}/  + outputs/index.html
scripts/build_warehouse.py → outputs/reports.duckdb (views SQL sobre os Parquet)
```

Decisão: **mantém-se monolítico** (volume ~5k linhas; simples e idempotente). Funções são
puras (DataFrame→DataFrame).

## 2. Módulos (`src/`)

| Módulo | Papel |
|---|---|
| `functions.py` | Motor: `get_product_status`, `calculate_rating`, `flag_last_cycle`, `build_cycle_grain`, saneamento de apólice. |
| `analytics.py` | Builders COMERCIAIS (ABC, cross-sell, market share, renovações, win-back, margens, `build_producer_performance`...). |
| `operacional.py` | Builders de QUALIDADE/processo (completude, status×situação, DQ1/DQ2/DQ3, acionabilidade). |
| `marketing.py` | Builders de MARKETING (base cliente×prospect + demografia). |
| `data_quality_advanced.py` | Testes de DQ (prêmio zerado, comissão>prêmio, outliers, duplicatas). Só sinaliza. |
| `report_html.py` | Relatórios HTML (Plotly) + **insights/recommendations** + portais. |
| `audit.py` | Workbooks de auditoria **Agregado \| Lastro** (rastreabilidade até a linha bruta). |
| `excel_report.py` / `persistence.py` | Excel formatado / Parquet + histórico DQ. |
| `parameters.py` / `utils.py` | Mapa produto→vigência, produtores internos/aliases; paths/helpers. |

## 3. Motor de recomendações — COMO FUNCIONA (avaliação honesta)

**Não existe LLM em tempo de execução nem modelo de ML.** Cada relatório HTML
(`_chart_*` em `report_html.py`) devolve duas listas de texto: `insights` e
`recommendations`. O comportamento é **determinístico e baseado em regras/heurísticas
escritas no código** (foram authored uma vez durante o desenvolvimento; rodam sempre igual).

### 3.1 Insights → DINÂMICOS (dirigidos pelos dados)
São f-strings que **interpolam agregados calculados na hora**: contagens, %, maior/menor
entidade, nomes, médias. Ex.: "Maior produtor: **X** (N itens, P% do total)".
➡️ **Mudam totalmente com uma base diferente** — refletem os números daquela base.

### 3.2 Recommendations → HÍBRIDO (texto fixo + valores/condições dos dados)
O **vocabulário de conselhos é fixo** (templates escritos no código), mas com 2 camadas
de dinamismo:
- **Valores interpolados:** ex. "Priorizar contato com os **N** cooperados Classe A
  (ticket médio **R$ X**)" — N e X vêm dos dados.
- **Recomendações condicionais (regra por threshold):** algumas só aparecem se o dado
  cruzar um limite. Ex.: market share só emite *"diversificar parceiros"* **se** a
  concentração top-3 > 70%; o mix só sugere foco numa especialidade **se** houver
  oportunidade detectada.

### 3.3 "Se eu rodar uma base totalmente diferente, as recomendações mudam?"
- **Os números dentro das recomendações: SIM** (recalculados).
- **Quais recomendações aparecem: PARCIALMENTE** — as condicionais ligam/desligam conforme
  os thresholds dos novos dados.
- **O texto/conselho em si: NÃO** — é um catálogo fixo de "playbook" por tipo de análise.
  Não é gerado nem aprendido a partir dos dados; é a experiência de negócio codificada.

### 3.4 O que É genuinamente data-driven (não confundir com "recomendações")
O **motor de regras** é 100% determinístico sobre os dados e muda com qualquer base:
`get_product_status` (vigência), `calculate_rating` (1–5★), `flag_last_cycle`,
detectores DQ1/DQ2/DQ3. Esses produzem **status/rating/flags**, não conselhos textuais.

### 3.5 Resumo executivo
| Camada | Dirigida por dados? | Muda com outra base? |
|---|---|---|
| Métricas/visões (números, gráficos) | ✅ Sim | ✅ Totalmente |
| Insights (texto) | ✅ Sim (interpola dados) | ✅ Totalmente |
| Recommendations (texto) | ⚠️ Parcial (valores + thresholds) | ⚠️ Números e quais aparecem mudam; **o conselho é fixo** |
| Status/Rating/DQ (motor de regras) | ✅ Sim (regras determinísticas) | ✅ Totalmente |

➡️ **Conclusão:** é um sistema de BI dirigido por dados com uma **camada de recomendação
heurística (rule-based), não um motor de recomendação de ML.** Para recomendações
verdadeiramente dinâmicas/personalizadas (ex.: *next-best-action* por segmento, modelo de
propensão), seria uma evolução futura — hoje **não** existe e não está no escopo.

## 4. Padrão para adicionar uma nova visão (reaproveitar, não reinventar)
1. `build_*` em `analytics.py` / `operacional.py` / `marketing.py` (função pura).
2. `_chart_*` em `report_html.py` + registrar na lista `visuals` (com o público `com`/`oper`/`mkt`).
3. Aba no workbook + tabela no Parquet em `Main.py`.
4. `audit_*` (Agregado|Lastro) roteado para o `*_AUDIT_DIR` do público.
5. Formatar (`black`/`isort`) e rodar com `--input-dir data/exemplo --force`.

## 5. Camadas de dados e enquadramento arquitetural (medallion / *lakehouse-lite*)

> Dois eixos **ortogonais**, que não devem ser confundidos: **arquitetura de armazenamento**
> (onde/como o dado mora — *data lake* / *data warehouse* / *lakehouse*) e **modelagem**
> (formato das tabelas — *flat* / normalizado / dimensional). Usar tabelas *flat* é decisão
> de modelagem, **não** caracteriza um *data lake*.

### 5.1 Camadas (medallion)
O pipeline materializa, conceitualmente, as três zonas do padrão *medallion*:
- **Bronze** — linhas brutas atômicas com âncora de origem (`producao_grain`,
  `ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`).
- **Silver** — saneado/conformado: `df_prod_status` (grão produto×cooperado), grão de ciclo,
  flags de último ciclo/contato.
- **Gold** — *marts* por público (as visões comerciais, operacionais e de marketing) +
  `producao_enriquecida` (fato denormalizado para BI).

### 5.2 Enquadramento: *lakehouse-lite* local (não é *data lake*, não é *lakehouse* pleno)
A solução grava em **Parquet** (formato aberto, colunar) consultado por **DuckDB** (engine
SQL **desacoplada** do storage), com **linhagem** ponta a ponta. Isso é um **lakehouse-lite
local**: formato aberto + SQL + linhagem sobre camadas medallion. Mas **Parquet sozinho não
faz um lake nem um lakehouse**:
- **Não é *data lake*:** sem *object storage*, sem zona *raw* multiformato, sem catálogo,
  carga única (sem acúmulo histórico além do `dq_history`).
- **Não é *lakehouse* pleno:** falta o item que define um lakehouse — uma **table format
  transacional** (Delta Lake / Apache Iceberg / Apache Hudi) que adicione **ACID**,
  ***time travel*** (histórico/SCD) e **MERGE** sobre os Parquet. Hoje os Parquet são
  arquivos sobrescritos a cada execução.

### 5.3 Decisão (simplicidade) e evolução mínima
Dado o volume (~5k linhas) e o objetivo de POC/TCC, **não** se adota Spark, *object storage*
ou cluster — seria desproporcional. A evolução para *lakehouse* pleno (adotar **uma** table
format em **um** mart, como PoC de ACID/*time travel*) é tratada como **trabalho futuro
opcional** — ver `docs/EVOLUCAO_PLATAFORMA.md`. A modelagem dimensional (*star schema*
conceitual) está em `docs/MODELAGEM_DIMENSIONAL.md`; o dicionário de dados em
`docs/DICIONARIO_DE_DADOS.md`.

> Referência: ARMBRUST, M. et al. *Lakehouse: A New Generation of Open Platforms…*, CIDR
> 2021; arquitetura *medallion* (Databricks).
