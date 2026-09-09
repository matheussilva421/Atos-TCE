# Task 6 — handoff

Data: 09/09/2026
Base de retomada: `74d0e0a`
Branch: `codex/fundamentacao-automatico`

## Estado

A integração Fase 6 está implementada, validada localmente e registrada no
commit solicitado. Alterações de código/teste estão restritas a:

- `work/tce-extractor/portable/extensao-complementar-ato/background/automation-controller.js`
- `work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
- `work/tce-extractor/portable/extensao-complementar-ato/content/form-detector.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-controller.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/form-detector.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`

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
6. Se `appendAutomationEvent` existir, eventos são persistidos; falha em
   `item_prepared` é fail-closed. Bridge antigo sem o método mantém Fase 5.
7. O worker adiciona `dataset_sha256` ao registro resolvido para amarrar o
   hash ao preflight, sem alterar o dataset persistido.

## Evidência

- Fase 6 + Fase 5: 98 testes, 98 aprovados, 0 falhas.
- `npm test`: 224 testes, 224 aprovados, 0 falhas.
- Sintaxe dos seis arquivos alterados: verde.
- `git diff --check`: verde.

## Fechamento

O commit local tem exatamente a mensagem `feat: integrate verifiable automatic
preparation`. Conferir o SHA atual com `git rev-parse HEAD`. Nenhum portal real
foi usado e nenhum push foi realizado.
