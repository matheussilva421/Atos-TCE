# Fundamentação Legal v3 — validação R2 (2026-09-17)

Escopo: evidência automatizada e local da correção `legal-foundation-v3` na worktree
`C:\Users\slvma\Downloads\Github\Atos-TCE\.worktrees\fundamento-legal-v3-r2`
mais o roteiro do smoke real supervisionado. O smoke no portal autenticado continua
pendente de operador humano (login manual + marcador selecionado manualmente).

## Ambiente

| Item | Valor |
|---|---|
| Worktree | `.worktrees/fundamento-legal-v3-r2`, detached HEAD |
| Base | `fd827da` (`origin/main`, contém `fa90605192d4ade824e0f71efbc45cfc4b34c588`) |
| Commits | `b8bc3f1`, `2345c4c`, `cb3e374`, `20f498c`, `a509405`, `45907f3`, `0fea2ee`, `e1c4c0d`, `3a8ee63` |
| Regras | `legal-foundation-v3` (extração `legal-context-v4` preservada) |
| Serviço local | `RULES_VERSION = legal-foundation-v3` |

## Comandos e resultados

| Comando | Resultado |
|---|---|
| `node --test` (extensão) três vezes | 455 passaram / 0 falharam em cada execução |
| `python -m unittest discover -s . -p 'test_*.py' -q` | 525 executados, 9 skip, 0 falhas |
| `verify-project.ps1` | 7 estágios verdes, 1218 passed / 0 failed (2 skips) |
| `git diff --check` | limpo (estágio `diff` do verificador) |

## Diagnóstico das três execuções de referência (ambiente automatizado)

Os três atos exigidos pelo plano foram reproduzidos no harness integrado
(`tests/panel.test.mjs`, `tests/legal-foundation.test.mjs`) com o catálogo cru do
portal e o worker real. Nenhum dado privado foi registrado: apenas rótulos públicos
do catálogo e números de regra.

| # | Ato | rules_version | context_status / source | decision_state | method | confidence | margin | class_id | writeAllowed |
|---|---|---|---|---|---|---|---|---|---|
| 1 | ECE/RN 20/2020 art. 7º, professor, transição | legal-foundation-v3 | sidecar / cache | AUTO_SELECTED | similarity (crosswalk ECE20) | 0.98 | 0.98 | EC41_TRANSITION_GENERAL | true |
| 2 | EC41 arts. 6/7 com ECE20 art. 2º como preservação | legal-foundation-v3 | sidecar / cache | AUTO_SELECTED | rule (estrutural) | 0.98 | 0.98 | EC41_TRANSITION_GENERAL | true |
| 3 | Contexto ausente / evidência insuficiente | legal-foundation-v3 | blocked / null | CONTEXT_BLOCKED (motivo `DOCUMENT_EVIDENCE_MISSING`) | none | 0 | 0 | null | false |

Observação de higiene: nos casos 1 e 2 o rótulo proposto é o do catálogo histórico
(`Civil - Artigo 6º ... EC 41/2003 c/c EC 47/2005`); o caso Maria-like nunca propõe
`EC 20/1998` art. 8º.

## Pré-condições verificadas antes do smoke

- `acervo-tce/automacao/execucoes.sqlite3` (aberto somente leitura):
  `runs=0`, `items=0`, `events=0`, `run_creation_requests=0`, `commands=0`,
  `confirmed_acts=0`, `confirmed_identity_history=0`. Nenhuma execução ou comando
  pendente a reconciliar antes do smoke.
- `work/tce-extractor/.codex-live-pilot.py` não existe neste checkout e não está
  rastreado (`git ls-files` sem saída). O helper local continua fora do Git.
- O worktree não contém `acervo-tce/` (dados privados). O smoke real precisa da
  raiz do projeto principal ou de uma cópia operacional liberada pelo operador.

## Roteiro do smoke real supervisionado (pendente de execução humana)

1. No portal autenticado: login manual, seleção manual do marcador vigente,
   campo opcional `#automation-marker` vazio e lista autenticada visível.
2. Confirmar que a automação captura `snapshot.marker` e trava o valor já
   selecionado; nenhum `filter_marker` deve ser enviado para reproduzir o marcador.
3. Cobrir três atos: (i) ECE/RN 20/2020 art. 7º professor em transição;
   (ii) EC41 arts. 6/7 com ECE20 art. 2º como preservação; (iii) um caso não-AUTO
   (`REVIEW_REQUIRED`, `TRUE_TIE` ou `CONTEXT_BLOCKED`).
4. Registrar, por ato, somente: `rules_version`, `context_status`, `context_source`,
   `resolution_status`, `decision_state`, `method`, `confidence`, `margin`,
   `class_id`, rótulo sanitizado da opção, `writeAllowed` e rótulo sanitizado do
   marcador. Nunca registrar CPF, matrícula, cookies, tokens ou HTML privado.
5. Executar “Preencher campos disponíveis” sob supervisão. Nos AUTO, reler o
   `<select>` e exigir valor idêntico a `legalDecision.option_value`. No caso
   não-AUTO, o fundamento não muda e os demais campos elegíveis podem ser preenchidos.
6. Este smoke valida preenchimento/seleção. Envio/finalização real continua sujeito
   às travas existentes (`autoSubmit=false`, `real_send_enabled=false`, 3 preflights
   reais + observador) e a uma autorização explícita e separada.

## Limitações ambientais

- Sem portal autenticado, sem Playwright logado e sem `acervo-tce/` neste worktree,
  o smoke real não pode ser executado por automação. Os itens correspondentes do
  Final Acceptance Checklist ficam como pendentes de evidência humana.
- O pacote portátil não foi regenerado nesta validação; a extração limpa e o
  `TESTAR-PACOTE.ps1` seguem como gate de empacotamento do projeto.
