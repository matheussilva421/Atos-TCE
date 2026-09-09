# Handoff — Fase 4: API local e compatibilidade

## Estado

Fase 4 implementada na branch `codex/fundamentacao-automatico`. O código
está pronto para revisão/integracão no commit solicitado
`feat: expose authenticated automation API`; o checkout não possui remoto.
Envio real permanece bloqueado.

## O que foi feito

- Backend autenticado com capabilities, contexto exato, runs, queue,
  snapshot, events, control e report HTML/CSV.
- Hash lógico recalculado contra o dataset atual/publicado; identidades e
  contexto jurídico conferidos antes de congelar fila.
- Revisões obsoletas, replay idempotente/conflito, payload extra, body >2 MiB
  e queue >10.000 tratados sem mutação parcial.
- Schema/bridge JS v1 e mensagens automáticas fechadas; serviço antigo retorna
  fallback manual quando capabilities não existem.
- Worker recebe contexto com cache indexado por identidade/hash/regras/revisão
  e restringe controle automático a páginas da extensão.

## Arquivos de ownership

`work/tce-extractor/portable/app/local_service.py`
`work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
`work/tce-extractor/portable/extensao-complementar-ato/lib/messages.js`
`work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
`work/tce-extractor/portable/extensao-complementar-ato/lib/automation-schema.js`
`work/tce-extractor/test_automation_api.py`
`work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
e os testes bridge/worker correspondentes.

## Verificação

Focais Python: 30/30 sem falhas, 1 skip ambiental. Python ampliado: 79
executados, 78 pass, 1 skip. JS focal: 37/37. `npm test`: 169/169.
`py_compile` e `git diff --check` passaram.

A descoberta Python completa foi interrompida após ficar sem saída; o PID
15456 foi encerrado de forma segura. Não há processo Python dessa execução
pendente. Isso fica como limitação ambiental, não como PASS.

## Próximo agente

1. Conferir `git diff --check` e `git status --short --branch`.
2. Revisar o relatório da Fase 4 e a ausência de endpoint de consumo.
3. Usar os contratos de API/bridge para a Fase 5, sem tocar em navegação,
   preenchimento ou envio real.
