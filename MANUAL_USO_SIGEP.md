# Manual de Uso do SIGEP

## 1. Visão geral

O SIGEP, Sistema Integrado de Gestão de Processos, foi desenvolvido para controlar o ciclo de vida de processos entre gerências, desde o cadastro inicial até a finalização e consulta histórica.

No sistema, um mesmo número de processo pode gerar demandas em mais de uma gerência. Cada demanda é acompanhada individualmente, com registro de responsáveis, status, prazos, tramitações, devoluções e histórico.

## 2. Perfis de acesso

O que cada perfil pode fazer:

- `Usuário`: visualiza processos de todas as gerências e pode editar, atribuir e dar andamento apenas nas gerências liberadas no seu perfil.
- `Assessoria`: tudo que o Usuário faz, além de cadastrar processos, exportar relatórios por gerência e configurar campos extras nas gerências liberadas.
- `Gerente`: tudo que o Usuário faz, com permissões da Assessoria nas gerências liberadas e possibilidade de cadastrar usuários da própria gerência.
- `Acesso total`: acesso global ao sistema, inclusive importação geral, exportação geral e administração mais ampla.

Observações importantes:

- O acesso depende das `gerências liberadas` no cadastro do usuário.
- O usuário comum pode, opcionalmente, ter permissão para `finalizar processos na gerência`.
- No primeiro acesso, o sistema pode exigir a troca da senha temporária.

## 3. Primeiro acesso

### 3.1 Entrar no sistema

1. Acesse a tela de login.
2. Informe `usuário ou e-mail`.
3. Informe a `senha`.
4. Clique em `Entrar`.

### 3.2 Trocar a senha temporária

Se o sistema solicitar:

1. Informe a `senha atual`.
2. Digite a `nova senha`.
3. Confirme a nova senha.
4. Clique em `Salvar nova senha`.

Regra do sistema:

- A nova senha deve ter pelo menos `6 caracteres`.

## 4. Página inicial

A página inicial funciona como painel geral do sistema.

Nela você encontra:

- cards das gerências com quantidade de processos ativos;
- indicadores como `Em andamento`, `Finalizados` e `Tempo médio`;
- filtro geral por `Gerência`, `Número SEI` e situação de `Prazo`;
- atalho para `Histórico de Processos`;
- atalho para `Meus Processos`;
- botão `Novo processo`, quando o perfil permitir;
- menu `Perfil`, com edição cadastral, troca de senha e, para quem tiver permissão, cadastro de usuários.

### 4.1 Como localizar um processo na página inicial

1. No painel inicial, use os filtros no topo da tabela.
2. Se quiser, filtre por `Gerência`.
3. Digite o `Número SEI` total ou parcial.
4. Se necessário, escolha a situação do `Prazo`.
5. Clique em `Buscar`.
6. Para remover os filtros, clique em `Limpar`.

### 4.2 Como entrar em uma gerência

1. Na página inicial, localize o card da gerência desejada.
2. Clique em `Acessar`.
3. O sistema abrirá o painel detalhado daquela gerência.

## 5. Painel da gerência

Cada gerência possui um painel com abas e filtros próprios.

As abas principais são:

- `Interações (Ativos)`: processos em andamento na gerência.
- `Arquivos Recentes (Finalizados)`: processos já concluídos naquela etapa.
- `Processos Devolvidos`: disponível para tratamento de devoluções na Assessoria.

No painel também podem aparecer:

- botão de `notificações`;
- menu para `Configurar campos extras`;
- opção de `Exportar Excel`;
- ações rápidas por processo, como editar, visualizar, atribuir, devolver e finalizar.

### 5.1 Como filtrar processos na gerência

1. Abra a gerência desejada.
2. Na aba `Interações`, preencha os filtros que desejar.
3. Você pode usar `Número SEI`, `Coordenadoria`, `Equipe / área` e `Responsável atribuído`.
4. Clique em `Buscar`.

## 6. Cadastro de novo processo

Somente perfis com permissão de cadastro conseguem usar esse recurso.

### 6.1 Como cadastrar

