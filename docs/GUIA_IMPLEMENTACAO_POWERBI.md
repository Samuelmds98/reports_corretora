# Guia de Implementação no Power BI

> Como reconstruir cada métrica do `GUIA_METRICAS.md` no Power BI: qual Parquet usar,
> quais campos e tipos, com qual agrupamento/granularidade, a medida DAX e o gráfico
> sugerido. No fim, as **pegadinhas** de tipo/qualidade que mais quebram o modelo.

---

## 0. Antes de tudo: carregar os Parquets e definir o modelo

### Carregar
- **Pasta inteira:** *Obter Dados → Pasta →* `outputs/parquet/` → *Combinar e Transformar*.
  O Power BI lê cada `.parquet` como uma consulta.
- **Arquivo único:** *Obter Dados → Parquet →* selecione o arquivo desejado.
- O histórico de qualidade é separado: *Obter Dados → Parquet →* `outputs/dq_history.parquet`.

### Tabelas disponíveis (papéis)
| Parquet | Papel | Grão |
|---|---|---|
| `producao_grain` | **Fato atômico** — linha bruta com `ID_LINHA` | 1 linha por registro de produção |
| `producao_enriquecida` | **Fato produto** + perfil + tipo de vigência | 1 linha por `CPF×SEGURADORA×PRODUTO` |
| `snapshot_grain` | **Fato mês** — produto explodido por mês | 1 linha por `produto×mês` |
| `producao_status` | igual à enriquecida, sem perfil | 1 linha por produto |
| `clientes_crm` | **Dimensão cooperado** (cadastro + rating/status) | 1 linha por CPF |
| `curva_abc`, `market_share`, `cohort_sazonalidade`, `demografico`, `mix_especialidade`, `agenda_renovacoes`, `winback`, `*_2025plus` | atalhos já agregados | — |
| `run_context` | metadados da execução (janela, órfãos) | 1 linha |

> **Para reconstruir** as métricas (e auditar em DAX), use os 3 fatos de grão:
> `producao_grain`, `producao_enriquecida`, `snapshot_grain`. As tabelas agregadas
> servem de **conferência** (devem bater com as suas medidas).

### Modelo (relacionamentos sugeridos)
```
clientes_crm[CPF_LIMPO] 1 ──── * producao_enriquecida[CPF_LIMPO]
clientes_crm[CPF_LIMPO] 1 ──── * producao_grain[CPF_LIMPO]
clientes_crm[CPF_LIMPO] 1 ──── * snapshot_grain[CPF_LIMPO]
dq_history            → tabela autônoma (sem relação)
run_context           → tabela autônoma (cartões de contexto)
```
`clientes_crm` é a dimensão; os fatos se ligam por `CPF_LIMPO`.

### Tipos de dados (aplicar na transformação) — crítico
| Campo | Tipo no Power BI | Por quê |
|---|---|---|
| `CPF_LIMPO`, `ID_LINHA`, `ARQUIVO_ORIGEM` | **Texto** | `CPF_LIMPO` tem zeros à esquerda (11/14 díg.) — número **perde** os zeros |
| `LINHA_ORIGEM` | Número inteiro | — |
| `PRÊMIO LÍQ. DO SEGURO`, `COMISSÃO`, `SOMA_*`, `TOTAL_*` | Número decimal | valores financeiros |
| `INÍCIO/TÉRMINO DE VIGÊNCIA` (em `producao_grain`) | Data/hora | datetime |
| `PRIMEIRO_INICIO`, `ULTIMO_TERMINO` (em `producao_status`) | Data | já são `date` |
| `MES_REFERENCIA`, `SAFRA_MES_VIGENCIA` | **Texto** (`AAAA-MM`) | use como eixo categórico ordenável |
| `RATING_ESTRELAS`, `LINHA_ORIGEM`, contagens | Número inteiro | — |

---

## 1. Curva ABC

