# Raio X Cooperados — Vínculo com o MBA em Gestão de BI

> Como o projeto evidencia, na prática, as competências de um **MBA em Gestão de
> Business Intelligence**. Estrutura sugerida para apresentar ao coordenador: cada
> disciplina/competência do curso mapeada ao que o projeto entrega como prova.

## Tese central

O projeto demonstra a **jornada de maturidade analítica de uma organização real**: sair de
**duas planilhas soltas** (decisão por achismo) para um **produto de dados governado**,
segmentado em **três públicos** (Comercial, Operacional/Qualidade e Marketing) e com caminho
claro de evolução para **plataforma de BI**. Não é só
"fazer gráficos" — é **gerir o ciclo de vida da informação**: ingestão → qualidade →
modelagem → métricas → consumo → governança → estratégia. Esse é exatamente o escopo da
*gestão* de BI (≠ apenas a parte técnica).

## Mapa: competência do MBA-BI × evidência no projeto

| Competência / disciplina típica | Como o projeto evidencia |
|---|---|
| **Modelagem de dados / Data Warehouse** | Camadas medallion (bronze/silver/gold), marts por público, definição de **grão** (produto, ciclo, cliente), tabela-fato `producao_enriquecida` para o Power BI. |
| **ETL / Engenharia de dados** | Pipeline `Main.py`: leitura → saneamento → transformação → carga; idempotência por hash; Parquet como camada de serving; DuckDB como camada de consulta. |
| **Qualidade e Governança de dados** | DQ que **só sinaliza** (prêmio zerado, comissão>prêmio, duplicatas, outliers), **contratos de dados** (`REGRAS_POR_PRODUTO_E_CONTRATOS.md`), **linhagem** ponta-a-ponta (lastro até a linha bruta), histórico de qualidade (`dq_history`). |
| **Métricas e KPIs de negócio** | Curva ABC/share-of-wallet, market share, **taxa de renovação** (retenção), churn/cancelamento, margem (taxa de comissão efetiva), cross-sell, performance de produtor; no Marketing, **mix de aquisição** (prospects × produto por especialidade) e **audiência alcançável** (e-mail + consentimento). |
| **Visualização e Data Storytelling** | 28 relatórios HTML com **insights + recomendações dinâmicos**, portais de navegação por público, padrão visual corporativo; integração com Power BI. |
| **Regras de negócio / Domínio** | Motor de status/rating, semântica de `SITUAÇÃO` (status do documento ≠ apólice), tipos de vigência por produto, correção da inflação multi-ciclo. |
| **Gestão de produtos de dados / Stakeholders** | Segmentação **Comercial × Operacional/Qualidade × Marketing** atendendo a 3 públicos com necessidades distintas — decisão de *produto*, não só técnica. O Marketing olha a base inteira (cliente × prospect), cobrindo o ponto cego do Comercial. |
| **Segmentação de mercado / Marketing analítico** | Personas (sexo, estado civil, tipo), demografia (idade/década/especialidade) cliente × prospect, alvos de aquisição por especialidade e dimensionamento de audiência endereçável por canal. |
| **Estratégia e maturidade analítica** | Avaliação honesta do estágio atual + **roadmap de evolução para plataforma** (DuckDB, orquestração, app interativo, contratos), com escopo de MVP/POC vs. produção. |
| **Tomada de decisão baseada em dados** | Listas acionáveis (renovações priorizadas, win-back, cross-sell por especialidade) e diagnósticos de processo (renovação-como-novo, status defasado) que viram **ação** no negócio. |

## Narrativa para a banca (3 atos)

1. **Problema real, dado sujo.** Uma corretora decide no Excel; os valores são pouco
   confiáveis e o cadastro tem furos. O desafio de BI aqui não é o gráfico — é **confiar no
   número** e **expor o que está errado**.
2. **Solução que prioriza confiança.** Em vez de "consertar" os dados silenciosamente, o
   projeto **rastreia** (linhagem), **sinaliza** (DQ + detectores de processo) e **segmenta**
   por público — entregando inteligência comercial sólida, uma agenda de saneamento para o
   backoffice e uma leitura de marketing da base inteira (cliente × prospect, aquisição e
   audiência). É **gestão de BI**, não só ferramenta.
3. **Da planilha à plataforma.** O MVP DuckDB prova o conceito de camada única de consulta;
   o roadmap mostra a visão de maturidade (orquestração, app, contratos) — decisões de
   *gestão* (o que fazer agora vs. antes de produção, e por quê).

## Por que esta é uma boa tese de Gestão de BI (e não só de Ciência de Dados)

- O foco não é um modelo preditivo, e sim o **sistema de informação que sustenta a
  decisão**: qualidade, governança, métricas, públicos e maturidade.
- Há **decisões de gestão** explícitas e defendidas: priorizar o não-monetário, separar
  públicos, manter monolito, remover a aba de conferência, evoluir por incremento.
- Conecta **dado → métrica → decisão → ação** no contexto de um negócio real, que é a
  promessa central do BI.

---

### Sugestões de variação para o 3º documento (escolha do autor)

- **(A) Este formato** — mapeamento competências do MBA × evidências (recomendado: mostra
  domínio amplo da disciplina).
- **(B) Estudo de caso** — formato acadêmico (problema, metodologia, resultados, limitações,
  trabalhos futuros), útil se a banca espera estrutura de artigo.
- **(C) Roadmap de maturidade de BI** — posicionar o projeto num modelo de maturidade
  analítica (descritivo → diagnóstico → preditivo → prescritivo) e mostrar onde está e para
  onde vai. Bom para destacar a visão estratégica.
