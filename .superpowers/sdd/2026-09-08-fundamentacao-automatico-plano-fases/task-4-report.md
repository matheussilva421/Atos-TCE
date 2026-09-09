# Relatório — Fase 4: API local e compatibilidade da extensão

Data: 2026-09-09
Branch: `codex/fundamentacao-automatico`
Brief: `task-4-brief.md` lido integralmente antes da implementação.

## Status

Implementação concluída dentro do ownership da Fase 4. A API permanece
loopback/autenticada, o envio real continua bloqueado (`real_send_enabled: false`)
e nenhum comando de consumo foi liberado nesta fase. O checkout não possui
remoto configurado; não houve push.

## Implementação

- `portable/app/local_service.py`
  - Expõe capabilities, contexto jurídico, criação/consulta de execução,
    congelamento de fila, eventos, controle e relatórios HTML/CSV.
  - Reutiliza `AutomationStore`, `legal_context` e `automation_report`.
  - Recalcula o hash lógico do dataset publicado/atual e rejeita troca de
    dataset, identidade ausente ou contexto de outra revisão.
  - Mantém payloads fechados, erros tipados, autenticação por token + Origin,
    limite de corpo de 2 MiB e lote máximo de 10.000 identidades.
  - Relatório resolve somente a raiz atual do serviço, aceita apenas `html` ou
    `csv` e não recebe caminho/root/URL do cliente.
- `lib/automation-schema.js`, `lib/bridge-client.js` e `lib/messages.js`
  - Adicionam os contratos v1, conversão wire camelCase/snake_case, validação
    de envelopes e fallback `null` de capabilities para serviço antigo.
  - Adicionam `AUTO_START`, `AUTO_PAUSE`, `AUTO_RESUME`, `AUTO_STOP` e
    `AUTO_STATUS` com payloads fechados.
  - Mantêm `GET_MATCH` v1 e aceitam contexto contextual com cache/revisão sem
    alterar os sete campos legados.
- `background/service-worker.js`
  - Cacheia contexto por identidade, hash, regras e revisão; limpa-o ao trocar
    dataset.
  - Só páginas `chrome-extension://` controlam execução; content scripts,
    origem inadequada e serviço antigo permanecem em fallback manual.

## TDD e verificação

RED foi observado para rotas sem token/origin inválida, dataset trocado,
revisão obsoleta, lote/corpo acima do limite e payload extra. Durante a
integração foi corrigida uma falha estrutural do backend: colisão entre o
método HTTP e a função de projeção de snapshot, agravada por chamadas sem o
rótulo obrigatório em `_require_text`; isso convertia criações válidas em 500.

Gates aprovados da rodada inicial:

- `python -m unittest test_automation_api -q`: 7 executados, 7 passaram, 0 falharam.
- `python -m unittest test_automation_api test_local_service test_bridge_auth -q`:
  30 executados, 29 passaram, 0 falharam, 1 skip ambiental.
- Python ampliado (`test_automation_store test_automation_report
  test_legal_context test_local_service test_bridge_auth test_automation_api`):
  79 executados, 78 passaram, 0 falharam, 1 skip ambiental.
- `node --test tests/automation-schema.test.mjs tests/bridge-client.test.mjs
  tests/service-worker.test.mjs`: 37/37 passaram.
- `npm test`: 169/169 passaram.
- `python -m py_compile portable/app/local_service.py test_automation_api.py`:
  passou.
- `git diff --check`: passou.

## Rodada de correções após revisão independente

Correções TDD concluídas no mesmo checkout, sem alterar navegação, envio,
empacotamento ou liberar `consume_command`:

- `AutomationStore` persiste o `event_id` inicial, o spec e o snapshot de
  criação na mesma transação. Retry com o mesmo payload devolve o mesmo
  resultado; reuso com payload diferente retorna `EVENT_CONFLICT` antes de
  considerar execução ativa.
- `GET /api/v1/legal-context` canonicaliza processo/interessado, exige que a
  identidade exista no dataset carregado, exige `dataset_sha256` por registro
  e injeta somente `context_revision`/`rules_version` derivados do backend.
  Hash ausente/divergente e identidade ausente permanecem erros tipados; o
  caminho de contexto grande altera apenas a cópia de resposta para `pending`.
