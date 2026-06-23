# Reports Corretora — Pitch

> Documento executivo (1 página) para apresentação. Problema de negócio + solução proposta.

## Contexto

Corretora de seguros que atende **cooperados (médicos)**. Toda a informação de negócio
vive em **dois relatórios Excel brutos** exportados de um sistema: **produção** (apólices,
faturas e endossos — 39 colunas) e **cadastro** dos cooperados (33 colunas). Não há visão
consolidada: cada análise é feita à mão, no Excel, sem rastreabilidade e sem padrão.

## O problema de negócio

1. **Sem inteligência sobre a carteira.** Não se sabe, de forma confiável e repetível,
   quem são os clientes de alto valor, o que cada um tem, quem está prestes a renovar,
   quem caiu, qual o market share por seguradora, qual produto/parceiro dá mais margem.
2. **Confiabilidade baixa dos valores** (prêmio/comissão) — números monetários sujos
   impedem decisões financeiras diretas.
3. **Qualidade de cadastro e de processo comprometida**, distorcendo qualquer análise:
   - prêmios zerados, comissão maior que prêmio, duplicatas;
   - **renovação cadastrada como negócio novo** (infla "novo", esconde a retenção);
   - **status do documento defasado** (apólice vencida ainda marcada como "Ativa");
   - ~40% da base é **carga migrada**, que enviesa as séries de venda.
4. **Força de vendas e acionabilidade no escuro** — sem leitura de desempenho por
   produtor nem de quais clientes têm telefone/e-mail para serem trabalhados.
5. **Maioria da base invisível.** O Comercial enxerga só quem já comprou (grão de
   produção), mas **68% dos cooperados são prospects** — nunca converteram. Sem visão
   de quem ainda dá para conquistar, por especialidade, idade ou persona.

## A solução

Um **motor de analytics em Python** que, a partir dos dois Excel, **saneia, aplica as
regras de negócio, calcula status e rating por cliente** e gera um **"data warehouse
local"** pronto para consumo — com três pilares de diferenciação:

- **Segmentado por três públicos** (decisão do gestor): trilha **Comercial** (vendas/CRM:
  curva ABC, cross-sell, market share, agenda de renovações, win-back, margens,
  performance de produtor…), trilha **Operacional/Qualidade** (completude de cadastro,
  status×situação, detectores de furos de processo, acionabilidade, testes de DQ) e trilha
  **Marketing** (a base INTEIRA — cliente × prospect: demografia, personas, **alvos de
  aquisição** por especialidade, **audiência de campanha** realmente alcançável por e-mail).
- **Qualidade como cidadão de 1ª classe**: o motor **só sinaliza, nunca corrige** —
  expõe os furos de cadastro/processo para o backoffice sanear na origem.
- **Rastreabilidade total**: cada número de cada relatório tem o seu **lastro** até a
  linha exata do Excel bruto (arquivo + linha).

Enquanto os valores não são saneados, o foco é a **abordagem qualitativa/não-monetária**
(contagens, datas, especialidade, status) — robusta e já acionável.

## O que é entregue (em uma rodada de `python Main.py`)

- **Comercial:** workbook de 22 abas + **12 relatórios HTML** interativos com insights e
  recomendações + portal de navegação + Parquet para Power BI + workbooks de auditoria.
- **Operacional/Qualidade:** workbook de 9 abas + **5 HTML** + portal + DQ + logs.
- **Marketing:** workbook de 10 abas + **11 HTML** (status da base, especialidade, década,
  faixa etária, histograma, alvos de aquisição, audiência de campanha, personas
  sexo/estado civil/tipo, **roadmap "Growth — dados a coletar"**) + portal + parquet + auditoria.
- **Camada de consulta** (MVP de plataforma): um **DuckDB** sobre os dados, para SQL
  ad-hoc sobre toda a base num só lugar.
- **Índice central** que conecta os três painéis.

## Impacto

- **Comercial:** priorizar renovações por urgência e valor; reativar inativos; achar
  cross-sell por especialidade; identificar produto/parceiro de alta margem; ler a
  performance e a retenção da força de vendas.
- **Operacional:** uma lista concreta de **apólices com status defasado**, **prováveis renovações mal cadastradas**, **registros em regras críticas de DQ** —
  trabalho de saneamento priorizado, não achismo.
- **Marketing:** enxergar os **prospects** (a maioria invisível ao Comercial) e
  transformá-los em campanha — alvos de aquisição por especialidade com o produto de
  maior aderência, e o **tamanho real da audiência** alcançável por e-mail (com
  consentimento), não a base bruta.
- **Gestão:** a ferramenta transforma dois Excel soltos em **decisão baseada em dados**,
  com governança e um caminho claro de evolução para uma plataforma.
