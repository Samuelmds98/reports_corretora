# Regras por Produto e Contratos de Dados

> Como documentar regras de negócio que **mudam por produto** (vigência, ativo, qual
> valor somar) e como formalizar o que cada arquivo de entrada precisa entregar
> (contrato de dados). Escrito para o "Raio X Cooperados", mas o padrão serve para o TCC.

## 1. O problema

Produtos diferentes têm comportamentos diferentes na base bruta:

- Uma **apólice RENOVÁVEL** (ex.: AUTOMÓVEL) é renovada ano a ano → várias linhas N/R
  para a MESMA apólice. Para "valor vigente" interessa **só o último ciclo**.
- Um produto **RECORRENTE** (ex.: ODONTO, VIDA) chega como **FATURA** mensal → cada
  linha é um pagamento distinto; a soma de todas faz sentido, e o "ativo" é "faturou
  nos últimos 90 dias".
- Um produto **TRANSACIONAL** (ex.: VIAGEM) é pontual → "ativo" é vigência atual OU
  vigência nos últimos 12 meses.

Hoje essas regras estão **espalhadas** em código (`functions.py`, `analytics.py`) e
no mapa `PRODUCT_TYPE_MAP` (`parameters.py`). Funciona, mas é difícil para o negócio
auditar "qual regra vale para o produto X" sem ler Python.

## 2. Recomendação: um registro único de regras por produto (machine-readable)

Centralizar, num só lugar versionado, **uma linha por produto** com todos os atributos
que o motor consulta. Hoje só existe `tipo_vigencia`; a proposta é expandir para um
dicionário de atributos. Duas opções:

**Opção A (recomendada p/ agora) — manter em Python, só enriquecer `parameters.py`.**
Zero dependência nova, fácil de testar:

```python
# parameters.py
PRODUCT_RULES = {
    "AUTOMÓVEL": {
        "tipo_vigencia": "RENOVÁVEL",
        "regra_ativo": "vigencia_atual",      # Início <= hoje <= Término, sem CN/CR
        "valor_vigente": "ultimo_ciclo",      # soma só o último ciclo da apólice
        "chave_apolice": "RAIZ_APÓLICE",      # como ligar renovações da mesma apólice
        "fonte_regra": "Página1.html (RAMO ATUAL × TIPO DE VIGÊNCIA)",
    },
    "ODONTO": {
        "tipo_vigencia": "RECORRENTE",
        "regra_ativo": "fatura_90d",          # houve fatura nos últimos 90 dias
        "valor_vigente": "soma_total",        # cada fatura é um pagamento distinto
        "chave_apolice": "APÓLICE",
        "fonte_regra": "Página1.html",
    },
    "VIAGEM": {
        "tipo_vigencia": "TRANSACIONAL",
        "regra_ativo": "vigencia_ou_12m",
        "valor_vigente": "soma_total",
        "chave_apolice": "APÓLICE",
        "fonte_regra": "Página1.html",
    },
    # ... 1 entrada por produto
}
# Compat: PRODUCT_TYPE_MAP pode ser derivado deste registro.
PRODUCT_TYPE_MAP = {k: v["tipo_vigencia"] for k, v in PRODUCT_RULES.items()}
```

O código passa a **perguntar ao registro** em vez de embutir `if tipo == "RENOVÁVEL"`.
Ganho: regras viram dado, não lógica solta; dá para exportar o registro para uma aba
Excel "Dicionário de Regras" que o gerente lê sem abrir o Python.

**Opção B — externalizar para YAML/CSV** (`config/product_rules.yaml`). Vale a pena
**quando o negócio quiser editar as regras sem mexer em código**. Custo: um loader +
validação de schema. Recomendo só migrar para B depois que o conjunto de atributos
estabilizar (evitar overengineering — ver CLAUDE.md).

> **Regra de ouro:** um produto sem entrada no registro deve **falhar barulhento**
> (ou cair num default explícito `INDEFINIDO` já sinalizado na DQ), nunca ser tratado
> silenciosamente como renovável.

### Tabela-espelho para o TCC / negócio

Manter também uma versão legível (esta tabela), gerada idealmente a partir do registro:

