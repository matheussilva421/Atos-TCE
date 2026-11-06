# Release 2.0.5 — janela do lote e parada segura

Data: 06/11/2026
Branch: `codex/complementador-e-contas`
Versão: `2.0.5`
Estado: `BUILT_AND_UNIT_TESTED` / `QA_LIVE_PENDING`

## Causa raiz 1 — abas fora da janela de origem

O `windowId` era capturado no clique em “⚡ Rodar automação” e persistido no lote, mas era descartado em `createRunnerDeps().openWorkspace`: a função recebia `windowId` e chamava `openWorkspace({ processId, previous, tabsApi, fresh, keepTabIds })` sem repassá-lo. Sem `windowId`, `chrome.tabs.create` usa a janela em foco, então uma segunda janela aberta em outro monitor recebia os processos.

Correção: `src/batch/deps.mjs` repassa `windowId` e mantém o valor na sessão do runner, de modo que a aba de verificação pós-salvamento também abre na janela do lote.

## Causa raiz 2 — “Parar” prendia o lote em `STOP_REQUESTED`

`REQUEST_STOP` com um processo em curso define `STOP_REQUESTED`, mas o runner só trabalhava em `RUNNING` e nenhum caminho emitia `STOP_SAFE`. O lote ficava sem Iniciar, Pausar, Parar ou Continuar, restando apenas “Zerar lote”.

Correção: em `src/batch/runner.mjs`, `STOP_REQUESTED`

- sem processo em curso → `STOP_SAFE` → `STOPPED`;
- com processo em curso e sem salvamento armado → `MARK_REVIEW` com motivo `STOPPED`, devolvendo o processo para revisão humana sem abrir, preencher ou salvar nada, e encerrando em `STOPPED`;
- com salvamento armado → aguarda a resolução do salvamento antes de qualquer transição.

`PAUSE_REQUESTED` passou a terminar o processo em curso antes de pausar: `ADVANCE_PHASE` é aceito nesse estado e, quando o processo termina, o redutor leva a `PAUSED`.

## Arquivos alterados

| Arquivo | Mudança |
| --- | --- |
| `src/batch/deps.mjs` | repassa `windowId` para `openWorkspace` e o mantém na sessão |
| `src/batch/runner.mjs` | parada segura e pausa com processo em curso |
| `src/batch/state-machine.mjs` | `ADVANCE_PHASE` aceito durante `PAUSE_REQUESTED` |
| `src/list/content.mjs` | inalterado (botão Zerar já existia) |
| `scripts/build.mjs` | opção `--outdir=` para builds de QA/release sem tocar em `dist` |
| `tests/unit/batch-deps.test.mjs` | 2 testes de janela |
| `tests/unit/batch-stop.test.mjs` | 5 testes de parada/pausa |

## Testes

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **344 PASS / 0 FAIL** |
| `node --test tests/unit/batch-deps.test.mjs` | 19 PASS |
| `node --test tests/unit/batch-stop.test.mjs` | 5 PASS |
| `npm run test:browser` | **BLOCKED** — `msedge.exe` fecha logo após o launch; com `TEST_BROWSER_CHANNEL=chrome` o navegador sobe mas a extensão não injeta em headless. Falha de ambiente, não do código. |
| Extração do ZIP 2.0.5 | PASS, 6 arquivos, 0 divergências de hash |

## Pacote

| Item | Valor |
| --- | --- |
| Arquivo | `release/Complementador-eContas-2.0.5.zip` |
| Bytes | 646.769 |
| SHA-256 | `0B775B3F8B5E868533836F40C49CE2E1D516DC512C88AD8D1C4ADC5FE11E1360` |
| Manifesto | 2.0.5 |
| Build funcional | `work/release-2.0.5-extract` (`BATCH_EXECUTION_ENABLED=true`, `BATCH_SAVE_ENABLED=true`) |

| Arquivo | Bytes | SHA-256 |
| --- | ---: | --- |
| manifest.json | 1.201 | `865B5B234534DDEACDF99B2D418F29B8FAEDD2A87F2F7B6AB255923A3000CAC0` |
| background.js | 139.199 | `190F8DB73B13F789734717C42BF5831AA71FF34B60FC1558C349023AEB87DD7E` |
| form-content.js | 57.943 | `C8E29A40ECBBFEA51D484356332F550831B241CD50D93409762DFC8FB166A6FC` |
| autos-content.js | 984.654 | `E35BFE18E66DE5E4FD92E567FA786260FCB16ACB849873F7A6136EEFE30E593E` |
| list-content.js | 30.637 | `DE7A600D936AC91A3B4130A4C8D139A048BC031678BE2CEBA005B41BDFDEF60A` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

## Pendente

- `QA_LIVE_PENDING`: prova em duas janelas reais e prova de “Parar → STOPPED” dependem de login no e-Contas.
- Os gates F7/F8 da 2.0.4 não são reabertos por esta versão: as mudanças ficam no motor de lote e na montagem das dependências.
