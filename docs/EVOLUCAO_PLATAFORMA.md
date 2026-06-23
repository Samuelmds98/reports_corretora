# Evolução para Plataforma de Inteligência de Dados / Negócios

> Avaliação do estado atual + **roadmap** de evolução do "Raio X Cooperados" de pipeline
> local para uma **plataforma de inteligência de dados** da corretora. Incorpora as quatro
> decisões já tomadas (ingestão via banco/API, Power BI, Streamlit, automação de e-mail de
> qualidade) e avalia evoluções arquiteturais e de produto adicionais. Arquitetura atual em
> `ARCHITECTURE.md`; histórico em `docs/CHANGELOG.md`.

---

## 1. Onde estamos (avaliação honesta)

**Já é mais maduro que a média de TCC** e tem fundações reaproveitáveis numa plataforma:

- **Motor de regras** puro e testável (`functions.py`: status, rating, ciclo de vigência) —
  é a lógica de negócio validada; nenhuma evolução abaixo o reescreve.
- **Linhagem ponta-a-ponta** (`ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`) + workbooks de
  auditoria Agregado|Lastro → cada número rastreável até a linha bruta.
- **Qualidade como cidadão de 1ª classe** (DQ que só sinaliza, guardrails de contexto,
  detectores operacionais DQ1–DQ3, histórico `dq_history`).
- **Saídas segmentadas em 3 públicos** (comercial/operacional/marketing) + Parquet pronto
  para BI + portais HTML + **DuckDB** como camada de consulta (MVP de plataforma já feito).
- **Idempotência por hash** e resiliência a arquivo aberto.

**Limites que impedem de chamar de "plataforma" hoje** — e que o roadmap ataca:

| # | Limite atual | Atacado na |
|---|---|---|
| L1 | **Ingestão manual** — depende de soltar 2 Excel em `data/raw/`; sem agenda, sem histórico de cargas, sem detecção de mudança de schema. | Fase 1 (banco/API) + Fase 4 (orquestração) |
| L2 | **Consumo estático** — HTML/Excel são fotografias; sem filtro/drill-down nem consulta ad-hoc. | Fase 2 (Power BI) + Fase 3 (Streamlit) |
| L3 | **Distribuição manual** — alguém precisa abrir e mandar os arquivos de qualidade ao backoffice. | Fase 4 (e-mail automático) |
| L4 | **Métrica definida em vários lugares** — a mesma regra vive no Python e, em breve, em DAX (Power BI) e no Streamlit. Risco de divergência. | Fase 5 (camada semântica) |
| L5 | **Sem testes automatizados nem CI** — frágil para automatizar em cima. | Fase 0 (fundações) |
| L6 | **Sem governança de PII/LGPD** formalizada — vira crítico quando há vários consumidores e e-mail. | Trilha transversal (governança) |

> **Decisão que se mantém:** o **motor continua monolítico** (`Main.py`). O volume (~5k
> linhas) cabe em memória; a evolução para plataforma **não** exige microsserviços — exige
> trocar a **fonte** (Excel → banco), **materializar** os dados num lugar consultável e
> **automatizar** distribuição e agenda. Os `build_*` permanecem como a lógica de negócio.

---

## 2. Arquitetura-alvo

```
 ORIGEM            Sistema da corretora (produção + cadastro)
   │               API de ingestão — construída pela ENGENHARIA DE DADOS
   ▼
 BANCO DE DADOS    VIEW(s) conformada(s)  ◄── substitui os 2 Excel de data/raw
   │               contrato de dados validado na leitura (pandera)
   ▼
 PIPELINE          Main.py — motor de regras (status/rating/ciclo) INALTERADO
   │               bronze → silver → gold (materializado no DuckDB)
   ▼
 SERVING           ┌── Parquet ─────────────►  POWER BI (.pbix, modelo semântico)   [#2]
   │               ├── DuckDB (views/tabelas) ► STREAMLIT (app 3 tracks + saúde)     [#3]
   │               └── arquivos DQ na rede ───► E-MAIL ao backoffice (notif.+caminho)[#4]
   │
 ORQUESTRAÇÃO      Prefect/Dagster: agenda · retry por etapa · lineage da execução
 SEMÂNTICA         Catálogo de métricas + PRODUCT_RULES → fonte única (Python/SQL/DAX)
 GOVERNANÇA        LGPD (CPF mascarado, acesso), testes (pytest), CI, observabilidade
```

