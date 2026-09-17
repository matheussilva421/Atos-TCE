# Handoff — merge da Fundamentação Legal v3 na main (2026-09-17)

## Resumo do que foi feito

- Plano `docs/superpowers/plans/2026-09-17-fundamento-legal-v3-r2.md` executado
  integralmente (Tasks 0 a 11) em worktree isolada e em detached HEAD:
  `.worktrees/fundamento-legal-v3-r2`.
- 12 commits produzidos a partir de `fd827da` (que contém `fa90605`).
- Merge **fast-forward** na `main` do checkout principal: `fd827da` → `a91d6b6`.
- `git push origin main` concluído: `fd827da..a91d6b6`.
- `local == remoto == a91d6b6de46768c344a309f8df4124dc1171bf78`.

## Commits (mais antigo primeiro)

| Commit | Assunto |
|---|---|
| `b8bc3f1` | fix: fail closed legal foundation without context |
| `2345c4c` | refactor: classify raw legal catalog structurally |
| `cb3e374` | fix: add legal decision v3 crosswalk states |
| `20f498c` | chore: bump legal foundation rules to v3 |
| `a509405` | feat: rebuild legal context per identity |
| `45907f3` | refactor: centralize legal context in service worker |
| `0fea2ee` | fix: guard legal foundation writes in panel |
| `e1c4c0d` | feat: show explicit legal decision diagnostics |
| `3a8ee63` | test: cover legal foundation v3 end to end |
| `45c09f4` | docs: validate legal foundation v3 |
| `4d3bbbb` | fix: harden legal foundation barriers after review |
| `a91d6b6` | docs: record v3 validation and review hardening |

## Arquivos criados (produção)

- `work/tce-extractor/portable/extensao-complementar-ato/lib/catalog-option-signature.js`
- `work/tce-extractor/portable/extensao-complementar-ato/background/legal-context-resolver.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/catalog-option-signature.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/legal-context-resolver.test.mjs`
- `docs/notes/2026-09-17-fundamento-legal-v3-validation.md`

## Arquivos alterados (principais)

- `lib/matcher.js`, `lib/legal-foundation.js`, `lib/portal-legal-crosswalk.js`,
  `lib/automation-preflight.js`, `lib/messages.js`, `lib/bridge-client.js`
- `background/service-worker.js`, `background/automation-controller.js`
- `content/form-detector.js`
- `sidepanel/panel.js`, `sidepanel/panel-view.js`
- `portable/app/legal_context.py`, `analysis_pipeline.py`, `local_service.py`, `qualification.py`
- testes JS e Python correspondentes, incluindo `test_extension_browser.py` e
  `test_panel_redesign_browser.py`

## Decisões técnicas relevantes

- `fundamento_legal` é fail-closed em quatro camadas: matcher, Service Worker,
  painel (`applyPayload`/override) e content script (`applyFields`/`overrideField`).
- `LegalContext` é resolvido exclusivamente pelo Service Worker via
  `ensureLegalContext()` (cache → sidecar → rebuild pontual).
- Regras renomeadas para `legal-foundation-v3`; `legal-context-v4` preservado.
- Só `TRUE_TIE` é apresentado como empate; demais estados não automáticos ficam
  em revisão ou bloqueio e nunca são escritos.
- Classe de catálogo não reconhecida sem evidência estrutural nunca é automática.

## Testes executados e status (pós-merge, no checkout principal)

| Comando | Resultado |
|---|---|
| `verify-project.ps1` | exit 0, 7 estágios verdes, 1223 passed / 0 failed / 2 skips |
| `python -m unittest discover -s . -p 'test_*.py' -q` | 525 executados, 0 falhas, 8 skips |
| `git diff --check` | limpo |

Baseline pré-v3 (Task 0): `verify-project.ps1` exit 0 (1174 passed), 517 testes
Python, controlador 70/70.

## Status do GitHub

- Branch: `main`
- Remoto: `origin/main` em `a91d6b6` (push confirmado por `git rev-parse`).
- Working tree limpo; único não rastreado é `work/tce-extractor/.codex-live-pilot.py`
  (ferramenta local, deve permanecer fora do Git).

## Pendências e próximos passos

1. Smoke real supervisionado no portal autenticado (itens 23/24 do checklist):
   login manual, marcador vigente já selecionado, `#automation-marker` vazio,
   lista autenticada visível. Roteiro em
   `docs/notes/2026-09-17-fundamento-legal-v3-validation.md`.
2. Regenerar o pacote portátil e rodar `TESTAR-PACOTE.ps1` sobre uma extração
   limpa para fechar o item de empacotamento.
3. Opcional: remover a worktree auxiliar com
   `git worktree remove .worktrees/fundamento-legal-v3-r2` (os commits já estão na main).

## Como reverter

- Reverter o merge preservando histórico: `git revert --no-commit fd827da..a91d6b6`
  e depois um único commit de reversão.
- Ou voltar a main para o estado anterior: `git reset --hard fd827da` seguido de
  `git push --force-with-lease origin main` (ação destrutiva; exigiria autorização
  explícita).