1. Na página inicial, clique em `Novo processo`.
2. Preencha `Data entrada na SUROD`.
3. Informe o `Número processo SEI`.
4. Informe o `Prazo - SUROD`, se houver.
5. Preencha `Assunto`.
6. Preencha `Interessado`.
7. Se aplicável, selecione a `Concessionária`.
8. Marque uma ou mais `Gerências destino`.
9. Informe `Responsável Adm`.
10. Preencha `Observação`, se necessário.
11. Salve o cadastro.

### 6.2 Regras importantes do cadastro

- O `Número SEI`, `Assunto`, `Interessado`, `Gerências destino` e `Responsável Adm` são tratados como dados essenciais.
- Um mesmo cadastro pode gerar demandas para várias gerências ao mesmo tempo.
- O sistema bloqueia novo cadastro quando já existe demanda ativa do mesmo processo na mesma gerência.
- Se o número já existir em outras demandas, o sistema pode propagar atualização de `Assunto`, `Interessado` e `Concessionária` para manter consistência.

## 7. Edição e tratamento de um processo

Ao abrir um processo para edição, o sistema exibe os dados da demanda e, conforme a gerência, permite complementar informações operacionais.

Campos operacionais comuns:

- coordenadoria;
- equipe ou área;
- responsável da equipe;
- tipo de processo;
- palavras-chave;
- status;
- data do status;
- prazo da equipe;
- observações complementares;
- campos extras da gerência, quando existirem.

### 7.1 Como editar um processo

1. No painel da gerência, localize o processo.
2. Clique no ícone de `Editar` ou `Visualizar`.
3. Atualize os campos necessários.
4. Clique em `Salvar` na própria tela.

Observação:

- Se o usuário tiver apenas visualização naquela gerência, o sistema abrirá o processo em modo somente leitura.

## 8. Atribuição de processos

O SIGEP permite atribuir um processo a um usuário ou responsável da equipe.

### 8.1 Como atribuir

1. No painel da gerência, localize o processo.
2. Clique no ícone de `Atribuir`.
3. Escolha o destinatário listado no modal.
4. Confirme a atribuição.

### 8.2 Como assumir um processo para si

1. Abra a ação de atribuição do processo.
2. Escolha a opção de assumir para o seu próprio usuário, quando disponível.
3. Confirme.

### 8.3 Regras da atribuição

- A atribuição respeita a gerência da demanda.
- O destinatário precisa estar no contexto permitido da demanda.
- O sistema considera coordenadoria e equipe para validar a atribuição.
- Quando o destinatário é um usuário do sistema, ele pode receber notificação.

## 9. Como finalizar uma demanda na gerência

Finalizar, no SIGEP, significa encerrar a etapa atual da gerência. Normalmente a demanda segue para `SAÍDA`, e o sistema pode criar uma nova demanda em outra gerência quando isso fizer parte do fluxo.

### 9.1 Antes de finalizar

Para demandas fora da SAÍDA, o sistema exige o preenchimento de:

- `Coordenadoria`;
- `Equipe / Área`;
- `Atribuído SEI`;
- `Status`.

### 9.2 Como finalizar

1. No painel da gerência, clique no ícone de finalizar ou abra o processo.
2. Revise os campos obrigatórios.
3. No campo de trâmite, informe para onde a demanda seguirá.
4. Registre comentário, se necessário.
5. Clique em `Finalizar`.

### 9.3 O que acontece após a finalização

- A etapa atual é encerrada.
- A demanda passa pela `SAÍDA`.
- Se houver uma gerência de destino, o sistema pode criar uma nova demanda para essa gerência.
- O histórico da movimentação fica registrado.

## 10. Como finalizar na SAÍDA

A gerência `SAÍDA` funciona como checkpoint final.

### 10.1 Como concluir na SAÍDA

1. Abra a gerência `SAÍDA`.
2. Localize o processo.
3. Clique em `Finalizar processo`.
4. Informe o `Destino SAÍDA`.
5. Revise a ficha e os dados complementares.
6. Clique em `Finalizar na SAÍDA`.

### 10.2 Regras da SAÍDA

- O sistema exige o preenchimento do `Destino SAÍDA`.
- Se ainda existir demanda ativa do mesmo processo em outra gerência, a finalização definitiva pode ser bloqueada.
- O sistema mantém a rastreabilidade das gerências envolvidas e dos snapshots da demanda.

## 11. Devolução de processos

Há dois tipos principais de devolução no sistema.

