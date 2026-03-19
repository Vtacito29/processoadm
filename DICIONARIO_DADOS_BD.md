# Dicionario de Dados do Banco

Este documento descreve a estrutura do banco de dados da aplicacao `processoadm_deploy`, com base nos modelos SQLAlchemy definidos em [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L1981) e no esquema SQLite atual.

## Visao Geral

O sistema utiliza as seguintes tabelas principais:

1. `usuarios`
2. `processos`
3. `movimentacoes`
4. `campos_extra`
5. `importacoes_temp`
6. `notificacoes`

## Relacionamentos

- `processos.assigned_to_id` referencia `usuarios.id`
- `movimentacoes.processo_id` referencia `processos.id`
- `campos_extra.criado_por_id` referencia `usuarios.id`
- `notificacoes.user_id` referencia `usuarios.id`
- `notificacoes.processo_id` referencia `processos.id`

## Tabela `usuarios`

Finalidade: armazenar os usuarios do sistema, seus perfis, permissoes e contexto de atuacao.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador unico do usuario |
| `username` | VARCHAR(80) | Nao | UNQ | Nome de login do usuario |
| `email` | VARCHAR(255) | Nao | UNQ | Email institucional ou de acesso |
| `nome` | VARCHAR(120) | Nao |  | Nome completo do usuario |
| `nome_vinculo_atribuido` | VARCHAR(120) | Sim |  | Nome vinculado a listas de atribuicao e responsavel exibido no sistema |
| `gerencia_padrao` | VARCHAR(50) | Sim |  | Gerencia principal do usuario |
| `gerencias_liberadas` | TEXT | Sim |  | Lista serializada em JSON com as gerencias em que o usuario pode atuar |
| `coordenadoria` | VARCHAR(120) | Sim |  | Coordenadoria padrao do usuario |
| `equipe_area` | VARCHAR(120) | Sim |  | Equipe ou area padrao do usuario |
| `aparece_atribuido_sei` | BOOLEAN | Sim |  | Indica se o usuario deve aparecer nas listas de atribuicao vinculadas ao SEI |
| `password_hash` | VARCHAR(255) | Nao |  | Hash da senha do usuario |
| `is_admin` | BOOLEAN | Sim |  | Indica perfil de assessoria/admin |
| `is_admin_principal` | BOOLEAN | Sim |  | Indica administrador principal |
| `is_gerente` | BOOLEAN | Sim |  | Indica perfil de gerente |
| `acesso_total` | BOOLEAN | Sim |  | Libera acesso amplo a varias gerencias e funcoes globais |
| `must_reset_password` | BOOLEAN | Sim |  | Obriga troca de senha no primeiro acesso ou apos reset |
| `pode_cadastrar_processo` | BOOLEAN | Sim |  | Permite cadastrar novos processos |
| `pode_finalizar_gerencia` | BOOLEAN | Sim |  | Permite finalizar processos na gerencia |
| `pode_exportar` | BOOLEAN | Sim |  | Permite exportar dados |
| `pode_importar` | BOOLEAN | Sim |  | Permite importar planilhas |
| `criado_em` | DATETIME | Sim |  | Data e hora de criacao do usuario |

Observacoes:

- `username` e `email` sao unicos.
- `gerencias_liberadas` armazena uma lista JSON de gerencias, por exemplo: `["GABINETE", "GEENG"]`.
- O perfil funcional do usuario e derivado da combinacao de `is_admin`, `is_gerente` e `acesso_total`.

## Tabela `processos`

