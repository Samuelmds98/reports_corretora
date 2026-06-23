# Reports Corretora — Arquitetura da Solução

> Documentação técnica resumida da arquitetura, histórico em `docs/CHANGELOG.md`; evolução em `docs/EVOLUCAO_PLATAFORMA.md`.

## 1. Visão geral do fluxo

```
 data/raw/  (2 Excel brutos)
   ├─ RptAnaliseProducao.xlsx   (produção: apólices, faturas, endossos)
   └─ RptClienteLista.xlsx      (cadastro dos cooperados)
        │
        ▼  Main.py (pipeline monolítico, idempotente por hash do input)
 ┌───────────────────────────────────────────────────────────────────────┐
 │ 1. LEITURA        carimba âncora de origem (ID_LINHA/ARQUIVO/LINHA)     │
 │ 2. SANEAMENTO     CPF/CNPJ, raiz de apólice, normalização de produtor   │
 │ 3. MOTOR          status do produto, ciclo de vigência, rating por CPF  │
 │ 4. GUARDRAILS     mede a "forma" do input e alerta sobre distorções     │
 │ 5. BUILDERS       ~40 visões (comerciais + operacionais/qualidade + mkt) │
 │ 6. DQ + AUDITORIA testes de qualidade + lastro por visão                │
 │ 7. EXPORTAÇÃO     segmentada por público                                │
 └───────────────────────────────────────────────────────────────────────┘
        │
        ▼  outputs/
   ├─ comercial/    (workbook 22 abas + 12 HTML + portal + parquet + auditoria)
   ├─ operacional/  (workbook 9 abas + 5 HTML + portal + DQ + logs + auditoria)
   ├─ marketing/    (workbook 10 abas + 11 HTML + portal + parquet + auditoria)
   ├─ index.html    (índice central — conecta os 3 painéis)
   └─ reports.duckdb (camada de consulta SQL — MVP de plataforma)
```

## 2. Módulos (`src/`) — funções puras DataFrame → DataFrame

| Módulo | Responsabilidade |
|---|---|
| `functions.py` | **Motor**: status do produto (regras de vigência), `flag_last_cycle` (último ciclo), `build_cycle_grain` (grão de ciclo), `calculate_rating` (1–5★), saneamento de apólice. |
| `analytics.py` | **Builders comerciais**: ABC, cross-sell, market share, cohort, renovações, win-back, margens (incl. seguradora×produto), performance de produtor, mix/contagens. |
| `operacional.py` | **Builders de qualidade/processo**: completude, origem (migrado×orgânico), status×situação, detectores DQ1/DQ2/DQ3, acionabilidade (telefone/e-mail/consentimento). |
| `marketing.py` | **Builders de marketing** (base inteira, cliente × prospect): status da base, distribuições de especialidade/década/faixa etária, **personas** (sexo/estado civil/tipo), **alvos de aquisição** (prospects × produto) e **audiência de campanha** (e-mail acionável). |
| `data_quality_advanced.py` | **Testes de DQ** (prêmio zerado, comissão>prêmio, inconsistência %, outliers, duplicatas) — só sinaliza. |
| `quality.py` | Auditoria linha a linha (diagnóstico consolidado por registro). |
| `guardrails.py` | `build_run_context`: mede janela temporal, órfãos, categorias; alerta sobre input distorcido. |
| `audit.py` | Workbooks de auditoria **Agregado \| Lastro** por visão (rastreabilidade até a linha bruta). |
| `report_html.py` | 28 relatórios HTML (Plotly) com insights/recomendações + portais de navegação + roadmap estático de growth. |
| `excel_report.py` | Exportação multi-abas formatada (paleta corporativa). |
| `persistence.py` | Parquet para Power BI + histórico de DQ acumulado. |
| `parameters.py` / `utils.py` | Mapa de produto→vigência, produtores internos/aliases; paths e helpers. |

## 3. Pilares arquiteturais (os diferenciais)

- **Rastreabilidade ponta-a-ponta.** Cada linha bruta recebe `ID_LINHA`/`ARQUIVO_ORIGEM`/
  `LINHA_ORIGEM` na leitura. Cada visão tem um workbook **Agregado \| Lastro**: filtra-se
  qualquer número pela chave e vê-se exatamente os registros de origem que o compõem.
- **Qualidade como cidadão de 1ª classe.** O motor **só sinaliza, nunca corrige**.
  Guardrails (contexto do input) + DQ (testes estatísticos/estruturais) + detectores de
  processo (DQ1/DQ2/DQ3) + histórico (`dq_history`) = furos expostos para saneamento na origem.
- **Segmentação por público (data products).** Três trilhas independentes — Comercial,
  Operacional/Qualidade e Marketing — cada uma com seu workbook, HTMLs, portal, parquet e
  auditoria. A trilha Marketing olha a **base inteira** (cliente × prospect), preenchendo o
  ponto cego do Comercial (que vê só quem já comprou).
- **Correção de domínio (valor vigente).** Apólices renovadas multi-ano não inflam: visões
  de carteira usam o **último ciclo** e o snapshot usa **grão de ciclo**.
- **Idempotência e resiliência.** Hash do input pula reprocessamento desnecessário;
  gravações de Excel são resilientes a arquivo aberto.

## 4. Camadas de dados (medallion — conceitual) e a camada de consulta

- **Bronze** = linhas brutas atômicas com âncora (`producao_grain`).
- **Silver** = saneado/conformado (`df_prod_status`, grão de ciclo, flags de último
  ciclo/contato).
- **Gold** = marts por público (as visões comerciais, operacionais e de marketing).
- **Camada de consulta (MVP):** `scripts/build_warehouse.py` projeta um **DuckDB** sobre
  os Parquet — schemas `comercial.*` / `operacional.*` + views `gold.*` (KPIs, ranking de
  produtores, agenda por urgência, scorecard de qualidade). SQL ad-hoc sobre toda a base,
  sem servidor.

## 5. Stack tecnológica

- **Python + pandas** (motor e builders), **NumPy**.
- **openpyxl** (Excel formatado), **Plotly** (HTML interativo), **PyArrow/Parquet** (BI).
- **DuckDB** (camada de consulta analítica embutida).
- **Power BI** consome os Parquet (guia de reconstrução será escrito após finalizar o projeto).
- **black/isort** (padronização), `data/exemplo/` anonimizado para apresentação sem expor dados.

## 6. Decisões de arquitetura (e o porquê)

| Decisão | Por quê |
|---|---|
| **Monolito** (`Main.py`), não microsserviços/DAG | Volume pequeno (~5k linhas); simples, idempotente e fácil de apresentar/manter. |
| **Não-monetário primeiro** | Confiabilidade baixa dos valores; contagens/datas/status são robustos e já acionáveis. |
| **Só sinaliza, nunca corrige** | Saneamento é decisão do negócio, na origem; a ferramenta dá transparência, não mascara. |
| **Três públicos separados** (Comercial, Operacional/Qualidade, Marketing) | Pedido do gestor; cada audiência recebe só o que lhe importa. Marketing surgiu para enxergar os prospects (68% da base), invisíveis ao grão de produção do Comercial. |
| **Aba Conferência removida; check no console** | Para o negócio, Agregado+Lastro bastam; o cross-check vira rede de segurança silenciosa. |
| **DuckDB sobre Parquet (não reescrever builders)** | Vira "plataforma" (camada única consultável) com o mínimo de trabalho. |
