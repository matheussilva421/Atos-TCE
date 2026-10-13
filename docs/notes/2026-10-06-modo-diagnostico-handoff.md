# Handoff — Modo Diagnóstico sempre ativo

Data: 2026-10-06  
Status: Tasks 1–4 concluídas, commitadas, verificadas e enviadas ao upstream.
Task 5: smoke, gates da fonte atual, CI e ZIP novo concluídos. O verificador
legado local ainda encerra no probe de PID; a interação com o probe Python 3.14
foi reproduzida, mas não alterada. Este handoff final acompanha o commit de
documentação que fecha o pacote.

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
- Task 3: commit `9a4e1b1` criado, validado e enviado ao upstream.
- Task 4: commit `2d3b2ea` criado, validado e enviado ao upstream.
- Task 5: smoke harness `scripts/portal-lab/diagnostics-smoke.py` criado e
  executado em diretório temporário; 14/14 verificações passaram. O smoke cobre
  form detect lento (4800 ms), `FORM_NOT_AVAILABLE`, `STALE_FORM`, FILL_FORM
  correlacionado com write/readback, `COMMAND_TIMEOUT`, seis membros exatos,
  build/versão/capabilities e ausência de sentinel de segredo. Nenhum portal,
  Chrome, dado de produção ou credencial foi usado.
- Commit `b9417151fa7ada3204cd2d28514e9ce5ae20c464` enviado ao upstream. ZIP novo
  `dist/Atos-TCE-diagnostic.zip`: 96.232.000 bytes, 526 entradas, 430 arquivos
  de runtime, build ID correspondente ao commit e SHA-256
  `3594cf46ea9de442e36695d00600a20960442677196a309376c144dc6727ebb5`.
  `verify-package.ps1` e seu health smoke passaram. A harness em
  `scripts/portal-lab/` é ferramenta de desenvolvimento e não é copiada pelo
  builder; `app/area_restrita/diagnostics.py` e os demais fontes de produção
  estão no ZIP. Sidecar `.sha256` criado e conferido.
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
- Task 3 acrescentou `monotonicNow` injetável, tempos de `portal_detected`,
  `frames_scanned` e `form_detected`, sidecar sibling no current-selection,
  recebimento/execução de comandos e tempos `field_write`/`field_reread` por
  campo. O servidor existente remove o sidecar antes da lógica funcional;
  `field_results` e o resultado retornado pelo poll mantêm seu formato.
- Task 4 adiciona painel responsivo de diagnóstico à Mesa, refresh inicial e
  em cada ciclo existente de cinco segundos, pausa/retomada/limpeza, export sob
  o nome retornado pelo servidor e registro fail-open de timeout em análise da
  Área Restrita, preenchimento e próximo ato. Códigos atuais do formulário e da
  seleção são expostos por duas chaves aditivas de `diagnostic_status()`, usando
  somente `portal_selection.public_state()` sanitizado. A URL blob do ZIP é
  revogada após breve atraso para permitir que o navegador consuma o download.
- O teste da UI revelou que `diagnostic_status()` fornecia o estado da seleção,
  mas não o código (`FORM_NOT_AVAILABLE`) necessário ao painel. Foi adicionada
  cobertura RED em `tests/test_api_server.py` antes de acrescentar
  `form_code`/`current_selection_code`; identidade, capacidade e seleção
  funcional não foram alteradas.
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
- Task 3 alterou `extension/background/router.js` e
  `extension/content/fill-form.js`, com cobertura em
  `extension/tests/router.test.mjs` e `extension/tests/fill-form.test.mjs`.
- Task 4 alterou `app/api/server.py`, `tests/test_api_server.py`,
  `app/web/index.html`, `app/web/app.js`, `app/web/app.css`, testes web de boot
  e wiring, e `LEIA-ME-OUTRO-PC.txt`.
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
- `node --test extension/tests/fill-form.test.mjs extension/tests/router.test.mjs`:
  121 testes, 121 passaram, 0 falharam. Inclui RED→GREEN de observação, sidecar,
  comando e tempos de escrita/readback.
- `npm test --prefix extension`: 267 testes, 267 passaram, 0 falharam.
- Task 4 RED: `node --test app/web/tests/app-boot.test.mjs
  app/web/tests/ui-wiring.test.mjs` falhou antes do painel em quatro
  verificações de boot/render/rotas; o teste da API falhou pela ausência de
  `form_code`. Após a implementação, o foco web passou 40/40 e
  `node --test app/web/tests/*.test.mjs` passou 69/69. Na revisão, um teste
  adicional falhou ao exigir a revogação adiada da URL blob; após a correção,
  a suíte web completa passou novamente 69/69.
- API após a alteração do status: `python -m unittest discover -s tests -p
  'test_api_server.py' -q` passou 153/153. A primeira solicitação de execução
  foi interrompida antes de iniciar por desconexão temporária do serviço de
  revisão automática; a repetição iniciou e concluiu normalmente.