Finalidade: armazenar os processos e demandas acompanhados pelo sistema.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador unico do processo |
| `numero_sei` | VARCHAR(50) | Nao |  | Numero SEI da demanda, normalmente com prefixo da gerencia |
| `assunto` | VARCHAR(255) | Nao |  | Assunto principal do processo |
| `interessado` | VARCHAR(255) | Nao |  | Interessado principal |
| `concessionaria` | VARCHAR(255) | Sim |  | Concessionaria relacionada ao processo |
| `descricao` | TEXT | Sim |  | Campo usado tambem como classificacao institucional no modelo atual |
| `gerencia` | VARCHAR(50) | Nao |  | Gerencia onde a demanda esta alocada |
| `prazo` | DATE | Sim |  | Prazo geral do processo |
| `data_entrada` | DATE | Sim |  | Data de entrada do processo |
| `responsavel_adm` | VARCHAR(255) | Sim |  | Responsavel administrativo |
| `observacao` | TEXT | Sim |  | Observacao principal |
| `data_entrada_geplan` | DATE | Sim |  | Campo legado ou especifico de entrada na GEPLAN |
| `descricao_melhorada` | TEXT | Sim |  | Descricao complementar ou refinada |
| `coordenadoria` | VARCHAR(255) | Sim |  | Coordenadoria associada |
| `equipe_area` | VARCHAR(255) | Sim |  | Equipe ou area associada |
| `responsavel_equipe` | VARCHAR(255) | Sim |  | Responsavel de equipe informado manualmente |
| `tipo_processo` | VARCHAR(255) | Sim |  | Tipo de processo |
| `palavras_chave` | VARCHAR(255) | Sim |  | Palavras-chave de apoio a busca |
| `status` | VARCHAR(100) | Sim |  | Status atual do processo |
| `data_status` | DATE | Sim |  | Data do status atual |
| `prazo_equipe` | DATE | Sim |  | Prazo especifico da equipe |
| `observacoes_complementares` | TEXT | Sim |  | Observacoes adicionais |
| `data_saida` | DATE | Sim |  | Data de saida da gerencia ou do fluxo |
| `tramitado_para` | VARCHAR(50) | Sim |  | Destino de tramitacao ou saida |
| `finalizado_em` | DATETIME | Sim |  | Data e hora de finalizacao |
| `finalizado_por` | VARCHAR(80) | Sim |  | Usuario que finalizou |
| `assigned_to_id` | INTEGER | Sim | FK -> usuarios.id | Usuario do sistema responsavel pela atribuicao formal |
| `dados_extra` | JSON | Sim |  | Estrutura flexivel com metadados adicionais e campos personalizados |
| `criado_em` | DATETIME | Sim |  | Data e hora de criacao |
| `atualizado_em` | DATETIME | Sim |  | Data e hora da ultima atualizacao |

Observacoes:

- `numero_sei` nao e unico porque o mesmo numero base pode gerar demandas por gerencia.
- A propriedade calculada `numero_sei_base` remove o prefixo da gerencia ou usa `dados_extra["numero_sei_original"]`.
- `descricao` e reaproveitado pela propriedade `classificacao_institucional`.

### Estrutura comum de `dados_extra` em `processos`

O campo JSON `dados_extra` guarda chaves variaveis. As mais importantes identificadas no codigo sao:

| Chave JSON | Descricao |
|---|---|
| `numero_sei_original` | Numero base informado no cadastro, sem prefixo da gerencia |
| `gerencias_escolhidas` | Lista de gerencias selecionadas no cadastro ou reenvio |
| `responsavel_adm_inicial` | Responsavel ADM informado no cadastro inicial |
| `chave_processo` | Chave de relacionamento entre demandas do mesmo numero base |
| `decisao_mesmo_numero` | Indica regra aplicada para nova demanda em numero existente |
| `sufixo` | Sufixo usado em exibicao consolidada do numero |
| `devolvido_gabinete` | Marca processo devolvido para gabinete/assessoria |
| `devolucao_origem` | Gerencia de origem da devolucao |
| `origem_devolucao` | Variacao de nome usada em alguns fluxos de leitura |
| `motivo_devolucao` | Motivo informado para devolucao |
| `extras` | Em snapshots, pode representar conjunto de campos extras congelados |

Observacao:

- Alem dessas chaves tecnicas, `dados_extra` tambem recebe campos personalizados definidos na tabela `campos_extra`, usando o `slug` do campo como chave JSON.

## Tabela `movimentacoes`

Finalidade: registrar o historico de tramitacao, finalizacao, cadastro, edicao e devolucao dos processos.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador da movimentacao |
| `processo_id` | INTEGER | Nao | FK -> processos.id | Processo relacionado |
| `de_gerencia` | VARCHAR(50) | Nao |  | Gerencia de origem |
| `para_gerencia` | VARCHAR(50) | Nao |  | Gerencia de destino |
| `motivo` | TEXT | Nao |  | Texto descritivo da movimentacao |
| `usuario` | VARCHAR(80) | Sim |  | Usuario que executou a acao |
| `tipo` | VARCHAR(40) | Sim |  | Tipo tecnico da movimentacao |
| `criado_em` | DATETIME | Sim |  | Data e hora do registro |
| `dados_snapshot` | JSON | Sim |  | Snapshot dos dados do processo no momento da movimentacao |

Valores importantes de `tipo` identificados no codigo:

- `cadastro`
- `movimentacao`
- `edicao`
- `finalizacao_gerencia`
- `finalizado_geral`
- `devolucao_gabinete`

Observacoes:

- Existe `ON DELETE CASCADE` em `processo_id`, ou seja, ao excluir um processo, seu historico tambem e removido.
- `dados_snapshot` e usado para reconstruir historico e painis consolidados de finalizacao.

## Tabela `campos_extra`

Finalidade: definir campos personalizados por gerencia.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador do campo extra |
| `gerencia` | VARCHAR(50) | Nao |  | Gerencia dona da configuracao |
| `label` | VARCHAR(120) | Nao |  | Nome de exibicao do campo |
| `slug` | VARCHAR(120) | Nao |  | Nome tecnico usado como chave no JSON `dados_extra` |
| `tipo` | VARCHAR(20) | Nao |  | Tipo do campo |
| `criado_por_id` | INTEGER | Sim | FK -> usuarios.id | Usuario que criou o campo |
| `criado_em` | DATETIME | Sim |  | Data e hora de criacao |

Tipos identificados:

- `texto`
- `numero`
- `data`

Observacoes:

- Ao remover um campo extra, o sistema tambem remove a chave correspondente de `processos.dados_extra` para os processos da mesma gerencia.

## Tabela `importacoes_temp`

Finalidade: armazenar arquivos temporarios de importacao Excel para permitir continuidade do fluxo.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador do registro temporario |
| `token` | VARCHAR(64) | Nao | UNQ | Token unico de recuperacao da importacao |
| `nome_arquivo` | VARCHAR(255) | Nao |  | Nome original do arquivo enviado |
| `conteudo` | BLOB | Nao |  | Conteudo binario do arquivo |
| `criado_em` | DATETIME | Sim |  | Data e hora da criacao |

Observacoes:

- E uma tabela operacional, nao funcional.
- Serve de apoio ao fluxo de importacao de Excel.

## Tabela `notificacoes`

Finalidade: armazenar avisos enviados aos usuarios.

| Campo | Tipo | Nulo | Chave | Descricao |
|---|---|---|---|---|
| `id` | INTEGER | Nao | PK | Identificador da notificacao |
| `user_id` | INTEGER | Nao | FK -> usuarios.id | Usuario destinatario |
| `processo_id` | INTEGER | Sim | FK -> processos.id | Processo relacionado, quando houver |
| `mensagem` | TEXT | Nao |  | Texto da notificacao |
| `lida` | BOOLEAN | Sim |  | Marca de leitura |
| `criada_em` | DATETIME | Sim |  | Data e hora da criacao |
| `criado_por` | VARCHAR(120) | Sim |  | Nome do usuario que originou a notificacao |

Observacoes:

- O sistema usa notificacoes para atribuicoes e eventos relevantes sobre processos.

## Regras de Negocio Relevantes para Documentacao

### Usuarios

- O login aceita `username` ou `email`.
- Usuarios podem ter perfis de `usuario`, `gerente`, `admin` ou `acesso_total`.
- `must_reset_password` obriga redefinicao de senha no primeiro acesso ou apos reset administrativo.

### Processos

- Um mesmo numero base pode gerar varias demandas em gerencias diferentes.
- O numero salvo normalmente recebe prefixo da gerencia, por exemplo `GEENG-12345`.
- Um processo pode ser atribuido formalmente a um usuario do sistema via `assigned_to_id`.
- O campo `dados_extra` acumula informacoes tecnicas e campos adicionais configuraveis.

### Historico

- Toda criacao, movimentacao, finalizacao ou acao equivalente gera rastreabilidade via `movimentacoes`.
- O painel de historico utiliza snapshots e consolidacoes para apresentar os dados finalizados.

## Fontes

- Modelos: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L1981)
- Esquema SQLite atual: `controle_processos.db`

## Dicionario de Dados Detalhado por Entidade

Esta secao amplia a leitura funcional de cada tabela, explicando como os campos sao usados nas funcoes do sistema.

## Entidade `usuarios` em detalhe

### Papel no sistema

A tabela `usuarios` sustenta:

- autenticacao
- autorizacao por perfil
- escopo de gerencias
- contexto de coordenadoria e equipe
- atribuicao formal de processos
- notificacoes
- criacao de campos extras

### Campos de autenticacao

| Campo | Uso no sistema |
|---|---|
| `username` | Login principal do usuario |
| `email` | Alternativa de login e canal de contato |
| `password_hash` | Validacao segura de senha |
| `must_reset_password` | Obriga troca de senha no primeiro acesso ou apos redefinicao |

### Campos de perfil e autorizacao