- **Fonte:** `producao_grain` (rebuild) ou `producao_enriquecida`.
- **Campos:** `CPF_LIMPO` (texto), `PRÊMIO LÍQ. DO SEGURO` (decimal).
- **Granularidade:** somar por `CPF_LIMPO`.
- **Medidas DAX:**
```DAX
Premio Total = SUM(producao_grain[PRÊMIO LÍQ. DO SEGURO])

-- % acumulado (ranqueando CPFs por prêmio desc)
% Acumulado ABC =
VAR Total = CALCULATE([Premio Total], ALL(producao_grain))
VAR Acum =
    CALCULATE(
        [Premio Total],
        FILTER(
            ALL(clientes_crm[CPF_LIMPO]),
            [Premio Total] >=
                CALCULATE([Premio Total], VALUES(clientes_crm[CPF_LIMPO]))
        )
    )
RETURN DIVIDE(Acum, Total)

Classe ABC =
SWITCH(TRUE(),
    [% Acumulado ABC] <= 0.80, "A (Top 80%)",
    [% Acumulado ABC] <= 0.95, "B (15%)",
    "C (Cauda 5%)")
```
- **Gráfico:** **Pareto** — barras de `Premio Total` por CPF (ordenado desc) + linha de
  `% Acumulado ABC` no eixo secundário, com linha de referência em 80%.
- **Confere com:** `curva_abc.parquet` (`TOTAL_PREMIO_LIQ`, `CURVA_ABC`).

---

## 2. Market Share

- **Fonte:** `producao_grain`.
- **Campos:** `SEGURADORA (ABREVIADO)` (texto), `PRÊMIO LÍQ. DO SEGURO` (decimal).
- **Granularidade:** somar por seguradora.
- **Medidas:**
```DAX
Premio Seguradora = SUM(producao_grain[PRÊMIO LÍQ. DO SEGURO])
Market Share % =
    DIVIDE([Premio Seguradora],
           CALCULATE([Premio Seguradora], ALL(producao_grain[SEGURADORA (ABREVIADO)]))) * 100
```
- **Gráfico:** **barras horizontais** por seguradora, ordenadas por prêmio, com rótulo `Market Share %`.
- **Confere com:** `market_share.parquet`.

---

## 3. Cohort / Sazonalidade

- **Fonte:** `producao_enriquecida` (tem `PRIMEIRO_INICIO` por produto).
- **Campos:** `PRIMEIRO_INICIO` (data), `CPF_LIMPO` (texto), `PRODUTO` (texto), `SOMA_PREMIO_LIQ`.
- **Granularidade:** agrupar por mês de `PRIMEIRO_INICIO` (`SAFRA`).
- **Coluna calculada / Power Query:** `SAFRA = FORMAT([PRIMEIRO_INICIO], "yyyy-MM")`.
- **Medidas:**
```DAX
Premio Safra      = SUM(producao_enriquecida[SOMA_PREMIO_LIQ])
Clientes na Safra = DISTINCTCOUNT(producao_enriquecida[CPF_LIMPO])
```
- **Gráfico:** **linha** (ou colunas) com `SAFRA` no eixo X e `Premio Safra`/`Clientes na Safra`.
- **Confere com:** `cohort_sazonalidade.parquet`.
- ⚠️ A 1ª safra (2024-01) está inflada por contratos pré-corte — destaque/exclua-a
  (ver `GUIA_METRICAS.md` §8).

---

## 4. Demografia / Taxa de Conversão

- **Fonte:** `clientes_crm` (dimensão cooperado).
- **Campos:** `CIDADE`, `ESTADO`, `SEXO`, `ESTADO CIVIL`, `FAIXA_ETARIA`, `CARACTERÍSTICA`
  (todos texto), `STATUS_GLOBAL` (texto), `RATING_ESTRELAS` (inteiro).
- **Granularidade:** agrupar pela(s) coluna(s) de perfil escolhida(s).
- **Medidas:**
```DAX
Total Cooperados = DISTINCTCOUNT(clientes_crm[CPF_LIMPO])
Cooperados Ativos =
    CALCULATE([Total Cooperados], clientes_crm[STATUS_GLOBAL] = "ATIVO")
Taxa Conversao % = DIVIDE([Cooperados Ativos], [Total Cooperados]) * 100
```
- **Gráfico:** **matriz** (especialidade × faixa etária) com `Taxa Conversao %`, ou
  **mapa de árvore** por cidade. Use segmentações (Sexo, Especialidade).
- **Confere com:** `demografico.parquet`.

---

## 5. Calculadora de Produtos (grão de produto)

- **Fonte:** `producao_enriquecida` (ou `producao_status`).
- **Campos:** `CPF_LIMPO`, `SEGURADORA`, `PRODUTO`, `STATUS_PRODUTO`, `SOMA_PREMIO_LIQ`,
  `SOMA_COMISSAO`, `TIPO_PRODUTO`.
- **Granularidade:** já está no grão de produto (1 linha por produto).
- **Uso:** tabela de apoio / drill. Para reconstruir do zero a partir do bruto, agrupe
  `producao_grain` por `CPF_LIMPO + SEGURADORA (ABREVIADO) + NOME ABREVIADO DO PRODUTO`
  e some prêmio/comissão (o **status** é melhor consumir pronto — ver §9).
