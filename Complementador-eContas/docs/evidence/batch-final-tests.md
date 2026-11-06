# Testes finais — Complementador e-Contas (F6)

Data: 05/11/2026
Branch: `codex/complementador-e-contas`
Base antes dos documentos finais: `913a9b5` (commits F1–F5 abaixo)

## Comandos e resultados

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **322 PASS**, 0 FAIL, 6,0 s |
| `npm run build:test` | PASS — `background.js` 132.349 B, `form-content.js` 57.821 B, `autos-content.js` 984.515 B, `list-content.js` 27.750 B, `manifest.json` 1.051 B |
| `npm run test:browser` | **24 PASS**, 0 FAIL, 33,5 s, uma única execução (Chromium 1248 headless) |
| `npm run build` | PASS — `background.js` 132.376 B, `form-content.js` 57.831 B, `autos-content.js` 984.542 B, `list-content.js` 27.760 B, `manifest.json` 1.198 B |
| `npm run benchmark` | 7 amostras: 704, 476, 414, 428, 424, 421, 437 ms; p50 **428 ms**, p95 **704 ms** |
| `git diff --check` | PASS |

A suíte de navegador inclui a nova spec `two_autos_tabs_do_not_cross_process` (duas abas de processos distintos, uma recusa a mensagem da outra). A contagem passou de 23 para 24 especificações; o número histórico não foi preservado por conveniência.

## Cobertura nova de F1–F5

- `batch-save-authorization.test.mjs`: execução não habilita salvamento; autorização é persistida no lote; lote sem autorização não salva.
- `batch-saving.test.mjs`: exceção após o despacho mantém `SAVE_UNCERTAIN`; `SAVE_PENDING` acordado reconcilia sem segundo clique; ACK sem readback não confirma; suspensão exige `RESUME_AUTHORIZED`; pausa vira `PAUSED` após ACK; resposta vazia não repete clique.
- `batch-save-adapter.test.mjs`: diálogo real (título **Complementar ato**, confirmação **sim, complementar**, cancelamento **NÃO**); título errado, falta de cancelamento, falta de `role="dialog"` e botão desabilitado falham fechado.
- `batch-form-content.test.mjs`: cinco campos, identidade, erros visíveis, processo errado e remetente não confiável são revalidados antes do clique.
- `batch-missing-fields.test.mjs`: todas as categorias causais de `MISSING_FIELDS`.
- `batch-lifecycle.test.mjs`: despertar normal continua; ausência de marcador de sessão (reinício) suspende; `PAUSED`/`SUSPENDED` não retomam sozinhos.
- `batch-reconciliation.test.mjs`: quatro atos externos viram `COMPLETED_EXTERNALLY` sem incrementar `counters.saved`, de forma idempotente.
- `document-cache.test.mjs`: alternância entre dois processos não reutiliza ids.
- `batch-autos.spec.mjs`: duas abas de processos distintos não respondem uma pela outra.

## Testes de negação dos gates

- Build de distribuição sem flags: `BATCH_EXECUTION_ENABLED=false`, `BATCH_FILL_ONLY=false` e `BATCH_SAVE_ENABLED=false` (teste de importação do bundle de teste + teste estático do build).
- `BATCH_FILL_ONLY` força `saveEnabled=false` por construção.
- `BATCH_SAVE` com remetente não confiável ou processo errado não clica.
- `SAVE_UNCERTAIN` nunca recebe segundo despacho.
- Modo manual permanece sem importar o adaptador de salvamento e sem submit.

## Limitações desta execução

- O teste físico de matar o service worker via CDP travou o navegador e foi removido; a reentrada MV3 está coberta por `decideWake` (7 casos) e por verificação estática do registro em `onStartup`/`initializeWake`. Estado: `MV3_WORKER_KILL_TEST_NOT_RUN`.
- Reinício real do navegador e suspensão real do worker seguem sem prova de runtime; a lógica decide suspender e exigir `Continuar`.
- Nenhum salvamento real foi executado nesta fase. Os quatro atos de H2 continuam sendo evidência supervisionada anterior.
- O benchmark é sintético (PDF de uma página, fixture local), não é SLA do e-Contas.
