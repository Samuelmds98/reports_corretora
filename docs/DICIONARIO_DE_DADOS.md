# Dicionário de Dados

> Colunas das **entradas** (2 Excel) e tabelas de **saída** (Parquet por público). Foco nos
> campos efetivamente usados pelo pipeline e nos *caveats* que mudam a leitura. Tipos e
> regras detalhadas em `docs/REGRAS_POR_PRODUTO_E_CONTRATOS.md`; métricas em
> `docs/GUIA_METRICAS.md`. Confiabilidade (base real): 🟢 alta · 🟡 média · 🟠 baixa · 🔴 inútil.

## 1. Entrada — Produção (`RptAnaliseProducao.xlsx`, 39 colunas)

Grão: **1 linha por movimento** (apólice/fatura/endosso/cancelamento).

| Coluna | Tipo | Semântica | Conf. |
|---|---|---|---|
| `CPF/CNPJ` | texto | Chave do cooperado (→ `CPF_LIMPO` após `clean_cpf_cnpj`) | 🟢 |
| `CLIENTE` | texto | Nome do segurado | 🟢 |
| `RAMO` | categórica | Natureza do risco (VIDA, AUTO, SAÚDE…) | 🟢 |
| `NOME ABREVIADO DO PRODUTO` | categórica | Produto comercial → define o **tipo de vigência** | 🟢 |
| `SEGURADORA (ABREVIADO)` | categórica | Companhia (chave de market share) | 🟢 |
| `APÓLICE` | texto | Nº do contrato (com sufixos/sujeira → `extract_policy_root`) | 🟢 |
| `TIPO DE NEGÓCIO` | categórica | `N`/`R` (apólice nova/renov.), `EN`/`ER` (endosso), `CN`/`CR` (cancelamento) | 🟢 |
| `TIPO DOCUMENTO` | categórica | `APÓLICE` / `FATURA` / `ENDOSSO` | 🟢 |
| `SITUAÇÃO` | categórica | **Status do DOCUMENTO** (Ativa/Renovada/Vencida/Cancelada). ⚠️ Só `Ativa` é vigente; pode estar defasada — ver caveats | 🟢 |
| `INÍCIO DE VIGÊNCIA` | data | Início da cobertura — **define a janela de avaliação** | 🟢 |
| `TÉRMINO DE VIGÊNCIA` | data | Fim da cobertura (regra: `>= INÍCIO`) | 🟢 |
| `PRÊMIO LÍQ. DO SEGURO` | numérico | Prêmio (medida). ⚠️ **confiabilidade baixa** na base real | 🟠 |
| `PORCENTAGEM` | numérico | Taxa de comissão (%) — **não aditiva** | 🟡 |
| `COMISSÃO` | numérico | Comissão (fonte única via `get_comissao_col`; ⚠️ existe também `COMISSÃO TOTAL (CORRET + CO-CORRET)`) | 🟠 |
| `PRODUTOR` | categórica | Vendedor/produtor (→ `normalize_producer`); dimensão de performance | 🟢 |
| `USUÁRIO DA INCLUSÃO` | categórica | `= MIGRACAO` marca carga histórica (~40% da base) — enviesa séries | 🟢 |
| `QTDEENDOSSO` | numérico | Intensidade de endosso | 🟢 |
| `QUANTIDADE DE PARCELAS` | numérico | Perfil de pagamento (à vista vs. 12x) | 🟢 |
| `CARACTERISTICA` | categórica | Especialidade (⚠️ **sem acento** aqui; no cadastro é `CARACTERÍSTICA`) | 🟢 |
| `MOTIVO/DATA CANCELAMENTO`, `DATA PAGAMENTO`, `VENCIMENTO`, `CAMPANHA` | — | Pouco/não preenchidos | 🔴 |

> Demais colunas (datas de proposta/emissão/inclusão, código do documento, grupo de
> produção etc.) existem mas têm uso marginal no pipeline atual.

## 2. Entrada — Cadastro (`RptClienteLista.xlsx`, 33 colunas)

