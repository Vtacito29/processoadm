# Manual de Uso do Sistema

Este manual descreve as funcoes implementadas no sistema `Controle de Processos`, com base nas rotas, telas e regras encontradas em [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py) e na pasta [templates](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates).

## Objetivo do Sistema

O sistema controla o ciclo de vida de processos entre gerencias, permitindo:

- cadastro de processos
- distribuicao para uma ou varias gerencias
- atribuicao de responsaveis
- acompanhamento de prazos e status
- movimentacao entre gerencias
- finalizacao
- devolucao para gabinete/assessoria
- reenvio de processos devolvidos
- exportacao e importacao por Excel
- gestao de usuarios
- configuracao de campos extras por gerencia
- consulta a historico consolidado

## Perfis e Permissoes

Os perfis sao derivados dos dados do usuario em [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L2286).

### 1. Usuario

Pode ter permissao para:

- acessar o sistema
- editar o proprio perfil
- alterar a propria senha
- visualizar paineis liberados
- atuar em gerencias liberadas
- cadastrar processos, se `pode_cadastrar_processo` estiver habilitado
- finalizar processos, se `pode_finalizar_gerencia` estiver habilitado

### 2. Gerente

Pode, alem do usuario comum:

- gerenciar processos da gerencia liberada
- configurar campos extras da gerencia
- exportar dados, conforme permissao

### 3. Admin / Assessoria

Pode, alem do gerente:

- cadastrar usuarios
- editar usuarios
- redefinir senhas
- excluir usuarios, conforme regra de permissao

### 4. Acesso Total

Pode atuar em varias gerencias e acessa funcoes globais, como:

- exportacao geral
- importacao global
- administracao mais ampla de usuarios e processos

## Estrutura das Telas

As telas HTML localizadas em [templates](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates) sao:

- `login.html`
- `reset_password.html`
- `perfil.html`
- `pg_inicial.html`
- `gerencias.html`
- `gerencia_campos.html`
- `processo_form.html`
- `importar_excel.html`
- `verificar_dados.html`

## Funcoes do Sistema por Tela

## 1. Login e Gestao de Usuarios

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L2282)

### O que a tela faz

- autentica o usuario com login ou email
- permite manter sessao ativa
- permite cadastrar novos usuarios, se o usuario logado tiver permissao
- permite editar usuarios existentes
- permite redefinir senha de usuarios
- permite listar usuarios para gerenciamento

### Campos principais no login

- usuario ou email
- senha
- lembrar sessao

### Funcoes administrativas de usuario

- criar usuario com senha temporaria
- definir perfil
- definir gerencia padrao
- definir gerencias liberadas
- definir coordenadoria e equipe
- vincular nome de atribuicao
- controlar permissao de finalizar gerencia
- redefinir senha
- excluir usuario

### Regras importantes

- o usuario criado recebe senha temporaria
- o usuario pode ser obrigado a trocar a senha no primeiro acesso
- username, email e nome nao podem conflitar com outro cadastro
- o administrador principal possui protecoes especiais

## 2. Logout

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L2706)

### Funcao

- encerra a sessao do usuario autenticado

## 3. Troca de Senha

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L2715)

### Funcao

- permite ao usuario informar senha atual
- definir nova senha
- confirmar nova senha

### Validacoes

- a senha atual deve estar correta
- a nova senha deve ter no minimo 6 caracteres
- a confirmacao deve ser igual a nova senha

## 4. Perfil do Usuario

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L2738)

### Funcao

- editar nome
- editar email
- editar username
- editar gerencia
- editar coordenadoria
- editar equipe
- alterar senha

### Regras

- usuarios sem acesso total devem manter contexto funcional completo, com gerencia, coordenadoria e equipe
- a senha atual e obrigatoria para salvar alteracoes

## 5. Dashboard Inicial

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L4585)

### Objetivo

- exibir visao geral dos processos em andamento
- mostrar contagens por gerencia
- exibir metricas operacionais
- listar processos com filtros e paginacao

### Funcoes disponiveis

- filtro por gerencia
- filtro por numero SEI
- filtro por prazo
- filtro por processos sem responsavel de equipe
- filtros por coluna
- ordenacao por coluna
- paginacao da lista
- atalho para exportacao geral
- atalho para importacao Excel, se permitido
- atalho para cadastro de novo processo, se permitido
- indicador de "Meus Processos"

