# Matriz CA-01–CA-20 — evidência atual

Data: 05/11/2026
Escopo: código local, testes sintéticos, suítes consolidadas e evidência real do Chrome QA (lote de preenchimento e quatro salvamentos supervisionados).

| CA | Requisito | Evidência | Status |
| --- | --- | --- | --- |
| CA-01 | Modo individual sem regressão | `batch-manual-regression.test.mjs`; suíte de navegador | PASS sintético + navegador |
| CA-02 | Fila limitada à página atual | `batch-list-reader.test.mjs`; leitura real de 10 linhas | PASS |
| CA-03 | Concluídos excluídos sem gastar cota | `batch-queue.test.mjs` | PASS sintético |
| CA-04 | Múltiplos interessados nunca salvos | `batch-interested.test.mjs`; recusas reais em execuções anteriores | PASS sintético + real |
| CA-05 | Interessado único selecionado e confirmado | `batch-interested.test.mjs`; 4 abas reais com um interessado | PASS real |
| CA-06 | Documentos corretos | `full-flow.spec.mjs`; lote real com 4 preenchidos; classificação nova cobre causas, mas os 6 reais não foram reclassificados | PARCIAL |
| CA-07 | Cinco campos conforme regras | `batch-validation.test.mjs`; lote real com modalidade + quatro campos | PASS real |
| CA-08 | Preexistentes compatíveis mantidos; divergentes bloqueiam | `batch-validation.test.mjs`, `batch-manual-regression.test.mjs` | PASS sintético |
| CA-09 | Dois limites não excedidos | `batch-queue.test.mjs`, `batch-state-machine.test.mjs`; lote real 10/1 | PASS |
| CA-10 | Só contar salvamentos comprovados | `batch-saving.test.mjs`; verificação em aba nova; 4 atos supervisionados verificados | PASS supervisionado; automático real NOT_RUN |
| CA-11 | Jamais repetir salvamento incerto | `batch-saving.test.mjs`: exceção pós-checkpoint, SAVE_PENDING, resposta vazia, sem segundo clique | PASS sintético + supervisionado |
| CA-12 | Pausa e parada seguras | `batch-state-machine.test.mjs`, `batch-protocol.test.mjs` | PASS sintético |
| CA-13 | Suspensão MV3 sem perda nem duplicação | `batch-lifecycle.test.mjs`, `batch-journal.test.mjs`; kill real do worker não executado | PARCIAL |
| CA-14 | Expiração permite retomada controlada | `batch-recovery.test.mjs` | PASS sintético |
| CA-15 | Falhas transitórias sem travar | `batch-waits.test.mjs`, retry condicionado do documento | PASS sintético |
| CA-16 | Apenas um lote por perfil | `batch-protocol.test.mjs` (duplo start) | PASS sintético |
| CA-17 | Relatório por processo/motivo | `batch-report.test.mjs`; causa e campos sanitizados | PASS sintético |
| CA-18 | Diário sem PDFs e dados pessoais | `batch-journal.test.mjs`, `security.test.mjs` | PASS |
| CA-19 | Nenhum salvamento real sem autorização | `batch-execution-gate.test.mjs`; H2/H3 supervisionados com autorização e limite de 4 | PASS |
| CA-20 | Retomada consistente | `batch-saving.test.mjs` (SAVE_PENDING), `batch-recovery.test.mjs`; reinício físico não executado | PARCIAL |

## Lacunas atuais

1. O salvamento automático pelo adaptador nunca foi executado em ato real (`H2_ADAPTER_BLOCKED_EXTERNAL_AUTH`).
2. Os seis `MISSING_FIELDS` reais não foram reclassificados; o código novo passará a gravar `cause` e `fields` no próximo lote/read-only.
3. O kill físico do service worker e o reinício do navegador não foram provados; a decisão de suspender está testada em unidade e a ligação em `onStartup` é estática.
4. Isolamento de cache entre dois processos tem teste unitário e spec de navegador com dois IDs; cache no portal real entre dois processos não foi exercitado.
5. Autosave do portal continua `UNKNOWN`.
6. Chrome profissional não foi validado.
7. G7 (release funcional, aceite e instalação) pendente; o ZIP atual é candidato seguro desligado.
8. O diário histórico ainda marca os quatro atos como `FILLED`; a reconciliação `COMPLETED_EXTERNALLY` existe, mas não foi aplicada ao diário do QA.
9. A verificação pós-save usa rota/processo/formulário + ausência do botão; não há ACK formal do portal.

## Declaração

`PARTIAL_WITH_EVIDENCE` · `SUPERVISED_REAL_SAVE_VERIFIED (4/4)` · `AUTOMATED_SAVE_NOT_RUN` · `MV3_WORKER_KILL_TEST_NOT_RUN` · `G7_PENDING`. A matriz combina código, testes e QA real; não substitui os gates F7/F8/F9.
