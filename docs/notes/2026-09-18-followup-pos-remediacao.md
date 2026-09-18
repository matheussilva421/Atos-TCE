# Follow-up pós-remediação — recibo (F1 → F7)

**Data:** 2026-09-18 · **Branch:** `codex/mesa-local-refactor`

Recibo do follow-up pedido em `docs/2026-09-18-atos-tce-followup-pos-remediacao.md`.
Nada de destrutivo foi executado: sem M2/M3/M5 reais, sem limpeza, sem remoção
do legado e sem merge.

## O que foi corrigido

| Item | Correção | Commit | Testes |
|---|---|---|---|
| F1.1 | `scripts/scan-area-cdp.ps1` era ignorado por `/scripts/*` (só `*.py` entravam): um clone limpo não tinha o scanner CDP e `tests/test_cdp_fallback.py` falhava. O `.gitignore` ganhou `!/scripts/*.ps1` e o script passou a ser versionado | `7b17c63` | provado em clone limpo: `tests.test_cdp_fallback` + `tests.test_storage_audit` = 40 testes verdes dentro de `tmp/clone-f1` |
| F1.2 | Comparação de caminhos Windows por string literal (`C:\Users\RUNNER~1\...` contra `C:\Users\runneradmin\...`) | `7b17c63` | `canonical_path()` (normcase + realpath) em `tests/test_packaging_contract.py` e `tests/test_storage_audit.py` |
| F1.3 | `SyntaxWarning: "\s" is an invalid escape sequence` no docstring de `compare-area-scans.py` | `7b17c63` | docstring virou raw string; `python -W error::SyntaxWarning -m py_compile` limpo |
| F2 | `generation` passou a ser obrigatória no filler: ausente, `null`, string, 0, negativo, fracionário, booleano ou `NaN` retornam `GENERATION_MISSING` com zero escritas | `b7d7cc6` | `extension/tests/fill-form.test.mjs` (8 valores inválidos, todos com `writeCount == 0`) |
| F3 | `scanAreaPages` nunca devolve parcial: `advancePage=false` com páginas restantes vira `PAGINATION_STALLED`; o teto de páginas vira `PAGE_LIMIT_EXCEEDED`; a página seguinte tem de ser exatamente `anterior + 1` | `ba300f9` | `extension/tests/router.test.mjs` (1/4 sem avanço, teto 3/99, salto 1→3, fluxo 1→2→3 e o `poll` reportando falha sem persistir scan) |
| F4 | O efeito durável é aplicado **antes** de o comando virar terminal: `SCAN_AREA` grava com `source_command_id` único (schema v7) e o replay encontra o mesmo scan; a transição do fill exige `current_command_id == command_id` | `a1dda0f` | `tests/test_api_server.py` (falha injetada na persistência deixa o comando `CLAIMED` e o retry aplica; replay não duplica; falha na transição do fill é retomável) |
| F5 | A fase 2 do arquivamento virou journal + recovery: qualquer falha deixa o journal, novas ações são recusadas, e a recuperação ou conclui (todos `ARCHIVED`) ou desfaz (todos `HOT`) | `0244a01` | `tests/test_archive_manager.py` (falha ao remover a 2ª visão, ao marcar o 2º documento, ao gravar presença, restart no meio e rollback quando a cópia não chegou) |
| F6 | O smoke do pacote passou a achar o interpretador pela pasta de extração, provar que a porta fechou e que nenhum processo sobrou antes de remover a extração, com retry limitado e bloqueadores nomeados no erro | `c96f51d` | duas execuções seguidas de `verify-package.ps1 -ZipPath dist\Atos-TCE-portable.zip` sem `-SkipSmoke`: exit 0 nas duas, zero processo órfão e zero pasta deixada |
| F7 | Suítes locais, pacote reconstruído, verificação com smoke, rotação e CI | (este commit) | ver abaixo |

## Gates finais

| Gate | Resultado |
|---|---|
| `python -m unittest discover -s tests -p 'test_*.py' -q` | 559 executados, 559 aprovados, 0 falhas |
| `cd extension && npm test` | 111 executados, 111 aprovados |
| `node --test app/web/tests/*.test.mjs` | 15 executados, 15 aprovados |
| `python -m unittest tests.test_packaging_contract -v` | 11 executados, 11 aprovados |
| `verify-package.ps1 -ZipPath dist/Atos-TCE-portable.zip` (com smoke) | exit 0 em duas execuções seguidas, sem `-SkipSmoke`, sem órfão |
| `work/tce-extractor/verify-project.ps1` | 7 estágios verdes, 1254 executados, 1252 aprovados, 0 falhas, 2 pulados |
| `git diff --check` | limpo |

Pacote promovido: `dist/Atos-TCE-portable.zip`, 96.115.726 bytes, SHA-256
`7f5c0a0bbd6f1bb0064f2912e4d09cf3467037c6730ac89228017bb29501e210`, 509 entradas,
430 arquivos de runtime, sem acervo. O smoke reporta `schema_version 7`. A
rotação deixou o build anterior como `.previous.zip`.

## O que continua sendo humano

M2 real (extensão × CDP), M3 real no e-Contas, M5 real supervisionado, retirada
do legado, limpeza destrutiva por recibo e merge para `main`.