### Informacoes exibidas

- total em andamento
- total finalizado
- tempo medio
- quantidade por gerencia
- quantidade em saida
- lista de processos ativos

## 6. API de Atualizacao do Painel

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L4910)

### Funcao

- atualiza via JSON os contadores e metricas do painel principal sem recarregar toda a pagina

## 7. API de Opcoes de Filtro da Home

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L4976)

### Funcao

- retorna os valores unicos de uma coluna para montar menus de filtro dinamico na tela inicial

## 8. Exportacao Geral

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L5131)

### Funcao

- gera arquivo Excel com dados do sistema em escopo global

### Uso esperado

- selecionar colunas desejadas
- acionar exportacao
- baixar planilha gerada

## 9. Importacao de Excel

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L5240)

### Funcao

- importar planilhas para cadastro ou atualizacao de processos

### Etapas do fluxo

1. enviar arquivo Excel
2. validar suporte e dependencias
3. identificar planilha
4. sugerir mapeamento de colunas
5. confirmar importacao
6. processar em lotes

### Recursos de apoio

- cache temporario do arquivo
- limite de tamanho de upload
- validacao de engine de leitura Excel
- sugestao automatica de mapeamento

## 10. Painel de Gerencia

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L5750)

### Objetivo

- centralizar a operacao de uma gerencia especifica

### Escopos observados no codigo

- processos ativos
- processos finalizados
- processos devolvidos
- interacoes e historico por gerencia

### Funcoes disponiveis

- listar processos da gerencia
- filtrar por varios campos
- ordenar colunas
- paginar resultados
- acessar edicao do processo
- mover processo
- finalizar processo
- atribuir responsavel
- exportar dados da gerencia
- configurar campos extras

### Casos especiais

- gabinete/assessoria possui regras para devolvidos
- a gerencia `SAIDA` possui comportamento proprio em consolidacoes

## 11. API de Opcoes de Coluna da Gerencia

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L6672)

### Funcao

- retorna valores distintos de colunas para filtros dinamicos dentro do painel da gerencia

## 12. Exportacao por Gerencia

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L6987)

### Funcao

- exportar processos ativos, finalizados ou todos de uma gerencia para Excel

### Possibilidades

- selecao de colunas base
- inclusao de campos extras personalizados
- download de arquivo `.xlsx`

## 13. Configuracao de Campos Extras

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L7097)

### Funcao

- criar campos extras por gerencia
- remover campos extras por gerencia

### Tipos suportados

- texto
- numero
- data

### Efeito pratico

- os campos criados passam a compor o formulario e os dados complementares dos processos da gerencia
- os valores ficam salvos em `processos.dados_extra`

## 14. Cadastro de Novo Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L7160)

### Objetivo

- cadastrar uma nova demanda de processo no sistema

### Campos principais observados

- data de entrada
- numero SEI
- prazo SUROD
- assunto
- interessado
- concessionaria
- responsavel ADM
- observacao
- gerencias de destino

### Comportamentos importantes

- um mesmo cadastro pode gerar processos em varias gerencias
- o numero recebe prefixo da gerencia
- o sistema analisa o numero informado para identificar processos relacionados
- dados base podem ser propagados para demandas do mesmo numero base
- no cadastro inicial e registrada uma movimentacao do tipo `cadastro`

## 15. Inspecao de Numero de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L7458)

### Funcao

- informar, via JSON, se ja existem demandas com o mesmo numero base
- retornar quantidade de ativos e finalizados
- retornar gerencias ativas relacionadas
- sugerir pre-preenchimento e indicacoes para decisao

## 16. Historico de Processos

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L7477)

### Objetivo

- exibir processos finalizados e seu historico consolidado

### Recursos

- filtros por gerencia
- filtros por coordenadoria
- filtros por equipe
- filtros por interessado
- filtro por numero SEI
- filtro por intervalo de datas
- filtros por coluna
- ordenacao
- consolidacao por numero base

### Uso principal

- auditoria
- consulta de historico
- levantamento de finalizacoes
- recuperacao de trilha de tramitacao

## 17. API de Opcoes de Coluna do Historico

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L9075)

### Funcao

- fornecer os valores de filtros dinamicos da tela `verificar-dados`