- **Gráfico:** tabela/matriz com filtro por `STATUS_PRODUTO` e `TIPO_PRODUTO`.

---

## 6. Mix por Especialidade

- **Fonte:** `producao_enriquecida` filtrada por `STATUS_PRODUTO = "ATIVO"`.
- **Campos:** `CARACTERÍSTICA` (texto), `PRODUTO` (texto), `CPF_LIMPO` (texto).
- **Granularidade:** agrupar por `CARACTERÍSTICA × PRODUTO`.
- **Medidas:**
```DAX
Cooperados com Produto =
    CALCULATE(DISTINCTCOUNT(producao_enriquecida[CPF_LIMPO]),
              producao_enriquecida[STATUS_PRODUTO] = "ATIVO")

Cooperados Ativos na Especialidade =
    CALCULATE(DISTINCTCOUNT(producao_enriquecida[CPF_LIMPO]),
              producao_enriquecida[STATUS_PRODUTO] = "ATIVO",
              ALLEXCEPT(producao_enriquecida, producao_enriquecida[CARACTERÍSTICA]))

Penetracao % = DIVIDE([Cooperados com Produto], [Cooperados Ativos na Especialidade]) * 100
```
- **Gráfico:** **heatmap/matriz** Especialidade (linhas) × Produto (colunas), valor `Penetracao %`.
- **Confere com:** `mix_especialidade.parquet`.
- ⚠️ Use a `CARACTERÍSTICA` de `producao_enriquecida`/`clientes_crm` (com acento, do
  cadastro), **não** a `CARACTERISTICA` (sem acento) de `producao_grain`.

---

## 7. Agenda de Renovações

- **Fonte:** `agenda_renovacoes.parquet` (já é a lista pronta) ou reconstrua de
  `producao_enriquecida` (filtre `STATUS_PRODUTO=ATIVO` e `TIPO_PRODUTO="RENOVÁVEL"`).
- **Campos:** `INICIO_ULTIMO_CICLO`/`ULTIMO_TERMINO` (datas), `URGENCIA`,
  `PREMIO_ULTIMO_CICLO`, `COMISSAO_ULTIMO_CICLO`, `RATING_ESTRELAS`.
- **Atenção ao valor:** use `PREMIO_ULTIMO_CICLO`/`COMISSAO_ULTIMO_CICLO` (somente o
  ciclo de vigência mais recente da apólice), **não** `SOMA_*`. Se reconstruir de
  `producao_enriquecida`/`producao_grain`, filtre `EH_ULTIMO_CICLO = TRUE` antes de somar,
  senão renovações de anos anteriores da mesma apólice inflam o prêmio em risco.
- **Coluna calculada (dias até vencer):**
```DAX
Dias Ate Vencer = DATEDIFF(TODAY(), producao_enriquecida[ULTIMO_TERMINO], DAY)
Urgencia =
SWITCH(TRUE(),
    [Dias Ate Vencer] < 0, "Vencida",
    [Dias Ate Vencer] <= 30, "🔴 Até 30 dias",
    [Dias Ate Vencer] <= 60, "🟡 31 a 60 dias",
    [Dias Ate Vencer] <= 90, "🟢 61 a 90 dias",
    "> 90 dias")
```
- **Gráfico:** **colunas** por `Urgencia` (contagem) com prêmio em rótulo; tabela
  detalhada ordenada por `Dias Ate Vencer` e `RATING_ESTRELAS` desc.
- **Confere com:** `agenda_renovacoes.parquet`.

---

## 8. Win-Back

- **Fonte:** `winback.parquet` (pronto) ou reconstrua: `clientes_crm` com
  `STATUS_GLOBAL = "INATIVO"` + `producao_enriquecida` para o `ULTIMO_TERMINO` máximo
  nos últimos 12 meses.
- **Campos:** `CPF_LIMPO`, `DIAS_INATIVO` (inteiro), `TOTAL_PREMIO_HISTORICO` (decimal).
- **Gráfico:** **barras horizontais** top 20 por `TOTAL_PREMIO_HISTORICO`, cor por
  `DIAS_INATIVO`.
- **Confere com:** `winback.parquet`.

---

## 9. Snapshot Mensal Ativo

