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
