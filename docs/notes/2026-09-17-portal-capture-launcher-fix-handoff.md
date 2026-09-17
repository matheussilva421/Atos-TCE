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
escopo finalístico e marcador `6189`. Confira o JSON final, depois pressione
`Ctrl+C` no terminal do runner e responda `N` à pergunta de encerramento; em
seguida execute
`INICIAR.cmd parar`. Só então revisar o JSON sanitizado e iniciar os três
preflights, ainda sem envio.

## GitHub

Commits locais relevantes: `94e05bc` (`fix: repair portal capture launcher
startup`), `3dc73cd` (`docs: record portal launcher validation`) e `0592aff`
(`fix: capture authenticated portal frames`) e `4824cfb` (`docs: clarify
portal authentication evidence`). O `origin/main` ainda não foi atualizado; a
pasta `outputs/` permanece privada e ignorada pelo Git.