- **Fonte:** `snapshot_grain` (já explodido por mês — **não precisa refazer a explosão**).
- **Campos:** `MES_REFERENCIA` (texto `AAAA-MM`), `CPF_LIMPO`, `PRODUTO`, `SOMA_PREMIO_LIQ`.
- **Granularidade:** agrupar por `MES_REFERENCIA`.
- **Medidas:**
```DAX
Clientes Ativos Mes = DISTINCTCOUNT(snapshot_grain[CPF_LIMPO])
Produtos Ativos Mes = COUNTROWS(snapshot_grain)
Premio Mes          = SUM(snapshot_grain[SOMA_PREMIO_LIQ])
```
- **Gráfico:** **linha dupla** — `Clientes Ativos Mes` (eixo esq.) e `Premio Mes` (eixo dir.)
  por `MES_REFERENCIA`.
- **Confere com:** `snapshot_mensal.parquet`.
- ⚠️ Ignore/realce os primeiros meses de 2024 (efeito de borda).

---

## 10. Curva ABC / Market Share 2025+ (janeladas)

- **Fonte:** `producao_grain`, **filtrando** `INÍCIO DE VIGÊNCIA >= 2025-01-01`.
- **Medidas:** idênticas às §1 e §2, mas com o filtro de data aplicado (página/segmentação
  ou medida com `CALCULATE(..., producao_grain[INÍCIO DE VIGÊNCIA] >= DATE(2025,1,1))`).
- **Gráfico:** mesmos da ABC/Market Share.
- **Confere com:** `curva_abc_2025plus.parquet`, `market_share_2025plus.parquet`.
- ⚠️ Lembre: o recorte é por **`INÍCIO DE VIGÊNCIA`** = "originação no período", **não**
  receita reconhecida (ver `GUIA_METRICAS.md` §15).

---

## 10.1 Ótica da Comissão (o que a corretora recebe)

Use `COMISSÃO` (não `COMISSÃO TOTAL...`) para bater com os números oficiais.

### Curva ABC por Comissão
- **Fonte:** `producao_grain` (rebuild) ou `producao_enriquecida` (`SOMA_COMISSAO`).
- **Medida / gráfico:** iguais à §1, trocando prêmio por comissão:
```DAX
Comissao Total = SUM(producao_grain[COMISSÃO])
```
  Pareto por CPF (barras de comissão + % acumulado). **Confere com:** `curva_abc_comissao.parquet`.

### Margem / Market Share por Comissão (seguradora)
- **Fonte:** `producao_grain` agrupado por `SEGURADORA (ABREVIADO)`.
- **Medidas:**
```DAX
Comissao Seguradora = SUM(producao_grain[COMISSÃO])
Premio Seguradora   = SUM(producao_grain[PRÊMIO LÍQ. DO SEGURO])
Share Comissao %    = DIVIDE([Comissao Seguradora],
                             CALCULATE([Comissao Seguradora], ALL(producao_grain[SEGURADORA (ABREVIADO)]))) * 100
Taxa Comissao Efetiva % = DIVIDE([Comissao Seguradora], [Premio Seguradora]) * 100
```
- **Gráfico:** **barras horizontais** por seguradora ordenadas por `Taxa Comissao Efetiva %`
  (margem). **Confere com:** `margem_comissao_seguradora.parquet`.

### Margem por Comissão (produto)
- **Fonte:** `producao_grain` agrupado por `NOME ABREVIADO DO PRODUTO`.
- **Medida:** `Taxa Comissao Efetiva %` (mesma fórmula acima, por produto).
- **Gráfico:** barras por produto ordenadas pela taxa efetiva. **Confere com:**
  `margem_comissao_produto.parquet`.

### Margem por Comissão (SEGURADORA × PRODUTO)
- **Fonte:** `margem_comissao_seg_produto.parquet` (pronto) ou reconstrua de
  `producao_grain` agrupando por `SEGURADORA (ABREVIADO)` **e** `NOME ABREVIADO DO PRODUTO`
  (filtre `EH_ULTIMO_CICLO = TRUE` antes de somar).
- **Campos:** `TAXA_COMISSAO_EFETIVA_%`, `SHARE_PREMIO_%`, `SHARE_COMISSAO_%`,
  `N_SEGURADORAS_DO_PRODUTO`, `PRODUTO_EXCLUSIVO_SEGURADORA`.
- **Gráfico:** **dispersão** prêmio (X) × taxa efetiva (Y), tamanho da bolha = comissão,
  uma bolha por seguradora×produto. Lê-se: bolha à direita = bloco grande de prêmio; no
  alto = alta margem. **Confere com:** `margem_comissao_seg_produto.parquet`.