Grão: **1 linha por cooperado**.

| Coluna | Tipo | Semântica | Conf. |
|---|---|---|---|
| `CGC/CPF` | texto | Chave (→ `CPF_LIMPO`) | 🟢 |
| `NOME` | texto | Nome do cooperado | 🟢 |
| `CARACTERÍSTICA` | categórica | **Especialidade médica** (com acento) — atributo mais rico | 🟢 |
| `DATA DE NASCIMENTO/DT. ABERTURA/FUNDAÇÃO` | data | → IDADE / FAIXA_ETARIA | 🟢 |
| `SEXO` | categórica | M / F (→ "NI" se ausente) | 🟡 |
| `TIPO` | categórica | Pessoa Física / Jurídica | 🟢 |
| `ESTADO CIVIL` | categórica | ⚠️ ~41% preenchido na base real | 🟠 |
| `CIDADE` / `ESTADO` / `BAIRRO` | categórica | Geografia ⚠️ ~54% preenchido | 🟠 |
| `CLIENTE DESDE` | data | Tempo de casa (tenure) ~86% | 🟡 |
| `TELEFONE` / `EMAIL` | texto | Canais de contato (acionabilidade) | 🟡 |
| `ACEITA RECEBER E-MAILS PROMOCIONAIS` | categórica | Consentimento (→ `EMAIL_ACIONAVEL`) | 🟢 |
| `PROFISSÃO` | categórica | ⚠️ "lixo" na base real (use `CARACTERÍSTICA`) | 🔴 |
| `RENDA FAMILIAR/FATURAMENTO MÉDIO` | numérico | ⚠️ não confiável | 🔴 |
| `QTDE FILHOS/QTDE FUNCIONÁRIOS`, `QTDE VEICS` | numérico | ⚠️ constantes na base real | 🔴 |

## 3. Derivados em memória (chave)
| Objeto | Grão | Conteúdo |
|---|---|---|
| `df_prod_status` | CPF × seguradora × produto | status + valores do último ciclo |
| `df_cruzamento` | cooperado | cadastro × insights (`STATUS_GLOBAL`, `RATING_ESTRELAS`) |
| `df_mkt_base` | cooperado | status ATIVO/INATIVO/PROSPECT + demografia + personas + contato |

## 4. Saídas — Parquet por público (`outputs/<track>/parquet/`)

**Comercial:** `clientes_crm`, `producao_status`, `producao_grain`, `producao_enriquecida`,
`curva_abc`, `curva_abc_comissao`, `curva_abc_2025plus`, `market_share`,
`market_share_2025plus`, `market_share_contagem`, `mix_especialidade`, `mix_produtos`,
`cross_sell`, `crosssell_gaps`, `agenda_renovacoes`, `winback`, `snapshot_mensal`,
`snapshot_grain`, `cohort_sazonalidade`, `demografico`, `performance_produtor`,
`profundidade_carteira`, `margem_comissao_seguradora`, `margem_comissao_produto`,
`margem_comissao_seg_produto`.

**Operacional/Qualidade:** `completude_cadastro`, `origem_cadastro`, `status_vs_situacao`,
`apolices_ativas_cancelamento`, `situacao_ativa_vencida`, `taxa_cancelamento`,
`acionabilidade_produtor`, `run_context`. *(+ `dq_history.parquet` na raiz do track —
histórico acumulado de DQ.)*

**Marketing:** `base_cooperados`, `status_base`, `distribuicao_especialidade`,
`decada_nascimento`, `faixa_etaria`, `personas_sexo`, `personas_estado_civil`,
`personas_tipo`, `alvos_aquisicao`, `audiencia_campanha`.

> Cada Parquet tem um workbook de **auditoria** correspondente (`<track>/auditoria/*.xlsx`,
> abas **Agregado | Lastro**) e, quando aplicável, um HTML em `<track>/visuals/`.
> Colunas-âncora de linhagem em todo lastro: `ID_LINHA`, `ARQUIVO_ORIGEM`, `LINHA_ORIGEM`.
