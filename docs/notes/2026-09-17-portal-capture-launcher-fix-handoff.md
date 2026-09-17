# Handoff — correção do launcher da captura portal-real (17/09/2026)

## Resultado

O launcher da captura agora encaminha corretamente os argumentos para
`real_portal_session.py` e o runner seleciona a aba **Automação** antes de
parear a ponte. O runner também escolhe a página/frame autenticado entre as
páginas abertas e trata um desafio inicial `ERR_INVALID_AUTH_CREDENTIALS` como
recuperável pelo login humano. A pasta privada `outputs/TCE-fixed-2026-09-16`
recebeu as mesmas correções, com hashes iguais às fontes.

## Causas encontradas

1. `%~dp0` inclui uma barra invertida final. Ao usar
   `"%PACKAGE_ROOT%"`, o `cmd.exe` interpretava a aspa final como escapada e
   juntava `--output`, `--record-root` e `--stay-open` ao valor de
   `--package-root`.
2. `#bridge-status` fica dentro da aba `panel-tab-automation`, que começa
   oculta. O runner esperava visibilidade sem clicar em `#tab-automation`.
3. A execução anterior chegou a `REAL_PORTAL_SESSION_READY` e registrou a
   navegação real até `ProcessonoSetor.asp`, mas o snapshot final apontou para
   a página inicial de erro. A causa foi o runner guardar somente a primeira
   página/frame, mesmo quando a interação humana ocorreu em outro frame.
4. O portal respondeu `401 Unauthorized` com `WWW-Authenticate: Basic` no
   primeiro acesso sem sessão; esse desafio pode ser resolvido manualmente na
   janela descartável. Falhas reais de rede continuam bloqueadoras.

## Arquivos alterados

- `work/tce-extractor/portable/INICIAR-CAPTURA-AREA-RESTRITA.cmd`
- `work/tce-extractor/test_portal_capture_launcher.py`
- `work/tce-extractor/real_portal_session.py`
- `work/tce-extractor/test_real_portal_session.py`
- `docs/notes/2026-09-16-runbook-sessao-portal-real.md`

Artefatos privados atualizados, ignorados pelo Git:

- `outputs/TCE-fixed-2026-09-16/INICIAR-CAPTURA-AREA-RESTRITA.cmd`
- `outputs/TCE-fixed-2026-09-16/real_portal_session.py`

## Testes e validações

