# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: Task 1 concluída (recorder local); Task 2 pendente.

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
  upstream. O código de Task 1 está implementado e testado, aguardando commit.
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
- A continuação explícita do objetivo foi interpretada como autorização para
  executar a arquitetura pragmática documentada e o plano, sem nova pausa para
  aprovação intermediária.

## Arquivos e marcos

- Especificação: `docs/superpowers/specs/2026-10-06-modo-diagnostico-design.md`.
- Plano TDD de cinco tarefas: `docs/superpowers/plans/2026-10-06-modo-diagnostico.md`.
- Este handoff deve acompanhar cada bloco significativo.
- Ledger de execução: `.superpowers/sdd/2026-10-06-modo-diagnostico/progress.md`
  (ignorado pelo Git conforme convenção do SDD).
- O helper SDD não iniciou no host (erro MSYS `NtCreateDirectoryObject`, acesso
  negado). A estrutura de diretório e marker foram preparados manualmente no
  mesmo caminho convencional; a implementação segue no checkout do projeto.

## Testes e validação

- RED confirmado antes de criar o módulo: `ModuleNotFoundError` para
  `app.area_restrita.diagnostics` nos testes novos.
- `python -m unittest discover -s tests -p 'test_area_restrita_diagnostics.py' -q`:
  10 testes, 10 passaram, 0 falharam. Inclui limite de linha de evento,
  cookies/header aninhado, pause transitório através de restart, sessão ativa
  completa em `ultima-sessao.json` e plataforma/versão em `ambiente.json`.
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
- Smoke, integração com APIs, gates finais, verificador legado, CI e ZIP novo
  continuam pendentes.

## GitHub

- Commit documental `10c1c8e` está no upstream.
- Task 1 será commitada e enviada como milestone independente, junto deste
  handoff atualizado.

## Retomada imediata

1. Revisar/commitar `diagnostics.py`, seu teste, e este handoff; enviar ao
   upstream e confirmar SHA/status.
2. Task 2: adicionar testes RED para rotas autenticadas, sidecar de resultado,
   current-selection e integração opcional do FillService; implementar
   fail-open sem alterar reliability/SQLite/resultado funcional.
3. Atualizar este handoff e o ledger por milestone; commitar/enviar cada tarefa.
4. Executar Task 3–5 do plano com testes sintéticos/offline; preservar os
   fluxos funcionais.
5. Reexecutar suites com `%TEMP%` sob `tmp/` e, quando loopback/hard links forem
   bloqueados pelo sandbox, usar CI como gate do runtime. Corrigir qualquer
   falha de produto reproduzível.
6. Após gates e commit final sincronizado, reconstruir e verificar ZIP, registrar
   SHA/build ID/contagem de testes/CI e estado final neste handoff.