## 18. Edicao de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10015)

### Funcao

- alterar dados do processo
- carregar e exibir campos extras configurados para a gerencia
- registrar historico de alteracoes

### Dados normalmente editaveis

- assunto
- interessado
- concessionaria
- descricao
- classificacao institucional
- coordenadoria
- equipe
- responsavel da equipe
- tipo de processo
- palavras-chave
- status
- prazos
- observacoes

## 19. Atualizacao de Classificacao

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10279)

### Funcao

- atualizar a classificacao institucional do processo por acao especifica

## 20. Finalizacao de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10313)

### Funcao

- finalizar processo na gerencia atual
- opcionalmente encaminhar para `SAIDA`
- opcionalmente abrir nova demanda em outra gerencia

### Regras observadas

- o usuario precisa de permissao para finalizar
- o sistema registra snapshot e movimentacao
- o processo pode compor historico consolidado apos a finalizacao

## 21. Exclusao de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10632)

### Funcao

- excluir um processo do sistema

### Observacao

- o historico em `movimentacoes` e removido junto por relacao em cascata

## 22. Movimentacao de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10651)

### Funcao

- mover processo para outra gerencia
- registrar motivo e trilha de movimentacao

### Efeitos

- altera a gerencia atual do processo
- gera registro em `movimentacoes`
- pode gerar notificacoes ou ajustes de contexto

## 23. Devolucao para Gabinete / Assessoria

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10763)

### Funcao

- devolver processo para a area tratada como gabinete/assessoria

### Efeitos

- o processo passa a integrar a caixa de devolvidos
- a origem da devolucao e registrada em `dados_extra` e historico

## 24. Reenvio de Processo Devolvido

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L10815)

### Funcao

- reenviar processo devolvido para uma ou mais gerencias

### Regras

- valida gerencias ativas, finalizadas e devolvidas
- pode bloquear ou exigir confirmacao em alguns cenarios
- gera novas demandas se necessario

## 25. Acao sobre Processo Devolvido

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L11062)

### Funcao

- tratar um processo que esta na caixa de devolvidos

### Possibilidades no fluxo

- excluir da caixa de devolvidos
- reenviar
- encaminhar nova demanda

## 26. Atribuicao de Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L11163)

### Funcao

- atribuir processo a um usuario especifico
- liberar atribuicao anterior
- registrar notificacao para o destinatario

### Dados envolvidos

- `assigned_to_id`
- `responsavel_equipe`
- `nome_vinculo_atribuido`
- notificacoes

## 27. Gerenciamento de Notificacoes

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L11377)

### Funcao

- marcar notificacoes como lidas
- limpar ou atualizar estado de notificacoes do usuario

## 28. Salvamento de Campos Extras do Processo

Base tecnica: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py#L12264)

### Funcao

- salvar os valores de campos personalizados de um processo

### Efeito

- atualiza o JSON `dados_extra` do processo com as chaves definidas em `campos_extra`

## Funcionalidades Transversais

## Filtros de Tabela

Base tecnica: [table_column_filter.js](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/static/js/table_column_filter.js)

O sistema possui filtros avancados de tabela com:

- selecao multipla por coluna
- filtros por datas
- ordenacao ascendente e descendente
- persistencia local no navegador
- filtros remotos alimentados por APIs

## Rastreabilidade e Historico

O sistema registra eventos em `movimentacoes` para preservar:

- cadastro inicial
- edicao
- mudanca de gerencia
- atribuicao
- finalizacao
- devolucao

## Regras Operacionais Importantes

1. O numero SEI base pode gerar varias demandas por gerencia.
2. O processo em geral e identificado visualmente pelo prefixo da gerencia.
3. Campos extras sao dinamicos e dependem da gerencia.
4. Nem todo usuario pode cadastrar, exportar, importar ou finalizar.
5. O historico consolidado depende de snapshots e das movimentacoes registradas.

## Fluxo Resumido de Uso

### Fluxo 1. Acesso ao sistema

1. Entrar com usuario ou email
2. Informar senha
3. Trocar senha, se o sistema exigir

### Fluxo 2. Cadastro de processo

1. Ir ao dashboard
2. Clicar em novo processo
3. Preencher os dados obrigatorios
4. Selecionar uma ou mais gerencias
5. Salvar

