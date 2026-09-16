# Handoff — fundamentação de professores v2 — Task 6

## Implementado

- `sidepanel/panel-view.js` agora constrói `legalDiagnostics` a partir de `documentary_foundation`, `portal_classification`, ranking, evidências e warnings.
- O diagnóstico visual distingue:
  - fundamento documental;
  - opção sugerida do portal;
  - método jurídico;
  - confiança e margem;
  - coincidências;
  - diferenças esperadas pelo crosswalk;
  - warnings de revisão.
- O crosswalk ECE20 → classe histórica EC41/EC47 é apresentado explicitamente quando as referências e razões internas sustentam essa leitura.
- O warning de professor identificado pelo cargo sem regra docente expressa é exibido e permanece compatível com o gate de revisão da Task 5.
- `sidepanel/panel.js` marca decisões jurídicas não-AUTO como empate para apresentação, sem transformar REVIEW/PENDING em preenchimento automático.
- O diagnóstico usa apenas dados jurídicos da decisão; matrícula, CPF e nome não são copiados para `legalDiagnostics`.

## Testes

- RED confirmado antes da implementação: `legalDiagnostics` não existia no view model.
- `node --test tests/panel.test.mjs`: 53 testes, 53 aprovados, 0 falhas.

## Arquivos alterados

- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel.js`
- `work/tce-extractor/portable/extensao-complementar-ato/sidepanel/panel-view.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/panel.test.mjs`

## Pendências / retomada

- Implementar Task 7: alinhar JS, serviço Python, qualification, capabilities e testes para `legal-foundation-v2`.
- Depois auditar allowlists/empacotamento e construir a matriz de validação >=12 casos.
- Executar suíte completa JS/Python e QA do pacote antes da conclusão.

## GitHub

- Branch: `codex/fundamentacao-professores-crosswalk-v2`.
- Este handoff deve ser commitado e enviado junto com o diagnóstico do painel.
