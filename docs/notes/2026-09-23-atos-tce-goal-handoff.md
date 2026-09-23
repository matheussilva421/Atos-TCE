# Atos-TCE M5, fundamento v4 e próximo processo — handoff

Data: 2026-09-23

## Estado atual

- `origin/main` foi promovida por fast-forward de `ffa208f6782cff080df4c84fd8c60b2a1932a246` para `b1d41e848c39cb61947b011501925c40f86793fb`, igual a `origin/codex/mesa-local-refactor`.
- Ancestralidade confirmada após novo fetch: `git merge-base --is-ancestor origin/codex/mesa-local-refactor origin/main` retornou 0. Push normal concluído; sem force-push.
- Implementação iniciada na branch `codex/best-effort-form-filling`, criada do `main` promovido, no clone isolado `.worktrees/atos-tce-baseline`.
- Checkout original preservado sem alterações por esta execução. Ele já continha 17 arquivos modificados e `work/tce-extractor/.codex-live-pilot.py` não rastreado.

## Gates de baseline antes da promoção

- `python -m unittest discover -s tests -p "test_*.py" -q`: 573 executados, 573 passaram incluindo 1 skip. A primeira tentativa no worktree gerenciado falhou em 3 testes de empacotamento por restrição de escrita; repetida com permissão no mesmo commit e passou.
- `npm test --prefix extension`: 135 passaram, 0 falhas.
- `node --test app/web/tests/*.test.mjs`: 20 passaram, 0 falhas; houve aviso não bloqueante `MODULE_TYPELESS_PACKAGE_JSON`.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1`: 1258 verificações, 1256 passaram, 0 falhas, 2 skips. Todos os 7 estágios passaram. Logs temporários em `%TEMP%\tce-project-verification-7b4e29484dfb4e9fbc527902c3fb93ee`.
- `git diff --check`: passou.
- Observação de layout: o gate oficial deste checkout é `work/tce-extractor/verify-project.ps1`, conforme `AGENTS.md`.

## Task 1 do plano — catálogo selecionável

- Criados 3 testes para excluir placeholders e valores/rótulos vazios, impedir fallback do label para `value`, e preservar valor bruto/índice original.
- RED confirmado: os 3 testes falharam por `AttributeError` porque `selectable_legal_options` ainda não existia.
- GREEN: helper implementado em `app/analysis/legal.py`; os 3 testes passaram e `python -m unittest tests.test_legal_rules -v` passou (27 testes, 0 falhas).
- Nenhum oracle v3 foi alterado; a escolha final ainda permanece v3 até completar o Task 2.

## Task 2 do plano — legal-foundation-v4

- RED confirmado nos contratos para fonte incompleta/contraditória, classe desconhecida, hard conflicts, thresholds, empate e catálogo vazio.
- Implementado `legal-foundation-v4`: texto documental é ranqueador; opções reais são filtradas pelo helper canônico; hard conflicts preferem candidatas sem conflito quando disponíveis e, caso contrário, a melhor candidata real é selecionada. Empate termina pelo índice original e produz warnings. Confiança/margem continuam diagnósticos.
- A decisão passa a `selected/AUTO_SELECTED` somente com `option_value` selecionável no catálogo; a validação de membership também existe no resolver. Sem texto ou sem opção real, não inventa seleção.
- O teste v3 deixou de exigir igualdade da decisão final. Harness e README identificam o JS como histórico v3; parser, normalizador, perfil e assinatura de catálogo continuam em paridade. Nenhum oracle JS foi alterado.
- O fixture com placeholder mostrou divergência preexistente: o oracle JS preserva `value=""`, mas `_option_parts()` Python o substituía pelo label. Corrigido para preservar o valor bruto e manter a paridade histórica.
- GREEN: `python -m unittest tests.test_legal_rules -q` — 32 testes, 32 passaram, 0 falhas. `git diff --check` passou.

## Task 3 do plano — preflight best-effort

- RED confirmado ao substituir os contratos antigos de bloqueio global: proposta obrigatória ausente, controle ausente/read-only, divergência existente e opção legal não literal falharam pelos `FillBlocked`/matcher anteriores.
- `build_fill_plan()` agora mantém hard blocks apenas para processo/formulário sem identidade suficiente, incompatibilidade de identidade e generation inválida. Proposta/controle ausente, disabled/read-only, divergência e opção comum indisponível viram warnings de campo e os demais campos permanecem no plano.
- Valores divergentes são registrados em `preserved` sem reescrita. A modalidade usa apenas valor/label de opção real; valor vazio e placeholder não podem vencer. Fundamento legal passa primeiro pelo resolver v4, valida membership no catálogo selecionável e nunca cai no matcher literal genérico; catálogo placeholder-only deixa o campo pendente e mantém os demais.
- RED adicional confirmou que o matcher comum aceitava um `<option>` com valor vazio por label; corrigido e coberto.
- Atualizados testes de preflight, fallback manual e orquestração API para parcial best-effort. A identity ausente na origem também bloqueia explicitamente.
- GREEN: `python -m unittest tests.test_fill_service -q` — 57 testes, 57 passaram; `python -m unittest tests.test_legal_rules -q` — 32/32; `python -m unittest tests.test_api_server -q` — 85/85. `git diff --check` passou.
- Arquivos alterados: `app/area_restrita/preflight.py`, `tests/test_fill_service.py`, `tests/test_api_server.py`.

## Task 4 do plano — leitor com controles parciais

- RED confirmado: leitor retornou `null` para formulário com identidade válida e controle `matricula` ausente, pois a versão anterior exigia todos os controles mapeados.
- Separadas as sentinelas de identidade (`txtNumeroProcesso`, `txtAnoProcesso`) dos controles de conteúdo. O formulário também precisa de uma raiz do ato, e os dois campos de identidade devem pertencer a ela; rádio de interessado selecionado continua obrigatório para identidade.
- `readForm()` inclui cada controle presente e omite campos ausentes, permitindo que o backend registre o controle como faltante. Sem âncoras de identidade, interessado selecionado ou raiz de formulário, a leitura continua recusada.
- RED adicional provou que números de processo fora da raiz de formulário não qualificam a página; a validação da raiz foi mantida fail-closed.
- GREEN: `node --test extension/tests/detect-form.test.mjs` — 12 testes, 12 passaram.
- Arquivos alterados: `extension/content/detect-form.js`, `extension/tests/detect-form.test.mjs`, `extension/tests/fake-dom.mjs`.

## Task 5 do plano — filler independente por campo

- RED confirmado em oito casos que antes recusavam o request ou mudavam campos válidos para `skipped`: select indisponível, disabled/read-only, proposta vazia, ausência de controle, falhas de escrita/releitura e valor divergente.
- Guardas globais de formulário, identidade e generation continuam antes de qualquer escrita. Identity incompleta/mismatch, reader ausente e generation ausente/stale retornam `ok:false` sem writes.
- Após os guardas, cada proposta recebe `field_results` próprio: `changed`, `preserved`, `missing_proposal`, `not_found`, `disabled`, `option_unavailable` ou `failed`. Divergência existente fica preservada com `existing_value_divergence`; placeholder selecionado é tratado como vazio; valor de select deve pertencer ao catálogo atual e não pode ser placeholder/disabled.
- Campos graváveis são escritos, relidos individualmente e a execução continua após falha daquele campo. Exceção de releitura permite continuar somente quando visibilidade e identidade do formulário continuam confirmadas.
- `ok:true` indica que os guards passaram e o passe por campo terminou; resultados parciais permanecem nos campos/warnings. Nenhuma capacidade de submit/finalização foi adicionada.
- GREEN: `node --test extension/tests/fill-form.test.mjs` — 17/17; `npm test --prefix extension` — 140/140; `git diff --check` passou.
- Arquivos alterados: `extension/content/fill-form.js`, `extension/tests/fill-form.test.mjs`.

## Proteções e decisões

- Os anexos do goal são as fontes canônicas desta execução: design best-effort como SPEC e os dois documentos de implementação como planos obrigatórios. Foram lidos diretamente como entradas do usuário; não é necessário criar cópias no repositório.
- O diff original de melhor-esforço foi inspecionado e não foi portado: parte dele permite escrita em formulário com identidade divergente e substitui valor real divergente, contradizendo a SPEC. Mantê-lo preservado no checkout original; implementar no branch limpo com TDD.
- Não iniciar código de navegação até completar e registrar toda a PHASE 0 observada na Área Restrita real. A descoberta deve preceder qualquer implementação dessa função.
- Ainda não foi feita validação real supervisionada nem login nesta sessão.

## Pendências e retomada

1. Commitar Task 5; continuar Tasks 6–9 (state machine, API e UI) em `codex/best-effort-form-filling`, com RED antes de cada correção, identity fail-closed e valores divergentes preservados.
2. Criar branch de discovery a partir do `main` promovido; usar a sessão real da Área Restrita para concluir PHASE 0 e commitar somente a nota de discovery antes de qualquer código de navegação.
3. A partir do commit de discovery, criar a branch de navegação; integrar nela os commits Best-Effort/v4 sem perder a ordem de base exigida pelos planos.
4. Executar todas as suítes, `verify-project.ps1`, `git diff --check`, validações reais supervisionadas, revisão final e push das branches.

## GitHub

- `main`: promoção publicada e verificada em `b1d41e8`.
- Branch de implementação: `.worktrees/atos-tce-baseline`, com Tasks 1–4 publicadas em `origin/codex/best-effort-form-filling` até `84d1946`; Task 5 validada e ainda sem commit.
