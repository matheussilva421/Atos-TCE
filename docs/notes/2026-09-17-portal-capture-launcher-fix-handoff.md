# Handoff — correção do launcher da captura portal-real (17/09/2026)

## Resultado

O launcher da captura agora encaminha corretamente os argumentos para
`real_portal_session.py` e o runner seleciona a aba **Automação** antes de
parear a ponte. A pasta privada `outputs/TCE-fixed-2026-09-16` recebeu as duas
mesmas correções, com hashes iguais às fontes.

## Causas encontradas

1. `%~dp0` inclui uma barra invertida final. Ao usar
   `"%PACKAGE_ROOT%"`, o `cmd.exe` interpretava a aspa final como escapada e
   juntava `--output`, `--record-root` e `--stay-open` ao valor de
   `--package-root`.
2. `#bridge-status` fica dentro da aba `panel-tab-automation`, que começa
   oculta. O runner esperava visibilidade sem clicar em `#tab-automation`.
3. Após as correções, a execução fora do sandbox chegou a
   `REAL_PORTAL_SESSION_READY`. O portal respondeu `401 Unauthorized` com
   `WWW-Authenticate: Basic`; a autenticação e a navegação continuam sendo
   uma ação humana na janela descartável.

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
- `python -m unittest test_real_portal_session test_portal_capture_launcher test_automation_qualification test_qa_workflow -q`: 59/59 aprovados.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 -TimeoutSeconds 900`: 1.174 checks, 1.172 aprovados, 0 falhas e 2 skips.
- Execução privada com acesso de rede: ponte iniciada, Chrome isolado aberto, extensão pareada e `REAL_PORTAL_SESSION_READY` confirmado.
- O teste em sandbox registrou `net::ERR_NETWORK_ACCESS_DENIED`; a repetição fora do sandbox alcançou o portal, que retornou `401 Unauthorized`.

## Estado atual

A sessão supervisionada continua aberta em modo `observe_only`. Nenhuma
credencial foi digitada pelo runner, nenhum campo foi preenchido e nenhum ato
foi enviado.

O próximo passo humano é resolver o login/autenticação na janela descartável e
navegar até `ProcessonoSetor.asp`, escopo finalístico e marcador `6189`. Depois
da captura, pressione `Ctrl+C` no terminal do runner e execute
`INICIAR.cmd parar`. Só então revisar o JSON sanitizado e iniciar os três
preflights, ainda sem envio.

## GitHub

Commit `94e05bc` (`fix: repair portal capture launcher startup`) registrado
localmente. O push ainda precisa ser confirmado. A pasta `outputs/` permanece
privada e ignorada pelo Git.
