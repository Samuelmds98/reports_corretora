# Guia de Auditoria — Como rastrear qualquer número até a origem

> Para o usuário final. Não é necessário saber programar.
> Tudo é feito abrindo arquivos Excel das pastas `outputs/<público>/auditoria/`.

---

## 1. A ideia em uma frase

**Todo número de qualquer relatório pode ser explicado, registro por registro, até a
linha exata do Excel de origem.** Para isso, cada análise tem um arquivo de auditoria
próprio na pasta `auditoria/` do seu público (`comercial/`, `operacional/`, `marketing/`).

---

## 2. Anatomia de um workbook de auditoria

Cada `.xlsx` de auditoria tem **2 abas**:

| Aba | O que é | Para que serve |
|---|---|---|
| **1_Agregado** | Os números (igual ao que aparece no relatório principal). | Ponto de partida: escolha a linha/número que quer conferir. |
| **2_Lastro** | **Todos** os registros de origem que alimentam aqueles números. | A prova: aqui estão as linhas que foram somadas/contadas. |

> O fechamento "soma do lastro == número agregado" é verificado automaticamente a cada
> execução: o pipeline re-agrega o lastro por um caminho independente e **só avisa no
> console se algo não fechar**. O artefato entregue fica enxuto (Agregado | Lastro).

### A âncora de origem (as 3 primeiras colunas do Lastro)

Toda linha da aba **2_Lastro** começa com:

| Coluna | Significado |
|---|---|
| `ID_LINHA` | Identificador único do registro (ex: `PROD-001234`, `CAD-000045`). |
| `ARQUIVO_ORIGEM` | De qual Excel bruto veio (`RptAnaliseProducao.xlsx` ou `RptClienteLista.xlsx`). |
| `LINHA_ORIGEM` | A **linha exata** naquele Excel (já considerando o cabeçalho na linha 1). |

> Com `ARQUIVO_ORIGEM` + `LINHA_ORIGEM` você abre o arquivo bruto e vai direto na
> linha que originou o registro. É a rastreabilidade ponta a ponta.

---

## 3. Receita de bolo: "quero conferir este número"

1. **Identifique a análise** (ex: Curva ABC, Market Share, Cohort...).
2. **Abra o workbook** correspondente na pasta `auditoria/` do público (ver tabela na seção 4).
3. Na aba **1_Agregado**, localize a linha do número que quer conferir e anote a
   **chave** dela (ex: o `CPF_LIMPO`, a `SEGURADORA`, a `SAFRA_MES_VIGENCIA`...).
4. Vá para a aba **2_Lastro** e **filtre** por essa chave (Dados → Filtro no Excel).
5. Pronto: aparecem **exatamente** os registros que compõem aquele número. Some a
   coluna de valor (ex: `PRÊMIO LÍQ. DO SEGURO`) e confira que bate.
6. Para chegar ao arquivo bruto, use `ARQUIVO_ORIGEM` + `LINHA_ORIGEM` de cada registro.

### Exemplo prático
> "A Curva ABC diz que o cooperado `12345678901` tem R$ 13.042 de prêmio. De onde veio?"
> - Abra `Curva_ABC.xlsx` → aba **2_Lastro** → filtre `CPF_LIMPO = 12345678901`.
> - Aparecem todas as linhas de produção desse CPF. Some `PRÊMIO LÍQ. DO SEGURO` → R$ 13.042.
> - Cada linha aponta `LINHA_ORIGEM` no `RptAnaliseProducao.xlsx`.

---

## 4. Mapa: análise → workbook → chave de filtro

> Os workbooks abaixo ficam em **`outputs/comercial/auditoria/`**. Os tracks
> **Operacional/Qualidade** (`outputs/operacional/auditoria/`) e **Marketing**
> (`outputs/marketing/auditoria/`) seguem o mesmo padrão Agregado | Lastro — ex.:
> `Alvos_Aquisicao.xlsx`/`Audiencia_Campanha.xlsx` (lastro = prospects),
> `Personas_*.xlsx` e `Status_Base.xlsx` (lastro = base por cooperado).

