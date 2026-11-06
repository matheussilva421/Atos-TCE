# Testes finais — Complementador e-Contas 2.0.0

Data: 06/11/2026
Branch: `codex/complementador-e-contas`
HEAD de código/testes antes da consolidação: `23e1339`

## Resultados

| Comando | Resultado |
| --- | --- |
| `node --test tests/unit/*.test.mjs` | **326 PASS**, 0 FAIL, 4,7 s |
| `npm run build:test` | PASS — `background.js` 133.817 B, `form-content.js` 57.821 B, `autos-content.js` 984.515 B, `list-content.js` 27.750 B, `manifest.json` 1.054 B |
| `npm run test:browser` | **24 PASS**, 0 FAIL, 32,4 s, uma execução (Chromium 1248 headless) |
| `npm run build` | PASS — `background.js` 133.844 B, `form-content.js` 57.831 B, `autos-content.js` 984.542 B, `list-content.js` 27.760 B, `manifest.json` 1.201 B |
| `git diff --check` | PASS |

## Cobertura de F1–F5

- Separação `BATCH_EXECUTION`/`BATCH_SAVE` com `saveAuthorized` no lote.
- Verificação pós-save em aba nova.
- `SAVE_PENDING` sem segundo clique, exceção pós-despacho e ACK sem readback.
- Diálogo estrutural homologado e revalidação dos cinco campos/identidade.
- Classificação de `MISSING_FIELDS` por causa e campos.
- Reconciliação `COMPLETED_EXTERNALLY`.
- Reentrada MV3 por evento e suspensão após reinício.
- Cache entre dois processos e duas abas de processos distintos.
- Fechamento das abas de trabalho somente após `CONFIRMED`; revisões/incertezas ficam abertas.

## Testes de negação dos gates

- Build de distribuição seguro sem flags: três flags falsos no bundle.
- `BATCH_FILL_ONLY` força salvamento desligado.
- Remetente não confiável, processo errado, resposta vazia e `SAVE_UNCERTAIN` não clicam.
- Modo manual não importa o adaptador de salvamento.

## Homologação real

- 25 examinados, 10 preenchidos, 10 salvos, 10/10 verificados no portal.
- 15 revisões; 0 `SAVE_UNCERTAIN`; 10 `SAVE_ACK`.
- Duração 243 s; p50 10,4 s; p95 23,5 s; máximo 31,9 s.
- Detalhes em `batch-2.0-homologation-attempt.md`.

## Limitações

- Kill físico do service worker/reinício do navegador: `MV3_WORKER_KILL_TEST_NOT_RUN`; lógica coberta por testes puros/estáticos.
- Autosave do portal: `UNKNOWN`.
- Chrome profissional: `NOT_RUN`.
- Benchmark sintético anterior: p50 428 ms, p95 704 ms; não é SLA do portal real.
