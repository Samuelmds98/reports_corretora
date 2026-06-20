# Arquitetura e Regras de Negócio — Motor "Raio X Cooperados"

> Documento de referência da arquitetura e das regras de negócio do projeto.
> Nasceu como o *prompt/spec* inicial (Analytics Engineer — Motor de Rating e
> Saneamento) e foi atualizado para refletir o sistema efetivamente implementado.
> Pipeline principal: **`Main.py`** (não mais notebook). Detalhes operacionais em
> `CLAUDE.md`; guias do usuário em `docs/`.

---

## 1. Mapeamento do Dataset (Schema)

Duas entradas Excel em `data/raw/` (ou outro diretório via `--input-dir`):

**Produção** (`RptAnaliseProducao.xlsx`, 39 colunas) — colunas-chave:
* **CPF/CNPJ**: chave do cliente.
* **CLIENTE**: nome do segurado.
* **RAMO**: natureza do risco (usado no saneamento de raiz).
* **NOME ABREVIADO DO PRODUTO**: nome comercial (define o tipo de vigência).
* **SEGURADORA (ABREVIADO)**: companhia.
* **APÓLICE**: número do contrato (sujeito a sufixos/sujeira).
* **TIPO DOCUMENTO**: `APÓLICE`, `FATURA`, `ENDOSSO`...
* **TIPO DE NEGÓCIO**: `N`, `R`, `EN`, `ER`, `CN`, `CR`.
* **INÍCIO DE VIGÊNCIA** / **TÉRMINO DE VIGÊNCIA**: datas operacionais.
* **PRÊMIO LÍQ. DO SEGURO**, **PORCENTAGEM**, **COMISSÃO**.

**Cadastro** (`RptClienteLista.xlsx`, 33 colunas) — perfil do cooperado:
* **CGC/CPF** (chave), **SEXO**, **CIDADE/ESTADO/ESTADO CIVIL**, **CARACTERÍSTICA**
  (especialidade médica), **DATA DE NASCIMENTO** (→ idade/faixa etária).

> ⚠️ **Pontos de atenção do schema:**
> - Duas colunas de comissão: `COMISSÃO` e `COMISSÃO TOTAL (CORRET + CO-CORRET)`.
>   Fonte única em `get_comissao_col` (prioriza `COMISSÃO`).
> - Acento divergente: `CARACTERISTICA` (produção, sem acento) × `CARACTERÍSTICA`
>   (cadastro, com acento).
> - A janela de avaliação é definida por `INÍCIO DE VIGÊNCIA` (base atual cortada em 2024+).

---

## 2. Arquitetura da Solução (Stack)

Pipeline orquestrado por **`Main.py`** (raiz), importando funções puras de `src/`.
Roda com `python Main.py [--input-dir <dir>] [--force]`.

| Módulo | Responsabilidade |
|---|---|
| `functions.py` | Saneamento (CPF, raiz de apólice), motor de status, rating, demografia. |
| `parameters.py` | `PRODUCT_TYPE_MAP` (produto → tipo de vigência). |
| `analytics.py` | Builders de BI (ABC, market share, cohort, snapshot, mix, renovações, win-back, janeladas e **as visões de comissão**) + grãos granulares. |
| `quality.py` | Auditoria linha a linha (`run_full_audit`) → diagnóstico por registro. |
| `data_quality_advanced.py` | Detecções estatísticas/estruturais (DQ). **Só sinaliza.** |
| `guardrails.py` | `build_run_context`: janela temporal, órfãos, categorias. **Só alerta.** |
| `audit.py` | Workbooks de auditoria por análise (Agregado \| Lastro \| Conferência). |
| `excel_report.py` | Paleta corporativa + exportação multi-abas formatada (resiliente a arquivo aberto). |
| `report_html.py` | Relatórios HTML interativos (Plotly) com insights/recomendações. |
| `persistence.py` | Parquets para Power BI + histórico DQ acumulado. |
| `utils.py` | Paths, `load_excel`, `get_comissao_col`, `save_fig`. |

---

## 3. Camada de Qualidade — Saneamento e Rastreabilidade

* **Âncora de origem (`ID_LINHA`)**: carimbada na **leitura** (antes de qualquer
  dedup/saneamento), junto de `ARQUIVO_ORIGEM` e `LINHA_ORIGEM` (linha exata no Excel).
  É o elo de rastreabilidade até a fonte.
* **Extract Root**: extrai a raiz numérica da apólice (remove caracteres especiais e
  sufixos de ano 2000–2029).
* **Identify Conflicts**: sinaliza ao cadastro quando a mesma chave
  `(CPF, SEGURADORA, RAMO, RAIZ)` tem APÓLICES diferentes — exporta `Log_Apolices_Conflito_RaioX.xlsx`.

---

## 4. Classificação por Tipo de Vigência (via PRODUTO)

