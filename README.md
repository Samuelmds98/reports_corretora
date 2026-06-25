# Reports Corretora

> Motor de **analytics e inteligência de dados** (Python/pandas) para uma **corretora de
> seguros que atende o público geral** (pessoas físicas e jurídicas). Lê dois relatórios
> Excel brutos, aplica saneamento e regras de negócio, calcula *status* e *rating* por
> cliente e exporta um "data warehouse local" **segmentado em 3 públicos** (Excel + HTML
> interativo + Parquet), com **camada de consulta DuckDB** e **app interativo Streamlit**.

Projeto de **TCC (MBA em Gestão de BI)** + ferramenta real de trabalho. A base usada na
análise é um **recorte de um público específico (cooperados médicos)** — delimitação do
estudo de caso, não a natureza da corretora; o motor e a modelagem são genéricos para
qualquer público. Foco atual em métricas **não-monetárias** (a confiabilidade dos valores
prêmio/comissão na base real é baixa — saneamento é uma 2ª fase).

---

## ✨ O que entrega

A partir de **2 Excel** (produção: apólices/faturas/endossos · cadastro: cooperados), uma
rodada produz **3 painéis** independentes, cada um com workbook formatado + relatórios HTML
(Plotly, com insights/recomendações) + Parquet para BI + workbooks de **auditoria**:

| Painel | Foco | Conteúdo |
|---|---|---|
| 🟢 **Comercial** | Vendas/CRM | Curva ABC, market share, cross-sell, agenda de renovações, win-back, margens (comissão), performance de produtor, snapshot mensal |
| 🟠 **Operacional/Qualidade** | Saúde do dado/processo | Completude de cadastro, migrado×orgânico, status×situação, detectores DQ1–DQ3, acionabilidade, testes de qualidade (DQ) |
| 🔵 **Marketing** | Base inteira (cliente × prospect) | Demografia, personas (sexo/estado civil/tipo), **alvos de aquisição**, **audiência de campanha**, roadmap de growth |

**Diferenciais:**
- **Rastreabilidade ponta a ponta** — cada número tem o *lastro* (registros de origem com
  arquivo e linha) num workbook **Agregado \| Lastro**.
- **Qualidade como 1ª classe** — o motor **só sinaliza, nunca corrige**; expõe os furos
  para saneamento na origem.
- **Mesma lógica, 3 formas de consumo** — os relatórios HTML, o app Streamlit e (futuro)
  o Power BI partem dos **mesmos** builders/gráficos (sem divergência de número).

---

## 🚀 Como rodar (reprodutível em qualquer máquina)

Pré-requisitos: **Python 3.10+** e git. Todos os caminhos são relativos à raiz do projeto
(nada hardcoded), então basta clonar e rodar.

```bash
# 1. Clonar e entrar
git clone https://github.com/Samuelmds98/reports_corretora.git
cd reports_corretora

# 2. Ambiente virtual + dependências
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
# source .venv/bin/activate
pip install -r requirements.txt

# 3. Rodar o pipeline sobre a BASE DE EXEMPLO (sintética/fictícia, já versionada)
python Main.py --input-dir data/exemplo --force

# 4. (opcional) Camada de consulta SQL — DuckDB sobre os Parquet
python scripts/build_warehouse.py

# 5. App interativo (consumo p/ TCC) — após o passo 3
streamlit run app/Home.py
```

Abra `outputs/index.html` para os painéis estáticos, ou o Streamlit para a versão
navegável. Para **regenerar** a base de exemplo (reprodutível por seed):
`python scripts/gerar_dados_exemplo.py`.

> **Dados reais:** o pipeline lê de `data/raw/` por padrão (`python Main.py`). Esses
> arquivos **não são versionados** (ver Segurança). Use `--input-dir data/exemplo` para a
> base fictícia. Idempotente por hash do input (`--force` reprocessa).

---

## 📂 Estrutura

```
data/exemplo/     2 Excel fictícios (versionados) — mesma estrutura dos brutos
data/raw/         2 Excel REAIS (NÃO versionados — gitignored)
src/              Lógica reutilizável (funções puras DataFrame -> DataFrame)
configs/          Configuração editável pelo negócio (ex.: product_types.csv = mapa produto→vigência)
Main.py           Pipeline principal (lê -> saneia -> motor -> builders -> exporta)
scripts/          Gerador de exemplo + build do warehouse DuckDB
tests/            Testes pytest do motor de regras
app/              App Streamlit (Home + pages/ + lib/) — lê os Parquet, reusa os _chart_*
outputs/          Saídas por público: {comercial,operacional,marketing}/ + index.html
docs/             Guias (auditoria, métricas, regras, evolução) + apresentação
```

## 🧱 Arquitetura (resumo)

```
data (Excel/visão) → load + carimbo de origem (ID_LINHA) → saneamento (CPF, raiz de apólice)
  → motor (status do produto, ciclo de vigência, rating) → guardrails de contexto
  → builders (analytics / operacional / marketing) → DQ + auditoria
  → exporta SEGMENTADO por público (Excel + HTML + Parquet + auditoria)
       → DuckDB (SQL ad-hoc)   → Streamlit (app)   → Power BI (futuro, via Parquet)
```

O pipeline é **monolítico e idempotente** (volume ~5k linhas). Detalhes em
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## 🔒 Segurança e privacidade (LGPD)

- `data/raw/` (CPF, nomes reais) e `notebooks/` (com outputs reais) **nunca** são
  versionados — regra seletiva no `.gitignore`.
- `outputs/` versiona **apenas** `*.html` e `*.xlsx` **gerados da base de exemplo**.
- **Publicar no GitHub somente a partir de uma rodada com `data/exemplo`.**

## 🛠️ Stack

Python · pandas/numpy · openpyxl (Excel) · Plotly (HTML) · PyArrow/Parquet · **DuckDB**
(consulta) · **Streamlit** (app) · black/isort (formatação).

## 📚 Documentação

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — arquitetura + avaliação do motor de recomendações
- [`docs/GUIA_METRICAS.md`](docs/GUIA_METRICAS.md) — fórmula, dados e impactos por métrica
- [`docs/GUIA_AUDITORIA.md`](docs/GUIA_AUDITORIA.md) — como rastrear qualquer número até a origem
- [`docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md`](docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md) — regras de negócio + contratos de dados
- [`docs/EVOLUCAO_PLATAFORMA.md`](docs/EVOLUCAO_PLATAFORMA.md) — **roadmap** de evolução para plataforma
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — histórico de implementação

## 🗺️ Roadmap (resumo)

Pipeline local → plataforma: ingestão via banco/API · Power BI sobre os Parquet ·
app Streamlit (✅ v1) · automação de e-mail de qualidade ao backoffice · camada semântica
(métrica única) · testes/CI · governança LGPD. Detalhe em
[`docs/EVOLUCAO_PLATAFORMA.md`](docs/EVOLUCAO_PLATAFORMA.md).