| Análise | Workbook | Filtre o Lastro por | Confere |
|---|---|---|---|
| Curva ABC (concentração de receita) | `Curva_ABC.xlsx` | `CPF_LIMPO` | Prêmio por CPF |
| Market Share (seguradoras) | `Market_Share.xlsx` | `SEGURADORA` | Prêmio por seguradora |
| Cohort / Sazonalidade | `Cohort_Sazonalidade.xlsx` | `SAFRA_MES_VIGENCIA` | Prêmio por safra |
| Demografia / Conversão | `Demografia.xlsx` | célula demográfica (Cidade, Sexo, Faixa, Especialidade...) | Total e ativos por célula |
| Calculadora de Produtos | `Calculadora_Produtos.xlsx` | `CPF_LIMPO` + `SEGURADORA` + `PRODUTO` | Prêmio e comissão por produto |
| Mix por Especialidade | `Mix_Especialidade.xlsx` | `CARACTERÍSTICA` + `PRODUTO` | Cooperados com o produto |
| Agenda de Renovações | `Agenda_Renovacoes.xlsx` | `CPF_LIMPO` + `SEGURADORA` + `PRODUTO` | Prêmio por produto |
| Win-Back | `Win_Back.xlsx` | `CPF_LIMPO` | Prêmio histórico por CPF |
| Snapshot Mensal | `Snapshot_Mensal.xlsx` | `MES_REFERENCIA` | Clientes/produtos/prêmio por mês |
| Curva ABC 2025+ | `Curva_ABC_2025plus.xlsx` | `CPF_LIMPO` | Prêmio (originação 2025+) por CPF |
| Market Share 2025+ | `Market_Share_2025plus.xlsx` | `SEGURADORA` | Prêmio (originação 2025+) por seguradora |

> **Calculadora_Produtos é a ponte universal.** Qualquer análise que trabalha por
> produto (Snapshot, Mix, Renovações) pode ser rastreada até a linha bruta passando
> pela chave `CPF_LIMPO + SEGURADORA + PRODUTO` neste workbook.

---

## 5. Situações comuns de auditoria

- **"Esse número parece alto/errado."** Abra o lastro, filtre pela chave e procure
  registros estranhos (prêmio fora do padrão, duplicatas, datas erradas). Cruze com
  o arquivo `DQ_Raio_X_Cooperados.xlsx`, que isola anomalias (prêmio zerado,
  comissão > prêmio, duplicatas, outliers).
- **"Apareceu um CPF que não conheço."** Veja `ARQUIVO_ORIGEM`/`LINHA_ORIGEM` —
  se vier de produção mas não existir no cadastro, é um **órfão** (o `DQ` sinaliza
  isso). Pode ser erro de digitação de CPF na origem.
- **"Por que esse cliente não aparece na demografia?"** A demografia parte do
  **cadastro**; se o CPF só existe na produção (órfão), ele não entra nas células
  demográficas. Veja a seção de impactos no `GUIA_METRICAS.md`.
- **"Quero a origem exata."** `ARQUIVO_ORIGEM` + `LINHA_ORIGEM` levam à linha no
  Excel bruto. Não confie no número da linha do **lastro** (ele já foi reordenado);
  use sempre `LINHA_ORIGEM`.

---

## 6. Avisos importantes

- Os workbooks são **regerados a cada execução** do pipeline (`python Main.py`).
  Se um deles estiver **aberto no Excel** na hora de rodar, ele é **pulado com aviso**
  e a execução não é marcada como concluída — feche o arquivo e rode de novo.
- O `Snapshot_Mensal.xlsx` tem o lastro no grão **produto × mês** (não a linha bruta),
  porque um produto ativo aparece em vários meses. Para descer à linha bruta, use a
  chave `CPF_LIMPO + SEGURADORA + PRODUTO` no `Calculadora_Produtos.xlsx`.
- Detalhes de **como cada número é calculado** e o que acontece com dados ruins estão
  no `GUIA_METRICAS.md`.