- `git diff --check` passou antes do commit das Tasks 2 e 3.
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
  ZIP negado em `%TEMP%` e runtime Python extraído que não iniciou. Os reruns
  atuais constam abaixo e passaram com o diretório temporário externo autorizado;
  esses números iniciais não representam o estado final.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: 901 testes,
  901 passaram, 0 falharam. Executado elevado com `%TEMP%`/`%TMP%` no diretório
  temporário externo autorizado; sem essa configuração, o host negava a
  resolução de caminhos do Python.
- `npm test --prefix extension`: 267 testes, 267 passaram, 0 falharam.
- `node --test app/web/tests/*.test.mjs`: 69 testes, 69 passaram, 0 falharam.
- `python -m unittest tests.test_packaging_contract -q`: 20 testes,
  20 passaram, 0 falharam; elevado e com temporário externo autorizado.
- `python scripts/portal-lab/diagnostics-smoke.py`: 14/14 verificações
  passaram. O teste é sintético/offline e usa `TemporaryDirectory`.
- `Test-PortableReset.ps1`: 31/31; `Test-QAChromeLauncher.ps1`: 11/11;
  `Test-TcePortable.ps1`: 143/143; `Test-WorkspaceCleanup.ps1`: 307/307.
  `Test-DocumentationTracking.ps1` e `Test-PortableMenu.ps1` também passaram
  no verificador agregado (20 e 100 verificações, respectivamente).
- `work/tce-extractor/verify-project.ps1`: executado elevado com Python
  empacotado no PATH; termina com código 1 após os primeiros três testes
  PowerShell (20, 100 e 31 passaram). `Test-ProjectVerification.ps1`, também
  executado isoladamente, imprime 23 `PASS` e encerra antes da verificação de
  PID/resumo, sem mensagem de falha. O rerun em TTY teve o mesmo resultado. A
  reprodução direta de `python.exe -c 'import os; os.kill(os.getpid(), 0); ...'`
  imprimiu o marcador Python, mas o PowerShell invocador saiu com código 1 sem
  executar a instrução seguinte; a falha está localizada na interação do probe
  Python 3.14 com o processo/console do runner, sem alteração da árvore legada.
  `Test-QAChromeLauncher.ps1`,
  `Test-TcePortable.ps1` e `Test-WorkspaceCleanup.ps1` passaram isoladamente.
  A causa interna do encerramento do runner permanece aberta; a árvore legada
  não foi alterada.
- Build novo: `packaging/build-portable.ps1 -OutputPath
  .\dist\Atos-TCE-diagnostic.zip -Force`; build ID `b9417151fa7ada3204cd2d28514e9ce5ae20c464`,
  526 entradas e runtime fixado reutilizado após verificação.
- Verificação: `packaging/verify-package.ps1 -ZipPath
  .\dist\Atos-TCE-diagnostic.zip -ExpectedBuildId b9417151fa7ada3204cd2d28514e9ce5ae20c464`;
  passou com health `ok`, runtime build ID igual ao commit e extensão `0.1.0`.
  O manifesto/contrato do ZIP foi validado; fontes diagnósticos esperados
  presentes e nenhum caminho proibido.
- Independente `Get-FileHash -Algorithm SHA256` e
  `dist/Atos-TCE-diagnostic.zip.sha256`: ambos
  `3594cf46ea9de442e36695d00600a20960442677196a309376c144dc6727ebb5`;
  tamanho 96.232.000 bytes.
- GitHub Actions [Mesa Local offline gates, run #294](https://github.com/matheussilva421/Atos-TCE/actions/runs/37476855907):
  `Offline gates (Windows)` concluído com sucesso para o SHA `b941715`.
  O workflow executa as suítes Python raiz, extensão, web, contrato do pacote e
  `git diff --check`; não executa o verificador legado.
- `git diff --check`: passou após o smoke final.
- Única ressalva: `Test-ProjectVerification.ps1` não chega ao resumo por
  interrupção no probe de PID, inclusive em TTY. Os gates atuais da raiz e o CI
  passaram; a pipeline do GitHub não inclui esse verificador legado.

## GitHub

- Commits `10c1c8e`, `0dfedf1`, `d111eab`, `9a4e1b1`, `2d3b2ea`, `9a5ea59` e
  `b941715` estão enviados ao upstream. `b941715` é o SHA do código de runtime
  e do pacote; este commit subsequente atualiza somente o handoff/plano. A
  branch será conferida limpa e sincronizada após este commit.

## Retomada imediata

1. O único follow-up opcional é investigar o runner legado em outro host que
   consiga executar o probe de PID sem interromper o processo de teste. Não
   alterar a árvore legada sem causa reproduzida.
2. Confirmar o commit desta atualização sincronizado e a árvore limpa.
3. `dist/Atos-TCE-diagnostic.zip` foi reconstruído do zero e verificado para o
   SHA de runtime `b941715`; não reutilizar ZIP antigo. Smoke é sintético e não
   demonstra qualificação no portal real nem habilita envio automático.