- `python -m unittest test_portal_capture_launcher -q`: 2/2 aprovados.
- `python -m unittest test_real_portal_session test_portal_capture_launcher test_automation_qualification test_qa_workflow -q`: 61/61 aprovados após a correção de página/frame e autenticação recuperável.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 -TimeoutSeconds 900`: 1.174 checks, 1.172 aprovados, 0 falhas e 2 skips.
- Execução privada com acesso de rede: ponte iniciada, Chrome isolado aberto, extensão pareada e `REAL_PORTAL_SESSION_READY` confirmado.
- O teste em sandbox registrou `net::ERR_NETWORK_ACCESS_DENIED`; a repetição fora do sandbox alcançou o portal, que retornou `401 Unauthorized`.

## Estado atual

A execução supervisionada anterior foi encerrada em modo `observe_only`.
Nenhuma credencial foi digitada pelo runner, nenhum campo foi preenchido e
nenhum ato foi enviado. A gravação privada preserva as ações manuais até
`ProcessonoSetor.asp`, mas o JSON daquela execução não deve virar fixture.

O próximo passo humano é executar novamente o launcher corrigido, resolver o
login/autenticação na janela descartável e navegar até `ProcessonoSetor.asp`,
escopo finalístico. O marcador deve ser selecionado manualmente no portal; o
campo opcional do painel deve ficar vazio para a automação ler o marcador
vigente. Confira o JSON final, depois pressione `Ctrl+C` no terminal do runner
e responda `N` à pergunta de encerramento; em seguida execute
`INICIAR.cmd parar`. Só então revisar o JSON sanitizado e iniciar os três
preflights, ainda sem envio.

## GitHub

Commits locais relevantes: `94e05bc` (`fix: repair portal capture launcher
startup`), `3dc73cd` (`docs: record portal launcher validation`) e `0592aff`
(`fix: capture authenticated portal frames`) e `4824cfb` (`docs: clarify
portal authentication evidence`). O `origin/main` ainda não foi atualizado; a
pasta `outputs/` permanece privada e ignorada pelo Git.

## Atualização — marcador escolhido manualmente (17/09/2026)

O marcador do portal não é fixo. Quando o campo opcional **Marcador do lote**
fica vazio, a extensão lê o marcador atualmente selecionado na Área Restrita,
confirma label e value e mantém essa identidade durante a análise. Se o
marcador mudar durante a execução, o fluxo pausa para revisão; ele não escolhe
outro marcador automaticamente. O valor `6189` deixou de ser requisito do
runbook.

O teste existente `reads and locks the marker already selected in the Area
Restrita without a typed marker or dataset` confirmou que nenhuma ação
`filter_marker` é enviada nesse modo. A cópia privada de
`extensao-complementar-ato/sidepanel/panel.html` foi atualizada junto com a
fonte e os hashes conferem.

Commit local desta atualização: `d5acfd9` (`feat: use manually selected portal
marker`). Testes da extensão: 411/411 aprovados; testes do controlador de
automação: 69/69 aprovados. O gate completo permaneceu em 1.174 verificações,
1.172 aprovadas, 0 falhas e 2 skips.

## Atualização — limpeza de runner antigo (17/09/2026)

O arquivo de observação permaneceu inválido porque um launcher antigo ainda
mantinha `real_portal_session.py --stay-open` ativo e reescrevia o mesmo JSON.
Após confirmação do usuário, a árvore antiga foi encerrada; o runner antigo
não está mais ativo e o JSON parou de mudar. Os artefatos privados foram
preservados. Antes da nova captura, parar a ponte residual com
`INICIAR.cmd parar` se necessário e iniciar uma sessão limpa.

## Atualização — reconhecimento da lista autenticada (17/09/2026)

A captura mais recente navegou até `ProcessonoSetor.asp`, registrou a seleção
manual do marcador e o clique em **Consultar**, e encontrou 59 chaves de
processo. O snapshot final ainda marcou `authenticated_ui_signal=false`
porque essa lista legada não exibe “Sair” ou “Meus Processos”. O sanitizador
agora reconhece a rota autenticada `SISTEMAS/Processo/ProcessonoSetor.asp` como
lista e sinal de autenticação, sem depender de texto de login.

O ciclo TDD foi RED (o novo teste falhou com `False != True`) e GREEN (62/62
testes focados aprovados). A cópia privada de
`real_portal_session.py` foi atualizada e o hash confere com a fonte. A sessão
anterior continua sem promoção a fixture enquanto não houver todos os IDs do
contrato; nenhum campo foi preenchido e nenhum ato foi enviado.

Commit local desta correção: `dcf1a94` (`fix: recognize authenticated process
list route`).

## Atualização — captura autenticada da lista (17/09/2026)

A sessão `real-portal-20260917T112749291744Z` terminou com origem
`https://novaarearestrita.tce.rn.gov.br`, `authenticated_ui_signal=true`,
`process_list_signal=true`, `portal_extension_origin_match=true`, sem erro de
navegação e com `submission_performed_by_runner=false`. A gravação preserva a
interação manual com o seletor de marcador. O JSON ainda não é fixture completa:
sete IDs de campos pertencentes ao formulário continuam ausentes porque a
captura terminou na lista `ProcessonoSetor.asp`. Para completar o contrato,
será necessário abrir manualmente um ato elegível e parar na tela do
formulário, sem preencher ou enviar.

## Atualização — seleção do formulário autenticado (17/09/2026)

