# H1 — homologação sintética (parcial)

Data: 05/11/2026
Estado: `H1_INCOMPLETE`

## Cobertura atual

| Área | Evidência | Estado |
| --- | --- | --- |
| Fila, limites e exclusão de concluídos | `tests/unit/batch-queue.test.mjs` (7 testes) | PASS |
| Máquina de estados, SAVE_PENDING e incerteza | `tests/unit/batch-state-machine.test.mjs` (6 testes) | PASS |
| Diário mínimo, corrupção, quota e retenção | `tests/unit/batch-journal.test.mjs` (6 testes) | PASS |
| Leitura da listagem e contexto de filtros | `tests/unit/batch-list-reader.test.mjs` (7 testes) | PASS |
| Interessado único e seleção | `tests/unit/batch-interested.test.mjs` (5 testes) | PASS |
| Campos preexistentes e pré-save | `tests/unit/batch-validation.test.mjs` (7 testes) | PASS |
| Abas dedicadas e recuperação | `tests/unit/batch-workspace.test.mjs` (6 testes) | PASS |
| Adaptador de salvamento | `tests/unit/batch-save-adapter.test.mjs` (7 testes) | PASS |
| Recuperação de contexto | `tests/unit/batch-recovery.test.mjs` (8 testes) | PASS |
| Esperas e disjuntor | `tests/unit/batch-waits.test.mjs` (6 testes) | PASS |
| Relatório sanitizado | `tests/unit/batch-report.test.mjs` (6 testes) | PASS |
| Protocolo e controlador serializado | `tests/unit/batch-protocol.test.mjs` (8 testes) | PASS |
| UI do painel da listagem | `tests/unit/batch-list-ui.test.mjs` (6 testes) | PASS |
| Runner, checkpoint e salvamento incerto | `tests/unit/batch-saving.test.mjs` (8 testes) | PASS |
| Comandos de formulário do lote | `tests/unit/batch-form-content.test.mjs` (5 testes) | PASS |
| Adaptador de dependências do runner | `tests/unit/batch-deps.test.mjs` (5 testes) | PASS |

Total: 218 testes unitários PASS (114 anteriores + 104 novos).

## Verificação no Chrome QA (05/11/2026)

- Painel `#complementador-econtas-batch-root` injetado na listagem real com os cinco controles e dois campos de limite.
- Pré-visualizar: 10 processos pendentes, 0 concluídos, 0 sem status.
- Iniciar: lote criado com 10 capturados, 10 na fila, 0 examinados, 0 salvos, estado `RUNNING`.
- Parar: estado `STOPPED`, sem examinar nenhum processo e sem salvar.
- Nenhum clique em Complementar ato e nenhuma alteração de ato no portal.

## O que ainda falta para H1

- ~~Protocolo de comandos no background (T06)~~ e ~~controles Iniciar/Pausar/Parar/Continuar (T17)~~ concluídos.
- Integração documental do fluxo de lote (T09) e readback no content script (T11).
- Runner com checkpoint pré-clique e reconciliação (T13) e ciclo de vida MV3 (T16).
- ~~Painel na listagem (T18)~~ concluído; faltam regressão explícita do modo manual (T20) e E2E sintético (T21).
- Matriz CA-01–CA-20 preenchida com evidência de navegador, não apenas unitária.

## Declaração de segurança

`REAL_SAVE_NOT_TESTED`. Nenhum clique em Complementar ato, nenhum diálogo real confirmado e nenhum ato salvo. A UI de salvamento observada limita-se ao botão da tela e à ausência de modal antes do clique.