### 11.1 Devolver para a Assessoria

Esse fluxo é usado pelas gerências ativas para devolver uma demanda à `GABINETE`, onde ela fica disponível na aba de devolvidos da Assessoria.

Passo a passo:

1. No painel da gerência, localize o processo.
2. Clique no ícone de `Devolver para a Assessoria`.
3. Informe o `motivo da devolução`.
4. Confirme a operação.

Resultado:

- o processo passa para `GABINETE`;
- o status é atualizado para devolvido;
- a atribuição é removida;
- o motivo fica salvo no histórico e nos dados da devolução.

### 11.2 Devolver a partir da SAÍDA

Na SAÍDA, a devolução pode mandar o processo de volta para uma gerência específica.

Passo a passo:

1. Abra o processo que está na `SAÍDA`.
2. Clique na opção de `Devolver`.
3. Selecione a gerência de retorno.
4. Informe um comentário.
5. Confirme.

Resultado:

- se o retorno for para a gerência de origem, a demanda volta para ela;
- em alguns cenários, o sistema cria uma nova demanda para a gerência escolhida;
- o histórico registra a movimentação.

## 12. Tratamento de processos devolvidos na Assessoria

A aba `Processos Devolvidos` fica disponível para tratamento na gerência `GABINETE`.

### 12.1 Como reenviar um processo devolvido

1. Abra `GABINETE`.
2. Vá para a aba `Processos Devolvidos`.
3. Localize o processo.
4. Clique em `Reenviar`.
5. Escolha a nova gerência ou as novas gerências de destino.
6. Confirme o reenvio.

Regras:

- apenas usuários com liberação para `GABINETE` podem tratar devolvidos;
- o sistema bloqueia envio para gerência onde já exista ou já tenha existido demanda do mesmo processo, conforme as validações do fluxo.

### 12.2 Como excluir um processo da caixa de devolvidos

1. Abra a aba `Processos Devolvidos`.
2. Localize o item.
3. Clique em `Excluir`.
4. Confirme a exclusão.

Use essa ação apenas quando a demanda devolvida não precisar mais ser reenviada.

## 13. Histórico de Processos

A tela `Histórico de Processos` concentra consultas analíticas e auditoria de processos finalizados.

Nela é possível:

- consultar processos finalizados;
- consultar demandas finalizadas;
- filtrar por gerência, coordenadoria, equipe, interessado, número SEI e intervalo de datas;
- abrir ficha técnica;
- abrir histórico detalhado;
- acompanhar indicadores consolidados.

### 13.1 Como consultar o histórico

1. Clique em `Histórico de Processos` no menu superior.
2. Escolha os filtros desejados.
3. Clique em `Aplicar`.
4. Na tabela, selecione o processo desejado.
5. Use os botões `Ver ficha` ou `Ver histórico` para aprofundar a análise.

## 14. Campos extras por gerência

As gerências podem ter campos personalizados para registrar informações específicas.

### 14.1 Como criar um campo extra

1. Entre na gerência desejada.
2. Abra o menu de ações no topo do painel.
3. Clique em `Configurar campos extras`.
4. Na tela de campos extras, informe o `Nome do campo`.
5. Escolha o `Tipo`: `Texto livre`, `Número` ou `Data`.
6. Clique em `Salvar campo`.

### 14.2 Como remover um campo extra

1. Na tela de campos extras, localize o campo existente.
2. Clique em `Remover`.
3. Confirme a remoção.

Atenção:

- a remoção descarta os dados já salvos nesse campo.

## 15. Importação de planilha Excel

Esse recurso é voltado para perfis com permissão de importação.

### 15.1 Como importar

1. Na página inicial, abra o menu de ações.
2. Clique em `Importar Excel`.
3. Selecione o arquivo `.xlsx` ou `.xls`.
4. Clique em `Continuar para mapeamento`.
5. Escolha a aba da planilha.
6. Informe a linha de cabeçalho, se necessário.
7. Faça o mapeamento das colunas da planilha para os campos do SIGEP.
8. Revise o preview das primeiras linhas.
9. Clique em `Importar planilha`.

### 15.2 Regras da importação

- O `Número SEI` é o campo mínimo mais importante para importação.
- Colunas não mapeadas podem ser ignoradas.
- O sistema aceita campos extras com identificação da gerência.
- Sempre valide o preview antes de confirmar a importação.