A sessão `real-portal-20260917T113259543003Z` registrou a navegação manual até
`ComplementarAto.asp`, mas o snapshot final ainda escolhia a lista porque a
rota do formulário não contribuía para `authenticated_ui_signal`. O runner
agora reconhece também a rota autenticada `ComplementarAto.asp`, fazendo o
formulário com os IDs completos vencer a lista no critério de seleção de
frames.

O ciclo TDD foi RED (o novo teste falhou com `False != True`) e GREEN (63/63
testes focados aprovados). A cópia privada de `real_portal_session.py` foi
atualizada e o gate completo passou com 1.174 verificações, 1.172 aprovadas,
0 falhas e 2 skips. Nenhum campo foi preenchido e nenhum ato foi enviado.

Commit local desta correção: `dbe2286` (`fix: prioritize authenticated
complement form`).

## Atualização — captura estrutural completa do formulário (17/09/2026)

A sessão `real-portal-20260917T114358997770Z` concluiu a captura no formulário
autenticado `ComplementarAto.asp`. A observação confirmou origem
`https://novaarearestrita.tce.rn.gov.br`, `authenticated_ui_signal=true`,
`portal_extension_origin_match=true`, nove IDs contratuais conhecidos, nenhum
ID ausente, `portal_drift=false` e ausência de erro de navegação.

O formulário foi aberto manualmente e permaneceu sem preenchimento. O marcador
continuou sendo escolhido pelo usuário; o campo opcional do painel pode ficar
vazio para acompanhar o marcador atualmente selecionado. Nenhum envio ou
finalização foi realizado: `submission_performed_by_runner=false`.

A gravação privada possui 69 passos. O runner registra o estado persistido como
`BLOCKED` por desenho enquanto a sessão real não é promovida a fixture, e houve
dois erros de gravação reportados no artefato; isso não alterou a observação
estrutural, que atingiu todos os IDs e os gates de autenticação/origem.

Status: captura estrutural concluída. A próxima etapa, somente se solicitada,
é gerar uma fixture sanitizada derivada dessa observação. Não promover nem
enviar atos automaticamente.

## Atualização — fixture sanitizada derivada (17/09/2026)

A observação privada foi convertida para o arquivo versionável
`work/tce-extractor/tests/fixtures/real-portal-observation-form.json`. A fonte
em `outputs/` não foi substituída. A fixture contém somente o contrato
estrutural, sinais de autenticação/origem e os nove IDs permitidos; não contém
identidade de processo ou pessoa, credenciais, tokens ou evidência de envio.

SHA-256 da fixture: `A6224308AFB2F86F0CD32BB7C8F9E3B1409F8617C3BFC1531ACBF143CE921F3A`.

Validação específica: `python -m unittest test_real_portal_session -q` — 34
testes aprovados, 0 falhas. Gate completo:
`verify-project.ps1 -TimeoutSeconds 900` — 1.174 verificações executadas,
1.172 aprovadas, 0 falhas e 2 skips. O arquivo ainda precisa ser registrado
em commit; a qualificação de envio, preflights reais e qualquer envio continuam
bloqueados até as etapas próprias e autorização explícita.

## Atualização — classificação segura da observação estrutural (17/09/2026)

Foi acrescentado um teste de contrato em
`portable/extensao-complementar-ato/tests/portal-submit.test.mjs`. Ele carrega
a fixture real sanitizada pela interface pública `classifyPortalOutcome` e
confirma que uma observação estrutural sem evidência de aceitação/persistência
permanece `unconfirmed`. O classificador não precisou de alteração: a
implementação existente já falha fechada nesse cenário.

Suíte da extensão: 412 testes aprovados, 0 falhas. Gate completo:
`verify-project.ps1 -TimeoutSeconds 900` — 1.175 verificações executadas,
1.173 aprovadas, 0 falhas e 2 skips. Nenhuma ação foi feita no portal; envio
real, preflights e qualificação continuam pendentes.

## Atualização — resultado da sessão de preflight (17/09/2026)

