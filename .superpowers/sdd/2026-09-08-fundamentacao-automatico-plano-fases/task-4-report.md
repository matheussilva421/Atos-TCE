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

Gates aprovados:

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

Warnings conhecidos: `fitz` depreciado e `ResourceWarning` de limpeza de
`HTTPError` já emitidos pelo ambiente/suítes; não alteraram o resultado.

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
`portable/extensao-complementar-ato/lib/bridge-client.js`,
`lib/messages.js`, `background/service-worker.js`,
`lib/automation-schema.js`, `test_automation_api.py`,
`tests/automation-schema.test.mjs`, `tests/bridge-client.test.mjs` e
`tests/service-worker.test.mjs`.

## Retomada

Próxima fase: revisar esta API e consumir seus contratos na formação de fila
da Fase 5. Não adicionar endpoint de consumo de comando, navegação de portal,
preenchimento ou envio nesta fase.
