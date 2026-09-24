# Área Restrita Portal Lab — handoff incremental

**Data:** 2026-09-24  
**Branch:** `codex/atos-tce-unified`  
**Estado:** baseline concluída; Portal Lab Task 1 validada, commitada e publicada. Implementação `6d809dc`; handoff `f0354f8`.

## Resumo

- Checkout revalidado limpo no início, em `c477026ce887cd4ac066b869d73e0e8049e8864d`, igual a `origin/codex/atos-tce-unified`.
- Os oito documentos obrigatórios do pacote foram lidos integralmente e na ordem indicada. O caminho de spec referenciado pelo plano de implementação não existe; foi usada a cópia de design incluída no pacote.
- Baseline: Python 616 testes (615 passaram, 1 skip); extensão 145/145; web 28/28; `verify-project.ps1` 1.259 executados (1.257 passaram, 0 falhas, 2 skips); `git diff --check` passou.
- Portal Lab Task 1: o teste RED mostrou que o verificador aceitava diretórios, capturas e nomes de ferramentas do laboratório em ZIPs. O verificador agora recusa essas entradas; `.gitignore` distingue fontes/fixtures sanitizadas de capturas raw; foi adicionado teste de fronteira runtime.
- Commit de implementação/contrato: `6d809dc` (`test: isolate portal lab from portable runtime`). O gate focado foi repetido após o commit e passou (15 testes, 1 skip).

## Arquivos alterados

- `.gitignore`
- `packaging/verify-package.ps1`
- `tests/test_packaging_contract.py`
- `tests/test_devtools_runtime_boundary.py`
- Este handoff.

## Testes e validações

- RED: `python -m unittest tests.test_packaging_contract.VerifierContractTests.test_rejects_portal_lab_and_agent_tool_artifacts -v` — falhou como esperado nos 7 casos; o verificador aceitou os artefatos.
- RED: `python -m unittest tests.test_devtools_runtime_boundary.RuntimeBoundaryTests.test_raw_capture_is_ignored_and_sanitized_lab_sources_are_trackable -v` — falhou como esperado porque as fixtures sanitizadas eram ignoradas.
- GREEN: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` — 15 executados, 14 passaram, 0 falhas, 1 skip.
- GREEN: `python -m unittest discover -s tests -p "test_*.py" -q` — 619 executados, 618 passaram, 0 falhas, 1 skip.
- O runtime de `app/`, `extension/` e `START.cmd` não ganhou dependência do laboratório. Nenhum código de navegação/preenchimento foi alterado.

## Ambiente de laboratório observado

- Chrome instalado: `153.0.8010.53`.
- `playwright-cli` disponível, versão `0.1.13`.
- Ferramentas Chrome DevTools MCP, incluindo `install_extension` e `list_extensions`, aparecem nesta sessão.
- A porta `127.0.0.1:9222` estava fechada na verificação inicial. Ainda não foi iniciado Chrome dedicado nem verificada uma conexão MCP/Playwright ao mesmo browser.
- Não houve login, observação de portal real, preenchimento ou clique final nesta etapa.

## Decisões

- O verificador de ZIP bloqueia `.agents`, `devtools`, `.playwright-cli`, `node_modules`, `tmp/portal-lab`, e nomes `chrome-devtools-mcp`/`playwright-cli` em qualquer caminho.
- O teste textual de dependência varre apenas os componentes distribuídos (`app/`, `extension/`, `START.cmd`). `packaging/` é verificado por comportamento, pois precisa conter os nomes proibidos para rejeitá-los.
- O plano de exemplo MCP será alinhado a `--browser-url=http://127.0.0.1:9222`, `--categoryExtensions`, `--no-usage-statistics` e `--no-performance-crux`; Chrome 153 atende ao requisito de versão indicado pelo CLI instalado.
- Trabalho permanece na branch canônica solicitada; nenhum branch paralelo foi criado.

## GitHub

- No início: branch sincronizada com `origin/codex/atos-tce-unified` em `c477026`.
- `6d809dc` e `f0354f8` estão publicados em `origin/codex/atos-tce-unified`; HEAD remoto confirmado em `f0354f8b7efb5ca63fa6d4cbe5f98b27c6be900b`.

## Pendências e retomada

1. Executar Task 2 com teste RED/GREEN: Chrome dedicado, perfil externo em `%LOCALAPPDATA%`, CDP limitado a `127.0.0.1`, sem fechar Chrome pessoal nem remover perfil.
2. Atualizar/verificar configuração MCP para conexão ao Chrome dedicado; `playwright-cli` já está instalado.
3. Prosseguir Tasks 4–7: workflow CLI, captura estrutural, sanitizador, comparador, portal-contract/fixtures e skill.
4. Só depois dos gates do laboratório abrir sessão supervisionada; concluir Best-Effort Task 10 e Phase 0 com observações reais antes de qualquer código de Próximo processo.

Nenhum submit, envio, finalize ou clique final foi automatizado. Runtime standalone e gates finais continuam pendentes.
