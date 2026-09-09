# Handoff — Fase 4: API local e compatibilidade

## Estado

Fase 4 implementada na branch `codex/fundamentacao-automatico`. A rodada de
correções da revisão independente está concluída, incluindo a guarda de
identidade da extensão para controles `AUTO_*`, no commit
`fix: enforce extension identity for automation control`; o checkout não
possui remoto. Envio real permanece bloqueado.

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
  e restringe controle automático a páginas da própria extensão, validando
  `sender.id` e o hostname da URL contra `chrome.runtime.id`.
- Retry de criação preserva o `event_id` inicial e o snapshot original de
  forma atômica no `AutomationStore`; payload divergente gera conflito.
- Legal-context canonicaliza a consulta, confere presença no dataset e hash
  por registro, e retorna revisão/regras autoritativas sem mutar o sidecar.
- Cache do worker só usa identidade/hash/regras/revisão verificados da resposta
  do backend e invalida a identidade em troca de dataset ou revisão.

## Arquivos de ownership

`work/tce-extractor/portable/app/local_service.py`
`work/tce-extractor/portable/app/automation_store.py`
`work/tce-extractor/portable/extensao-complementar-ato/lib/bridge-client.js`
`work/tce-extractor/portable/extensao-complementar-ato/lib/messages.js`
`work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
`work/tce-extractor/portable/extensao-complementar-ato/lib/automation-schema.js`
`work/tce-extractor/test_automation_api.py`
`work/tce-extractor/test_automation_store.py`
`work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
e os testes bridge/worker correspondentes.

## Verificação

Focais Python: 32 executados, 31 pass, 0 falhas, 1 skip ambiental. Store:
17/17. Após a correção de identidade, JS focal: 40/40 e `npm test`: 172/172;
`git diff --check` passou.

TDD da correção: os dois testes de identidade falharam antes da implementação
porque `AUTO_START` alcançava o bridge; após a guarda, os cinco `AUTO_*` de cada
cenário retornam `UNAUTHORIZED` sem chamada ao bridge. O fallback do serviço
antigo continua verde.

A descoberta Python completa foi interrompida após ficar sem saída; o PID
15456 foi encerrado de forma segura. Não há processo Python dessa execução
pendente. Isso fica como limitação ambiental, não como PASS.

## Próximo agente

1. Conferir `git diff --check` e `git status --short --branch`.
2. Revisar o relatório da Fase 4 e a ausência de endpoint de consumo.
3. Usar os contratos de API/bridge para a Fase 5, sem tocar em navegação,
   preenchimento ou envio real.