| Produto      | Tipo         | "Ativo" quando…                | Valor vigente | Chave p/ ligar renovações |
|--------------|--------------|--------------------------------|---------------|---------------------------|
| AUTOMÓVEL    | RENOVÁVEL    | Início ≤ hoje ≤ Término, s/ CN | último ciclo  | RAIZ_APÓLICE              |
| RESIDENCIAL  | RENOVÁVEL    | idem                           | último ciclo  | RAIZ_APÓLICE              |
| ODONTO       | RECORRENTE   | fatura nos últimos 90 dias     | soma total    | APÓLICE                   |
| VIDA EM GRUPO| RECORRENTE   | fatura nos últimos 90 dias     | soma total    | APÓLICE                   |
| VIAGEM       | TRANSACIONAL | vigência atual OU últimos 12m  | soma total    | APÓLICE                   |

## 3. Contratos de dados (data contracts) das entradas

Um **contrato de dados** é a especificação do que cada arquivo de entrada precisa
entregar para o pipeline funcionar — colunas, tipos, obrigatoriedade, domínio de
valores e **semântica**. Serve de acordo entre quem exporta os relatórios (origem) e
o motor (consumidor). Proposta de estrutura, um arquivo por entrada:

```yaml
# contracts/RptAnaliseProducao.yaml
arquivo: RptAnaliseProducao.xlsx
grão: 1 linha por movimento (apólice nova/renovação/endosso/fatura/cancelamento)
chave_logica: [CPF/CNPJ, SEGURADORA (ABREVIADO), RAMO, APÓLICE, TIPO DE NEGÓCIO, INÍCIO DE VIGÊNCIA]
colunas:
  - nome: "CPF/CNPJ"
    tipo: string
    obrigatoria: true
  - nome: "TIPO DE NEGÓCIO"
    tipo: categórica
    obrigatoria: true
    valores_aceitos: [N, R, EN, ER, CN, CR]   # apólice / endosso / cancelamento
  - nome: "INÍCIO DE VIGÊNCIA"
    tipo: data
    obrigatoria: true
    regra: "<= TÉRMINO DE VIGÊNCIA"
  - nome: "PRÊMIO LÍQ. DO SEGURO"
    tipo: numérico
    obrigatoria: true
    regra: ">= 0 (zero/negativo vira apontamento na DQ, não erro)"
  - nome: "COMISSÃO"
    tipo: numérico
    nota: "fonte única via get_comissao_col; confirmar COMISSÃO vs TOTAL com o negócio"
  - nome: "SITUAÇÃO"
    tipo: categórica
    valores_aceitos: [Ativa, Renovada, Vencida, Cancelada, Perda total]
    nota: "status do DOCUMENTO. Só `Ativa` é vigente; `Renovada` = linha SUBSTITUÍDA
           por uma renovação (inativa). Ver caveat abaixo."
  - nome: "USUÁRIO DA INCLUSÃO"
    tipo: categórica
    nota: "= MIGRACAO marca carga histórica (~40% da base); enviesa séries de venda"
  - nome: "PRODUTOR"
    tipo: categórica
    nota: "vendedor/produtor — dimensão de performance (track comercial)"
observacoes:
  - "CARACTERISTICA (produção) é SEM acento; no cadastro é CARACTERÍSTICA — não unificar à toa."
```

### ⚠️ Caveats de domínio que mudam a leitura (registrar e respeitar)

1. **`SITUAÇÃO` é o status do documento, não da apólice efetiva.** Semântica confirmada
   com o negócio:
   - **`Ativa`** = único valor que indica vigência. Mas pode estar **defasado**: uma
     apólice cujo `TÉRMINO` já passou deveria virar `Renovada`/`Vencida` e às vezes
     segue `Ativa`. ⇒ Detector `build_situacao_ativa_vencida` (DQ3): apólice `Ativa`
     com `TÉRMINO < hoje` (220 casos nos dados reais, até 800+ dias defasada).
   - **`Renovada`** = linha **substituída** por uma renovação ⇒ **inativa**; existe outro
     registro `Ativa` do mesmo negócio.
   - Uma apólice pode ainda estar `Ativa` e ter um **endosso de cancelamento** na mesma
     apólice que a cancela de fato sem mudar a `SITUAÇÃO`. ⇒ Detector
     `build_active_with_cancellation` (DQ1). *Obs.: o comportamento de vigência dos
     ENDOSSOS ainda será confirmado com o backoffice — por isso DQ1/DQ3 olham apólices (N/R).*
   - `build_status_vs_situacao` mede a concordância motor × situação (89% nos dados
     reais; o que sobra é majoritariamente `Ativa` defasada).

