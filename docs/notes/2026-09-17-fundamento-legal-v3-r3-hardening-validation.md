# Fundamentação Legal v3 — validação Hardening R3

## Baseline

- worktree isolada: `.worktrees/fundamento-legal-v3-r3` (detached HEAD)
- base: `34a1c03` (`origin/main`, contém `a91d6b6`); baseline pré-R3 verde no gate
  completo (1223 passed / 0 failed / 2 skips) antes da primeira alteração
- rules_version: `legal-foundation-v3`
- extraction_version: `legal-context-v4`
- commits R3: `4dfb6ec` (bind decisão↔valor), `e7ae6e9` (cache por revisão exata),
  `5af285d` (TRUE_TIE), `5342bd6` (matcher), `98a7054` (CE40), `3809488` (E2E),
  `543e6b7` (allowlists de empacotamento)

## Invariantes comprovados

| Invariante | Evidência |
|---|---|
| Decisão AUTO só escreve o mesmo `option_value` | `lib/automation-preflight.js` (`legalDecisionAuthorizesValue`), `content/form-detector.js`, `sidepanel/panel.js` |
| Decisão A + payload B é recusada mesmo com A e B no `<select>` | `tests/form-detector.test.mjs` (barreira direta e pelo handler real de mensagens) |
| Preflight automático recusa divergência | `tests/automation-preflight.test.mjs` → `LEGAL_DECISION_VALUE_MISMATCH` |
| Painel omite fundamento quando decisão e proposta divergem | `tests/panel.test.mjs` (payload sem `fundamento_legal` e sem `legalDecision`) |
| Cache de LegalContext não usa `startsWith` | `background/legal-context-resolver.js` (chaves exatas via `JSON.stringify`) |
| Revisão 44 não serve requisição de revisão 4 | `tests/legal-context-resolver.test.mjs` prefixo |
| Revisão solicitada divergente bloqueia | `tests/legal-context-resolver.test.mjs` → `CONTEXT_REVISION_MISMATCH` |
| Sem revisão conhecida o resolver consulta a fonte atual | resolver + `tests/legal-context-resolver.test.mjs` (revisão 4 → 5) |
| Revisão nova chega ao worker e ao painel | `tests/service-worker.test.mjs` e E2E `tests/panel.test.mjs` (proposta muda de EC47 para EC41) |
| TRUE_TIE é o único `tie` | `sidepanel/panel.js` (`createRows`), `sidepanel/panel-view.js`; `tests/panel.test.mjs` (5 estados) |
| REVIEW/BLOCKED/CONFLICT/NO_CANDIDATE permanecem `pending` | `tests/panel.test.mjs` (linhas e DOM) |
| Matcher exige `legal-context-v4`, revisão inteira e regras v3 | `lib/matcher.js`; `tests/matcher.test.mjs` (3 falhas fechadas) |
| CE art. 40 recebe `CE40` e nunca `CF40_*` | `lib/catalog-option-signature.js`; `tests/catalog-option-signature.test.mjs` (+ regressões CF40 III_A / III_B / A_P5) |

## Gates

| Comando | Resultado |
|---|---|
| `node --test` (3×) | 477 testes, 477 aprovados, 0 falhas em cada execução |
| `python -m unittest discover -s . -p 'test_*.py' -q` | 526 executados, 0 falhas, 9 skips |
| `verify-project.ps1` | exit 0, 7 estágios verdes, 1241 passed / 0 failed / 2 skips |
| `git diff --check` | sem saída |

## Pacote portátil

Defeito real encontrado no passo de empacotamento (herdado da rodada v3 anterior):
os dois módulos novos de produção — `background/legal-context-resolver.js` e
`lib/catalog-option-signature.js` — não constavam de nenhuma allowlist de pacote,
de modo que o ZIP da extensão sairia sem eles e quebraria no primeiro import.

Como foi provado: novo teste de fechamento de imports em
`test_extension_zip_packager.py` monta o ZIP pelo empacotador oficial e verifica
que todo import relativo do pacote existe dentro do pacote. Ele falhava com
`service-worker.js imports ./legal-context-resolver.js, absent from the packaged ZIP`.

Correção aplicada (somente empacotamento): allowlists de
`empacotar-extensao-complementar-ato.ps1`, `empacotar-coletor-portatil.ps1`,
`package_qa_release.ps1`, `package_complete_archive.py`,
`portable/app/package_audit.py`, `verify_qa_release.py`,
`test_package_audit.py` e `test_extension_zip_packager.py`.

Estado após a correção: `python -m unittest test_extension_zip_packager -q` → OK
(2 testes), fechamento de imports completo, e o estágio `package` do
`verify-project.ps1` verde.

## Portal real

- smoke autenticado de preenchimento: **PENDENTE** (exige login manual, marcador
  vigente selecionado e campo de marcador vazio; ver a seção do plano R3)
- submit/finalização real: **NÃO AUTORIZADO POR ESTE PLANO**
