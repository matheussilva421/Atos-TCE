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

## Fix round atual — validado e pronto para commit

Em 2026-09-09 foram implementados os fixes pendentes da revisão:

- criação de run e congelamento de queue consultam replay por `event_id` e
  payload canônico antes da validação do dataset atual;
- retry idêntico continua idempotente após troca do dataset, payload diferente
  conflita e `event_id` novo permanece sujeito ao dataset/identidade/contexto
  atuais;
- payloads de eventos são discriminados por tipo em Python e JS;
  `send_confirmed` exige identidade, origem, timestamp, campos e citações não
  vazios; hashes de intenção e eventos de controle têm validação fechada;
- eventos de controle não aceitam `item_id`, e não há endpoint
  `consume_command` nem envio real.

RED/GREEN observado para `send_confirmed`: Python retornava 409 de transição e
o schema JS aceitava `fields: {}`/`citations: []`; após a implementação ambos
retornam a rejeição de contrato esperada. Estado focal atual: Python API,
serviço e auth 37 testes, 36 pass e 1 skip ambiental; store 17/17; JS focal
41/41.

Blocker preservado para a Fase 10: `lib/automation-schema.js` foi alterado,
mas a allowlist/empacotador não foi tocada. A Fase 10 precisa incluir o módulo
e sua cobertura no pacote antes de qualquer declaração release-ready.

Gates finais: Python API/serviço/auth 37 testes, 36 pass e 1 skip ambiental;
store 17/17; Node focal 41/41; `npm test` 173/173; `py_compile` e
`git diff --check` passaram. Warnings de `ResourceWarning`/`fitz` são conhecidos
do ambiente. Não houve teste amplo pendente nesta retomada.

Próxima retomada: conferir o SHA do commit
`fix: harden automation retries and event payloads` e registrar que o checkout
não possui remoto configurado; não fazer push se o remoto continuar ausente.

## Fechamento final

Commit criado: `fix: harden automation retries and event payloads`; o SHA final
foi verificado no fechamento e é reportado na resposta da sessão. O checkout está limpo na branch local
`codex/fundamentacao-automatico`; não há remoto configurado, portanto não
houve push. O próximo agente deve manter `consume_command`, envio real e
empacotamento fora desta fase e tratar o módulo `automation-schema.js` como
blocker explícito da Fase 10.