| Campo | Uso no sistema |
|---|---|
| `is_admin` | Libera funcoes administrativas de assessoria |
| `is_admin_principal` | Reserva papel estrutural do administrador principal |
| `is_gerente` | Libera funcoes gerenciais por escopo |
| `acesso_total` | Libera acesso amplo a multiplas gerencias e funcoes globais |
| `pode_cadastrar_processo` | Permite cadastro de novos processos |
| `pode_finalizar_gerencia` | Permite finalizar processos |
| `pode_exportar` | Permite exportacao |
| `pode_importar` | Permite importacao |

### Campos de contexto organizacional

| Campo | Uso no sistema |
|---|---|
| `gerencia_padrao` | Define a gerencia principal do usuario e atalhos de navegacao |
| `gerencias_liberadas` | Define em quais gerencias o usuario pode atuar |
| `coordenadoria` | Contexto funcional padrao do usuario |
| `equipe_area` | Equipe/area padrao do usuario |
| `nome_vinculo_atribuido` | Nome usado para vinculo com listas de atribuicao do processo |
| `aparece_atribuido_sei` | Controla participacao nas listas visuais de atribuicao |

### Relacionamentos funcionais

- um usuario pode ter varios processos atribuidos via `processos.assigned_to_id`
- um usuario pode criar varios `campos_extra`
- um usuario pode receber varias `notificacoes`

### Regras importantes

- `username`, `email` e, em alguns fluxos, `nome` sao validados contra duplicidade
- ao excluir um usuario, notificacoes podem ser apagadas e atribuicoes podem ser limpas
- usuarios sem acesso total normalmente precisam ter contexto de gerencia, coordenadoria e equipe coerente

## Entidade `processos` em detalhe

### Papel no sistema

A tabela `processos` e a entidade central da aplicacao. Ela representa uma demanda operacional de um processo administrativo dentro de uma gerencia.

### Grupos de campos

#### Identificacao

| Campo | Uso |
|---|---|
| `id` | Identificador tecnico interno |
| `numero_sei` | Identificacao da demanda com prefixo de gerencia |
| `dados_extra.numero_sei_original` | Numero base informado sem prefixo |

#### Informacoes basicas do processo

| Campo | Uso |
|---|---|
| `assunto` | Tema principal do processo |
| `interessado` | Interessado principal |
| `concessionaria` | Concessionaria vinculada |
| `descricao` | Campo reutilizado como classificacao institucional no modelo atual |
| `descricao_melhorada` | Texto refinado ou complementar |
| `tipo_processo` | Categoria do processo |
| `palavras_chave` | Apoio a pesquisa e organizacao |

#### Localizacao e contexto operacional

| Campo | Uso |
|---|---|
| `gerencia` | Gerencia atual da demanda |
| `coordenadoria` | Coordenadoria responsavel |
| `equipe_area` | Equipe ou area responsavel |
| `responsavel_adm` | Responsavel administrativo |
| `responsavel_equipe` | Responsavel tecnico/operacional |
| `assigned_to_id` | Responsavel formal vinculado a um usuario do sistema |

#### Controle temporal

| Campo | Uso |
|---|---|
| `data_entrada` | Entrada geral do processo |
| `data_entrada_geplan` | Campo legado/especifico |
| `data_status` | Quando o status foi atualizado |
| `prazo` | Prazo institucional |
| `prazo_equipe` | Prazo da equipe |
| `data_saida` | Data de saida |
| `finalizado_em` | Data/hora da finalizacao |
| `criado_em` | Criacao da demanda no sistema |
| `atualizado_em` | Ultima alteracao |

#### Controle de fluxo

| Campo | Uso |
|---|---|
| `status` | Status atual |
| `tramitado_para` | Destino de tramitacao ou saida |
| `finalizado_por` | Usuario que finalizou |
| `observacao` | Observacao principal |
| `observacoes_complementares` | Observacoes adicionais |

### Comportamento funcional do registro

- um numero base pode originar varias demandas em gerencias diferentes
- o sistema consolida demandas relacionadas por `numero_sei_base` e por chaves em `dados_extra`
- processos ativos, finalizados e devolvidos sao tratados em fluxos diferentes
- historicos e snapshots dependem tanto da linha atual de `processos` quanto da tabela `movimentacoes`

### Campos extras dinamicos

Os campos personalizados definidos em `campos_extra` nao viram novas colunas SQL. Eles sao persistidos em `dados_extra`, usando a chave `slug` do campo extra.

Exemplo conceitual:

```json
{
  "numero_sei_original": "12345",
  "responsavel_adm_inicial": "Fulano",
  "chave_processo": "PROC-2026-ABC",
  "campo_personalizado_x": "valor livre"
}
```

## Entidade `movimentacoes` em detalhe

### Papel no sistema

