# Área Restrita Portal Lab — handoff incremental

**Data:** 2026-09-24  
**Branch:** `codex/atos-tce-unified`  
**Estado:** Tasks 1–3 publicadas; o gate de conexão MCP aguarda recarga do cliente. Task 4 workflow implementado e validado; commit/push pendente.

## Resumo

- Checkout revalidado limpo no início, em `c477026ce887cd4ac066b869d73e0e8049e8864d`, igual a `origin/codex/atos-tce-unified`.
- Os oito documentos obrigatórios do pacote foram lidos integralmente e na ordem indicada. O caminho de spec referenciado pelo plano de implementação não existe; foi usada a cópia de design incluída no pacote.
- Baseline: Python 616 testes (615 passaram, 1 skip); extensão 145/145; web 28/28; `verify-project.ps1` 1.259 executados (1.257 passaram, 0 falhas, 2 skips); `git diff --check` passou.
- Portal Lab Task 1: o teste RED mostrou que o verificador aceitava diretórios, capturas e nomes de ferramentas do laboratório em ZIPs. O verificador agora recusa essas entradas; `.gitignore` distingue fontes/fixtures sanitizadas de capturas raw; foi adicionado teste de fronteira runtime.
- Commit de implementação/contrato: `6d809dc` (`test: isolate portal lab from portable runtime`). O gate focado foi repetido após o commit e passou (15 testes, 1 skip).
- Portal Lab Task 2: criada inicialização de Chrome isolado e validação HTTP/CDP loopback. O perfil foi criado fora do repositório em `%LOCALAPPDATA%\Atos-TCE\Chrome-Debug`; Chrome PID 2800 permaneceu aberto. `netstat` confirmou `127.0.0.1:9222` em LISTENING, e o checker retornou `CDP_ENDPOINT_OK`.
- Commit Task 2: `777cab2` (`dev: add isolated Chrome portal lab`).
- Portal Lab Task 3: adicionados o exemplo MCP com `--browser-url=http://127.0.0.1:9222`, categoria de extensões e flags de privacidade, além da política L0/L1/L2. A entrada global já instalada foi atualizada, sem reinstalar o pacote; `codex mcp get chrome-devtools` confirmou todos os argumentos.
- Gate de conexão Task 3: as ferramentas MCP ativas continuaram ligadas a outro Chrome depois da atualização global. O marcador temporário em `about:blank` não apareceu em `/json/list` na porta 9222. A aba foi restaurada para `about:blank`; snapshot confirmou página vazia e network não encontrou requisições. Nenhum portal foi aberto.
- Commit Task 3 (artefatos locais): `298cac1` (`dev: configure safe Chrome DevTools MCP`).
- Portal Lab Task 4: instalado localmente o skill oficial do Playwright CLI (0.1.13) e criado workflow restrito. Attach CDP a `127.0.0.1:9222`, snapshot de `chrome://new-tab-page/` e `detach` passaram; o Chrome permaneceu aberto. A skill vendorizada em `.agents/skills/playwright-cli/` fica ignorada, assim como o snapshot `.playwright-cli/`.

## Arquivos alterados

- `.gitignore`
- `packaging/verify-package.ps1`
- `tests/test_packaging_contract.py`
- `tests/test_devtools_runtime_boundary.py`
- `scripts/portal-lab/Start-AtosChrome.ps1`
- `scripts/portal-lab/Test-CdpEndpoint.ps1`
- `devtools/area-restrita/README.md`
- `devtools/area-restrita/chrome-devtools-mcp.example.json`
- `.agents/skills/area-restrita/references/safety.md`
- `.agents/skills/area-restrita/references/workflow.md`
- `tests/test_devtools_runtime_boundary.py`
- `tests/test_portal_lab_contract.py`
- Este handoff.

## Testes e validações

