# SDD ledger — plan: docs/notes/2026-09-15-corrigir-achados-qa-plano.md

## Preflight

| tarefa/interface | produtor | consumidor | verificação/conflict scan |
|---|---|---|---|
| Task 1 / app files | empacotador | ZIP, auditor e menu | O menu exige `process_list.py` e `register_process_list.py`; o empacotador atual não os copia. Corrigir ambos no mesmo bloco. |
| Task 1 / binary policy | auditor | distribuição pública/privada | `.xlsx`/`.sqlite3` são necessários apenas em dados privados; a regra pública não pode herdá-los como allowlist global. |
| Task 2 / process identity | driver | manifest/eventos/downloader | O manifest depende do ID resolvido; fallback divergente é load-bearing e deve bloquear antes dos eventos. |
| Task 3 / scope | painel/controller/materializer | snapshot e preview | A automação geral já aceita dois escopos, mas análise e materialização estão fixadas em setor; propagar o escopo confirmado sem relaxar validação. |
| Task 3 / cardinalidade | content snapshot | fila/preview | Chaves de interessados podem repetir o processo; agrupar por processo para classificar como `AMBIGUO` não pode descartar itens distintos. |
| Task 4 / readiness | dataset/painel | `batch_scope` | Citação nominal não é por si só hash de documento/OCR; separar aquisição pendente de elegibilidade final. |
| Task 4 / confirmation | painel | serviço de lotes/aquisição | A confirmação modal já existe antes do download; não duplicar envio. Acrescentar somente evidência/estado necessário ao gate da prévia. |
| Task 5 / docs | código/testes | handoff/relatório/pacote | O handoff atual tem estado Git antigo; atualizar apenas depois de validar a implementação. |

### Rulings

- Ruling: trabalhar na `main` — o usuário autorizou explicitamente; custo se errado: alterações ficam no branch principal e precisam de rollback por commits.
- Ruling: usar `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md` como autoridade funcional e o plano de 15/09 como decomposição de correções — o plano original está na conversa, não em arquivo; custo se errado: algum detalhe de QA poderá exigir ajuste no final.
- Ruling: o fluxo de aquisição continua permitindo `acquisition_eligible` sem documento/OCR, mas `eligible` permanece bloqueado — isso é exatamente a distinção da especificação; custo se errado: impediria a coleta necessária.

## Status

- Base: `c84bced`.
- Pacote de referência: preservado.
- Task 1: fix round 1/5 (2 addressed, 0 open; commits 605834f..4b4d6a7).
- Task 1: complete (commits c84bced..4b4d6a7, review clean after focused re-review).
- Task 2: complete (commits d00938e..ee5c6ae; review clean after focused re-review; 2 P2 addressed).
- Task 3: complete (commits 409461c..20e6b8f; initial review P1 addressed in fix round; re-review approved).
- Task 4: complete (commits 395c89e..499fb34; review P1/P2 fix rounds approved by LUNA; residuals closed).
- Task 5: conteúdo concluído em `74646b6`; documentação em `7062766`, `8d3716d` e `c5dff4a`; correção P1 em `e899dcb`; push realizado com sucesso para `https://github.com/matheussilva421/Atos-TCE.git` no intervalo `c84bced..e899dcb`.
- Task 5: cadeia documental real confirmada em `7062766`, `8d3716d` e `c5dff4a`, com `c5dff4a` como HEAD observado antes da correção P1; não atribuir conteúdo de teste a esses commits documentais.

## Task 5 — fechamento QA e regressão final (2026-09-15)

- Causa confirmada: após o Task 1, `package_audit.py` passou a exigir os quatro módulos de `app/` quando a árvore contém `app/`; dois fixtures do empacotador completo não incluíam `process_list.py` e `register_process_list.py`. Isso produzia `18 erros/118` no conjunto pacote/transferência.
- Correção mínima: somente `test_package_complete_archive.py` e `test_portable_end_to_end.py` foram ajustados para modelar o inventário autoritativo e verificar os dois membros no ZIP. Nenhum auditor, empacotador de produção, regra de privacidade ou dado real foi alterado.
- TDD: RED focado `1 erro` com `app_file_missing` esperado; GREEN focado `1/1`; regressão selecionada `118 executados, 115 pass, 0 falhas, 3 skips`.
- Gates já obtidos: extensão Node `389/389`; web `npm test` `6/6`; `Test-TcePortable.ps1` `136/136`; descoberta `-s portable` `6/6`, insuficiente como suíte completa.
- Python completo `python -m unittest discover -s . -p 'test_*.py' -q`: nova tentativa foi interrompida após aproximadamente 8 s por solicitação do usuário; resultado final não disponível e não será promovido a PASS.
- Auditoria/empacotamento: auditoria pública direta da referência foi interrompida por ser longa e já havia mostrado achados esperados de acervo privado; empacotamento físico permanece bloqueado pela ausência de `staging-task5-verified`/runtime verificado. Não tocar em `Versions`.
- Matriz final preservada: `PASS_REAL=0`, `PASS_PACKAGE=1`, `PASS_FIXTURE=24`, `FAIL_REPRODUCED=0`, `BLOCKED=5`, `NOT_TESTED=0`; nenhuma fixture ou teste local promoveu gate portal real.
- Handoff final: `docs/notes/2026-09-15-qa-final-handoff.md`.

## Correção P1 — conflito de identidade na execução/preparação (2026-09-15)

- Finding reproduzido no caminho `start()`/preparação: conflito da mesma tupla `(processKey, interestedNormalized)` era marcado em `areaObservations`, mas a identidade original ainda podia entrar na fila e chegar a `APPLY_FIELDS`.
- Correção mínima: `collectSnapshot()` bloqueia a observação conflitante antes do enfileiramento e remove uma ocorrência já enfileirada antes do congelamento. Análise, identidade ausente e fluxo sem conflito foram preservados; não houve alteração de envio/`auto_submit`.
- TDD: RED `1 falha` (`pending` 0 vs. 1); GREEN `1/1`; `automation-controller` `69/69`; Node completo da extensão `390/390`.
- Arquivos: `background/automation-controller.js`, `tests/automation-controller.test.mjs`, relatório Task 5 e handoff final.
- Status: correção commitada em `e899dcb` e publicada; `main` e `origin/main` foram verificadas alinhadas nesse SHA; `Versions/` permanece intocado.

## Verificação pós-push (2026-09-15)

- Remoto: `https://github.com/matheussilva421/Atos-TCE.git`.
- Push realizado com sucesso: `c84bced..e899dcb`.
- `git status --short --branch` foi verificado após o push e mostrou `main...origin/main` sem divergência; `HEAD` e `origin/main` estavam em `e899dcb`.
- Esta atualização é somente documental; testes, matriz e código não foram alterados.