### Fluxo 3. Tratamento pela gerencia

1. Abrir painel da gerencia
2. Filtrar ou localizar processo
3. Editar dados e campos extras
4. Atribuir responsavel
5. Mover, devolver ou finalizar, conforme necessario

### Fluxo 4. Consulta de historico

1. Acessar historico de processos
2. Aplicar filtros
3. Consultar consolidacoes e datas de entrada/finalizacao

### Fluxo 5. Gestao administrativa

1. Acessar tela de login/usuarios em modo autenticado
2. Criar, editar ou resetar senha de usuario
3. Ajustar gerencias, perfil e permissoes

## Referencias Tecnicas

- Rotas e regras: [app.py](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/app.py)
- Telas: [templates](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates)
- Filtros client-side: [table_column_filter.js](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/static/js/table_column_filter.js)
- Banco de dados: [DICIONARIO_DADOS_BD.md](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/DICIONARIO_DADOS_BD.md)

## Catalogo Completo de Rotas e Funcoes

Esta secao lista todas as rotas Flask identificadas no sistema e sua finalidade operacional.

| Rota | Metodo | Funcao principal |
|---|---|---|
| `/login` | GET, POST | login e gestao de usuarios |
| `/usuarios/<usuario_id>/excluir` | POST | excluir usuario |
| `/logout` | GET | sair do sistema |
| `/trocar-senha` | GET, POST | redefinir a propria senha |
| `/perfil` | GET, POST | editar o proprio perfil |
| `/` | GET | dashboard inicial |
| `/api/atualizacoes-painel` | GET | atualizar metricas do dashboard |
| `/api/home-column-options` | GET | valores de filtros da home |
| `/exportar-geral` | POST | exportacao geral para Excel |
| `/importar-excel` | GET, POST | importacao de planilhas |
| `/gerencia/<nome_gerencia>` | GET | painel operacional da gerencia |
| `/api/gerencia-column-options/<nome_gerencia>` | GET | filtros dinamicos da gerencia |
| `/gerencia/<nome_gerencia>/exportar` | POST | exportacao da gerencia |
| `/gerencia/<nome_gerencia>/campos` | GET, POST | configuracao de campos extras |
| `/processo/novo` | GET, POST | cadastro de processo |
| `/processo/inspecionar-numero` | GET | analise do numero SEI |
| `/verificar-dados` | GET | historico e verificacao de dados |
| `/api/verificar-dados-column-options` | GET | filtros dinamicos do historico |
| `/processo/<processo_id>/editar` | GET, POST | editar processo |
| `/processo/<processo_id>/classificacao` | POST | atualizar classificacao |
| `/processo/<processo_id>/finalizar` | POST | finalizar processo |
| `/processo/<processo_id>/excluir` | POST | excluir processo |
| `/processo/<processo_id>/mover` | POST | mover processo de gerencia |
| `/processo/<processo_id>/devolver-gabinete` | POST | devolver para gabinete/assessoria |
| `/processo/<processo_id>/devolvido/reenviar` | GET, POST | reenviar processo devolvido |
| `/processo/<processo_id>/devolvido/acao` | POST | tratar processo devolvido |
| `/processo/<processo_id>/atribuir` | GET, POST | atribuir processo |
| `/notificacoes` | POST | gerenciar notificacoes |
| `/processo/<processo_id>/campos-extra` | POST | salvar campos extras do processo |

## Mapa de Telas e Usabilidade

## Tela `pg_inicial.html` - Dashboard