## 16. Exportação de dados

O sistema possui exportação por gerência e, para perfis mais amplos, exportação geral.

### 16.1 Como exportar por gerência

1. Entre no painel da gerência.
2. Abra o menu de ações.
3. Clique em `Exportar Excel`.
4. Confirme a geração do arquivo.

### 16.2 Como exportar geral

1. Na página inicial, use o menu de ações disponível para seu perfil.
2. Escolha a exportação geral.
3. Aguarde a geração do arquivo.

## 17. Perfil do usuário

Cada usuário pode manter seus próprios dados atualizados.

### 17.1 Como editar o perfil

1. No menu superior, clique em `Perfil`.
2. Clique em `Editar perfil`.
3. Atualize nome, e-mail, usuário, gerência, coordenadoria e equipe.
4. Informe sua `senha atual`.
5. Se quiser, informe uma nova senha.
6. Clique em `Salvar alterações`.

Observação:

- usuários sem acesso total precisam manter gerência, coordenadoria e equipe preenchidas.

## 18. Cadastro e gestão de usuários

Esse recurso é permitido para perfis administrativos.

### 18.1 Como cadastrar um novo usuário

1. Abra o menu `Perfil`.
2. Clique em `Cadastrar usuário`.
3. Informe a gerência vinculada, se aplicável.
4. Informe coordenadoria e equipe.
5. Preencha `Nome completo`.
6. Preencha `Nome de usuário`.
7. Preencha `E-mail`.
8. Selecione as `Gerências liberadas`.
9. Escolha o `Perfil de acesso`.
10. Defina se o usuário comum poderá `finalizar processos na gerência`.
11. Clique em `Gerar acesso`.
12. Anote e entregue ao colaborador o usuário e a senha temporária exibidos pelo sistema.

### 18.2 Como editar um usuário

1. Na mesma tela de cadastro, vá para `Gerenciar usuários`.
2. Localize o usuário.
3. Clique em `Editar`.
4. Ajuste nome, e-mail, gerências, perfil, coordenadoria, equipe e permissões.
5. Clique em `Salvar alterações`.

### 18.3 Como redefinir senha de um usuário

1. Em `Gerenciar usuários`, localize o colaborador.
2. Clique em `Redefinir senha`.
3. Confirme.
4. Entregue a nova senha temporária ao usuário.

### 18.4 Como excluir um usuário

1. Em `Gerenciar usuários`, localize o cadastro.
2. Clique em `Excluir`.
3. Confirme a operação.

Observações:

- o sistema não permite excluir o próprio usuário;
- usuários estratégicos podem ter restrições adicionais de edição ou exclusão.

## 19. Boas práticas de uso

- Sempre preencha corretamente `coordenadoria`, `equipe`, `responsável` e `status` antes de finalizar uma demanda.
- Use a atribuição para deixar claro quem está responsável pelo tratamento.
- Registre comentários e observações quando houver exceções, devoluções ou decisões importantes.
- Antes de reenviar ou criar nova demanda, confira se já existe histórico anterior para a mesma gerência.
- Revise o histórico antes de concluir definitivamente na SAÍDA.
- Na importação de planilhas, valide o preview e o mapeamento antes de confirmar.

## 20. Resumo rápido dos fluxos

### Fluxo padrão de trabalho

1. Cadastrar processo.
2. Gerar demanda para uma ou mais gerências.
3. Atribuir responsável.
4. Preencher dados operacionais.
5. Finalizar a etapa da gerência.
6. Passar pela SAÍDA.
7. Finalizar definitivamente ou devolver/reencaminhar, conforme o caso.

### Fluxo de devolução para Assessoria

1. Gerência ativa devolve para GABINETE com motivo.
2. Processo aparece em `Processos Devolvidos`.
3. Assessoria analisa.
4. Assessoria reenvia para nova gerência ou exclui da caixa de devolvidos.

## 21. Observação final

Este manual foi elaborado com base nas telas, permissões e fluxos implementados no sistema atual. Se desejar, o próximo passo pode ser transformar este material em:

- versão mais curta para treinamento;
- versão em PDF;
- versão com capturas de tela;
- versão separada por perfil, por exemplo Usuário, Assessoria e Gerente.