`[#2]`/`[#3]`/`[#4]` = as decisões já tomadas pelo usuário (ver fases correspondentes).

---

## 3. Roadmap em fases

Cada fase: **objetivo · o que entra · o que reaproveita · dependências · esforço**.
A ordem reflete dependências reais (não se automatiza em cima de código sem teste, nem se
agenda em cima de ingestão manual).

### Fase 0 — Fundações (pré-requisito de tudo) · esforço: baixo–médio
**Objetivo:** tornar o pipeline confiável o bastante para automatizar em cima.
- **Testes `pytest`** sobre o motor (`calculate_rating`, `get_product_status`,
  `flag_last_cycle`, extração de raiz de apólice) usando `data/exemplo` — a maior lacuna
  técnica hoje. Trava regressões antes de qualquer automação.
- **CI** (GitHub Actions): roda os testes + um `python Main.py --input-dir data/exemplo` a
  cada push. Falha barulhento, não silencioso.
- **Pin do contrato de dados** (`REGRAS_POR_PRODUTO_E_CONTRATOS.md`) como artefato vivo — é
  a especificação que a view (Fase 1) terá de cumprir.
- *Reaproveita:* `data/exemplo`, as funções puras. *Dependências:* nenhuma.

### Fase 1 — Ingestão via banco de dados (substituir o Excel) · esforço: médio
**Objetivo:** trocar a fonte de `data/raw/*.xlsx` por **uma view em banco**, alimentada por
uma **API que a engenharia de dados vai construir**.
- Abstrair a leitura: `load_excel(path)` → `load_source(conn)` que lê a(s) **view(s)**
  conformada(s). O resto do pipeline não muda (já opera sobre DataFrames).
- **Contrato na fronteira:** validar a view na leitura com `pandera` (colunas obrigatórias,
  tipos, domínio de `TIPO DE NEGÓCIO`, `INÍCIO ≤ TÉRMINO`) — promove os *caveats de domínio*
  a checagens. Schema novo/divergente → WARNING, não quebra o run.
- **Idempotência** passa a usar o hash de um snapshot da query (ou um carimbo de carga),
  em vez do hash dos arquivos.
- **`data/exemplo` permanece** como fonte de teste/CI e demo sem tocar no banco (`--input-dir`).
- *Reaproveita:* `_stamp_origin`, guardrails, todo o motor. *Dependências:* Fase 0 (testes
  protegem a troca de fonte) + entrega da view/API pela engenharia de dados.
- ⚠️ **Coordenação:** alinhar com a eng. de dados o **grão** e a **semântica** da view (1
  linha por movimento; `SITUAÇÃO`, `USUÁRIO DA INCLUSÃO`, `PRODUTOR` preservados) — o
  contrato de dados é o acordo.

### Fase 2 — Painel Power BI (consumo executivo) · esforço: médio
**Objetivo:** dashboards no **Power BI sobre os Parquet** que o pipeline já gera.
- O Parquet já é a camada de serving — modelar relacionamentos (fato `producao_enriquecida`
  + dimensões) e medidas.
- **Medidas DAX derivadas do catálogo de métricas** (Fase 5), não reinventadas — evita que o
  número do Power BI divirja do HTML/Excel (risco L4).
- Foco inicial não-monetário (contagens/datas/status), coerente com a confiabilidade atual
  dos valores; visões de prêmio/comissão entram após o saneamento (Fase 5).
- **Guia de implementação Power BI** será escrito **após finalizar o projeto** (decisão do
  autor) — campos, tipos, granularidade, DAX e pegadinhas de tipo/qualidade.
- *Reaproveita:* `outputs/*/parquet/*`. *Dependências:* nenhuma técnica (pode começar já);
  idealmente após Fase 5 para não retrabalhar as medidas.

