# TODO — Próximos passos (próxima sessão)

> **Todos os itens abaixo são construídos DENTRO do track/painel de MARKETING**
> (`src/marketing.py`, `outputs/marketing/`, público `mkt` em `report_html.py`).
> Seguir o padrão de "adicionar nova visão" da seção 4 do `ARCHITECTURE.md`.
> Rodar e validar sempre com `python Main.py --input-dir data/exemplo --force`.

## Checklist

> ✅ **Itens 1–4 implementados** (ver `docs/CHANGELOG.md`). Validados com
> `python Main.py --input-dir data/exemplo --force`. Marketing passou a 10 abas /
> 11 HTMLs / +5 parquet / +5 workbooks de auditoria.

- [x] **1. Cruzamento prospects × mix da especialidade (campanhas acionáveis).**
  Para cada especialidade: nº de prospects (Marketing) + os produtos que os **clientes**
  daquela especialidade mais possuem (reusar `build_specialty_mix` do Comercial / penetração
  por especialidade). Saída: tabela "alvos de aquisição" = especialidade → prospects →
  produto(s) a ofertar. Nova função em `marketing.py` (recebe `df_mkt_base` + a penetração
  por especialidade do Comercial) + `_chart_*` + aba/HTML/auditoria no público `mkt`.

- [x] **2. Universo realmente acionável (audiência de campanha).**
  Quantos **prospects** têm e-mail **E** consentimento (`ACEITA RECEBER E-MAILS` + `EMAIL`).
  Reusar a lógica de `operacional.build_contact_lookup` (já calcula `EMAIL_ACIONAVEL` =
  e-mail + consentimento) aplicada ao `df_mkt_base`/cadastro, filtrando `STATUS == PROSPECT`.
  Saída: tamanho da audiência alcançável (total e %), idealmente quebrada por especialidade.

- [x] **3. Segmentação demográfica extra (personas).**
  Incluir `SEXO`, `ESTADO CIVIL` e `TIPO` de cliente (E/P/S) nas visões de Marketing
  (distribuições + comparativo cliente×prospect). Campos já vêm do cadastro em
  `df_cruzamento` → adicionar a `build_marketing_base` e novos builders de distribuição.
  ⚠️ Caveat de qualidade: `ESTADO CIVIL` ~41% preenchido; sinalizar "Não Informado".

- [x] **4. Sub-página "Growth — Dados a Coletar" (roadmap, não-implementável hoje).**
  Nova seção/HTML no painel Marketing **documentando** métricas futuras e dados a capturar
  (não há dado para calcular agora — é um roadmap visual para o gestor):
  Origem do lead · Engajamento de campanha (aberturas/cliques) · Motivos de não-conversão
  · Renda/porte real (hoje `RENDA`/`PROFISSÃO` são lixo) · Share of wallet externo ·
  NPS/indicação. Pode ser um HTML estático (cards) no padrão dos portais, sem builder de dados.

## Dívida técnica / bugs conhecidos

- [ ] **Warehouse (`scripts/build_warehouse.py`) — views `gold.*` quebradas + schema
  marketing ausente no sumário.** Ao rodar `python scripts/build_warehouse.py`, as views
  `gold.kpis` e `gold.qualidade_resumo` são puladas com `Catalog Error: Table with name
  renovacao_como_novo does not exist` — o SQL da view referencia a tabela sem qualificar o
  schema (`operacional.renovacao_como_novo`). Além disso, o `marketing.*` é criado mas não
  aparece na string de sumário final (`schemas comercial / operacional / gold`). Corrigir o
  schema-qualify das views gold e incluir `marketing` no sumário. (Pré-existente; detectado
  ao regenerar o warehouse no rebrand.)

## Notas para quem continuar
- Confiabilidade de valores monetários é baixa → manter foco **não-monetário** (contagens/datas).
- 68% da base são **prospects** (invisíveis ao Comercial, que é grão de produção) — é o
  coração do track Marketing.
- Geografia (`CIDADE`/`ESTADO`/`BAIRRO`, ~54% preenchido) e coorte de aquisição
  (`CLIENTE DESDE`, 86%) são extras de alto valor para Marketing — candidatos pós-checklist
  (ver `docs/interno/DATA_DISCOVERY.md`).
- **Segurança:** publicar no GitHub só após rodar com `data/exemplo` (ver `CONTEXT.md`).
