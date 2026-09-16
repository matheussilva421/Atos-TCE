# Consolidação da main — 16/09/2026

## Resumo

A branch `codex/fundamentacao-professores-crosswalk-v2` foi integrada à
`main` após a atualização da `main` com `origin/main`. O único conflito foi um
`add/add` no plano jurídico de professores. Foi preservada a versão detalhada
já existente na `main`, pois ela contém o plano completo; a versão da branch
era um resumo redundante.

Também foi corrigido o teste do empacotador da extensão para incluir os três
módulos legais v2 que já estavam na allowlist do empacotador:
`legal-reference-parser-v2.js`, `retirement-legal-profile.js` e
`portal-legal-crosswalk.js`.

## Validação

No resultado mesclado, passaram:

- extensão: 406;
- web: 6;
- Python portátil: 6;
- documentação: 19;
- menu: 91;
- reset: 31;
- verificador de projeto: 43;
- testes portáteis: 136;
- limpeza de workspace: 307;
- contratos de pacote: 79, com 2 skips ambientais;
- `git diff --check` e `git diff --cached --check`, sem diagnóstico.

Nenhum teste de portal autenticado, coleta, complementação ou envio foi
executado durante a consolidação.

## GitHub e estado final

O merge foi publicado na `main` no commit `ac8cb6a`. A única branch local e
remota mantida é `main`, alinhada com `origin/main`; a worktree
`.worktrees/fundamentacao-professores-crosswalk-v2` e a branch de trabalho
foram removidas após a confirmação de que todos os commits estavam contidos
na `main`.

Última verificação: árvore de trabalho limpa, `main...origin/main = 0 0`,
`2260266` contido na `main` e `git ls-remote --heads origin` retornando apenas
`refs/heads/main`.
