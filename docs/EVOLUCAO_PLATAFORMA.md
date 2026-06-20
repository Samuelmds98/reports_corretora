# Evolução para Plataforma de Inteligência de Dados (MVP/POC)

> Avaliação de como evoluir o pipeline atual do "Raio X Cooperados" para uma **plataforma
> de inteligência de dados** da corretora. Escopo **MVP/POC**: foco em arquitetura e valor
> analítico, **sem** gestão de acessos, segurança ou tuning de performance. Aproveita ao
> máximo o que já existe.

## 1. Onde estamos (avaliação honesta)

**Já é mais maduro que a média de TCC.** O que hoje funciona como diferencial:
- **Motor de regras** puro e testável (`functions.py`: status, rating, ciclo de vigência).
- **Linhagem ponta-a-ponta** (`ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`) + workbooks de
  auditoria Agregado|Lastro → cada número rastreável até a linha bruta.
- **Qualidade como cidadão de 1ª classe** (DQ que só sinaliza, guardrails de contexto,
  detectores operacionais DQ1–DQ3, `dq_history`).
- **Saídas segmentadas por público** + Parquet pronto para BI + portais HTML.
- **Idempotência por hash** e resiliência a arquivo aberto.

**Limites que impedem de chamar de "plataforma" hoje:**
1. **Ingestão manual** — depende de alguém soltar 2 Excel em `data/raw/`. Sem agendamento,
   sem histórico de cargas, sem detecção de mudança de schema na origem.
2. **Camadas implícitas** — bronze/silver/gold existem só na memória do `Main.py`; não há
   uma camada de dados **persistida e consultável** (cada visão re-deriva do zero).
3. **Métrica definida em 3 lugares** — a mesma regra vive em `analytics.py` (Python), no
   `GUIA_IMPLEMENTACAO_POWERBI.md` (DAX) e implícita no Excel. Risco de divergência.
4. **Consumo estático** — HTML/Excel são fotografias; sem filtro/drill-down interativo nem
   consulta ad-hoc (“e se eu olhar só a especialidade X em 2025?”).
5. **Orquestração linear** — `python Main.py` é um monólito; sem DAG, retry por etapa,
   nem observabilidade de execução.

## Decisão: o pipeline continua MONOLÍTICO (e está certo assim)

Dado o volume (≈5k linhas) e o contexto de MVP/POC, **não há razão para quebrar o
`Main.py` em microsserviços/DAG agora** — o monólito é simples, idempotente e fácil de
apresentar. A evolução para "plataforma" **não** exige reescrever a orquestração: exige
apenas tornar os dados **consultáveis num lugar só**. Por isso o MVP mínimo é uma *camada
de consulta* por cima do que já existe, e todo o resto (orquestrador, app interativo,
validação automática) fica como **sugestão de implementação antes de produção**.

**MVP mínimo implementado:** `scripts/build_warehouse.py` projeta um **DuckDB**
(`outputs/raio_x.duckdb`) sobre os Parquet que o pipeline já gera — cada Parquet vira uma
view (schemas `comercial.*` / `operacional.*`) + algumas views `gold.*`. Resultado: SQL
ad-hoc sobre **toda** a base, sem servidor, sem tocar no pipeline. É o conceito de
"plataforma" (camada única de dados consultável) com pouquíssimo trabalho.

## 2. Visão-alvo: arquitetura em camadas (medallion) — referência conceitual

```
            ┌─────────────────────────────────────────────────────────────┐
 INGESTÃO   │ watch/`data/raw` ou conector ao sistema da corretora         │
            │ → valida contrato (pandera) → carimba origem → zona BRONZE   │
            └─────────────────────────────────────────────────────────────┘
                                    ↓
 ARMAZÉM    ┌── DuckDB (1 arquivo .db local) — camada de query única ──────┐
 (DuckDB)   │ BRONZE  linhas brutas atômicas (producao_grain, cadastro)    │
            │ SILVER  saneado/conformado: df_prod_status, cycle grain,     │
            │         flags (último ciclo, contato), contratos validados   │
            │ GOLD    marts: comercial.* e operacional.* (as visões atuais)│
            └─────────────────────────────────────────────────────────────┘
                                    ↓
 SEMÂNTICA  ┌── Registro único de métricas + regras de produto ───────────┐
            │ PRODUCT_RULES + catálogo de métricas (1 def → Python/SQL/DAX)│
            └─────────────────────────────────────────────────────────────┘
                                    ↓
 CONSUMO    ┌── App Streamlit (2 abas: Comercial | Operacional) ──┐  Power BI
            │ filtros, drill-down, lê do DuckDB; reusa os HTMLs    │  (parquet)
            │ + página "Saúde do Pipeline" (run_context, dq_history)│
            └─────────────────────────────────────────────────────┘
 ORQUESTRAÇÃO  Prefect/Dagster (flow com tasks, retry, agenda, lineage da execução)
```

