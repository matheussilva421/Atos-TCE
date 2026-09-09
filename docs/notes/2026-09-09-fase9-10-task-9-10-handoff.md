# Handoff — Fases 9 e 10 locais

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
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`
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
manifesto, auditoria pública e diagnóstico PowerShell: ZIP temporário de
95.838.277 bytes, SHA-256
`5d8496be04bccfd461b9476531ce95ad0c5fbd5cc3202b7f9b09a2a5fa497900`.

No mesmo ZIP, o serviço portátil publicou `service.json`, aceitou `pair=200`,
respondeu `capabilities=200` autenticado com `real_send_enabled=false`,
rejeitou o reuso do código com 401 e foi encerrado pelo helper.

O diagnóstico PowerShell também foi alinhado à permissão `alarms` do manifesto.
O RED foi observado primeiro no contrato da allowlist (8 assets) e depois no
teste PowerShell do manifesto; ambos ficaram verdes após as correções. Isso é
evidência offline da composição local, não smoke Chrome nem qualificação real.

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

1. Repetir a suíte ampla somente se houver novas alterações; o último gate amplo
   anterior foi `382/382`, com 5 skips ambientais. O gate JavaScript atual passou
   `255/255`; API/store/report passou `56/56`, recuperação `5/5`, o focal
   pacote/end-to-end/serviço passou `68` testes com `3` skips, e
   `Test-TcePortable.ps1` passou `114/114`.
2. Manter `42eeeac` como referência da correção do launcher; depois rodar
   `git diff --check` e `git status --short --branch`.
3. Se houver nova alteração, revisar mudanças privadas/ignoradas e fazer stage
   explícito; não usar `git add .`. O bloco de packager/teste/diagnóstico foi
   commitado em `a8ae6e2`, a sequência bridge em `e1d9618`; esta documentação
   foi atualizada em `8de1b87`.
4. Os commits `61dce28`, `c4246c6`, `453a043` e `0ec7109` contêm
   guard/piloto, delegação ao worker, controles, probe e reconciliação das
   tasks locais; o gate formal de acessibilidade está em `692ed27`.
5. Não executar push sem remoto; manter este handoff como ponto de retomada.

## Pendência bloqueante

O gate real permanece por autorização e segurança: não abrir perfil autenticado,
não clicar “Complementar Ato” no portal real e não habilitar lote. O próximo
agente deve parar no checkpoint de preparação real e pedir autorização antes de
qualquer side effect remoto.
