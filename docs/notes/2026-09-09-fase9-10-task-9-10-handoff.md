# Handoff — Fases 9 e 10 locais

## Atualização de execução real — 09/09/2026

O pacote final8 foi extraído em perfil/pasta temporários e passou a auditoria
`TESTAR-PACOTE.ps1`. O `INICIAR.cmd` real foi executado pelo teste opt-in
`test_portable_launcher.py` e iniciou o serviço antes de exibir o menu. O
smoke `test_portable_zip_browser_smoke.py` confirmou `pair`, capabilities e
token de sessão da extensão no Chrome descartável. Artefato temporário:
95.838.420 bytes, SHA-256
`25223A75101031BBFD70CA2BD9750A507C4D630660406608927E7A60EAC44E17`.

Com autorização explícita do usuário para o teste real, o runner
`real_portal_session.py` abriu outro perfil descartável, pareou a extensão e
acessou o portal oficial. O inventário sanitizado está em
`work/tce-extractor/outputs/real-portal-dom-sanitized-2026-09-09.json` e
contém apenas estrutura/contagens/origens. O portal respondeu em
`https://processos.tce.rn.gov.br/` na tela de login: 1 formulário, 3
controles e ação `ENTRAR`; nenhum ato foi aberto, nenhum campo foi preenchido
e nenhum envio ocorreu. A extensão ficou conectada ao serviço local, mas não
há injeção esperada na origem inicial `processos.tce.rn.gov.br`, que difere da
allowlist atual `novaarearestrita.tce.rn.gov.br`.

Checkpoint de retomada: fazer login manualmente na janela descartável, sem
compartilhar credenciais, e responder `continue`. Depois disso, capturar a
origem/DOM autenticados, localizar três atos representativos e executar apenas
preflight supervisionado antes de qualquer primeiro envio. Se o login não
redirecionar para a origem permitida ou não expuser a tela esperada, parar e
registrar o bloqueio; não ampliar a allowlist por suposição.

## Estado atual

Branch: `codex/fundamentacao-automatico`.

As entregas locais das Fases 9 e 10 estão no checkout e foram commitadas em
`25ca99e` (`test: qualify local automation and package release`), `692ed27`
(`test: add formal panel accessibility gate`), `61dce28` (`feat: add opt-in
automation pilot guard`) e `c4246c6` (`fix: route automation controls through
worker`), seguidos de `453a043` (`docs: record portable runtime probe`) e
`0ec7109` (`docs: reconcile local phase tasks`), com documentação intermediária
em `9ad2a50`, `76e37f5`, `5e1617c` e `407ca6c`, além de `42eeeac`
(`fix: require portable service readiness`) e `21e9a63` (`docs: record launcher
gate boundary`), `9d21441` (`feat: harden automation confirmation recovery`),
`a8ae6e2` (`fix: complete portable package inventory`), `1fcfad8` (`docs:
record verified portable composition`) e `e1d9618` (`test: verify portable
bridge startup sequence`), seguido de `8de1b87` (`docs: record portable bridge
qualification`). O repositório não possui remoto configurado, portanto não há
push.

O launcher portátil agora exige `service.json` produzido pelo próprio helper;
se o processo encerra ou não confirma a ponte, o menu não fabrica PID/porta e
preserva o modo manual.

Atualização final de 09/09/2026: o commit `03b5b8e` (`fix: qualify portable
bridge in Chrome`) corrigiu o listener do código de pareamento no painel, a
opção CORS do cliente loopback e a compatibilidade de autenticação para GETs
sem `Origin` (somente leituras; mutações continuam exigindo origem de
extensão). O smoke `test_portable_zip_browser_smoke.py` abriu a extensão do
ZIP final6 em Chrome com perfil descartável, iniciou o Python portátil,
pareou, sincronizou dataset/capabilities e confirmou o token em
`chrome.storage.session`. ZIP final6: 95.838.384 bytes, SHA-256
`4ecbbf150a13e1f45b454a5097f67329d7086994cef3cde24d67b9ad54f73770`.
Nenhum portal real, ato real ou envio foi acessado.

## Arquivos principais

- `work/tce-extractor/test_automation_browser.py`
- `work/tce-extractor/tests/fixtures/automatic-portal/simulator.html`
- `work/tce-extractor/tests/fixtures/automatic-portal/form.html`
- `work/tce-extractor/portable/test_automation_integration.py`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/app/package_audit.py`
- `work/tce-extractor/package_complete_archive.py`
- `work/tce-extractor/test_package_audit.py`
- `work/tce-extractor/test_portable_end_to_end.py`
- `work/tce-extractor/test_panel_accessibility.py`
- `work/tce-extractor/test_automation_api.py`
- `work/tce-extractor/portable/app/automation_store.py`
- `work/tce-extractor/portable/app/bridge_auth.py`
- `work/tce-extractor/portable/app/local_service.py`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/bridge-client.test.mjs`
- `work/tce-extractor/test_bridge_auth.py`
- `work/tce-extractor/test_local_service.py`
- `work/tce-extractor/test_portable_zip_browser_smoke.py`
- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- `work/tce-extractor/portable/extensao-complementar-ato/manifest.json`
- `docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md`
- `docs/notes/2026-09-09-fase9-10-task-9-10-report.md`

## Testes e decisões

O primeiro teste SQLite esperava `running` depois da reabertura. A implementação
correta do store pausa execuções ativas durante recovery; o teste foi ajustado
para exigir `paused`, preservar `unconfirmed`/`pending` e aceitar somente
`run_resumed` explícito. A primeira suíte ampla revelou que o fixture de pacote
não copiava `legal_context.py`; o fixture foi corrigido e
`test_portable_end_to_end` ficou verde.

