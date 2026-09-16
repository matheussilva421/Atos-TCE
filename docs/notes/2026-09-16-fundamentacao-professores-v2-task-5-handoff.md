# Handoff — fundamentação de professores v2 — Task 5

## Implementado

- Criada `isAutomaticLegalDecision(decision)` em `lib/automation-preflight.js`.
- O gate exige simultaneamente `status=selected`, método diferente de `none`, `hard_conflict=false`, `confidence >= 0.90` e `margin >= 0.12`.
- Decisão selecionada sem os campos numéricos v2, com confiança baixa, margem pequena ou conflito explícito agora gera `LEGAL_DECISION_REVIEW_REQUIRED` e não prepara nenhum campo.
- Evidência sanitizada do preflight preserva `confidence`, `margin` e `hard_conflict` sem copiar dados privados, DOM ou tokens.
- `background/service-worker.js` usa o mesmo predicado antes de inserir `fundamento_legal` em `matchedValues`.
- Em REVIEW/PENDING, o worker mantém a decisão rica para o evento interno e sinaliza `matchKinds.fundamento_legal` como `tie`; nenhum `APPLY_FIELDS` é emitido.
- `autoSubmit` e `real_send_enabled` não foram ampliados nem ativados; o cenário testado continua sem envio externo.

## Testes

- RED confirmado antes da implementação: confiança `0,82` ainda preparava campos.
- `node --test tests/automation-preflight.test.mjs tests/service-worker.test.mjs`: 66 testes, 66 aprovados, 0 falhas.
- O teste integrado executa uma decisão segura e, depois, uma decisão com confiança baixa; verifica que a primeira prepara uma vez e a segunda registra `item_pending` sem nova escrita.

## Arquivos alterados

- `work/tce-extractor/portable/extensao-complementar-ato/lib/automation-preflight.js`
- `work/tce-extractor/portable/extensao-complementar-ato/background/service-worker.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/automation-preflight.test.mjs`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/service-worker.test.mjs`

## Pendências / retomada

- Implementar Task 6: diagnóstico legível no painel, distinguindo fundamento documental de opção cadastral.
- Depois atualizar a integração Python e qualification para `legal-foundation-v2`, allowlists/empacotamento e matriz de validação.
- Rodar suíte completa e QA do pacote distribuído antes da conclusão.

## GitHub

- Branch: `codex/fundamentacao-professores-crosswalk-v2`.
- Este handoff deve ser commitado e enviado junto com o gate da Task 5.