- O service worker compara contexto com o hash do dataset importado, valida a
  revisão e as regras retornadas pelo backend, usa esses valores verificados
  na chave e invalida entradas da identidade quando dataset/revisão mudam.
  Metadados arbitrários do cliente não populam cache.

Gates desta rodada:

- `python -m unittest test_automation_api test_local_service test_bridge_auth -q`:
  32 executados, 31 passaram, 0 falharam, 1 skip ambiental.
- `python -m unittest test_automation_store -q`: 17 executados, 17 passaram,
  0 falharam.
- `node --test tests/automation-schema.test.mjs tests/bridge-client.test.mjs
  tests/service-worker.test.mjs`: 38/38 passaram.
- `npm test`: 170/170 passaram.
- `python -m py_compile portable/app/local_service.py
  portable/app/automation_store.py test_automation_api.py
  test_automation_store.py`: passou.
- `git diff --check`: passou.

Commit anterior: `fix: bind automation API identity and retry state`.

Warnings conhecidos: `fitz` depreciado e `ResourceWarning` de limpeza de
`HTTPError` já emitidos pelo ambiente/suítes; não alteraram o resultado.

## Correção após revisão independente

- Os testes RED adicionados em `tests/service-worker.test.mjs` cobrem URL
  `chrome-extension://` de outro ID e `sender.id` divergente do
  `chromeApi.runtime.id`; cada cenário rejeita os cinco tipos `AUTO_*` com
  `UNAUTHORIZED` sem chamar o bridge.
- `background/service-worker.js` agora exige simultaneamente `sender.id` igual
  ao ID da própria extensão e URL `chrome-extension:` válida cujo hostname é o
  mesmo ID antes de despachar controle automático.
- O fallback manual para serviço antigo e as mensagens existentes foram
  preservados. Navegação, envio real e `consume_command` não foram alterados.

Gates desta correção:

- RED confirmado antes da implementação: 2 testes falharam porque o bridge
  era alcançado nos dois cenários.
- `node --test tests/automation-schema.test.mjs tests/bridge-client.test.mjs
  tests/service-worker.test.mjs`: 40 executados, 40 passaram, 0 falharam.
- `npm test`: 172 executados, 172 passaram, 0 falharam.
- `git diff --check`: passou.

## Limitação registrada

`python -m unittest discover -s . -p 'test_*.py' -q` e uma tentativa ampla
equivalente ficaram sem saída por mais tempo que o gate focal. O processo
Python específico da descoberta (`PID 15456`) foi encerrado com segurança após
a tentativa normal retornar acesso negado; não restou processo Python dessa
execução. Como a descoberta ampla não produziu contagem final, ela não é
declarada PASS. Os testes de navegador/ambiente amplo permanecem fora da
evidência GREEN desta fase; nenhum envio ou navegação real foi iniciado.

## Arquivos

Alterados/criados no escopo: `portable/app/local_service.py`,
`portable/app/automation_store.py`,
`portable/extensao-complementar-ato/lib/bridge-client.js`,
`lib/messages.js`, `background/service-worker.js`,
`lib/automation-schema.js`, `test_automation_api.py`,
`test_automation_store.py`, `tests/automation-schema.test.mjs`,
`tests/bridge-client.test.mjs` e
`tests/service-worker.test.mjs`.

## Retomada

Próxima fase: revisar esta API e consumir seus contratos na formação de fila
da Fase 5. Não adicionar endpoint de consumo de comando, navegação de portal,
preenchimento ou envio nesta fase.

## Fix round — retries e payloads de eventos

Data: 2026-09-09. Este round corrige os dois achados pendentes da revisão da
Fase 4, preservando o checkout compartilhado e sem alterar empacotador,
navegação, preenchimento ou envio.

- `POST /api/v1/automation/runs` consulta primeiro o replay persistido por
  `event_id` e payload canônico. Um retry idêntico devolve o snapshot original
  mesmo se o dataset publicado mudou; payload diferente devolve
  `EVENT_CONFLICT`; `event_id` novo continua sujeito ao hash do dataset atual.