A sessão `real-portal-20260917T120633932395Z` foi encerrada sem envio e
confirmou novamente a origem oficial autenticada, os nove IDs do formulário,
nenhuma ausência, `portal_drift=false` e
`submission_performed_by_runner=false`. A gravação registrou três visitas ao
formulário `ComplementarAto.asp`, cada uma com seleção manual do interessado,
sem preenchimento dos campos.

O clique em **Atualizar prévia** no painel não apareceu na gravação. Assim, a
sessão comprova três inspeções estruturais read-only, mas não comprova os três
preflights da automação nem as propostas documentais correspondentes. Para
fechar esse gate, é necessária uma nova sessão curta: abrir cada formulário,
clicar somente em **Atualizar prévia**, aguardar o resultado e repetir nos três
atos. Não clicar em preenchimento ou envio.

## Atualização — sessão de preflight iniciada (17/09/2026)

Foi iniciada uma nova sessão privada do pacote para os preflights reais em
modo de observação. A ponte local está conectada na porta `18743` e o Chrome
isolado abriu com o runner `real-portal-20260917T120633932395Z`. O código de
pareamento foi usado somente em memória pelo launcher e não foi registrado.

A sessão está aguardando login manual e navegação do operador. O procedimento
pendente é abrir três atos representativos, sem preencher campos e sem clicar
em **Complementar Ato**. O marcador deve continuar sendo escolhido manualmente;
o campo opcional do painel deve ficar vazio. Até a conclusão dessa etapa não há
preflight real promovido nem qualquer envio autorizado.

## Atualização — confirmação de atualização automática da prévia (17/09/2026)

O usuário esclareceu que acionou o fluxo nos três atos e que, ao entrar em cada
tela **Complementar Ato**, a prévia do painel foi atualizada automaticamente.
Portanto, a interpretação anterior baseada exclusivamente na ausência de um
clique em `refresh-button` estava incompleta. A sessão
`real-portal-20260917T120633932395Z` deve ser tratada como três preflights reais
read-only observados: três entradas na rota do formulário, três seleções manuais
do interessado, origem oficial autenticada, nove IDs presentes, sem deriva e
sem preenchimento ou envio pelo runner.

O comportamento também é compatível com o código do painel: ao restaurar a
sessão e o dataset, `init()` chama `refresh()`, que obtém o snapshot atual,
resolve a prévia e publica a seleção na ponte sem preencher campos. A gravação
sanitizada preserva a estrutura da tela e os eventos de navegação, mas não os
valores das propostas exibidas; a comparação documental de cada proposta ainda
precisa de evidência própria antes de qualquer qualificação de envio.

Após essa sessão, uma segunda execução privada
`real-portal-20260917T121322579301Z` foi aberta por engano e encerrada antes de
qualquer interação no portal. Ela terminou com origem nula, sem autenticação e
não deve ser usada como evidência nem como motivo para repetir os três
preflights. O arquivo privado corrente em `outputs/` foi sobrescrito por essa
execução vazia; a gravação boa da sessão `120633932395Z` e a fixture versionada
continuam preservadas. Nenhum envio ocorreu.

Status: os três preflights read-only estão observados conforme confirmação do
usuário. Permanecem pendentes a validação dos valores documentais e qualquer
gate separado de envio supervisionado; manter `autoSubmit=false` e
`real_send_enabled=false`.

## Atualização — launcher sem janela interativa (17/09/2026)

Duas tentativas de iniciar uma nova sessão pelo ambiente do Codex não abriram
uma janela utilizável para o operador. A execução
`real-portal-20260917T122613521626Z` terminou com página de erro e a execução
`real-portal-20260917T123123759020Z` terminou com `pairing rejected` antes de
qualquer interação no portal. Nenhuma delas é evidência de preflight e nenhuma
preencheu ou enviou ato.

O launcher deve ser executado pelo usuário em uma janela própria e interativa
do PowerShell, no diretório do pacote. O Chrome isolado e o pareamento dependem
desse desktop; o código deve ser informado no painel da extensão e o login
continua manual.

