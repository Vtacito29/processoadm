# Comentarios Do Codigo

Este documento explica o que cada arquivo e cada bloco principal do sistema faz.

## Visao Geral
- Tipo: Aplicacao web Flask para controle de processos administrativos.
- Recursos principais: autenticacao, permissoes por perfil, cadastro/edicao de processos, movimentacoes entre gerencias, finalizacao, importacao/exportacao Excel, campos extras por gerencia, notificacoes e assistente interno.
- Banco: PostgreSQL no Render (producao) ou SQLite local (fallback quando `DATABASE_URL` nao existe).

## Arquivos Da Raiz
- `app.py`: arquivo principal da aplicacao (configuracoes, modelos, regras de negocio, rotas e bootstrap).
- `render.yaml`: define servico web e banco no Render (build, start, variaveis e plano).
- `requirements.txt`: dependencias Python do projeto.
- `interessados.txt`: base textual de nomes/cadastros usados por funcionalidades de apoio.
- `controle_processos.db`: banco SQLite local (ambiente local).

## app.py Por Partes
- `# === Caminhos e constantes basicas ===` (inicio): caminhos do projeto, limites de importacao, listas padrao (gerencias, status, equipes etc.).
- Utilitarios de permissao e usuarios (`buscar_usuario_por_login`, `usuario_pode_*`, `perfis_disponiveis_para_usuario`): controlam acesso por perfil e escopo de gerencia.
- Campos extras (`coletar_dados_extra_form`, `obter_campos_por_gerencia`, `listar_campos_gerencia`): camada dinamica de campos por gerencia.
- Setup Flask/SQLAlchemy/Login (`# === Setup Flask, banco e autenticacao ===`): cria app, config de sessao, conexao com banco e login manager.
- `# === Models ===`: modelos `Usuario`, `Processo`, `Movimentacao`, `CampoExtra`, `ImportacaoTemp`, `Notificacao`.
- Hooks de request/contexto (`carregar_usuario`, `exigir_troca_senha`, `contexto_global`): injeta dados globais e valida fluxo de sessao.
- Autenticacao e perfil (`/login`, `/logout`, `/trocar-senha`, `/perfil`, exclusao de usuario): ciclo de usuario.
- `# === Utilitarios de normalizacao e parsing ===`: limpeza de texto, parse de datas, normalizacao de gerencia, agrupamento por numero SEI, historico.
- Importacao Excel (helpers `_registrar_importacao_temp`, `_sugerir_mapeamento_importacao`, `_mensagem_erro_excel`, e rota `/importar-excel`): upload, preview, mapeamento, persistencia em lote.
- Inicializacao e migracoes leves (`inicializar`, `garantir_colunas_extra`, `garantir_usuario_padrao`): prepara estrutura do banco no startup.
- Filtros de template (`date_input`, `date_br`, `trilha_gerencias`): formatacao para HTML.
- Rotas principais:
  - `/`: dashboard geral.
  - `/exportar-geral`: exportacao global em Excel.
  - `/gerencia/<nome>`: painel por gerencia (ativos/finalizados/devolvidos).
  - `/gerencia/<nome>/exportar`: exportacao por gerencia.
  - `/gerencia/<nome>/campos`: configuracao de campos extras.
  - CRUD de processo (`/processo/novo`, `/processo/<id>/editar`, `/finalizar`, `/mover`, `/excluir`, devolucao/reenvio, atribuicao).
  - `/verificar-dados`: consolidacao/auditoria de dados por demanda.
  - `/assistente/responder`: endpoint do assistente interno para perguntas operacionais.
- Bootstrap final (`preparar_app`, `create_app`, `main`): ponto de entrada para `gunicorn` e execucao local.

## Templates (HTML)
- `templates/pg_inicial.html`: dashboard inicial (cards, filtros, atalhos, modais de import/export).
- `templates/gerencias.html`: tela mais importante operacional (listas de ativos/finalizados/devolvidos, acoes por linha, historico inline).
- `templates/processo_form.html`: formulario completo de processo (cadastro, edicao, finalizacao, campos extras).
- `templates/verificar_dados.html`: visao analitica/historica consolidada para conferencia de demandas.
- `templates/importar_excel.html`: fluxo em duas etapas (upload + mapeamento de colunas).
- `templates/gerencia_campos.html`: CRUD de campos extras de uma gerencia.
- `templates/login.html`: login e gestao de usuarios por quem tem permissao.
- `templates/perfil.html`: ajustes de perfil/senha do usuario autenticado.
- `templates/reset_password.html`: tela dedicada a reset de senha.
- `templates/_assistente_global.html`: componente compartilhado de UI do assistente.

## CSS
- `static/css/global.css`: regras globais (base visual, tipografia, componentes comuns).
- `static/css/pg_inicial.css`: estilos especificos do dashboard inicial.
- `static/css/gerencias.css`: estilos do painel de gerencias, chips, tabelas e historico.
- `static/css/processo_form.css`: layout e componentes do formulario de processo.
- `static/css/verificar_dados.css`: estilos da tela de verificacao/auditoria.

## Assets De Imagem
- `static/img/gerencias/*`: ilustracoes usadas em cards e contextualizacao visual por gerencia.

## Observacoes De Manutencao
- Regras de negocio principais estao concentradas em `app.py`; ideal separar em modulos (`services/`, `repositories/`, `routes/`) quando houver refatoracao.
- Importacao Excel faz persistencia em lote; alteracoes de schema/tamanho de colunas devem ser refletidas nos sanitizadores dessa rotina.
- Permissoes impactam renderizacao de botoes e rotas; alteracoes de perfil exigem revisar backend + templates.