O teste de navegador usa a API `chrome.tabs.sendMessage` a partir de uma página
da extensão, pois content scripts rodam em isolated world. O envio é bloqueado
sem bridge e o botão sintético permanece sem clique. Isso é uma qualificação
local de integração, não uma prova do portal real.

O gate adicional de acessibilidade passou em 3/3: contraste mínimo dos tokens
de texto/status/ação/foco, `lang=pt-BR`, IDs únicos, targets de labels existentes
e cópia estática de segurança. O smoke combinado de painel e automação passou
em 5/5.

O runtime staging disponível foi executado diretamente com `-I -B -s`: Python
3.14.4, SQLite 3.50.4 e imports de `automation_store`/`local_service` passaram.
Depois, o packager público foi corrigido para copiar oito assets de automação
que estavam ausentes da allowlist. A validação de startup revelou também que
`local_service.py` precisava de `automation_report.py`, `automation_store.py` e
`legal_context.py`; os três módulos agora são copiados explicitamente. A
composição final extraída em pasta limpa passou runtime Python/Tesseract,
manifesto, auditoria pública e diagnóstico PowerShell: ZIP final6 de
95.838.384 bytes, SHA-256
`4ecbbf150a13e1f45b454a5097f67329d7086994cef3cde24d67b9ad54f73770`.

No mesmo ZIP, o serviço portátil publicou `service.json`, aceitou `pair=200`,
respondeu `capabilities=200` autenticado com `real_send_enabled=false`,
rejeitou o reuso do código com 401 e foi encerrado pelo helper. O smoke Chrome
adicional também passou no mesmo pacote extraído; isso é evidência local da
integração, não qualificação do portal real.

O diagnóstico PowerShell também foi alinhado à permissão `alarms` do manifesto.
O RED foi observado primeiro no contrato da allowlist (8 assets) e depois no
teste PowerShell do manifesto; ambos ficaram verdes após as correções. Isso é
evidência offline e de integração local da composição, não qualificação do
portal real.

O smoke Chrome acrescentado depois encontrou e corrigiu duas falhas de
integração locais: o botão não era reabilitado ao editar o código e os GETs
autenticados chegavam sem `Origin`. Há regressões para ambos os casos. A
extração final6 passou `TESTAR-PACOTE.ps1`, pareamento, dataset e capabilities
no Chrome descartável; o fixture limpa `service.json` anterior e usa um lote
sanitizado válido. A versão final do pacote é o hash registrado no bloco de
estado acima.

O incidente do launcher foi coberto em TDD: o teste RED reproduziu a ausência
de confirmação para um processo encerrado; a correção passou no teste completo
do menu portátil, 75/75, e foi commitada em `42eeeac`. A mudança é local e
não converte o incidente de pareamento real da seção 14.2 em PASS.

O bloco seguinte fechou gates locais da Fase 7: histórico durável por identidade
impede reenvio em outro lote, hash alterado retorna `ACT_REQUIRES_REVIEW`,
reconciliação após `unconfirmed` exige leitura explícita, `send_confirmed`
renderiza o relatório antes da resposta da API e o submitter aguarda observação
por 30 s com uma releitura final. Tudo está em `9d21441`; isso não habilita
envio real.

Foi adicionada uma regressão de segurança na API: execução comum não pode
consumir comando quando `real_send_enabled=false`; o serviço devolve
`REAL_SEND_DISABLED` sem persistir `command_consumed`. O piloto opt-in ainda não
foi executado no portal; sua infraestrutura local agora exige `--automation-pilot`,
identidade explícita, conserva o limite de um comando após reinício e recebe
`AUTO_START`/`AUTO_PAUSE`/`AUTO_RESUME`/`AUTO_STOP` no worker/controller do
painel.

Três auditorias Luna xhigh foram solicitadas em paralelo para separar checklists
históricos das pendências reais, mas permaneceram sem resposta e foram
encerradas; não produziram alterações nem evidência adicional.

## Retomada imediata

1. Repetir a suíte ampla somente se houver novas alterações; o gate documentado
   passou `385/385`, com 6 skips ambientais. O gate JavaScript passou `256/256`;
   o focal pacote/end-to-end/serviço/auth passou `69` testes com `3` skips; o
   smoke Chrome do ZIP passou `1/1`; o novo foco de pacote/launcher passou
   `43` testes com `2` skips; e o `Test-TcePortable.ps1` passou `114/114` com
   Windows PowerShell 5.1.
2. Manter `42eeeac` como referência da correção do launcher; depois rodar
   `git diff --check` e `git status --short --branch`.
3. Se houver nova alteração, revisar mudanças privadas/ignoradas e fazer stage
   explícito; não usar `git add .`. O bloco de packager/teste/diagnóstico foi
   commitado em `a8ae6e2`, a sequência bridge em `e1d9618`, e o smoke/browser
   bridge em `03b5b8e`; o plano, relatório e handoff foram atualizados em
   `cbf30ca` (`docs: record Chrome bridge qualification`).
4. Os commits `61dce28`, `c4246c6`, `453a043` e `0ec7109` contêm
   guard/piloto, delegação ao worker, controles, probe e reconciliação das
   tasks locais; o gate formal de acessibilidade está em `692ed27`.
5. Não executar push sem remoto; manter este handoff como ponto de retomada.

## Pendência bloqueante

A autorização para teste real foi dada, e a sessão descartável já foi aberta,
mas o portal parou na tela de login. O próximo agente deve aguardar o login
manual do operador e a resposta `continue`; depois deve verificar a origem
autenticada e o formulário antes de qualquer preflight. Não capturar
credenciais, não ampliar a allowlist por suposição e não habilitar lote até a
qualificação versionada.
