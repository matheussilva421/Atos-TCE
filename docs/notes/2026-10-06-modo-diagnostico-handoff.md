# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: Tasks 1 e 2 concluídas, commitadas, verificadas e enviadas ao upstream;
falta commit/push desta atualização do handoff; Task 3 pendente.

## Objetivo e limites

Implementar o Modo Diagnóstico leve, ON por padrão e iniciado automaticamente,
conforme `goal-objective.md`. A timeline deve correlacionar Mesa, extensão,
heartbeat, portal/formulário, current-selection, preflight, comandos, escrita,
readback e resultado; marcar `SLOW`; aparecer na Mesa; permitir pausa, retomada,
limpeza e ZIP; limitar retenção; e excluir credenciais utilizáveis.

O diagnóstico só observa. Não alterar identity resolution, qualification,
capability gates, decisão de fill, AR-1/AR-2/AR-3 nem envio manual. Não registrar
na timeline de reliability nem adicionar telemetria nova ao SQLite ou resultados
funcionais.

## Estado Git verificado

- Branch: `codex/area-restrita-reliability-reset`.
- Base da implementação: `67f0c9ec453c99cdd184c6ff8030ae6db0ecfdcc`.
- Milestone documental (especificação/plano/handoff): `10c1c8e`, enviado ao
  upstream. Task 1: `0dfedf1`, implementada, testada e enviada ao upstream.
- Task 2: commit `d111eab` criado, validado e enviado ao upstream.
- Manter checkout atual: branch prevista pelo projeto, sincronizada e sem código
  local pré-existente; não há necessidade de churn de branch/worktree.
- Builder antigo `AR1_BUILD=88eed8ce...` não serve para esta mudança. O pacote
  final será reconstruído somente depois do commit final.

## Descobertas e decisões

- Produção portátil fica em `app/`, `extension/`, `tests/`, `packaging/` e
  `scripts/`; `work/tce-extractor/` é legado/verificador.
- `reliability.py` valida um ledger estrito de qualification; manter intocado.
- current-selection integral é transitório; enviar somente os campos
  explicitamente permitidos ao recorder.
- API/ciclo de vida em `app/api/server.py`; integração de escrita em
  `app/area_restrita/fill_service.py`; extensão em
  `extension/background/router.js` e `extension/content/fill-form.js`; UI em
  `app/web/`.
- Builder já inclui `app/` e `extension/` automaticamente.
- Usar um recorder local separado, sessões UUID por boot, settings persistente
  com `diagnostic_enabled: true`, pause transitório, allowlist/redação,
  threshold de 2.000 ms, cinco sessões e trim de 8 MiB para 6 MiB.
- Eventos diagnósticos da extensão via sidecar `diagnostic_events` nos payloads
  existentes; servidor remove o sidecar antes da validação/serviço/persistência
  funcional. Heartbeat atualiza idade em memória em cada poll e é persistido na
  timeline só no primeiro, mudança ou intervalo de 10 s.
- A especificação refinou este turno os limites entre telemetria nova e o campo
  structural `diagnostics` que já existe em FillService, a rota de eventos da
  Mesa e a amostragem de heartbeat.
- Task 2 adicionou rotas Mesa autenticadas de status/controle/evento/export,
  registro de current-selection e ingestão/remoção do sidecar antes da
  validação funcional. FillService registra preflight e resultado fora do
  reliability/SQLite; falhas do recorder são fail-open.
- O status agregado conserva último comando/resultado/erro mesmo após heartbeat.
  `portal_state` só indica `OK` quando current-selection está `MATCHED`; sem
  formulário mostra `NO_ACTIVE_FORM`.
- A continuação explícita do objetivo foi interpretada como autorização para
  executar a arquitetura pragmática documentada e o plano, sem nova pausa para
  aprovação intermediária.

## Arquivos e marcos

