# Handoff — fundamentação de professores v2 — Task 3

## Implementado

- Criado `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`.
- Expandido `tests/portal-legal-crosswalk.test.mjs` com ECE20, alínea, incapacidade/professor e similaridade lexical não segura.
- O classificador lê `option.value`/`option.label` atuais, infere assinatura por label/class_id e não fixa IDs de produção.
- Crosswalk declarado `ECE20_ART7_VOLUNTARY_TRANSITION` permite ECE20 → EC41/EC47 histórico.
- Score normalizado expõe componentes e peso lexical fixo de 0,05; `confidence` e `margin` governam AUTO/REVIEW/PENDING.
- Hard rejects cobrem civil/militar, modalidade incompatível, alínea/inciso discriminante, placeholder e opção não selecionável.

## Testes

- RED inicial: módulo ausente, `ERR_MODULE_NOT_FOUND` confirmado.
- `node --test tests/portal-legal-crosswalk.test.mjs tests/retirement-legal-profile.test.mjs tests/legal-reference-parser-v2.test.mjs`: 12 pass, 0 fail.

## Decisão importante

Incapacidade com cargo `PROFESSOR`, mas sem referência jurídica específica, pode ter `CF40_I` como melhor sugestão, porém permanece `REVIEW` com `automatic=false`. O cargo não é ground truth suficiente para AUTO.

## Retomada

Integrar o classificador ao `legal-foundation.js`/`matcher.js`, mantendo o contrato legado dos demais campos e adaptando REVIEW/PENDING para caminho não automatizável.