Mapa `PRODUCT_TYPE_MAP` (`parameters.py`):
* **RENOVÁVEL**: ciclos anuais (ex: AUTO, RC PROFISSIONAL).
* **RECORRENTE**: ciclos mensais/faturas (ex: SAÚDE, ODONTO, VIDA).
* **TRANSACIONAL**: pontuais (ex: VIAGEM).

> Produto não mapeado → tipo `INDEFINIDO` (sinalizado no DQ; não conta no rating).

---

## 5. Regras de Status e Atividade

* **Status do Produto** (por `CPF × SEGURADORA × PRODUTO`):
  * **RENOVÁVEL/TRANSACIONAL** (Bloco A — apólice N/R mais recente):
    `ATIVO` se `Início ≤ Hoje ≤ Término` e sem cancelamento (CN/CR) na janela;
    `CANCELADO` se houver cancelamento; senão `INATIVO`.
  * **RECORRENTE** (Bloco B — sem N/R, mas há `FATURA`): `ATIVO` se a fatura mais
    recente começou nos últimos **90 dias** e sem cancelamento; senão `INATIVO`.
* **Cliente Ativo (Global)**: ≥ 1 produto Renovável/Recorrente ATIVO, OU ≥ 1
  Transacional ativo ou com vigência nos últimos **12 meses**. Sem produção → `INATIVO (PROSPECT)`.

---

## 6. Motor de Rating (Hierarquia Top-Down)

Por CPF, sobre o **mix de produtos ativos**:

1. **5★**: recorrentes ≥ 1 E renováveis ≥ 2 E transacionais_12m ≥ 1
2. **4★**: recorrentes ≥ 1 E renováveis ≥ 1 E transacionais_12m ≥ 1
3. **3★**: categorias_distintas ≥ 2
4. **2★**: produtos_ativos ≥ 2 E categorias_distintas == 1
5. **1★**: produtos_ativos == 1 · **0★**: nenhum ativo

> Rating e status são derivados juntos: um cliente **INATIVO sempre tem rating 0**
> (não existe "rating histórico").

---

## 7. Visões de BI

**Ótica do prêmio (volume):** Curva ABC, Market Share por seguradora, Cohort/Safra,
Snapshot mensal de ativos, Mix por especialidade, Agenda de renovações (90d), Win-Back,
e as versões **janeladas 2025+** (originação por `INÍCIO DE VIGÊNCIA`).

**Ótica da comissão (receita real da corretora):**
* **Curva ABC por Comissão** — concentração de quem remunera a corretora.
* **Market Share / Margem por Comissão (seguradora)** — share de comissão e
  **taxa de comissão efetiva** = comissão / prêmio.
* **Margem por Produto** — taxa efetiva por produto (rentabilidade).

> A concentração/margem por comissão diverge da de prêmio porque as taxas variam por
> produto/seguradora — daí a importância das duas óticas.

---

## 8. Qualidade de Dados (DQ) — só sinaliza, nunca corrige

Arquivo `DQ_Raio_X_Cooperados.xlsx`. Regras: prêmio zerado/negativo, comissão > prêmio,
inconsistência percentual (tolerância 1%), outliers de prêmio/% (média ± 3σ por grupo),
duplicatas exatas, grupos com amostra < 5 e resumo com severidade. Histórico acumulado
em `dq_history.parquet`.

---

## 9. Rastreabilidade e Auditoria

Para cada análise, um workbook em `outputs/auditoria/` com 3 abas:
**Agregado** (os números) · **Lastro** (todos os registros de origem, com a âncora
`ID_LINHA`/`ARQUIVO_ORIGEM`/`LINHA_ORIGEM` + a chave do agrupamento) · **Conferência**
(re-agrega o lastro e prova que soma == número). Detalhe em `docs/GUIA_AUDITORIA.md`.

---

## 10. Guardrails e Idempotência

* **`run_context`**: mede a "forma" do input (janela temporal, % de órfãos, nº de
  categorias) e alerta sobre distorções de base filtrada/janelada. Só sinaliza.
* **Idempotência por hash** do input: pula a execução se nada mudou (`--force` força).
* **Resiliência**: gravações Excel pulam com aviso se o arquivo estiver aberto e a
  execução não é marcada como concluída (a próxima regenera).

---

## 11. Saídas e Execução

* Relatório principal (Excel multi-abas), `DQ_Raio_X_Cooperados.xlsx`, HTMLs em
  `outputs/visuals/`, Parquets em `outputs/parquet/` (inclui grãos granulares para
  Power BI), workbooks de auditoria em `outputs/auditoria/`, histórico `dq_history.parquet`.
* **Rodar:** `python Main.py` (lê `data/raw/`); `--input-dir data/exemplo` para a base
  de exemplo anonimizada; `--force` para reprocessar.

---

## 12. Diretrizes de Desenvolvimento

* **Código**: funções e variáveis em **inglês**; comentários e docstrings em **português**.
* **Simplicidade**: evitar overengineering; funções puras DataFrame → DataFrame.
* **Não destrutivo**: o pipeline só sinaliza problemas de qualidade; nunca altera o dado original.
* **Formatação**: `black` e `isort`.
