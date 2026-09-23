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
- Observação de layout: o caminho `.erify-project.ps1` dos planos não existe neste repositório; usar o caminho acima, conforme `AGENTS.md`.

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

## Proteções e decisões

- Os três arquivos fornecidos pelo usuário são a SPEC/plano canônico. Estão no checkout original e são ignorados pelo padrão `/*` do `.gitignore`; não foram copiados nem versionados.
- O diff original de melhor-esforço foi inspecionado e não foi portado: parte dele permite escrita em formulário com identidade divergente e substitui valor real divergente, contradizendo a SPEC. Mantê-lo preservado no checkout original; implementar no branch limpo com TDD.
- Não iniciar código de navegação até completar e registrar toda a PHASE 0 observada na Área Restrita real. A descoberta deve preceder qualquer implementação dessa função.
- Ainda não foi feita validação real supervisionada nem login nesta sessão.

## Pendências e retomada

1. Continuar os Tasks 3–9 (preflight best-effort, leitor, filler, state machine e UI) em `codex/best-effort-form-filling`, com RED antes de cada correção, identidade fail-closed e valores divergentes preservados.
2. Fazer commits por tarefa conforme o plano e atualizar este handoff após cada bloco.
3. Criar branch de discovery a partir do `main` promovido; usar a sessão real da Área Restrita para concluir PHASE 0 e commitar somente a nota de discovery antes de qualquer código de navegação.
4. A partir do commit de discovery, criar a branch de navegação; integrar nela os commits Best-Effort/v4 sem perder a ordem de base exigida pelos planos.
5. Executar todas as suítes, `verify-project.ps1`, `git diff --check`, validações reais supervisionadas, revisão final e push das branches.

## GitHub

- `main`: promoção publicada e verificada em `b1d41e8`.
- Branch de implementação: local em `.worktrees/atos-tce-baseline`; commits de feature ainda pendentes.