## Atualização — três formulários revisados na sessão interativa (17/09/2026)

A sessão `real-portal-20260917T123415041541Z` foi encerrada pelo operador após
três entradas em `ComplementarAto.asp` e três seleções manuais do interessado.
O usuário confirmou que precisou clicar em **Atualizar prévia** no primeiro ato
e concluiu os dois restantes; o gravador estrutural não captura de forma
confiável esse clique feito no painel, mas registrou a jornada portal-side,
`human_stop=1` e nenhum evento de preenchimento, aplicação ou envio.

O artefato privado dessa sessão tem 96 passos, dois erros de gravação e nenhum
evento de envio. Ele serve como registro estrutural read-only, junto com a
confirmação manual do operador; não contém os valores documentais exibidos no
painel. A verificação independente das propostas continua pendente antes de
qualquer gate de envio.

O caminho privado `dados-locais/observacao-portal-real.json` não deve ser usado
para promover essa sessão: ele foi sobrescrito por uma execução anterior
inválida (`real-portal-20260917T122613521626Z`, origem nula e pareamento
incorreto). A gravação `123415041541Z` e a fixture sanitizada versionada estão
preservadas. Nenhum ato foi preenchido ou enviado.

## Atualização — autorização para preenchimento supervisionado (17/09/2026)

O usuário informou que já conferiu as propostas documentais e autorizou o
preenchimento supervisionado dos atos. A autorização é restrita à aplicação
dos campos para revisão no formulário. O envio, a finalização e qualquer ação
externa continuam fora do escopo desta etapa.

Antes da execução, foram confirmadas as guardas do pacote: `autoSubmit=false`,
`real_send_enabled=false` e marcador opcional nulo, para que o marcador seja
sempre escolhido pelo usuário. A sessão interativa anterior foi encerrada;
retomar exige uma nova execução do launcher no PowerShell do usuário, com
login manual e pareamento manual.

## Atualização — preenchimento supervisionado concluído (17/09/2026)

Na sessão `real-portal-20260917T124507014264Z`, o usuário autorizou e concluiu
o preenchimento supervisionado após revisar as propostas. O registro estrutural
confirmou três entradas em `ComplementarAto.asp`, três seleções do interessado
e 18 mudanças de campos: `txtModalidade`, `txtDataDOE`, `txtCargo`,
`txtMatricula`, `txtDataNascimento` e `txtFundamentoLegal`, uma sequência de
seis campos por ato. Não houve evento de preenchimento de marcador, envio,
finalização ou submissão; o marcador continuou sob escolha manual do usuário.

O registro privado terminou após a interação do operador com 119 passos, um
erro de gravação e nenhum evento estrutural de envio. O estado `BLOCKED` do
artefato continua sendo a proteção esperada para a sessão real; não é falha de
preenchimento. As propostas foram aplicadas somente para revisão no portal.

O JSON privado corrente em `dados-locais/observacao-portal-real.json` continua
sem valor probatório para esta sessão porque foi sobrescrito por uma execução
antiga inválida. A evidência utilizável é a gravação privada
`real-portal-20260917T124507014264Z/recording.json`, combinada com a confirmação
do operador. Nenhum envio ocorreu. Qualquer etapa de envio real permanece
separada e desabilitada.

## Atualização — piloto com marcador dinâmico pausado (17/09/2026)

O usuário autorizou a continuidade do piloto supervisionado e determinou que a
automação não escolha o marcador, pois ele muda periodicamente. O fluxo deve
usar o marcador já selecionado manualmente no portal e manter o campo opcional
`#automation-marker` vazio. Login, seleção do marcador e eventual confirmação
visual continuam sendo ações humanas.

