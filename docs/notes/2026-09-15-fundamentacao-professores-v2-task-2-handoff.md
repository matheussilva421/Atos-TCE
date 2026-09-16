# Handoff — fundamentação de professores v2 — Task 2

## Implementado

- Criado `work/tce-extractor/portable/extensao-complementar-ato/lib/retirement-legal-profile.js`.
- Criado `work/tce-extractor/portable/extensao-complementar-ato/tests/retirement-legal-profile.test.mjs`.
- O perfil produz `scope`, `modality`, `proportionality`, `calculation_basis`, `parity`, contexto docente, regra docente explícita, transição, referências e evidências.
- `proventos integrais` vira `proportionality=integral`; `integralidade`/remuneração e média são sinais separados de base de cálculo.
- `cargo=PROFESSOR` marca contexto, mas não cria regra docente; CF art. 40 §5º expresso pode criar `professor_rule_explicit=true`.

## Testes

- RED inicial: módulo ausente, `ERR_MODULE_NOT_FOUND` confirmado.
- `node --test tests/retirement-legal-profile.test.mjs`: 4 pass, 0 fail.
- `node --test tests/retirement-legal-profile.test.mjs tests/normalizer.test.mjs`: 15 pass, 0 fail.

## Retomada

Implementar `portal-legal-crosswalk.js` com regras por assinatura de label, crosswalk ECE20, hard reject civil/militar, score normalizado, ranking, margem e estados selected/review/pending.
