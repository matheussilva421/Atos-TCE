# Handoff — Fase 7: envio único e recuperação

## Estado

Fase 7 foi implementada no simulador local em 09/09/2026. O comando de envio é
durável e de uso único; o resultado incerto não autoriza repetição automática.
O portal real permanece fora do escopo e `real_send_enabled=false`.

## Arquivos relevantes

- Extensão: `content/portal-submit.js`, `content/form-detector.js`,
  `background/automation-controller.js`, `background/service-worker.js`,
  `lib/messages.js`, `lib/bridge-client.js`, `lib/automation-schema.js`,
  `manifest.json`.
- Testes: `tests/portal-submit.test.mjs` e testes atualizados de schema,
  bridge, controller, worker, detector e painel.
- Serviço: `portable/app/automation_store.py`,
  `portable/app/local_service.py`, `portable/test_automation_recovery.py`.
- Relatório: `docs/notes/2026-09-09-fase7-task-7-report.md`.

## Contrato de retomada

1. `send_intent` deve existir antes do comando ser consumível.
2. `consume_command` exige execução `running`, revisão atual, item em
   `send_intent`, prazo vigente e comando `issued`.
3. O consumo registra `command_consumed` e marca o comando como consumido numa
   transação CAS. Uma segunda tentativa falha sem clique.
4. Após reinício, uma intenção aberta vira `unconfirmed` e a execução pausa;
   não consumir novamente sem conciliação explícita.
5. Confirmação exige aceitação observada e leitura posterior da mesma
   identidade; ausência de prova permanece incerta.

## Validação

- JS: `npm test` — 238/238 pass.
- Submitter: `node --test tests/portal-submit.test.mjs` — 6/6 pass.
- Python: `python -m unittest test_automation_recovery -q` — 3/3 pass.
- Sintaxe JS/Python e `git diff --check`: verdes.
- Nenhum envio real, clique real, dado real ou token foi publicado.

## Próxima retomada

Começar a Fase 8 lendo a seção 13.1–13.5 do plano e os contratos atuais de
`panel.html`, `panel.js`, `panel.css`, `panel.test.mjs`, histórico e status.
Implementar primeiro RED para indisponibilidade sem pareamento/serviço,
execução ativa e contexto ausente. Integrar apenas estado já persistido; o
painel não deve iniciar consumo automaticamente ao reabrir.