Foi corrigido na fonte
`work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
o início do piloto sem marcador digitado: depois de obter a primeira lista, o
controlador captura o marcador atualmente selecionado no portal, trava esse
valor para a execução e não envia `filter_marker`. Foi acrescentado o teste
regressivo correspondente em
`work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`.
A cópia privada em `outputs/TCE-fixed-2026-09-16/extensao-complementar-ato/`
foi sincronizada com a fonte; ela não é fonte de código nem deve ser versionada.

Também foi criado o launcher operacional temporário
`work/tce-extractor/.codex-live-pilot.py`. Ele abre um perfil Playwright
isolado, pareia a extensão com a ponte local, importa o lote, reconhece o
marcador já selecionado, abre um registro elegível, atualiza a prévia e inicia
um lote de um ato com `auto_submit=true` somente após a confirmação do painel.
O launcher não escolhe marcador e só considera sucesso com evento
`send_confirmed` e uma linha em `confirmed_acts`.

O launcher foi ajustado para tentar novamente a rota oficial quando a página
fica em `chrome-error://` e para reconhecer conteúdo do portal em frames sem
URL própria do host. A sintaxe passou. A primeira sessão permaneceu em
`AGUARDANDO_PORTAL` mesmo depois de uma lista aparecer numa janela; ela foi
interrompida com Ctrl+C. Ao relançar, a primeira tentativa encontrou o perfil
preso (`TargetClosedError`); a árvore antiga do Chromium isolado foi fechada
pelo PID 24676 e filhos. A segunda tentativa abriu o Chromium, mas terminou
com `Page.wait_for_function: Target page, context or browser has been closed`
enquanto aguardava o pareamento, com processo 30484 saindo com código 21.

Nenhum piloto chegou a criar execução. A conferência do SQLite mostrou:
`runs=0`, `events=0`, `commands=0`, `confirmed_acts=0`. Portanto nenhum campo
foi aplicado, nenhum ato foi enviado e não há confirmação de resultado externo.
A ponte local continuou disponível na porta 18743 durante a pausa; o código de
pareamento é temporário e deve ser lido novamente em uma retomada.

Validações realizadas neste bloco:

- teste focal do controlador: 18 aprovados, 0 falhas;
- suíte da extensão: 413 aprovados, 0 falhas;
- `python -m py_compile .\\.codex-live-pilot.py`: aprovado;
- `git diff --check`: aprovado;
- gate completo `verify-project.ps1` ainda não foi repetido depois da última
  alteração de fonte;
- o piloto real permanece `NOT_TESTED`, sem evidência de envio.

Estado do GitHub no momento da pausa: branch `main` alinhada com `origin/main`,
com alterações locais não commitadas em `automation-controller.js`,
`automation-controller.test.mjs` e o launcher temporário
`.codex-live-pilot.py`. O handoff também fica alterado por esta atualização.
Nenhum commit ou push foi feito, respeitando a solicitação do usuário para
parar.

Retomada recomendada:

1. Conferir `git status --short --branch` e ler este handoff.
2. Decidir se o launcher temporário deve ser mantido como ferramenta de QA;
   se for mantido, adicionar uma cobertura pequena para a navegação de retry.
3. Rodar novamente o gate completo em
   `work/tce-extractor/verify-project.ps1` e a descoberta Python.
4. Iniciar ou confirmar a ponte local e executar
   `python .\\.codex-live-pilot.py` a partir de
   `C:\\Users\\slvma\\Downloads\\Github\\Atos-TCE\\work\\tce-extractor`.
5. Na janela isolada criada por essa execução, fazer login manual se for
   solicitado, selecionar manualmente o marcador vigente e deixar a lista
   autenticada aberta. O campo de marcador do painel deve permanecer vazio.
6. Antes de qualquer nova tentativa, consultar o SQLite para garantir que não
   existe execução pendente ou confirmação. Só considerar sucesso com
   `send_confirmed`, `confirmed_acts=1` e confirmação visual do ato persistido.
7. Depois das validações, atualizar este handoff, fazer commit e push somente
   dos arquivos de fonte, teste e documentação aprovados; manter dados
   privados, perfis, logs, HARs e traces fora do Git.