## 3. Componentes e como reaproveitar o atual

| Camada | O que entra | Reaproveita | Esforço |
|---|---|---|---|
| **Ingestão** | watcher de pasta ou conector; `pandera` valida o contrato (`REGRAS_POR_PRODUTO_E_CONTRATOS.md`) na entrada | `_stamp_origin`, `load_excel`, guardrails | médio |
| **Armazém DuckDB** | 1 `.db` com schemas bronze/silver/gold; as funções `build_*` viram transforms que materializam tabelas | **todos** os builders de `analytics.py`/`operacional.py`/`functions.py` | médio |
| **Camada semântica** | `PRODUCT_RULES` + catálogo de métricas (nome, fórmula, grão, fonte) — fonte única para Python e DAX | `parameters.py`, os docstrings já descrevem as fórmulas | baixo→médio |
| **Orquestração** | flow Prefect: ingest → silver → gold → marts → DQ gate → publish | a sequência do `run_pipeline` já é o DAG, só explicitar | baixo |
| **Consumo interativo** | app Streamlit lendo o DuckDB; filtros por período/especialidade/produtor; embeda os HTMLs e abre os workbooks de auditoria | portais HTML, `report_html` (vira componentes), Parquet | médio |
| **Observabilidade** | página de saúde: tendência `dq_history`, `run_context`, status do último flow | `dq_history.parquet`, `run_context.parquet` | baixo |

## 4. Stack MVP recomendada (local, simples, grátis)

- **DuckDB** — “SQLite analítico”: 1 arquivo, lê Parquet nativamente, SQL completo. É o
  pulo do gato do MVP — vira a **camada de query única** sem subir banco/servidor.
- **Prefect** (ou Dagster) — orquestração leve em Python; agenda + retry + UI local.
- **pandera** — valida os contratos de dados na ingestão (Camada 3 do contrato).
- **Streamlit** — app de dados em Python puro; do script ao painel interativo em horas.
- Mantém **pandas + Parquet + openpyxl/plotly** que já são a base.

> Tudo roda na máquina, sem nuvem nem credenciais — coerente com "é um POC".

## 5. Roadmap incremental

### ✅ MVP (feito agora — o que se apresenta)
- **DuckDB como camada de consulta única** (`scripts/build_warehouse.py`): views sobre os
  Parquet (schemas `comercial.*`/`operacional.*`) + `gold.*` de exemplo. SQL ad-hoc sobre
  toda a base, sem servidor, sem mudar o pipeline monolítico. **É o conceito de plataforma
  com o mínimo de trabalho.** Rode `python scripts/build_warehouse.py` após o `Main.py`.

### 🔭 Sugestões de implementação ANTES de ir para produção (fora do POC)
- **Materializar** as camadas no DuckDB (tabelas em vez de views) ao fim do `run_pipeline`.
- **App Streamlit (2 públicos)** lendo o DuckDB — filtros, drill-down, embed dos HTMLs e
  links de auditoria; substitui os portais estáticos por algo interativo.
- **Catálogo de métricas + `PRODUCT_RULES`** como fonte única (Python/SQL/DAX) — elimina a
  divergência de definição entre Excel, HTML e Power BI.
- **Orquestração** (Prefect/Dagster) + agenda + página de saúde (`run_context`/`dq_history`).
- **Validação de contrato (pandera) na ingestão** — promove os caveats de domínio a checagens.
- **Conector direto ao sistema da corretora** e, só então, **acesso/segurança/performance**.

## 6. O que NÃO fazer no POC
- Nada de autenticação, RBAC, criptografia, multi-tenant.
- Nada de nuvem/Kubernetes/Spark — o volume (≈5k linhas) cabe em memória com folga.
- Não reescrever os builders: eles **são** a lógica de negócio validada; só mudam de
  "função chamada no Main" para "transform materializada e consultável".
- Não otimizar performance antes de ter o fluxo ponta-a-ponta.

## Relacionados
- `CLAUDE.md` (arquitetura atual) · `docs/CHANGELOG.md` (histórico) ·
  `docs/DATA_DISCOVERY.md` (catálogo de análises) ·
  `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md` (contratos → base da Camada de validação).
