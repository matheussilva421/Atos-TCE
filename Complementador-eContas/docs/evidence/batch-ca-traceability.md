# Matriz CA-01–CA-20 — evidência atual

Data: 05/11/2026
Escopo: código local e testes sintéticos. Nenhum salvamento real, nenhum diálogo real confirmado e nenhum lote real executado.

| CA | Requisito | Evidência | Status |
| --- | --- | --- | --- |
| CA-01 | Modo individual sem regressão | `batch-manual-regression.test.mjs`; suíte de navegador mantém 19 fluxos manuais | PASS sintético |
| CA-02 | Fila limitada à página atual | `batch-list-reader.test.mjs`; leitura real de 10 linhas sem paginar | PASS |
| CA-03 | Concluídos excluídos sem gastar cota | `batch-queue.test.mjs` | PASS sintético |
| CA-04 | Múltiplos interessados nunca salvos | `batch-interested.test.mjs`, `batch-form-content.test.mjs` | PASS sintético |
| CA-05 | Interessado único selecionado e confirmado | `batch-interested.test.mjs`; `batch-form.spec.mjs` | PASS sintético (unitário + navegador) |
| CA-06 | Documentos corretos | `full-flow.spec.mjs` (descoberta no fluxo manual); lote ainda não exercitado | PARCIAL |
| CA-07 | Cinco campos conforme regras | `batch-validation.test.mjs`; `batch-form.spec.mjs` (4 campos + modalidade) | PASS sintético (unitário + navegador) |
| CA-08 | Preexistentes compatíveis mantidos; divergentes bloqueiam | `batch-validation.test.mjs`, `batch-manual-regression.test.mjs` | PASS sintético |
| CA-09 | Dois limites não excedidos | `batch-queue.test.mjs`, `batch-state-machine.test.mjs` | PASS sintético |
| CA-10 | Só contar salvamentos comprovados | `batch-saving.test.mjs` | PASS sintético |
| CA-11 | Jamais repetir salvamento incerto | `batch-saving.test.mjs` (reclique bloqueado) | PASS sintético |
| CA-12 | Pausa e parada seguras | `batch-state-machine.test.mjs`, `batch-protocol.test.mjs` | PASS sintético |
| CA-13 | Suspensão MV3 sem perda nem duplicação | `batch-journal.test.mjs`, `batch-saving.test.mjs` (despertar concorrente) | PARCIAL |
| CA-14 | Expiração permite retomada controlada | `batch-recovery.test.mjs` | PASS sintético |
| CA-15 | Falhas transitórias sem travar | `batch-waits.test.mjs`, `batch-protocol.test.mjs` (timeouts) | PASS sintético |
| CA-16 | Apenas um lote por perfil | `batch-protocol.test.mjs` (duplo start) | PASS sintético |
| CA-17 | Relatório exato por processo/motivo | `batch-report.test.mjs` | PASS sintético |
| CA-18 | Diário sem PDFs e dados pessoais | `batch-journal.test.mjs` | PASS |
| CA-19 | Nenhum salvamento real sem autorização | `batch-execution-gate.test.mjs`; H2/H3 não executados | PARCIAL (código fechado) |
| CA-20 | Retomada consistente | `batch-recovery.test.mjs`, `batch-state-machine.test.mjs` | PARCIAL |

## Lacunas que impedem H1 pleno

1. ~~Rota da aba de Autos não revalidada~~ — revalidada em 05/11/2026 (iframe, 54 eventos, content script ativo).
2. Fluxo de lote por processo não exercitado em navegador; apenas o painel foi coberto.
3. Reinício do navegador e suspensão real do service worker não simulados.
4. Nenhum salvamento real; H2/H3 permanecem `NOT_RUN`.

## Declaração

`REAL_SAVE_NOT_TESTED`. A matriz acima combina evidência de código e testes sintéticos; não substitui homologação real.
