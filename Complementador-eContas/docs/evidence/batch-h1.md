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
| Runner, checkpoint, salvamento incerto, clique não disparado e despertar duplicado | `tests/unit/batch-saving.test.mjs` (10 testes) | PASS |
| Comandos de formulário do lote (seleção, validação e snapshot) | `tests/unit/batch-form-content.test.mjs` (6 testes) | PASS |
| Adaptador de dependências do runner (com verificação de abas) | `tests/unit/batch-deps.test.mjs` (6 testes) | PASS |
| Regressão do modo manual (inclui gate do BATCH_APPLY) | `tests/unit/batch-manual-regression.test.mjs` (7 testes) | PASS |
| Driver do background montando dependências reais | `tests/unit/batch-driver.test.mjs` (2 testes) | PASS |
| Gate de execução e registro no service worker | `tests/unit/batch-execution-gate.test.mjs` (3 testes) | PASS |
| Retry limitado para content script de aba nova | `tests/unit/retry.test.mjs` (3 testes) | PASS |
| Painel do lote em navegador sintético | `tests/browser/batch-panel.spec.mjs` (1 teste) | PASS |
| Pipeline de formulário do lote no navegador | `tests/browser/batch-form.spec.mjs` (1 teste) | PASS |

Total: 237 testes unitários PASS (114 anteriores + 123 novos).
Suíte de navegador: 21 testes PASS (19 anteriores + 2 novos), em fixtures locais, sem acesso ao portal.

## Verificação no Chrome QA (05/11/2026)

- Painel `#complementador-econtas-batch-root` injetado na listagem real com os cinco controles e dois campos de limite.
- Pré-visualizar: 10 processos pendentes, 0 concluídos, 0 sem status.
- Iniciar: lote criado com 10 capturados, 10 na fila, 0 examinados, 0 salvos, estado `RUNNING`.
- Parar: estado `STOPPED`, sem examinar nenhum processo e sem salvar.
- Nenhum clique em Complementar ato e nenhuma alteração de ato no portal.

## O que ainda falta para H1

- ~~Protocolo de comandos no background (T06)~~ e ~~controles Iniciar/Pausar/Parar/Continuar (T17)~~ concluídos.
- ~~Integração documental do fluxo de lote (T09)~~ adaptador pronto; falta ligar o `runFillTransaction` real ao background.
- ~~Readback no content script (T11)~~ comandos de formulário prontos.
- ~~Regressão explícita do modo manual (T20)~~ concluída.
- Runner com checkpoint pré-clique e reconciliação (T13) pronto no núcleo; falta o ciclo de vida MV3 completo (T16).
- E2E sintético do fluxo por processo (T21 restante): documentos, interessados, formulário, limites e salvamento incerto no navegador.
- Matriz CA-01–CA-20 preenchida com evidência de navegador, não apenas unitária.

## Declaração de segurança

`REAL_SAVE_NOT_TESTED`. Nenhum clique em Complementar ato, nenhum diálogo real confirmado e nenhum ato salvo. A UI de salvamento observada limita-se ao botão da tela e à ausência de modal antes do clique.

## Execução real supervisionada com preenchimento (05/11/2026)

Com o filtro do operador aplicado (marcador *Mutirão - Educação* e ATO COMPLEMENTADO = *Não*), o lote foi iniciado pelo painel com 10 examinados / 1 salvo.

| Verificação | Resultado |
| --- | --- |
| Fila | 10 capturados na página atual |
| Processos examinados | 7 até a suspensão |
| Processos recusados | 6 em `REVIEW_REQUIRED` (múltiplos interessados ou campos ausentes) |
| Processo preenchido | 1 em `VALIDATING` |
| Campos | data DOE 10, cargo 26, matrícula 10, nascimento 10 caracteres; modalidade selecionada |
| Salvamentos | 0 |
| Estado final do lote | `SUSPENDED` (gate de salvamento) |

O diário registra `READING → FILLING → VALIDATING → SUSPEND` para o processo, e a aba do formulário confirma os quatro campos e a modalidade preenchidos. Nenhum clique em Complementar ato.

Defeitos corrigidos para chegar aqui: listener de preparação de documento aninhado no lugar errado, `tabs.remove()` sem Promise, envio de mensagem aceitando resposta vazia e `FETCH_PDF` recusando o lote por falta de transação. Tempos ampliados para 60 s (mensagem) e 300 s (documentos).

## Preenchimento em lote sem salvar (05/11/2026)

Build estruturalmente só-preenchimento (`BATCH_FILL_ONLY=1`), com `saveEnabled` forçado a falso. Filtro do operador aplicado e BUSCAR executados automaticamente pelo painel.

| Verificação | Resultado |
| --- | --- |
| Processos examinados | 10 |
| Preenchidos (`FILLED`) | 4 |
| Revisão (`MISSING_FIELDS`) | 6 |
| Salvamentos | 0 |
| Abas de formulário mantidas | 4 |

Cada aba mantida tem um interessado selecionado, modalidade escolhida e os quatro campos preenchidos (comprimentos observados 10/26–32/9–11/10). O lote terminou em `COMPLETED` com `counters.saved = 0`.
