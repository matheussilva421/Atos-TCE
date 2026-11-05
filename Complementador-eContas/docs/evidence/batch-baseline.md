# Baseline da automação em lote (T00 / G0)

Data: 05/11/2026

## Estado do repositório

- Repositório: `matheussilva421/Atos-TCE`
- Branch de trabalho: `codex/complementador-e-contas`
- HEAD no início do T00: `09578a6` (sincronizado com `origin/codex/complementador-e-contas`)
- `main` permanece em `6e1acd5`; nenhum merge, rebase ou push foi executado.
- Árvore de trabalho limpa no início do T00 (saída de `git status --short --branch`).
- Projeto: `Complementador-eContas/`, versão 0.1.1.

## Dependências

O checkout autoritativo não tinha `node_modules`. Foi executado `npm ci` no diretório isolado do projeto, a partir do `package-lock.json` versionado, sem instalação global.

O Chrome instalado na máquina (build de marca) não carrega extensões via `--load-extension`. Os testes de navegador usam o Chromium do Playwright em
`C:\Users\slvma\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe`,
com `TEST_BROWSER_HEADLESS=1`.

## Testes do baseline

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | 114 testes, 114 PASS, 0 FAIL |
| `node --test --test-force-exit --test-concurrency=1 tests/browser/*.spec.mjs` | 19 testes, 19 PASS, 0 FAIL |
| `npm run build` | PASS |
| `npm run build:test` | PASS |

Ambiente: Node v24.15.0, npm 11.12.1, Windows.

## Backup verificado

- Destino: `C:\Users\slvma\Downloads\Github\Atos-TCE\work\batch-baseline-2026-11-05`
- Conteúdo: 59 arquivos de fonte/configuração/documentação em `source/` e 5 arquivos do build v0.1.1 em `build/dist/`.
- Inventário: `SHA256SUMS.txt` com 64 linhas.
- Teste de restauração: cópia isolada de um arquivo de `src/` comparada por SHA-256, com correspondência confirmada.
- `build/dist/background.js`: SHA-256 `91281F9B92720DE84CD3FBE6BF49214CB26136646C7BB79F3BC0414A1600234A` (62.394 bytes).

O diretório `work/` é ignorado pelo versionamento, portanto o backup não entra em commits.

## Gates

| Gate | Estado |
| --- | --- |
| G0 — baseline, backup e testes de partida | PASS |
| G1 — reconhecimento somente leitura do portal | NOT_RUN |
| G2 — TDD do núcleo | NOT_RUN |
| G3/H1 — E2E sintético | NOT_RUN |
| G5/H2 — um salvamento real | NOT_RUN (exige autorização humana específica) |
| G6/H3 — lote real pequeno | NOT_RUN (exige H2 + autorização específica) |
| G7 — release/aceite | NOT_RUN |

Nenhum salvamento, clique em Complementar Ato ou alteração no perfil profissional de Chrome foi realizado neste baseline.