Base visual: [pg_inicial.html](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates/pg_inicial.html#L1)

### O usuario encontra nesta tela

- barra de navegacao com acesso ao historico, meus processos, perfil e logout
- hero com resumo do sistema
- metricas operacionais
- cards de gerencias
- card especial de `SAIDA`
- filtros da lista principal
- tabela de processos ativos
- acoes rapidas de cadastro, exportacao e importacao, conforme permissao

### Acoes disponiveis

- `Historico de Processos`
- `Meus Processos`
- `Editar perfil`
- `Trocar senha`
- `Cadastrar usuario`, para perfis administrativos
- `Novo processo`, para quem possui permissao
- acesso ao painel da gerencia por meio dos cards
- aplicar filtros e ordenacoes na tabela

### Filtros principais

- gerencia
- numero SEI
- prazo
- processos sem responsavel de equipe
- filtros por coluna

### Usabilidade esperada

1. o usuario acessa o dashboard
2. observa metricas
3. decide se quer filtrar a lista ou abrir uma gerencia
4. usa os cards para entrar no painel da area
5. acompanha a fila ativa pelo quadro de processos

## Tela `gerencias.html` - Painel da Gerencia

Base visual: [gerencias.html](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates/gerencias.html#L1)

### O usuario encontra nesta tela

- barra superior com historico, meus processos, perfil e inicio
- painel de notificacoes
- titulo da gerencia
- listas de processos ativos, finalizados e devolvidos
- controles de colunas
- filtros da area
- botoes de acao por processo

### Finalidade operacional

E a tela principal de trabalho da gerencia. Aqui o usuario opera a fila da area.

### Acoes tipicas

- localizar processo
- abrir ficha
- editar
- atribuir
- mover
- finalizar
- devolver
- exportar
- configurar campos extras

### Comportamentos de usabilidade

- alertas fecham automaticamente apos alguns segundos
- a tela possui separacao por abas/escopos
- filtros de coluna sao dinamicos
- algumas acoes ficam ocultas ou desabilitadas conforme perfil e gerencia

## Tela `processo_form.html` - Cadastro, Edicao e Reenvio

Base visual: [processo_form.html](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates/processo_form.html#L1)

### Modos de uso

- cadastro de novo processo
- edicao de processo existente
- reenvio de processo devolvido
- visualizacao somente leitura em alguns cenarios

### Blocos de campos observados

- data de entrada
- numero SEI
- prazo SUROD
- assunto
- interessado
- concessionaria
- gerencias destino
- responsavel ADM
- observacoes
- classificacao institucional
- coordenadoria
- equipe / area
- responsavel da equipe
- status
- prazo da equipe
- observacoes complementares
- destino de saida
- campos extras da gerencia

### Comportamentos importantes de usabilidade

- ha mensagens de erro por campo
- alguns campos ficam somente leitura em edicao ou reenvio
- a escolha de gerencias usa chips clicaveis
- a ordem de clique nas gerencias influencia o contexto do envio
- existem listas de apoio com busca para interessado, concessionaria e responsavel ADM
- o formulario preserva contexto e posicao de rolagem em certos fluxos

### Validacoes visiveis ao usuario

- obrigatoriedade dos campos essenciais
- validacao de concessionaria contra lista oficial
- obrigatoriedade de ao menos uma gerencia
- analise de numero SEI duplicado ou relacionado
- controle de gerencias bloqueadas no reenvio

## Tela `verificar_dados.html` - Historico e Auditoria

Base visual: [verificar_dados.html](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates/verificar_dados.html#L1)

### O usuario encontra nesta tela

- filtros analiticos por gerencia, coordenadoria, equipe, interessado, numero SEI e datas
- alternancia entre visao por processos e por demandas
- metricas do periodo
- tabela consolidada
- acoes para ver ficha e historico

### Finalidade operacional

Serve para auditoria, verificacao de informacoes, consolidacao de finalizados e consulta historica.

### Acoes disponiveis

- aplicar filtros
- limpar filtros
- alternar entre painel de processos e de demandas
- selecionar processo para ver ficha
- selecionar processo para ver historico

## Tela `login.html` - Acesso e Administracao de Usuarios

Base visual: [login.html](/c:/Users/vinicius.ferreira/Desktop/processoadm_deploy/templates/login.html)

### Modos de uso

- login de usuario
- cadastro de usuario
- edicao de usuario
- reset de senha
- exclusao de usuario

### Usabilidade

- usuarios administrativos veem formularios de cadastro e listas de usuarios
- campos de contexto podem ser preenchidos com apoio de listas por gerencia, coordenadoria e equipe
- o sistema ajuda no vinculo de nomes para atribuicao

## Tela `perfil.html`

### Objetivo

- permitir manutencao do proprio cadastro

### Acoes

- atualizar nome
- atualizar email
- atualizar username
- atualizar gerencia
- atualizar coordenadoria
- atualizar equipe
- trocar senha

## Tela `reset_password.html`

### Objetivo

- concluir troca obrigatoria ou voluntaria de senha

## Tela `importar_excel.html`

### Objetivo

- conduzir o usuario pelo fluxo de upload, validacao e importacao de Excel

## Tela `gerencia_campos.html`

### Objetivo

- criar e remover campos extras da gerencia

### Acoes

- informar rotulo do campo
- escolher tipo
- salvar nova configuracao
- remover campo existente

## Funcoes por Botao, Formulario e Acao

## Acoes de usuario

- entrar no sistema
- sair do sistema
- trocar senha
- editar proprio perfil
- cadastrar usuario
- editar usuario
- redefinir senha de usuario
- excluir usuario

## Acoes de processo

- cadastrar processo
- inspecionar numero SEI antes do cadastro
- editar processo
- atualizar classificacao
- salvar campos extras
- atribuir processo
- mover processo
- finalizar processo
- excluir processo
- devolver para gabinete/assessoria
- reenviar processo devolvido
- tratar devolvido

## Acoes de consulta e analise

- acessar dashboard
- acessar painel de gerencia
- acessar historico
- consultar ficha
- consultar historico detalhado
- aplicar filtros por coluna
- ordenar tabelas
- exportar dados
- importar dados

## Validacoes e Regras de Usabilidade

## Login e seguranca

- credenciais invalidas geram mensagem de erro
- troca de senha pode ser obrigatoria
- senha nova precisa ter tamanho minimo

## Usuarios

- nao permite duplicar username
- nao permite duplicar email
- em varios fluxos tambem valida duplicidade de nome
- protege o administrador principal em operacoes sensiveis
- impede autoexclusao do usuario logado

## Processos

- exige campos obrigatorios no cadastro
- valida concessionaria contra lista conhecida
- controla cadastro em gerencias permitidas
- evita conflito com demandas ativas do mesmo numero base
- pode propagar dados base para demandas relacionadas

## Devolvidos

- verifica gerencias ativas, finalizadas e devolvidas antes de reenviar
- pode exigir confirmacao em certos cenarios

## Campos extras

- so podem ser criados por quem tem permissao sobre a gerencia
- ao remover um campo extra, o valor associado tambem e limpo dos processos daquela gerencia

## Impacto das Funcoes no Banco

| Funcao | Tabelas impactadas |
|---|---|
| Login | `usuarios` |
| Cadastro de usuario | `usuarios` |
| Reset de senha | `usuarios` |
| Perfil | `usuarios` |
| Cadastro de processo | `processos`, `movimentacoes` |
| Edicao de processo | `processos`, `movimentacoes` |
| Atribuicao | `processos`, `movimentacoes`, `notificacoes` |
| Movimentacao entre gerencias | `processos`, `movimentacoes`, possivelmente `notificacoes` |
| Finalizacao | `processos`, `movimentacoes`, possivelmente `notificacoes` |
| Devolucao | `processos`, `movimentacoes`, possivelmente `notificacoes` |
| Reenvio de devolvido | `processos`, `movimentacoes` |
| Campos extras | `campos_extra`, `processos` |
| Importacao | `importacoes_temp`, `processos`, `movimentacoes` |
| Notificacoes | `notificacoes` |

## Roteiro de Operacao do Sistema

## Roteiro 1. Usuario operacional

1. entrar no sistema
2. abrir `Meus Processos` ou a gerencia de trabalho
3. localizar o processo
4. editar dados, atribuir ou tramitar
5. finalizar quando o fluxo da gerencia terminar

## Roteiro 2. Gerente

1. acessar painel da gerencia
2. aplicar filtros para organizar a fila
3. acompanhar atribuicoes e pendencias
4. configurar campos extras quando necessario
5. exportar relatorios da area

## Roteiro 3. Assessoria / administrativo

1. acessar dashboard e historico
2. cadastrar ou ajustar usuarios
3. redefinir senhas
4. acompanhar devolvidos
5. operar exportacao/importacao

## Cobertura Funcional Declarada

Com base no codigo atual, a documentacao cobre:

- todas as tabelas do banco encontradas
- todos os endpoints Flask identificados
- todas as telas HTML encontradas
- todos os fluxos principais de usuario, processo, historico, importacao e exportacao

Se o sistema receber novas rotas, novas tabelas ou novos templates, o ideal e versionar esta documentacao junto com o codigo.