- Especificação: `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md`.
- Plano TDD de cinco tarefas: `docs/superpowers/plans/2026-10-06-modo-diagnostico.md`.
- Este handoff deve acompanhar cada bloco significativo.
- Task 2 alterou `app/api/server.py`, `app/area_restrita/fill_service.py` e
  `app/area_restrita/diagnostics.py`; adicionou cobertura em
  `tests/test_api_server.py`, `tests/test_fill_service.py` e
  `tests/test_area_restrita_diagnostics.py`, com pequeno ajuste no plano.
- Ledger de execução: `.superpowers/sdd/2026-10-06-modo-diagnostico/progress.md`
  (ignorado pelo Git conforme convenção do SDD).
- O helper SDD não iniciou no host (erro MSYS `NtCreateDirectoryObject`, acesso
  negado). A estrutura de diretório e marker foram preparados manualmente no
  mesmo caminho convencional; a implementação segue no checkout do projeto.

## Testes e validação

- RED confirmado antes de criar o módulo: `ModuleNotFoundError` para
  `app.area_restrita.diagnostics` nos testes novos.
- `python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -q`:
  Task 1: 10 testes, 10 passaram, 0 falharam; Task 2: 11 testes, 11 passaram,
  0 falharam. Inclui limite de linha de evento,
  cookies/header aninhado, pause transitório através de restart, sessão ativa
  completa em `ultima-sessao.json` e plataforma/versão em `ambiente.json`.
- RED→GREEN do status: os testes novos falharam primeiro pela ausência dos
  campos `last_command`/`last_result`/`last_error` e status incorreto do portal;
  após implementação, recorder 11/11 e teste API de status 1/1 passaram.
- `python -m unittest tests.test_fill_service -q`: 109 testes, 109 passaram,
  0 falharam.
- `python -m unittest tests.test_api_server -q` (loopback local autorizado):
  152 testes, 152 passaram, 0 falharam.
- `git diff --check` passou após a implementação da Task 2.
- Baseline JS: `npm test --prefix extension` — 263/263; `node --test
  app/web/tests/*.test.mjs` — 65/65.
- Baseline focada com `%TEMP%` dentro de `tmp/`: `test_fill_service.py` 106/106
  e `test_area_restrita_reliability.py` 57/57.
- Baseline `test_api_server.py`: 141 testes, 145 erros e 1 falha; causas
  ambientais observadas: bloqueio de loopback (`WinError 10013`) e hard links
  negados. Sem a variável `%TEMP%` redirecionada, testes Python também falham
  por ACL negada no temp sandbox do sistema.
- Suíte Python raiz inicial: 875 testes, 11 falhas e 1.375 erros; saída extensa
  majoritariamente por permissões de temp, loopback/hard link e smoke do pacote
  legado. Contrato de pacote baseline: 20 testes, 5 falhas e 43 erros, incluindo
  ZIP negado em `%TEMP%` e runtime Python extraído que não iniciou. Reexecutar
  gates com temp em `tmp/` e distinguir restrições de sandbox das falhas reais.
- `git diff --check` passou no código desta tarefa.
- Smoke sintético, Task 3–5, suíte Python raiz final, extensão/web, contrato do
  pacote, verificador legado, CI e ZIP novo continuam pendentes.

## GitHub

- Commits `10c1c8e`, `0dfedf1` e `d111eab` estão enviados ao upstream. Este
  registro do push será commitado em seguida.

## Retomada imediata

1. Commitar e enviar esta atualização do handoff; verificar branch sincronizada.
2. Executar Task 3–5 do plano com testes sintéticos/offline; preservar os
   fluxos funcionais.
3. Reexecutar suítes com `%TEMP%` sob `tmp/` e, quando loopback/hard links forem
   bloqueados pelo sandbox, usar CI como gate do runtime. Corrigir qualquer
   falha de produto reproduzível.
4. Após gates e commit final sincronizado, reconstruir e verificar ZIP, registrar
   SHA/build ID/contagem de testes/CI e estado final neste handoff.
