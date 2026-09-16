# Handoff — fundamentação de professores v2 — Task 0

## Estado

- Branch: `codex/fundamentacao-professores-crosswalk-v2`
- Base: `79b19a5` (`main` local)
- Worktree: `.worktrees/fundamentacao-professores-crosswalk-v2`
- Escopo: baseline, fixture e RED; nenhum módulo de produção v2 foi escrito.

## Arquivos

- Criado `work/tce-extractor/tests/fixtures/legal-foundations-professores-v2.json` com catálogo civil de referência, opção militar negativa e três casos sintéticos prioritários.
- Criado `work/tce-extractor/portable/extensao-complementar-ato/tests/portal-legal-crosswalk.test.mjs`.
- Criado `docs/superpowers/plans/2026-09-15-fundamentacao-professores-crosswalk.md` como plano versionado resumido; o plano-fonte do usuário continua em `docs/PLANO_CODEX_FUNDAMENTACAO_LEGAL_PROFESSORES_TCE.md` no checkout principal.

## Evidência

- Baseline JS: `node --test tests/legal-foundation.test.mjs tests/matcher.test.mjs tests/automation-preflight.test.mjs tests/service-worker.test.mjs tests/panel.test.mjs` — 170 pass, 0 fail.
- Baseline Python: `python -m unittest test_legal_context.py test_local_service.py test_automation_api.py` — 67 executados, 67 pass, 0 fail, 1 skip ambiental.
- RED: `node --test tests/portal-legal-crosswalk.test.mjs` — falha esperada por `ERR_MODULE_NOT_FOUND` do módulo ainda inexistente `lib/portal-legal-crosswalk.js`.

## Retomada

1. Implementar o parser v2 e seu teste RED/GREEN.
2. Implementar o perfil funcional e cobrir integralidade versus proventos integrais.
3. Implementar o crosswalk e transformar o RED atual em GREEN.
4. Manter `autoSubmit=false`, `real_send_enabled=false` e testar somente no worktree.
