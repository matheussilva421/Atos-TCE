# Handoff — Fases 9 e 10 locais

## Estado atual

Branch: `codex/fundamentacao-automatico`.

As entregas locais das Fases 9 e 10 estão no checkout e foram commitadas em
`25ca99e` (`test: qualify local automation and package release`), `692ed27`
(`test: add formal panel accessibility gate`) e `61dce28` (`feat: add opt-in
automation pilot guard`), com documentação intermediária em `9ad2a50` e
`76e37f5`. O repositório não possui remoto configurado, portanto não há push.

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

Foi adicionada uma regressão de segurança na API: execução comum não pode
consumir comando quando `real_send_enabled=false`; o serviço devolve
`REAL_SEND_DISABLED` sem persistir `command_consumed`. O piloto opt-in ainda não
foi executado no portal; sua infraestrutura local agora exige `--automation-pilot`,
identidade explícita, conserva o limite de um comando após reinício e recebe
`AUTO_START` no worker/controller do painel.

Três auditorias Luna xhigh foram solicitadas em paralelo para separar checklists
históricos das pendências reais, mas permaneceram sem resposta e foram
encerradas; não produziram alterações nem evidência adicional.

## Retomada imediata

1. Repetir a suíte ampla somente se houver novas alterações; o último gate amplo
   anterior foi `373/373`, com 5 skips ambientais. O gate JavaScript atual passou
   `253/253`; API/store passou `39/39`, recuperação `4/4` e a suíte Python
   ampla passou `380/380`, com 5 skips ambientais.
2. Rodar `git diff --check` e `git status --short --branch`.
3. Se houver nova alteração, revisar mudanças privadas/ignoradas e fazer stage
   explícito; não usar `git add .`.
4. O commit `61dce28` contém o guard/piloto, delegação ao worker, testes e
   documentação; o gate formal de acessibilidade está em `692ed27`.
5. Não executar push sem remoto; manter este handoff como ponto de retomada.

## Pendência bloqueante

O gate real permanece por autorização e segurança: não abrir perfil autenticado,
não clicar “Complementar Ato” no portal real e não habilitar lote. O próximo
agente deve parar no checkpoint de preparação real e pedir autorização antes de
qualquer side effect remoto.