- RED: `python -m unittest tests.test_packaging_contract.VerifierContractTests.test_rejects_portal_lab_and_agent_tool_artifacts -v` — falhou como esperado nos 7 casos; o verificador aceitou os artefatos.
- RED: `python -m unittest tests.test_devtools_runtime_boundary.RuntimeBoundaryTests.test_raw_capture_is_ignored_and_sanitized_lab_sources_are_trackable -v` — falhou como esperado porque as fixtures sanitizadas eram ignoradas.
- GREEN: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` — 15 executados, 14 passaram, 0 falhas, 1 skip.
- GREEN: `python -m unittest discover -s tests -p "test_*.py" -q` — 619 executados, 618 passaram, 0 falhas, 1 skip.
- Task 2 RED: `python -m unittest tests.test_portal_lab_contract -v` — após corrigir o fixture HTTP, 5 falharam porque os scripts ainda não existiam.
- Task 2 GREEN: `python -m unittest tests.test_portal_lab_contract -v` — 5 passaram.
- Task 2 Python completo: `python -m unittest discover -s tests -p "test_*.py" -q` — 624 executados, 623 passaram, 0 falhas, 1 skip.
- Gate completo: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; os 7 estágios passaram.
- Gate manual local: `Start-AtosChrome.ps1` iniciou o Chrome visível no perfil isolado; `Test-CdpEndpoint.ps1 -Port 9222` validou o endpoint; `netstat -ano -p tcp` confirmou bind em `127.0.0.1`.
- Task 4 RED: `python -m unittest tests.test_devtools_runtime_boundary.RuntimeBoundaryTests.test_raw_capture_is_ignored_and_sanitized_lab_sources_are_trackable -v` — falhou porque o skill vendorizado apareceu como untracked.
- Task 4 GREEN: o mesmo teste passou após ignorar `.agents/skills/playwright-cli/` sem ignorar a skill do projeto.
- Task 4 fronteira: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` — 15 executados, 14 passaram, 0 falhas, 1 skip (ZIP de distribuição não existe neste checkout).
- Task 4 manual: `playwright-cli -s=portal-lab-verify attach --cdp=http://127.0.0.1:9222`, snapshot de `chrome://new-tab-page/` e `detach` concluídos; nenhum acesso ao portal.
- Task 3 RED: `python -m unittest tests.test_portal_lab_contract.McpConfigContractTests -v` — 2 testes falharam porque o exemplo e a política ainda não existiam.
- Task 3 GREEN: `python -m unittest tests.test_portal_lab_contract -v` — 7 passaram.
- Task 3 Python completo: `python -m unittest discover -s tests -p "test_*.py" -q` — 626 executados, 625 passaram, 0 falhas, 1 skip.
- Gate completo: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; os 7 estágios passaram.
- O runtime de `app/`, `extension/` e `START.cmd` não ganhou dependência do laboratório. Nenhum código de navegação/preenchimento foi alterado.

## Ambiente de laboratório observado

- Chrome instalado: `153.0.8010.53`.
- `playwright-cli` disponível, versão `0.1.13`.
- Ferramentas Chrome DevTools MCP, incluindo `install_extension` e `list_extensions`, aparecem nesta sessão.
- Chrome dedicado continua aberto: PID 2800; a porta responde em `127.0.0.1:9222`.
- Playwright CLI 0.1.13 e skill local instalados; snapshot gerado está em caminho `.playwright-cli/` ignorado pelo Git.
- O MCP DevTools está instalado e enabled. A configuração global foi atualizada; o processo de ferramentas já carregado nesta sessão ainda não adotou o novo alvo. O shell isolado usa `CodexSandboxOffline`; consultas à configuração global do usuário exigem elevação.
- Não houve login, observação do portal real, preenchimento ou clique final.

## Decisões

- O verificador de ZIP bloqueia `.agents`, `devtools`, `.playwright-cli`, `node_modules`, `tmp/portal-lab`, e nomes `chrome-devtools-mcp`/`playwright-cli` em qualquer caminho.
- O teste textual de dependência varre apenas os componentes distribuídos (`app/`, `extension/`, `START.cmd`). `packaging/` é verificado por comportamento, pois precisa conter os nomes proibidos para rejeitá-los.
- A configuração global do MCP usa `--browser-url=http://127.0.0.1:9222`, `--categoryExtensions`, `--no-usage-statistics` e `--no-performance-crux`; Chrome 153 atende ao requisito de versão indicado pelo CLI instalado.
- A skill Playwright fornecida inclui comandos genéricos de cookies/storage/close/kill; para o Portal Lab prevalece o workflow local restrito, que proíbe esses comandos e usa `detach`.
- `.agents/skills/playwright-cli/` é uma instalação local do fornecedor, ignorada no Git; a skill/referências próprias em `.agents/skills/area-restrita/` continuam versionáveis.
- Trabalho permanece na branch canônica solicitada; nenhum branch paralelo foi criado.
- As ferramentas MCP desta sessão ainda apontam para outro Chrome mesmo após editar a configuração. Reiniciar/reconectar o cliente MCP e repetir a prova do alvo antes de qualquer login.

## GitHub

- No início: branch sincronizada com `origin/codex/atos-tce-unified` em `c477026`.
- Até Task 2, `6d809dc`, `f0354f8`, `777cab2`, `9d5a248` e `03afec2` estavam publicados em `origin/codex/atos-tce-unified`.
- `298cac1`, `d95b228` e `c3b2f42` estão publicados; HEAD local/remoto estava em `c3b2f42` antes das mudanças da Task 4.
- Arquivos Task 4 e atualização deste handoff aguardam commit/push.

## Pendências e retomada

1. Commitar/publicar Task 4 e este handoff.
2. Recarregar o cliente MCP e provar que as ferramentas estão ligadas a `127.0.0.1:9222`; não iniciar login enquanto essa prova falhar.
3. Prosseguir Tasks 5–7: captura estrutural, sanitizador, comparador, portal-contract/fixtures e skill.
4. Só depois dos gates do laboratório abrir sessão supervisionada; concluir Best-Effort Task 10 e Phase 0 com observações reais antes de qualquer código de Próximo processo.

Nenhum login, submit, envio, finalize ou clique final foi automatizado. Chrome dedicado PID 2800 continua aberto para as tarefas seguintes. Runtime standalone e gates finais continuam pendentes.
