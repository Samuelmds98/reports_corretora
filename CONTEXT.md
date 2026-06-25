# CONTEXT — reports_corretora (handoff para a próxima sessão)

> **Leia este arquivo primeiro.** Resumo do estado do projeto para continuar de onde paramos.
> Detalhes profundos em `CLAUDE.md` e `docs/`. Arquitetura + motor de recomendações em
> `ARCHITECTURE.md`. Próximos passos em `TODO.md`.

## O que é
Motor de analytics (Python/pandas) para uma corretora de seguros que atende o **público
geral** (PF/PJ). Lê 2 Excel brutos, saneia, aplica regras de negócio, calcula status/rating
por cliente e exporta um "data warehouse" local **segmentado em 3 públicos** (Excel + HTML +
Parquet). A base analisada é um **recorte específico (cooperados médicos)** — delimitação do
estudo de caso, não a natureza da corretora.

- Nome do projeto: **reports_corretora**. Pasta local: `raio_x_cooperados`.
  GitHub: `https://github.com/Samuelmds98/reports_corretora`.
- É um **TCC de MBA em Gestão de BI** + ferramenta real do trabalho do autor.

## Stack e como rodar
- Python + pandas/numpy, openpyxl (Excel), plotly (HTML), pyarrow/Parquet, **duckdb**
  (camada de consulta), black/isort (formatação).
- Venv em `.venv` → usar `.venv/Scripts/python.exe`.
- Rodar: `python Main.py [--input-dir data/exemplo] [--force]`. Idempotente por hash do input.
- Warehouse: `python scripts/build_warehouse.py` (DuckDB sobre os Parquet).
- App interativo (Fase 3, aditivo — TCC): `streamlit run app/Home.py` (após um `Main.py`).
  Lê os Parquet e reusa os `_chart_*`; não substitui a geração local de HTML/XLSX.

## ⚠️ PROTOCOLO DE SEGURANÇA (crítico — já houve 1 vazamento)
- `data/raw/` = **dados REAIS de clientes** (CPF, nomes). **NUNCA versionar** (gitignored).
- `notebooks/` = EDA com **outputs reais embutidos** → foi a causa do vazamento. Gitignored.
- `*.pptx`, `.claude/`, `CLAUDE.md` → gitignored.
- `outputs/` versiona **apenas `*.html` e `*.xlsx`** (regra seletiva no `.gitignore`).
- **Publicar no GitHub SÓ a partir de uma rodada com `data/exemplo`** (base fictícia
  anonimizada). O histórico git foi recriado do zero uma vez para apagar o commit contaminado.

## Estado atual (o que já foi feito)
- **3 tracks segmentados por público**, cada um com workbook + `visuals/` (HTML) + `parquet/`
  + `auditoria/` (workbooks Agregado|Lastro):
  - `outputs/comercial/` — vendas/CRM (ABC, cross-sell, market share, renovações, win-back,
    margens incl. seguradora×produto, performance de produtor, snapshot).
  - `outputs/operacional/` — qualidade de cadastro/processo (completude, status×situação,
    DQ1/DQ2/DQ3, acionabilidade, testes de DQ) + `DQ_Reports.xlsx`.
  - `outputs/marketing/` — base inteira: **cliente × prospect** + demografia + acionabilidade
    (status da base, especialidade, década, faixa etária, histograma de idade, **alvos de
    aquisição**, **audiência de campanha**, **personas** sexo/estado civil/tipo, roadmap de
    growth).
  - `outputs/index.html` — índice central que linka os 3 painéis.
- **Correção multi-ciclo**: visões de carteira usam último ciclo (`flag_last_cycle`);
  snapshot usa grão de ciclo (`build_cycle_grain`). Não inflam renováveis multi-ano.
- **Rastreabilidade total** (âncora `ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM`).
- **DuckDB** como camada de consulta (MVP de "plataforma").
- Repo no GitHub com **resultados fictícios** (gerados de `data/exemplo`).

## Estrutura de dados (resumo — detalhe em `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md`)
- Entradas: `RptAnaliseProducao.xlsx` (39 col: apólices/faturas/endossos) +
  `RptClienteLista.xlsx` (33 col: cadastro dos cooperados).
- Derivados-chave em memória: `df_prod_status` (1 linha por CPF×SEGURADORA×PRODUTO,
  status + valores último ciclo), `df_cruzamento` (cadastro × insights, com `STATUS_GLOBAL`),
  `df_mkt_base` (1 linha/cooperado: status ATIVO/INATIVO/PROSPECT + demografia).
- **Confiabilidade dos valores (prêmio/comissão) é BAIXA** → foco em métricas
  **não-monetárias** (contagens, datas, especialidade, status).

## Documentos de referência
- `CLAUDE.md` — contexto completo do projeto (carregado automaticamente pela IA).
- `ARCHITECTURE.md` — arquitetura + **avaliação do motor de recomendações**.
- `TODO.md` — próximos passos (todos no track Marketing).
- `docs/CHANGELOG.md` — histórico de tudo que foi implementado.
- `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md` — regras por produto + contratos de dados + caveats.
- `docs/GUIA_METRICAS.md` — fórmula/dados/impacto por métrica.
- `docs/interno/` — docs de desenvolvimento (não versionadas): DATA_DISCOVERY, etc.
