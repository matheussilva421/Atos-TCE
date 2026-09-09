# Task 6 — relatório de integração verificável

Data: 09/09/2026
Base: `74d0e0a feat: validate automatic field preparation`
Status: implementação concluída localmente.

## Escopo

Alterados somente o controller de automação, o service worker, o detector de
formulário, os testes relacionados e este relatório/handoff. Navegação do
portal, semântica do matcher, envio/submissão, painel e outras fases ficaram
fora do escopo.

## Entrega

- `createAutomationController` aceita o resolver opcional
  `resolveAutomaticAct(identity, formSnapshot, portalSnapshot)`.
- Com o resolver presente, lê o formulário no frame vinculado, enriquece o
  snapshot com identidade/frame/geração, executa `prepareAutomaticAct` e
  bloqueia qualquer lote inelegível antes de escrever.
- O caminho elegível persiste `item_prepared`, envia somente `APPLY_FIELDS`
  com os sete campos permitidos e `matchKinds`, relê o formulário e a tela do
  portal, valida valores propostos/preservados, identidade, frame e geração, e
  persiste `fields_verified`.
- Divergência, contexto ausente/incompleto, decisão jurídica não selecionada,
  campo disabled/readOnly, opção ausente, falha de aplicação ou mismatch de
  releitura gera `item_pending`/`item_failed` sem clique final. Falha ao
  persistir `item_prepared` pausa antes de qualquer escrita.
- O detector bloqueia o lote inteiro se algum campo/opção/identidade mudar
  entre `GET_FORM_SNAPSHOT` e `APPLY_FIELDS`.
- O worker resolve o registro do dataset carregado, chama
  `bridge.getLegalContext`, usa o ranker existente com as opções atuais e
  repassa a decisão jurídica contextual e `matchKinds`.
- Sem o resolver opcional, a Fase 5 permanece inalterada.

## TDD e validação

- RED inicial observado antes da produção: quatro testes do controller, um de
  wiring/auth do worker e um de divergência do detector falharam pelas
  capacidades ausentes.
- Gate Fase 6 + Fase 5: `node --test tests/automation-preflight.test.mjs tests/automation-controller.test.mjs tests/form-detector.test.mjs tests/service-worker.test.mjs tests/portal-navigation.test.mjs` — 98/98 aprovados, 0 falhas.
- Suíte completa: `npm test` — 224/224 aprovados, 0 falhas.
- `node --check` passou nos três módulos produtivos e três testes alterados.
- `git diff --check` passou.

## Segurança e limites

Nenhum portal real, clique de “Complementar Ato”, `REQUEST_COMPLEMENTAR_ATO`,
`OVERRIDE_FIELD`, envio ou submissão foi executado.

## Git

Commit criado localmente com a mensagem exata:
`feat: integrate verifiable automatic preparation`.
O SHA atual deve ser conferido com `git rev-parse HEAD`. Nenhum push foi
realizado; não havia remote configurado para este checkout.