### Fase 3 — App interativo em Streamlit (substitui os HTMLs estáticos) · esforço: médio
**Objetivo:** transformar os portais/HTMLs em um **app Streamlit** interativo.
- Lê do **DuckDB** (camada de consulta já existente); **3 páginas** espelhando os tracks
  (Comercial · Operacional/Qualidade · Marketing) + página **"Saúde do Pipeline"**
  (`run_context`, tendência de `dq_history`).
- **Filtros e drill-down** (período, especialidade, produtor, seguradora) — o que o HTML
  estático não faz; embute os gráficos Plotly já construídos em `report_html._chart_*`
  (viram componentes) e linka os workbooks de auditoria.
- Mantém o princípio de rastreabilidade: cada visão com link para o lastro.
- *Reaproveita:* `report_html._chart_*`, DuckDB, Parquet, os builders. *Dependências:* DuckDB
  (feito); ganha muito com a Fase 1 (dados sempre frescos) e a Fase 5 (métrica única).

### Fase 4 — Automação e notificação de qualidade ao backoffice · esforço: baixo–médio
**Objetivo:** rodar o pipeline em **agenda** e **notificar o backoffice por e-mail** sobre
os arquivos de qualidade de dados.
- **Orquestração** (Prefect ou Dagster, ou um simples agendador no começo): `ingest →
  silver → gold → marts → DQ gate → publish`. A sequência do `Main.py` já é o DAG; só
  explicitar, com retry por etapa e lineage da execução.
- **E-mail automático de DQ:** ao concluir, envia ao time de backoffice uma **notificação**
  com o **resumo do DQ** (nº de ocorrências por regra/severidade, vindo de `build_dq_summary`)
  e o **caminho do arquivo na pasta de rede** — **sem anexar o arquivo** (são dados reais de
  cliente; o anexo violaria LGPD e a política de não trafegar PII por e-mail). O dado fica na
  rede; o e-mail é só ponteiro + sumário.
- **Alerta condicional (não só relatório):** disparar destaque quando a qualidade **regride**
  — novas ocorrências CRÍTICAS, salto na taxa de órfãos, ou schema drift na view. Compara com
  o `dq_history` para falar só quando há o que agir (mesma filosofia "só sinaliza o relevante").
- *Reaproveita:* `data_quality_advanced.build_dq_summary`, `dq_history.parquet`, `run_context`.
  *Dependências:* Fase 0 (não automatizar sobre código sem teste) e Fase 1 (agenda só faz
  sentido com fonte automática).

### Fase 5 — Maturidade de dados e de produto · esforço: médio–alto (incremental)
**Objetivo:** consolidar a plataforma e abrir novas frentes de valor.
- **Camada semântica / catálogo de métricas** (ataca L4): um registro único `PRODUCT_RULES`
  + catálogo (nome, fórmula, grão, fonte) como **fonte única** para Python, SQL (DuckDB) e
  DAX (Power BI). Com **3 consumidores** (Excel, Power BI, Streamlit), é a peça que impede a
  mesma métrica de dar 3 números diferentes.
- **Materializar o medallion no DuckDB** (tabelas bronze/silver/gold em vez de views) ao fim
  do run — consulta mais rápida e camadas persistidas.
- **Histórico / séries temporais** (agora que a fonte é um banco): snapshots de carteira e de
  qualidade ao longo do tempo (SCD leve) — habilita **retenção real, tendência de DQ,
  evolução de cohort** sem depender de uma única carga.
- **Fase monetária (saneamento de valores):** com a confiabilidade de prêmio/comissão
  endereçada na origem, ligar as visões de receita/margem que hoje ficam em segundo plano.
- **Fechar o loop de Marketing:** capturar os dados do roadmap "Growth — Dados a Coletar"
  (origem do lead, engajamento de campanha, motivos de não-conversão) e medir conversão real
  dos *alvos de aquisição* / *audiência de campanha*.
- **Next-best-action / propensão (ML):** hoje as recomendações são **heurísticas rule-based**
  (ver `ARCHITECTURE.md` §3). Com histórico acumulado, evoluir para um modelo de propensão por
  segmento — só depois que houver série temporal e valores saneados (não antes).