2. **Renovação cadastrada como negócio novo (sem linkar a apólice antiga).** A antiga
   vira `Vencida` (em vez de `Renovada`) e a renovação entra como `N`. Efeitos:
   **infla "negócio novo"**, **subestima a taxa de renovação** e **quebra o link de
   ciclo** (a `RAIZ_APÓLICE` não casa quando o número muda). O `Log_Apolices_Conflito`
   pega só o caso de mesma raiz; o número totalmente diferente é detectado por
   `operacional.build_renewal_as_new` (DQ2, heurística por datas + raiz diferente).
   É um problema de **processo operacional/cadastro**, não do motor.

3. **Confiabilidade dos valores (prêmio/comissão) é baixa** (ver CLAUDE.md) — por isso
   o foco em métricas não-monetárias e o uso das métricas operacionais para **chamar
   atenção** aos furos de cadastro, não para fechar caixa.

**Por que escrever isso, mesmo sem validar automaticamente:**

1. **Onboarding/TCC** — qualquer pessoa entende o input sem abrir o Excel.
2. **Defesa contra mudança silenciosa** — se a origem trocar um código de
   `TIPO DE NEGÓCIO` ou renomear uma coluna, o contrato é o lugar onde isso é discutido.
3. **Base para o gate de qualidade** — o contrato vira teste.

### Como tratar (enforce) o contrato — em camadas

- **Camada 0 — documento** (este YAML/markdown). Custo zero, valor alto. Comece aqui.
- **Camada 1 — guardrail leve na leitura** (já existe `guardrails.build_run_context`):
  ao carregar, verificar **presença das colunas obrigatórias** e **domínio de
  `TIPO DE NEGÓCIO`**; valores fora do contrato viram WARNING (não derrubam o run).
- **Camada 2 — DQ existente** (`data_quality_advanced.py`): regras de conteúdo
  (prêmio ≤ 0, comissão > prêmio, vigência invertida) já implementam parte do contrato.
  **Amarrar cada regra de DQ a uma cláusula do contrato** (rastreabilidade da regra).
- **Camada 3 — validação declarativa (opcional)** com `pandera` ou `pydantic`:
  o YAML do contrato vira um `DataFrameSchema` e a validação roda no início do
  pipeline. Só adotar se a Camada 1+2 não bastarem — evitar dependência prematura.

> Princípio que o projeto já segue: **o pipeline só sinaliza, nunca corrige**
> (ver `data_quality_advanced.py`). O contrato segue a mesma filosofia — ele define o
> "certo", a DQ aponta os desvios, e a decisão de saneamento fica com o negócio.

## 4. Checklist de adoção (incremental)

1. [ ] Escrever os 2 contratos em markdown/YAML (`RptAnaliseProducao`, `RptClienteLista`).
2. [ ] Expandir `PRODUCT_TYPE_MAP` → `PRODUCT_RULES` (Opção A) e derivar o mapa atual.
3. [ ] Gerar a aba "Dicionário de Regras" no relatório a partir de `PRODUCT_RULES`.
4. [ ] Amarrar cada regra de DQ a uma cláusula do contrato (comentário/coluna `REGRA`).
5. [ ] (Opcional) Guardrail de schema na leitura; (opcional) `pandera` na Camada 3.

## Relacionados

- `docs/GUIA_METRICAS.md` — §12 Agenda de Renovações (uso de `PREMIO_ULTIMO_CICLO`).
- `docs/Definição de Arquitetura e Regras de Negócio.md` — regras completas de vigência.
- `src/parameters.py` — `PRODUCT_TYPE_MAP` (fonte de verdade: `Página1.html`).
- `src/guardrails.py`, `src/data_quality_advanced.py` — onde o enforce já mora.