A tabela `movimentacoes` e a trilha de auditoria do sistema.

Ela registra:

- cadastro inicial
- mudancas de gerencia
- edicoes relevantes
- finalizacoes
- devolucoes
- outras acoes operacionais relevantes

### Semantica dos principais campos

| Campo | Uso |
|---|---|
| `de_gerencia` | Origem da acao |
| `para_gerencia` | Destino da acao |
| `motivo` | Texto explicativo legivel |
| `usuario` | Quem executou a acao |
| `tipo` | Classificacao tecnica da movimentacao |
| `dados_snapshot` | Estado congelado do processo ou da gerencia naquele momento |

### Uso em telas

- painel de gerencia
- historico consolidado
- ficha tecnica

### Valor documental

Em auditoria interna, `movimentacoes` e a principal fonte para reconstruir:

- por onde o processo passou
- quando entrou e saiu de cada etapa
- quem executou a acao
- qual era o estado contextual na data do evento

## Entidade `campos_extra` em detalhe

### Papel no sistema

Permite que cada gerencia configure metadados proprios sem alterar o schema fisico do banco.

### Estrutura logica

- a definicao fica em `campos_extra`
- o valor preenchido vai para `processos.dados_extra`

### Exemplo funcional

Se a gerencia criar um campo:

- `label = "Numero do contrato"`
- `slug = "numero_do_contrato"`
- `tipo = "texto"`

entao o valor salvo de um processo pode ficar em:

```json
{
  "numero_do_contrato": "CT-2026-001"
}
```

## Entidade `importacoes_temp` em detalhe

### Papel no sistema

Tabela de apoio tecnico para o fluxo de importacao por Excel.

### Justificativa de existencia

- preservar o arquivo durante etapas de mapeamento
- permitir continuidade do fluxo mesmo com reinicio de contexto
- evitar perda do upload antes da confirmacao final

## Entidade `notificacoes` em detalhe

### Papel no sistema

Tabela voltada a comunicacao entre eventos do processo e usuarios do sistema.

### Exemplos de uso observados

- aviso de atribuicao de processo
- avisos relacionados a movimentacoes relevantes

### Estados

- `lida = false`: notificacao pendente
- `lida = true`: notificacao tratada

## Constraints, Integridade e Observacoes Tecnicas

## Chaves primarias

- todas as tabelas possuem `id` como chave primaria

## Chaves estrangeiras

| Origem | Destino | Observacao |
|---|---|---|
| `processos.assigned_to_id` | `usuarios.id` | Vinculo opcional de atribuicao |
| `movimentacoes.processo_id` | `processos.id` | Obrigatorio; com `ON DELETE CASCADE` |
| `campos_extra.criado_por_id` | `usuarios.id` | Opcional |
| `notificacoes.user_id` | `usuarios.id` | Obrigatorio |
| `notificacoes.processo_id` | `processos.id` | Opcional |

## Unicidade

| Tabela | Campo | Regra |
|---|---|---|
| `usuarios` | `username` | Unico |
| `usuarios` | `email` | Unico |
| `importacoes_temp` | `token` | Unico |

## Campos JSON

| Tabela | Campo | Finalidade |
|---|---|---|
| `processos` | `dados_extra` | Metadados do processo e campos personalizados |
| `movimentacoes` | `dados_snapshot` | Snapshot historico |

## Indices observados no schema

- `importacoes_temp.token`
- `importacoes_temp.criado_em`

## Matriz de Uso das Tabelas por Funcionalidade

| Funcionalidade | usuarios | processos | movimentacoes | campos_extra | importacoes_temp | notificacoes |
|---|---|---|---|---|---|---|
| Login | X |  |  |  |  |  |
| Cadastro de usuario | X |  |  |  |  |  |
| Perfil | X |  |  |  |  |  |
| Dashboard | X | X |  | X |  |  |
| Cadastro de processo | X | X | X |  |  |  |
| Edicao de processo | X | X | X | X |  |  |
| Atribuicao | X | X | X |  |  | X |
| Finalizacao | X | X | X | X |  | X |
| Devolucao / reenvio | X | X | X |  |  | X |
| Historico |  | X | X |  |  |  |
| Exportacao | X | X | X | X |  |  |
| Importacao | X | X | X |  | X |  |
| Campos extras | X | X |  | X |  |  |

## Sugestao de Uso deste Documento

Este dicionario pode ser usado como base para:

- inventario formal de banco de dados
- anexo tecnico de projeto
- base para DER e modelagem conceitual
- material para auditoria
- apoio a homologacao
- documentacao para sustentacao
