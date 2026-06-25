# Modelagem Dimensional (star schema conceitual)

> Modelo **dimensional** (Kimball) proposto sobre os dados do **Reports Corretora**. Hoje a
> camada *gold* são *marts* denormalizados por análise (*flat*); este documento formaliza o
> **star schema conceitual** que os organiza — base para o consumo (Power BI) e para a
> rastreabilidade conceitual. É **modelagem** (formato das tabelas), independente da
> arquitetura de armazenamento (ver `ARCHITECTURE.md` §5). Materialização é opcional.

## 1. Star schema principal — Fato Produção

**Grão:** *1 linha por movimento de produção* (apólice nova/renovação, endosso, fatura ou
cancelamento) — o mesmo grão da base bruta `RptAnaliseProducao` (com âncora `ID_LINHA`).

```
                          ┌──────────────────┐
                          │   DIM_TEMPO       │
                          │  (data, ano, mês, │
                          │   trim., safra)   │
                          └────────┬─────────┘
   ┌──────────────────┐            │            ┌──────────────────┐
   │  DIM_PESSOA       │           │            │  DIM_SEGURADORA   │
   │ CPF/CNPJ, nome,   │           │            │ abreviado, nome   │
   │ sexo, idade/faixa,│     ┌─────┴──────┐     └────────┬─────────┘
   │ especialidade,    │─────│ FATO_      │──────────────┘
   │ cidade/estado,    │     │ PRODUCAO   │
   │ estado civil,     │     │            │──────────────┐
   │ tipo (PF/PJ),     │     │ (medidas + │     ┌────────┴─────────┐
   │ cliente desde,    │     │ dims degen.)│    │  DIM_PRODUTO      │
   │ contato/rating    │     └─────┬──────┘     │ produto, ramo,    │
   └──────────────────┘           │            │ tipo de vigência  │
                          ┌────────┴─────────┐  └──────────────────┘
                          │  DIM_PRODUTOR     │
                          │ produtor/vendedor │
                          └──────────────────┘
```

### 1.1 Medidas (fato)
| Medida | Origem | Observação |
|---|---|---|
| `PREMIO_LIQ` | `PRÊMIO LÍQ. DO SEGURO` | aditiva; confiabilidade baixa hoje (foco não-monetário) |
| `COMISSAO` | `COMISSÃO` (via `get_comissao_col`) | aditiva |
| `PORCENTAGEM` | `PORCENTAGEM` | **não aditiva** (é taxa — usar média ponderada) |
| `QTD_ENDOSSO` | `QTDEENDOSSO` | aditiva |
| `QTD_PARCELAS` | `QUANTIDADE DE PARCELAS` | semiaditiva |

### 1.2 Dimensões degeneradas (no próprio fato)
`APÓLICE`, `TIPO DE NEGÓCIO` (N/R/EN/ER/CN/CR), `TIPO DOCUMENTO` (APÓLICE/FATURA/ENDOSSO),
`SITUAÇÃO` (status do documento). São atributos de baixa cardinalidade do próprio movimento.

### 1.3 Dimensões conformadas
| Dimensão | Chave de negócio | Atributos principais | Origem |
|---|---|---|---|
| **DIM_PESSOA** | `CPF_LIMPO` (CPF ou CNPJ) | nome, SEXO, IDADE/FAIXA_ETARIA, **CARACTERÍSTICA** (especialidade), CIDADE/ESTADO, ESTADO CIVIL, **TIPO** (PF/PJ), CLIENTE DESDE, flags de contato, `STATUS_GLOBAL`, `RATING_ESTRELAS` | `RptClienteLista` + insights |
| **DIM_PRODUTO** | `NOME ABREVIADO DO PRODUTO` | RAMO, **TIPO_VIGENCIA** (RENOVÁVEL/RECORRENTE/TRANSACIONAL via `PRODUCT_TYPE_MAP`) | produção + `parameters.py` |
| **DIM_SEGURADORA** | `SEGURADORA (ABREVIADO)` | nome completo | produção |
| **DIM_TEMPO** | `data` | ano, mês, trimestre, safra (AAAA-MM) | derivada de `INÍCIO/TÉRMINO DE VIGÊNCIA` |
| **DIM_PRODUTOR** | `PRODUTOR` (normalizado) | — | produção (`normalize_producer`) |

> **DIM_PESSOA é a dimensão central.** Representa **qualquer pessoa (física ou jurídica),
> cliente ou não-cliente** — a corretora atende **público geral** e o cadastro inclui
> não-clientes; por isso "pessoa" (não "cliente", que excluiria os prospects, nem
> "cooperado", específico do recorte atual). No recorte de **cooperados médicos**, a
> `CARACTERÍSTICA` (especialidade) é o atributo mais rico e 100% confiável.
> `RATING_ESTRELAS`/`STATUS_GLOBAL` são atributos derivados pelo motor.

## 2. Fatos secundários (snapshots periódicos)

- **FATO_STATUS_PRODUTO** — grão *pessoa × seguradora × produto* (snapshot
  *accumulating*): status ATIVO/INATIVO/CANCELADO, valores do último ciclo. Materializa-se
  hoje como `producao_status` / `producao_enriquecida`.
- **FATO_SNAPSHOT_MENSAL** — grão *pessoa × produto × mês* (snapshot *periodic*): pessoas
  e prêmio ativos por mês. Materializa-se como `snapshot_mensal` (a partir do grão de ciclo).

## 3. Mapeamento: star schema → marts atuais (gold)

| Elemento dimensional | Mart/Parquet atual |
|---|---|
| FATO_PRODUCAO | `comercial/parquet/producao_grain` + `producao_enriquecida` |
| FATO_STATUS_PRODUTO | `producao_status` |
| FATO_SNAPSHOT_MENSAL | `snapshot_mensal` / `snapshot_grain` |
| DIM_PESSOA | `clientes_crm` + `marketing/base_cooperados` |
| DIM_PRODUTO | derivável de `producao_status` + `PRODUCT_TYPE_MAP` |
| DIM_SEGURADORA | derivável de `market_share` / produção |
| DIM_PRODUTOR | `performance_produtor` |

As demais visões (curva ABC, market share, mix, renovações, win-back, margens, personas…)
são **agregações** sobre este modelo — no Power BI, viram *medidas* sobre o fato + dimensões,
em vez de tabelas separadas.

## 4. Por que formalizar (mesmo sem materializar tudo)
- **Reuso e consistência:** dimensões conformadas evitam recalcular a mesma entidade em N
  marts; o número não diverge entre visões.
- **Consumo em BI:** o Power BI (futuro) modela melhor com fato + dimensões do que com
  tabelas *flat* isoladas (relacionamentos, *drill*, *slicers*).
- **Rastreabilidade conceitual:** o grão do fato = grão da base bruta (com `ID_LINHA`),
  preservando a linhagem.

> Diagrama visual (figura) e materialização de 1 fato + 2–3 dimensões como demonstração são
> trabalhos futuros (ver `docs/EVOLUCAO_PLATAFORMA.md`). Dicionário de campos em
> `docs/DICIONARIO_DE_DADOS.md`.
