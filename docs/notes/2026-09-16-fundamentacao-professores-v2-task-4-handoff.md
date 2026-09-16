# Handoff — fundamentação de professores v2 — Task 4

## Implementado

- Integrado `classifyPortalLegalFoundation` ao `lib/legal-foundation.js` por meio de um adaptador compatível com o contrato legado.
- Mantidos os retornos públicos existentes (`selected`/`pending`, `method`, `rule_id`, valores, ranking e citações), sem expor IDs internos de catálogo como regras públicas.
- Adicionados ao resultado integrado `confidence`, `margin`, `references`, `documentary_foundation` e `portal_classification`.
- Fixado `LEGAL_FOUNDATION_RULES_VERSION` em `legal-foundation-v2`.
- Mantidos os guardas de contexto incompleto, referência sem ano, contradição de anos e ausência de referências jurídicas.
- Reforçado o crosswalk estrutural para EC41 com §5º, EC41 art. 6º-A e EC47, com distinção de regra docente explícita.
- Corrigido o parser v2 para não capturar pontuação isolada como número de diploma.
- Atualizado o teste legado de similaridade: artigos diferentes do mesmo diploma, sem crosswalk declarado, permanecem pendentes.

## Testes

- `node --test tests/legal-foundation.test.mjs`: 25 testes, 25 aprovados, 0 falhas.
- `node --test tests/matcher.test.mjs tests/portal-legal-crosswalk.test.mjs tests/retirement-legal-profile.test.mjs tests/legal-reference-parser-v2.test.mjs`: 41 testes, 41 aprovados, 0 falhas.

## Decisões relevantes

- O status legado continua `pending` quando a classificação v2 seria `review`, preservando a superfície pública e bloqueando preenchimento automático; o estado v2 permanece disponível em `portal_classification`.
- A similaridade lexical não seleciona uma opção por si só; a seleção exige confiança mínima e margem mínima, além da ausência de conflito.
- O cargo `Professor` não cria regra docente constitucional implícita.

## Arquivos alterados

- `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-foundation.js`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-reference-parser-v2.js`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/portal-legal-crosswalk.js`
- `work/tce-extractor/portable/extensao-complementar-ato/lib/retirement-legal-profile.js`
- `work/tce-extractor/portable/extensao-complementar-ato/tests/legal-foundation.test.mjs`

## Pendências / retomada

- Implementar Task 5: gate compartilhado de decisão segura em `automation-preflight.js` e `service-worker.js`, com `autoSubmit=false` e `real_send_enabled=false`.
- Depois seguir para diagnóstico da extensão, integração Python, allowlists e matriz de validação.
- Antes do encerramento, executar a suíte completa, QA do pacote distribuído e revisão final.

## GitHub

- Branch de trabalho: `codex/fundamentacao-professores-crosswalk-v2`.
- Este handoff deve ser commitado e enviado junto com a integração da Task 4.