- `POST /api/v1/automation/runs/<run_id>/queue` aplica a mesma ordem por
  `event_id`/payload antes de `_assert_run_dataset`. O retry idêntico sobrevive
  à troca do dataset, conflito não muta estado e um evento novo continua
  sujeito a `DATASET_MISMATCH`/identidade/contexto atuais.
- Python e `automation-schema.js` agora discriminam os payloads por
  `event_type`, rejeitam payload vazio/incompleto e chaves extras conforme o
  contrato de cada evento, validam `expected_fields_hash` como SHA-256 e
  restringem eventos de controle a `payload: {}` sem `item_id`.
- `send_confirmed` exige identidade, origem, timestamp, campos e citações;
  identidade/campos/citações não podem ser vazios. Isso mantém a confirmação
  vinculada a dados observáveis, sem interpretar intenção ou estado local como
  confirmação de portal.

TDD desta rodada: o novo RED Python retornava 409 de transição porque o
  payload vazio de confirmação era aceito; o RED JS não lançava exceção para
  `fields: {}`/`citations: []`. Após a correção mínima, ambos passaram. Os
  testes de replay foram mantidos no contrato HTTP para cobrir retry após
  troca de dataset, conflito por payload e evento novo fail-closed.

### Blocker da Fase 10

`portable/extensao-complementar-ato/lib/automation-schema.js` foi alterado
para fechar o contrato, mas o empacotador não foi alterado nesta fase. A Fase
10 deve atualizar a allowlist/QA do pacote para incluir o módulo e seus testes;
até essa integração, o ZIP portátil não deve ser declarado release-ready.

Arquivos funcionais deste round: `portable/app/automation_store.py`,
`portable/app/local_service.py`, `test_automation_api.py`,
`portable/extensao-complementar-ato/lib/automation-schema.js`,
`portable/extensao-complementar-ato/tests/automation-schema.test.mjs` e
`tests/bridge-client.test.mjs`. Nenhum arquivo de empacotamento foi tocado.

Gates finais do round: Python API/serviço/auth 37 testes, 36 pass e 1 skip
ambiental; store 17/17; Node focal 41/41; `npm test` 173/173;
`python -m py_compile` passou para os módulos/testes Python alterados;
`git diff --check` passou. Warnings de `ResourceWarning`/`fitz` são do
ambiente já conhecido e não falharam a suíte.

Commit final: `fix: harden automation retries and event payloads`. Branch local:
`codex/fundamentacao-automatico`; nenhum remoto está configurado e nenhum
push foi realizado. O SHA final foi verificado no fechamento do checkout e é
reportado na resposta da sessão.

## Correção final — identidade global de `event_id`

Foi corrigida a colisão entre `run_creation_requests.event_id` e
`events.event_id`. O store agora mantém `event_id_registry` e reserva o ID
na mesma transação da criação/replay do run ou da persistência do evento.
Retries idempotentes continuam sendo resolvidos primeiro: `create_run` com o
mesmo payload e eventos já persistidos retornam o resultado original; payload
alterado ou colisão entre namespaces gera `EventConflict` sem avançar a
revisão. A checagem ocorre antes da validação de dataset no replay.

Para bancos existentes, a inicialização cria a tabela ausente e faz backfill
tolerante (`INSERT OR IGNORE`) de `run_creation_requests` e `events`, sem
invalidar o banco por duplicidades históricas. O teste de migração também
confirma replay legado e bloqueio posterior da colisão.

TDD e gates desta rodada:

- RED: 2 testes reproduziram o mesmo ID em `create_run`/evento e em
  evento/`create_run`; ambos falharam antes da correção por ausência de
  conflito.
- GREEN: `test_automation_store` 20/20; Python API/serviço/auth 37 testes,
  36 pass, 0 fail e 1 skip ambiental; Node focal 41/41; `npm test` 173/173.
- `python -m py_compile` passou e `git diff --check` passou.

Arquivos funcionais deste round: `portable/app/automation_store.py` e
`test_automation_store.py`, além deste relatório e do handoff. Empacotador,
`consume_command` e envio real permaneceram fora do escopo. O blocker da Fase
10 sobre a allowlist/QA do pacote permanece registrado acima e não é falha da
Fase 4.
