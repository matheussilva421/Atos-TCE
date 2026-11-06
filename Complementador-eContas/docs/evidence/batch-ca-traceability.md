# Matriz CA-01–CA-20 — evidência atual

Data: 05/11/2026
Escopo: código local, testes sintéticos e evidência real do Chrome QA (preenchimento em lote e quatro salvamentos supervisionados).

| CA | Requisito | Evidência | Status |
| --- | --- | --- | --- |
| CA-01 | Modo individual sem regressão | `batch-manual-regression.test.mjs`; suíte de navegador mantém os fluxos manuais | PASS sintético + navegador |
| CA-02 | Fila limitada à página atual | `batch-list-reader.test.mjs`; leitura real de 10 linhas sem paginar | PASS |
| CA-03 | Concluídos excluídos sem gastar cota | `batch-queue.test.mjs` | PASS sintético |
| CA-04 | Múltiplos interessados nunca salvos | `batch-interested.test.mjs`; recusas reais em execuções anteriores | PASS sintético + real |
| CA-05 | Interessado único selecionado e confirmado | `batch-interested.test.mjs`; lote real com 4 abas de um interessado | PASS real |
| CA-06 | Documentos corretos | `full-flow.spec.mjs`; lote real: 4 preencheram os cinco campos, 6 em `MISSING_FIELDS` | PARCIAL |
| CA-07 | Cinco campos conforme regras | `batch-validation.test.mjs`; lote real com modalidade + quatro campos | PASS real |
| CA-08 | Preexistentes compatíveis mantidos; divergentes bloqueiam | `batch-validation.test.mjs`, `batch-manual-regression.test.mjs` | PASS sintético |
| CA-09 | Dois limites não excedidos | `batch-queue.test.mjs`, `batch-state-machine.test.mjs`; lote real 10/1 | PASS |
| CA-10 | Só contar salvamentos comprovados | `batch-saving.test.mjs`; 4 atos salvos e verificados no QA | PASS supervisionado |
| CA-11 | Jamais repetir salvamento incerto | `batch-saving.test.mjs`; uma confirmação por ato no QA | PASS sintético + supervisionado |
| CA-12 | Pausa e parada seguras | `batch-state-machine.test.mjs`, `batch-protocol.test.mjs` | PASS sintético |
| CA-13 | Suspensão MV3 sem perda nem duplicação | `batch-journal.test.mjs`, `batch-saving.test.mjs` (despertar concorrente) | PARCIAL |
| CA-14 | Expiração permite retomada controlada | `batch-recovery.test.mjs` | PASS sintético |
| CA-15 | Falhas transitórias sem travar | `batch-waits.test.mjs`, `batch-protocol.test.mjs` (timeouts) | PASS sintético |
| CA-16 | Apenas um lote por perfil | `batch-protocol.test.mjs` (duplo start) | PASS sintético |
| CA-17 | Relatório exato por processo/motivo | `batch-report.test.mjs` | PASS sintético |
| CA-18 | Diário sem PDFs e dados pessoais | `batch-journal.test.mjs` | PASS |
| CA-19 | Nenhum salvamento real sem autorização | `batch-execution-gate.test.mjs`; H2/H3 executados com autorização explícita e limite de 4 atos | PASS |
| CA-20 | Retomada consistente | `batch-recovery.test.mjs`, `batch-state-machine.test.mjs`; falta o caminho `SAVE_PENDING` | PARCIAL |

## Lacunas atuais

1. O salvamento automático pelo adaptador nunca foi executado; `createBatchDriver` não recebe `saveEnabled` e `verify()` devolve `unknown`.
2. A causa dos 6 `MISSING_FIELDS` não foi isolada (documento, campo ausente no PDF ou falha de leitura).
3. Suspensão real do service worker e reinício do navegador não simulados.
4. Isolamento de cache entre dois processos reais não exercitado.
5. Comportamento de autosave do portal desconhecido.
6. Chrome profissional não validado.
7. G7 (release, hashes, instalação/rollback e aceite) pendente.
8. O diário ainda marca os 4 atos salvos como `FILLED`; falta reconciliar `COMPLETED_EXTERNALLY`/`ALREADY_COMPLETED` sem contar em `counters.saved`.
9. O diálogo real está identificado por texto (título e botão); falta uma checagem estrutural antes de confirmar.

## Declaração

`SUPERVISED_REAL_SAVE_VERIFIED (4/4)` · `AUTOMATED_SAVE_NOT_RUN` · `MV3_ENDURANCE_NOT_RUN` · `G7_PENDING`. A matriz combina evidência de código, testes sintéticos e QA real; não substitui a homologação integral do salvamento automático nem o aceite de release.
