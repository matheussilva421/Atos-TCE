# Task 7 — envio auditável e recuperação no simulador

Data: 09/09/2026
Base: `850421c feat: integrate verifiable automatic preparation`
Status: implementação local concluída; envio real bloqueado até a Fase 9.

## Entrega

- `content/portal-submit.js` implementa `submitVerifiedAct` e
  `classifyPortalOutcome`:
  - aceita somente comando emitido, não expirado e vinculado a frame/geração,
    identidade e hash dos campos;
  - exige exatamente um botão habilitado com texto `Complementar Ato`;
  - solicita o consumo durável ao worker antes do clique;
  - não repete clique após consumo ou resultado incerto;
  - só classifica `confirmed` com aceitação e releitura posterior da identidade;
    timeout, queda, diálogo desconhecido ou prova insuficiente ficam
    `unconfirmed`.
- O listener do frame de botões recebe `AUTO_SUBMIT_COMMAND`, envia o comando
  tipado `AUTO_CONSUME_COMMAND` ao worker e devolve a classificação sem expor
  valores dos sete campos.
- `automation-controller.js`, `service-worker.js`, `messages.js` e
  `bridge-client.js` validam frame, geração, identidade, revisão, execução
  ativa e consumo CAS; a ponte reconstrói credenciais persistidas sem colocar
  token em mensagens.
- `automation_store.py` persiste `send_intent` e o comando de uso único,
  registra `command_consumed` transacionalmente, rejeita consumo duplicado ou
  expirado e, ao reabrir, converte intenção aberta em `unconfirmed`/pausado.
- `local_service.py` expõe o endpoint autenticado de consumo e converte
  transições inválidas em códigos tipados (`COMMAND_ALREADY_CONSUMED`,
  `COMMAND_EXPIRED`, `COMMAND_NOT_READY`, `COMMAND_NOT_FOUND`).
- `form-detector.js` expõe apenas o snapshot necessário ao submitter; o
  manifest carrega o script de submissão em todos os frames do portal.

## TDD e validação

- RED registrado para listener ausente (`installPortalSubmit` não exportado);
  GREEN após instalação e teste de consumo antes do único clique.
- `node --test tests/portal-submit.test.mjs`: 6/6 aprovados.
- `npm test`: 238/238 aprovados, 0 falhas.
- `python -m unittest test_automation_recovery -q`: 3/3 aprovados, 0 falhas.
- `node --check` passou nos módulos JS alterados.
- `compile()` passou em `automation_store.py`, `local_service.py` e no teste
  Python novo.
- `git diff --check` passou.

## Limites e validação manual

- Nenhum portal real foi aberto para envio; nenhum botão real foi clicado.
- `real_send_enabled` continua `false`; os resultados são de contratos,
  fixtures e harness local.
- Não existe suíte Python ampla de automação/browser neste checkout; a
  descoberta ampla anterior encontrou zero testes. Isso não é declarado como
  aprovação.
- Revisões paralelas solicitadas aos subagents não concluíram antes do
  timeout; não há aprovação independente adicional a declarar.

## Git e retomada

- As alterações estão locais e ainda aguardam commit desta rodada.
- Não há remoto configurado; nenhum push foi realizado.
- Próxima etapa: Fase 8 — redesign operacional do painel, sem liberar envio
  real e sem reimplementar a mesa web.
