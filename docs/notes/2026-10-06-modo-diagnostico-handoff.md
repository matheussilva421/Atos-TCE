# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: implementação iniciada; plano TDD definido; Task 1 (recorder local) pendente de RED.

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
- Base da implementação: `67f0c9ec453c99cdd184c6ff8030ae6db0ecfdcc` (`HEAD` igual
  ao upstream antes deste milestone documental).
- Código de produção sem alterações. A revisão da especificação e o plano estão
  sendo preparados para commit antes do primeiro teste RED.
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

- Ainda não foram executados testes de produto nem smoke; nenhum código foi
  alterado.
- Próximo gate: criar primeiro os testes do `DiagnosticRecorder`, executar o
  teste de startup esperado RED e então implementar o mínimo para GREEN.
- A suíte completa, smoke sintético, gates de empacotamento/verificador legado,
  CI e ZIP novo permanecem pendentes.

## GitHub

- Commits de especificação/handoff/plano e progresso serão enviados ao upstream
  desta branch por marcos.
- Nenhum push da implementação ocorreu ainda.

## Retomada imediata

1. Confirmar commit e push do milestone documental e árvore limpa.
2. Task 1: criar `tests/test_area_restrita_diagnostics.py` primeiro; executar os
   comandos RED do plano; implementar `app/area_restrita/diagnostics.py` em
   incrementos de startup/schema, privacidade, controles/retention/export.
3. Após cada tarefa, executar gates focados, atualizar este handoff e o ledger,
   commitar e enviar.
4. Executar Task 2–5 do plano; preservar os fluxos funcionais e testar somente
   com fixtures/smoke offline.
5. Após gates e commit final sincronizado, reconstruir e verificar ZIP, registrar
   SHA/build ID/contagem de testes/CI e estado final neste handoff.
