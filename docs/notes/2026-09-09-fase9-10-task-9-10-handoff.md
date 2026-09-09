# Handoff — Fases 9 e 10 locais

## Estado atual

Branch: `codex/fundamentacao-automatico`.

As entregas locais das Fases 9 e 10 estão no checkout e foram commitadas em
`25ca99e` (`test: qualify local automation and package release`). O checkout
foi conferido limpo após o commit. O repositório não possui remoto configurado,
portanto não há push.

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

## Retomada imediata

1. Repetir a suíte ampla somente se houver novas alterações; o último gate foi
   `373/373`, com 5 skips ambientais.
2. Rodar `git diff --check` e `git status --short --branch`.
3. Se houver nova alteração, revisar mudanças privadas/ignoradas e fazer stage
   explícito; não usar `git add .`.
4. Não executar push sem remoto; o SHA atual é `25ca99e`.
5. Atualizar este handoff somente se o estado mudar.

## Pendência bloqueante

O gate real permanece por autorização e segurança: não abrir perfil autenticado,
não clicar “Complementar Ato” no portal real e não habilitar lote. O próximo
agente deve parar no checkpoint de preparação real e pedir autorização antes de
qualquer side effect remoto.
