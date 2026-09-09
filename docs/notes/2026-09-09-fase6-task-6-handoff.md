# Task 6 — handoff

Data: 09/09/2026
Base de retomada: `850421c`, com remediação pós-revisão não commitada
Branch: `codex/fundamentacao-automatico`

## Estado

A integração Fase 6 está implementada e a rodada de remediação está validada
localmente. Alterações de código/teste/documentação nesta retomada incluem:

- `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
- `work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
- `work/tce-extractor/portable/extensao-complementar-ato/content/form-detector.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/form-detector.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/automation-schema.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-schema.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/bridge-client.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`

Este handoff e o relatório são os únicos documentos adicionados.

## Contratos para retomada

1. A integração é opt-in: só roda quando `resolveAutomaticAct` é fornecido.
2. `prepareAutomaticAct` decide elegibilidade; qualquer divergência retorna
   plano vazio e evita escrita parcial.
3. O único write automático é `APPLY_FIELDS`, limitado aos sete campos e
   `matchKinds`; nunca chamar `OVERRIDE_FIELD`.
4. A releitura exige todos os valores propostos/preservados, identidade da
   fila, frame vinculado e geração estável.
5. O controller não chama `REQUEST_COMPLEMENTAR_ATO` nem executa envio.
6. O caminho integrado exige `appendAutomationEvent`; ausência ou falha em
   `item_prepared` é fail-closed. O caminho sem resolver preserva Fase 5.
7. O worker reconstrói o bridge a partir de credenciais persistidas somente ao
   iniciar/controlar automação e não expõe o token.
8. Eventos usam `item_id` canônico e evidência redigida por hashes; não
   persistem os valores pessoais dos sete campos.
9. A guarda do detector vincula `APPLY_FIELDS` ao `requestId` do snapshot e a
   releitura compara todos os catálogos/estados dos sete campos.

## Evidência

- Gate focado: 146 testes, 146 aprovados, 0 falhas.
- `npm test`: 231 testes, 231 aprovados, 0 falhas.
- Sintaxe dos módulos alterados e `git diff --check`: verdes.
- Probe Python/store: `process_key` foi aceito como `item_id` após a fila
  wire em snake_case e a transição terminou em `prepared`.
- `git diff --check`: verde.

## Fechamento

O commit-base tem a mensagem `feat: integrate verifiable automatic preparation`;
a remediação pós-revisão ainda não foi commitada. Nenhum portal real foi usado
e nenhum push foi realizado.
