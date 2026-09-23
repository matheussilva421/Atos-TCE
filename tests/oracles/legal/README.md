# Oráculos de paridade

Estes arquivos são **cópias** dos módulos JavaScript comprovados que serviam de
oráculo para o fundamento legal do backend (M4, tarefa 3). Eles foram promovidos
da extensão legada para cá em 2026-09-18 para que o gate de paridade sobreviva à
aposentadoria do legado (M6, tarefa 8): o teste `tests/test_legal_rules.py` roda
`tests/legal_parity_harness.mjs`, que carrega exatamente estes arquivos.

| Arquivo | Papel |
|---|---|
| `legal-foundation.js` | fundação legal comprovada (resolução de referências, classes) |
| `normalizer.js` | normalização de texto legal |
| `legal-reference-parser-v2.js` | parser de referências v2 |
| `retirement-legal-profile.js` | perfil legal de aposentadoria |
| `catalog-option-signature.js` | assinatura de opções do catálogo |
| `portal-legal-crosswalk.js` | cruzamento portal × catálogo |
| `automation-preflight.js` | pré-checagem usada pela fundação |

Regras:

1. não editar estes arquivos para "consertar" o backend — a divergência é o que
   o teste precisa mostrar; se o backend mudar de propósito, o oráculo e o teste
   mudam juntos, com a decisão registrada no handoff;
2. eles são a única superfície JS do legado que o runtime/testes modernos podem
   usar: nenhum caminho de `app/`, `extension/`, `packaging/` ou `START.cmd`
   aponta para a árvore legada (ver `tests/test_no_legacy_paths.py`).

3. The final decisions emitted by the harness are historical v3 results and do
   not gate current selection policy. Python v4 tests own the best-available
   choice contract. Parser, profile, normalization and catalog-signature parity
   remain covered.