- **Por que este grão:** a margem por seguradora (acima) esconde que a liderança de prêmio
  pode vir de **um produto de alta margem concentrado** naquela seguradora (às vezes
  exclusivo dela). Este grão dá a comparação justa.

> **Insight-chave:** a concentração por **comissão** difere da por **prêmio** (as taxas
> variam). Compare ABC-prêmio × ABC-comissão e o market share × a taxa efetiva para achar
> parceiros/produtos de **alto volume e baixa margem** — e use o grão seguradora×produto
> para explicar a concentração.

---

## 11. Status do Produto e Rating — **consuma, não reconstrua**

`STATUS_PRODUTO`, `RATING_ESTRELAS` e `STATUS_GLOBAL` dependem de regras com janela de
cancelamento (CN/CR), faturas dos últimos 90 dias e a hierarquia top-down do rating —
**difíceis de reproduzir fielmente em DAX**. Recomendação: **consumir prontos** de
`producao_enriquecida`/`clientes_crm` e usá-los como filtro/atributo. Para auditar a
origem desses status, use os workbooks (`Calculadora_Produtos.xlsx`).

---

## 12. Contexto da execução (cartões de governança)

- **Fonte:** `run_context.parquet` (1 linha).
- **Campos:** `JANELA_INICIO`, `JANELA_FIM`, `MESES_NA_JANELA`, `N_CPF_PRODUTORES`,
  `N_CADASTRO`, `N_CATEGORIAS_CADASTRO`, `CPF_ORFAOS`, `PCT_ORFAOS`, `WARNINGS`.
- **Gráfico:** **cartões** no topo do relatório (janela temporal, % de órfãos) +
  caixa de texto com `WARNINGS`. Deixa explícito o recorte da base para quem lê.
- **Tendência de qualidade:** `dq_history.parquet` → **linha** com `RUN_DATE` no X,
  `QTD_REGISTROS_FLAGADOS` no Y, `REGRA_DQ` na legenda; filtre `SEVERIDADE = "CRÍTICO"`.

---

## 13. Pegadinhas que quebram o modelo (leia antes de publicar)

1. **`CPF_LIMPO` como número apaga zeros à esquerda.** Mantenha **Texto** em todas as
   tabelas, senão os relacionamentos não casam e CPFs somem.
2. **Acento em CARACTERÍSTICA.** `producao_grain` traz `CARACTERISTICA` (sem acento, da
   produção); `clientes_crm`/`producao_enriquecida` trazem `CARACTERÍSTICA` (com acento,
   do cadastro). Para mix/demografia use a **do cadastro**. Não tente juntar as duas por
   nome sem padronizar.
3. **Duas colunas de comissão** em `producao_grain`: `COMISSÃO` e
   `COMISSÃO TOTAL (CORRET + CO-CORRET)`. O pipeline usa **`COMISSÃO`** — use a mesma
   para bater com os números oficiais.
4. **Tipos de data divergentes:** `producao_grain` usa datetime; `producao_status`/
   `producao_enriquecida` usam `date`. Padronize antes de criar medidas de tempo.
5. **Janela por `INÍCIO DE VIGÊNCIA` (2024+).** Toda soma é da janela, não vitalícia;
   cohort/snapshot têm efeito de borda em 2024. Exponha isso com `run_context`.
6. **Órfãos:** há CPFs em `producao_grain` que não existem em `clientes_crm`. Em
   relacionamento, esses ficam "em branco" no lado cooperado. Decida se filtra ou exibe
   como "Sem cadastro" — e acompanhe `PCT_ORFAOS` do `run_context`.
7. **Reconciliação:** suas medidas DAX devem bater com os Parquets agregados
   (`curva_abc`, `market_share`...). Se não baterem, revise tipo de dado/filtro antes de
   suspeitar dos dados — e cruze com os workbooks de `outputs/auditoria/`.

---

## 14. Ordem sugerida de construção

1. Carregar `clientes_crm` (dimensão) + `producao_grain`, `producao_enriquecida`,
   `snapshot_grain` (fatos). Ajustar **tipos**.
2. Criar relacionamentos por `CPF_LIMPO`.
3. Cartões de `run_context` (governança) primeiro — para o leitor saber o recorte.
4. Construir ABC, Market Share, Snapshot (medidas das §1, §2, §9) e **conferir** com os
   Parquets agregados.
5. Demografia/Mix (dimensão cooperado) e Renovações/Win-Back.
6. Publicar com a aba de tendência de DQ (`dq_history`).
