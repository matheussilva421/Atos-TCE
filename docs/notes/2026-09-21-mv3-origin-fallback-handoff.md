# Handoff — autenticação do service worker MV3 sem Origin (2026-09-21)

## Resumo

O Chrome QA mostrava Conectando à Mesa... mesmo com token e cliente
registrados. A captura real do DevTools confirmou GET /api/v1/bridge/status
com Authorization e X-TCE-Client, mas sem Origin, retornando 401.

## Causa raiz

O servidor derivava o ID da extensão exclusivamente de Origin. O Chromium
pode omitir esse cabeçalho na requisição real feita pelo service worker MV3 para
o loopback. O token estava correto no SQLite, mas a validação recusava a
requisição antes de consultar o estado pareado.

## Correção

- extension/lib/api.js envia X-TCE-Extension-ID em todas as chamadas usando
  chrome.runtime.id; o ID fica injetável nos testes.
- app/api/server.py permite o fallback somente quando Origin está ausente e
  o cabeçalho contém exatamente TRUSTED_EXTENSION_ID.
- O servidor reconstrói a origem confiável apenas nesse caso e ainda exige o
  bearer e X-TCE-Client registrados; origem inválida ou ID não confiável
  continuam recusados.
- O preflight CORS anuncia o novo cabeçalho.
- README e o guia de reexecução registram o comportamento atual.

## Arquivos alterados

- app/api/server.py
- extension/lib/api.js
- extension/tests/api.test.mjs
- tests/test_bridge.py
- README.md
- docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md
- docs/notes/2026-09-18-code-review-remediation.md
- este handoff

O arquivo local não rastreado work/tce-extractor/.codex-live-pilot.py foi
preservado e não faz parte deste bloco.

## Validação

- RED antes da correção: chamada sem Origin retornou 401; o novo teste da
  extensão não encontrou X-TCE-Extension-ID.
- GREEN focado: node --test extension/tests/api.test.mjs — 13/13;
  python -m unittest tests.test_bridge — 25/25.
- Suíte da extensão: npm test --prefix extension — 124/124.
- Suíte web: node --test app/web/tests/*.test.mjs — 16/16.
- Suíte Python da Mesa: python -m unittest discover -s tests -p 'test_*.py' -q
  — 561/561.
- Gate oficial: powershell.exe -NoLogo -NoProfile -NonInteractive
  -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 —
  1.254 verificações, 1.252 aprovadas, 0 falhas e 2 skips ambientais.
- git diff --check — verde.

## Validação manual pendente

Depois de atualizar a extensão no Chrome QA, reinicie a Mesa para carregar o
servidor alterado:

~~~powershell
Set-Location 'C:\Users\slvma\Downloads\Github\Atos-TCE'
git switch codex/mesa-local-refactor
git pull --ff-only origin codex/mesa-local-refactor
.\START.cmd --data-root data --port 18743 --no-browser
~~~

Na janela do Chrome QA, abra chrome://extensions, clique em Atualizar na
extensão carregada de C:\Users\slvma\Downloads\Github\Atos-TCE\extension e
reabra o painel lateral. O estado esperado é Mesa conectada sem código de
pareamento. Não copie bearer, cookie ou URL de sessão para o log.

Como o token apareceu nas capturas de DevTools, remova uma vez
tce.bridge.token pelo console do service worker após atualizar a extensão;
ela emitirá um token local novo automaticamente.

M2, M3, M5 e M6 continuam dependendo da execução humana no portal e não são
fechados por estes testes automatizados.

## GitHub e retomada

- Branch: codex/mesa-local-refactor.
- Gate oficial concluído.
- Commit publicado: e204049 (fix: authenticate MV3 service worker status requests).
- Remote atualizado: origin/codex/mesa-local-refactor contém e204049.
- Retomar pelo comando de validação manual acima e pelo guia
  docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md.
