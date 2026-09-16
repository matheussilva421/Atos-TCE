# Handoff — fundamentação de professores v2 — Task 1

## Implementado

- Criado `work/tce-extractor/portable/extensao-complementar-ato/lib/legal-reference-parser-v2.js`.
- Criado `work/tce-extractor/portable/extensao-complementar-ato/tests/legal-reference-parser-v2.test.mjs`.
- O parser retorna referências com `diploma_type`, número/ano normalizados, artigo/sufixo, parágrafos estruturados, incisos, alíneas, itens e texto bruto.
- O caso ECE 20/2020 mantém `art. 7`, `art. 6`, os parágrafos múltiplos e `§ 11` associado ao artigo 6.
- Anos de dois dígitos seguem a regra 50/00: `20/98` vira `1998`; `41/03` vira `2003`.

## Testes

- RED inicial: módulo ausente, `ERR_MODULE_NOT_FOUND` confirmado.
- `node --test tests/legal-reference-parser-v2.test.mjs`: 4 pass, 0 fail.
- `node --test tests/normalizer.test.mjs tests/legal-foundation.test.mjs`: 36 pass, 0 fail.

## Riscos/limites

- O parser é deliberadamente limitado ao vocabulário e às formas necessárias ao catálogo TCE/RN; não é um parser universal de legislação.
- A associação de qualificadores complexos é conservadora e deve ser exercitada pelo perfil/crosswalk antes de permitir AUTO.

## Retomada

Implementar o perfil funcional em `lib/retirement-legal-profile.js`, sempre iniciando pelos testes RED para modalidade, proporcionalidade, base de cálculo, paridade e contexto docente.