- *Dependências:* Fases 1–4 estáveis.

---

## 4. Trilha transversal — Governança, segurança e observabilidade

Não é uma fase; acompanha tudo a partir da Fase 1 (quando deixa de ser POC local).

- **LGPD / PII:** CPF e nomes são dados reais. Mascarar/pseudonimizar CPF nas saídas de
  consumo (Power BI/Streamlit); **e-mail nunca carrega PII** (só caminho + sumário —
  princípio já adotado na Fase 4); restringir a pasta de rede ao backoffice.
- **Controle de acesso:** Power BI e Streamlit por público/perfil (comercial ≠ backoffice ≠
  marketing); log de quem acessa o quê.
- **Observabilidade:** página "Saúde do Pipeline" (Streamlit) sobre `run_context`/`dq_history`;
  status do último flow do orquestrador; alerta de schema drift na view.
- **Segredos:** credenciais do banco fora do código (variáveis de ambiente / secret manager)
  assim que a Fase 1 introduzir a conexão.

---

## 5. Sequenciamento e dependências (visão rápida)

| Fase | Entrega | Depende de | Pode começar |
|---|---|---|---|
| 0 Fundações | testes + CI + contrato | — | **agora** |
| 1 Ingestão DB/API | view substitui Excel | 0 + eng. de dados | após 0 / em paralelo à eng. |
| 2 Power BI | dashboards sobre Parquet | — (ideal: 5) | agora; guia após o projeto |
| 3 Streamlit | app interativo 3 tracks | DuckDB (feito); ganha com 1 e 5 | após 0 |
| 4 Automação + e-mail DQ | agenda + notificação backoffice | 0 + 1 | após 1 |
| 5 Semântica / histórico / ML | métrica única, séries, propensão | 1–4 | incremental |
| — Governança/LGPD | mascaramento, acesso, segredos | a partir de 1 | transversal |

> **Caminho crítico real:** 0 → 1 → 4. Testes destravam a automação; a ingestão por banco
> destrava a agenda; só então o e-mail automático de DQ roda sozinho com segurança. Power BI
> (2) e Streamlit (3) correm em paralelo assim que houver dado fresco.

---

## 6. Stack recomendada (evolutiva, sem big-bang)

- **Banco + view:** definido pela engenharia de dados (Postgres/SQL Server/etc.); o pipeline
  só precisa de um conector + a view conformada.
- **DuckDB** — segue como camada de consulta local/serving para o Streamlit e SQL ad-hoc.
- **pandera** — validação do contrato na ingestão.
- **Prefect** (ou Dagster) — orquestração leve em Python; agenda + retry + UI.
- **Streamlit** — app de dados em Python puro, reaproveitando os gráficos Plotly.
- **Power BI** — consumo executivo sobre os Parquet.
- **pytest + GitHub Actions** — testes e CI.
- Mantém **pandas + Parquet + openpyxl/plotly** que já são a base. Nada de nuvem/Spark/
  Kubernetes: o volume (~5k linhas) não justifica.

---

## 7. O que NÃO fazer (anti-overengineering)

- Não quebrar o `Main.py` em microsserviços/DAG distribuído — o monólito é a escolha certa
  para o volume; orquestrar ≠ fragmentar.
- Não construir o modelo de ML (propensão/next-best-action) **antes** de ter histórico e
  valores saneados — sem série temporal é chute com verniz.
- Não anexar arquivos de dados reais no e-mail — só notificação + caminho de rede (LGPD).
- Não duplicar a definição de métrica em DAX/SQL/Python sem o catálogo único (Fase 5) — é a
  origem garantida de divergência entre Power BI, Streamlit e Excel.
- Não automatizar (Fase 4) sobre um motor sem testes (Fase 0).

## Relacionados
- `ARCHITECTURE.md` (arquitetura atual + avaliação do motor de recomendações) ·
  `CLAUDE.md` (contexto) · `docs/CHANGELOG.md` (histórico) ·
  `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md` (contratos → base da validação na ingestão) ·
  `docs/interno/DATA_DISCOVERY.md` (catálogo de análises ainda não exploradas).
