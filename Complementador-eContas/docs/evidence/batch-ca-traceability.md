# Matriz CA-01–CA-20 — evidência atual

Data: 06/11/2026
Escopo: código local, testes sintéticos, suítes consolidadas e homologação real no Chrome QA (25 examinados, 10 salvos, 10/10 verificados).

| CA | Requisito | Evidência | Status |
| --- | --- | --- | --- |
| CA-01 | Modo individual sem regressão | `batch-manual-regression.test.mjs`; suíte de navegador | PASS sintético + navegador |
| CA-02 | Fila limitada à página atual | `batch-list-reader.test.mjs`; 25 linhas reais sem paginar | PASS real |
| CA-03 | Concluídos excluídos sem gastar cota | `batch-queue.test.mjs`; 0 pré-concluídos na captura | PASS |
| CA-04 | Múltiplos interessados nunca salvos | 9 `MULTIPLE_INTERESTED` reais, nenhum salvo | PASS real |
| CA-05 | Interessado único selecionado e confirmado | 10 atos reais com um interessado | PASS real |
| CA-06 | Documentos corretos | 10 salvamentos verificados; 15 revisões classificadas | PASS real |
| CA-07 | Cinco campos conforme regras | 10 atos preenchidos e salvos com modalidade + quatro campos | PASS real |
| CA-08 | Preexistentes compatíveis mantidos; divergentes bloqueiam | `batch-validation.test.mjs`, `batch-manual-regression.test.mjs` | PASS sintético |
| CA-09 | Dois limites não excedidos | 25/10 exatos; nenhum limite ultrapassado | PASS real |
| CA-10 | Só contar salvamentos comprovados | 10 `SAVE_ACK`, 10/10 verificados no portal, 0 incertos | PASS real |
| CA-11 | Jamais repetir salvamento incerto | 0 `SAVE_UNCERTAIN`; testes de exceção/checkpoint | PASS real + sintético |
| CA-12 | Pausa e parada seguras | `batch-state-machine.test.mjs`, `batch-protocol.test.mjs` | PASS sintético |
| CA-13 | Suspensão MV3 sem perda nem duplicação | `batch-lifecycle.test.mjs`, `batch-journal.test.mjs`; kill físico não executado | PARCIAL |
| CA-14 | Expiração permite retomada controlada | `batch-recovery.test.mjs` | PASS sintético |
| CA-15 | Falhas transitórias sem travar | `batch-waits.test.mjs`; retry condicionado | PASS sintético |
| CA-16 | Apenas um lote por perfil | `batch-protocol.test.mjs` | PASS sintético |
| CA-17 | Relatório por processo/motivo | `batch-report.test.mjs`; 15 causas reais | PASS sintético + real |
| CA-18 | Diário sem PDFs e dados pessoais | `batch-journal.test.mjs`, `security.test.mjs` | PASS |
| CA-19 | Nenhum salvamento real sem autorização | 10 salvamentos com autorização expressa e limites 25/10 | PASS real |
| CA-20 | Retomada consistente | `batch-saving.test.mjs` (SAVE_PENDING), `batch-recovery.test.mjs`; reinício físico não executado | PARCIAL |

## Resultado real

- 25 processos distintos examinados; 10 preenchidos/salvos/confirmados.
- 15 revisões: 9 múltiplos interessados, 3 documento não encontrado, 2 guia não localizada, 1 campo ausente.
- 10 `SAVE_ACK`, 0 `MARK_UNCERTAIN`, 0 segundo clique.
- 10/10 abas do portal sem o botão “Complementar ato”.
- Duração 243 s; p50 10,4 s; p95 23,5 s; máximo 31,9 s.
- Abas de processos `CONFIRMED` agora fecham após o ACK; revisões permanecem abertas.

## Lacunas restantes

1. Kill físico do service worker/reinício do navegador: `MV3_WORKER_KILL_TEST_NOT_RUN`.
2. Autosave do portal: `UNKNOWN`.
3. Chrome profissional: `NOT_RUN` (não instalado por escopo).
4. G7: aceite humano do operador pendente.
5. A homologação real usou o build QA 0.1.1 com o mesmo caminho de preenchimento/salvamento; a 2.0.3 acrescenta limpeza pós-save, Meus Processos, presets por rota e tempos ampliados.

## Declaração

`RELEASE_2.0_READY` · `G7_PENDING_HUMAN_ACCEPTANCE` · `MV3_WORKER_KILL_TEST_NOT_RUN` · `AUTOSAVE_UNKNOWN`. A matriz combina código, testes, 10 salvamentos reais e verificação independente.
