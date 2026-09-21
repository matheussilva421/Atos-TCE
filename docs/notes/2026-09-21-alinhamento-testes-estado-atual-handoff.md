# Handoff — alinhamento dos testes ao trust automático da extensão

Data: 2026-09-21  
Branch: `codex/mesa-local-refactor`  
Base do bloco: `abef057`  
Commit final: `51591eb` (`test: align Mesa tests with automatic extension trust`)

## Resultado

Os testes derivados do plano `docs/superpowers/plans/2026-09-18-atos-tce-plano-completo.md`
foram alinhados ao estado atual da extensão e da Mesa. O helper de API agora
registra a extensão por `POST /api/v1/bridge/register`, usando a origem do ID
confiável do Manifest V3, em vez de inserir manualmente um token no SQLite com
uma origem fictícia. Os testes de rotas antigas continuam verificando que o
pareamento manual permanece aposentado.

O plano de 18/09 recebeu uma nota de supersessão para que seus trechos de
pareamento por código sejam tratados como histórico. O roteiro de execução
atualizado foi criado em
`docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md`.

## Arquivos alterados

- `tests/test_api_server.py`
- `tests/test_bridge.py`
- `tests/test_area_scan.py`
- `app/api/server.py`
- `app/core/store.py`
- `docs/superpowers/plans/2026-09-18-atos-tce-plano-completo.md`
- `docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md`
- este handoff

O arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py` foi preservado
fora do bloco.

## Testes executados

- `python -m unittest tests.test_api_server tests.test_bridge tests.test_area_scan -q`
  — 144/144 aprovados.
- `npm test --prefix extension` — 123/123 aprovados.
- `node --test app/web/tests/*.test.mjs` — 16/16 aprovados.
- `python -m unittest discover -s tests -p 'test_*.py' -q` — 559/559 aprovados.
- `verify-project.ps1` — 1.254 executados, 1.252 aprovados, 0 falhas e 2
  skips ambientais documentados.
- `git diff --check` — aprovado pelo gate oficial.

## Validação manual pendente

O guia inclui os comandos para reiniciar a Mesa, abrir o Chrome QA com perfil
isolado e carregar `extension/`. A validação física de perfil limpo, reconexão
após reinício do Chrome/Mesa, remoção do token pelo DevTools e confirmação
visual de `Mesa conectada` ainda precisa ser executada pelo operador.

M2 real (extensão contra CDP), M3 real (aquisição limitada), M5 real
(preenchimento supervisionado sem clique final) e M6 destrutivo continuam
`BLOCKED_HUMAN_PORTAL`. Nenhum fixture, teste automatizado, pacote ou auditoria
local fecha esses gates.

## Retomada

1. Leia `docs/notes/2026-09-21-guia-reexecucao-testes-mesa-local.md`.
2. Inicie a Mesa com `.\START.cmd --data-root data --port 18743 --no-browser`.
3. Abra o Chrome QA com o perfil separado e use a URL completa
   `/bootstrap#token=...` impressa pelo launcher.
4. Carregue somente `C:\Users\slvma\Downloads\Github\Atos-TCE\extension`.
5. Não use código de pareamento; confirme a reconexão automática.
