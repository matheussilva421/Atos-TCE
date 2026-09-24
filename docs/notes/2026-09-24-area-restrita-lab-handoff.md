# Área Restrita Portal Lab — handoff incremental

**Data:** 2026-09-24  
**Branch:** `codex/atos-tce-unified`  
**Estado:** Tasks 1–7 publicadas em `origin/codex/atos-tce-unified`. Task 8 está em andamento: Mesa autenticada no Chrome QA e scan real via extensão salvo com 27 itens (24 concluídos, 3 pendentes); a lista completa informada pelo portal tem 1.197 itens e ainda não foi reconciliada. Best-Effort Task 10 e Next Process Phase 0 seguem abertos; Tasks 9–12 e Próximo Processo não foram implementadas nesta retomada.

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
- Commit Task 4: `1a5250b` (`docs: define Playwright portal investigation workflow`).
- Portal Lab Task 5: criados `capture-structure.js`, `sanitize-capture.py` e `compare-captures.py`. A captura não lê `.value`; o sanitizador usa allowlist, remove query strings/segredos, classifica texto e rejeita CPF/processo/token residual, inclusive processo percent-encoded; o comparador sanitiza ambos os arquivos e gera deltas estruturais determinísticos.
- Portal Lab Task 6: criado o contrato versionado, JSON Schema e quatro fixtures com identidade fictícia. A paridade cobre os papéis emitidos pelo scanner, sentinelas de formulário, rotas/fontes existentes, frame irmão e a separação entre tela de botões e formulário. Nenhuma suposição de comportamento foi adicionada ao runtime.
- Portal Lab Task 7: criado o skill `area-restrita` com sequência obrigatória A–M, limites L0/L1/L2/L3, regra contra timeout-first e dono único de seletores; criado `portal-states.md` e atualizadas as referências de segurança e workflow.
- Os três testes de pressão foram repetidos após a mudança: timeout sem predicado estrutural foi bloqueado; frame/radio ambíguo parou em L0 e confirmou `extension/lib/area-snapshot.js` como dono único; clique final e leitura de corpo de resposta foram recusados, mantendo o clique manual com o operador.
- Conexão MCP/CDP provada nesta sessão: o Chrome isolado foi iniciado como PID 2272, o checker confirmou `127.0.0.1:9222`, e um marcador `about:blank` temporário apareceu em `mcp__chrome_devtools__list_pages` e em `/json/list` do endpoint local. A aba de prova foi fechada; restou só a nova guia.
- Task 8 preflight: a origem canônica em `extension/lib/protocol.js` respondeu `401` ao GET de `/`; o Chrome mostrou `ERR_INVALID_AUTH_CREDENTIALS`. Só metadados de rede foram inspecionados; nenhum header/corpo foi lido, nenhuma credencial foi fornecida e nenhuma transição do portal foi executada. A janela dedicada foi trazida à frente para a operadora.
- Task 8 L0 após o login informado pelo operador: página atual `/telaPrincipalMenu.asp`, `readyState=complete`. Captura estrutural recursiva confirmou quatro frames diretos e nove documentos/frame no total; a lista já estava carregada em `/SISTEMAS/Processo/ProcessonoSetor.asp` e o frame irmão de botões em `/botoesNOVO.asp`. A lista tinha 482 controles estruturais (110 hidden; valores nunca lidos) e o frame de botões 17 botões; nenhuma interação foi executada.
- A baseline da página reportou 198 requests (197 GET, 1 OPTIONS; 196 status 200, 1 status 204, 1 status 206). Console: 7 linhas, 5 IDs de mensagem; não foi feita classificação de erro. Snapshot de acessibilidade: 1.023 linhas e 987 tokens `uid`; conteúdo bruto não foi exibido nem salvo no handoff.
- Sanitização: `python .\scripts\portal-lab\sanitize-capture.py .\tmp\portal-lab\2026-09-24-task8-l0\raw\menu-structure.json .\tmp\portal-lab\2026-09-24-task8-l0\sanitized\menu-structure-verified.json` terminou com código 0; arquivo sanitizado local de 4.263 bytes. Capturas locais permanecem ignoradas pelo Git.
- `portal-contract.json` e fixtures não foram alterados: as rotas observadas já constam no contrato; uma sessão não confirma sentinelas/seletores novos. A paridade existente passou 7/7. Interessado e formulário não estão na árvore atual; abrir Complementar Ato é L1 e não foi feito nesta etapa.

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
- `scripts/portal-lab/capture-structure.js`
- `scripts/portal-lab/sanitize-capture.py`
- `scripts/portal-lab/compare-captures.py`
- `tests/test_portal_lab_contract.py`
- `devtools/area-restrita/portal-contract.schema.json`
- `devtools/area-restrita/portal-contract.json`
- `devtools/area-restrita/fixtures/list-page.json`
- `devtools/area-restrita/fixtures/interested.json`
- `devtools/area-restrita/fixtures/form.json`
- `devtools/area-restrita/fixtures/buttons.json`
- `extension/tests/portal-contract.test.mjs`
- `.agents/skills/area-restrita/SKILL.md`
- `.agents/skills/area-restrita/references/portal-states.md`
- `.agents/skills/area-restrita/references/safety.md`
- `.agents/skills/area-restrita/references/workflow.md`
- `docs/notes/2026-09-24-area-restrita-lab-handoff.md`
- `.superpowers/sdd/2026-09-24-area-restrita-reverse-engineering-plan/progress.md`
- Este handoff.

## Testes e validações

- RED: `python -m unittest tests.test_packaging_contract.VerifierContractTests.test_rejects_portal_lab_and_agent_tool_artifacts -v` — falhou como esperado nos 7 casos; o verificador aceitou os artefatos.
- RED: `python -m unittest tests.test_devtools_runtime_boundary.RuntimeBoundaryTests.test_raw_capture_is_ignored_and_sanitized_lab_sources_are_trackable -v` — falhou como esperado porque as fixtures sanitizadas eram ignoradas.
- GREEN: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` — 15 executados, 14 passaram, 0 falhas, 1 skip.
- GREEN: `python -m unittest discover -s tests -p "test_*.py" -q` — 619 executados, 618 passaram, 0 falhas, 1 skip.
- Task 8 gate integrado: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; os 7 estágios passaram. `git diff --check` passou.
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
- Task 5 RED inicial: 5 contratos falharam porque os três utilitários ainda não existiam. REDs adicionais apontaram que o comparador omitiria conteúdo de frames novos, o sanitizador sobrescrevia saída existente e o scanner não detectava processo percent-encoded; todos foram corrigidos.
- Task 5 GREEN: `python -m unittest tests.test_portal_lab_contract -v` — 13 testes passaram; o caso percent-encoded também passou após a correção.
- Task 5 Python completo: `python -m unittest discover -s tests -p "test_*.py" -q` — 632 executados, 631 passaram, 0 falhas, 1 skip.
- Gate completo final: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; todos os sete estágios passaram.
- Não houve captura de portal real; os testes usam valores sintéticos, Node VM e arquivos temporários.
- O runtime de `app/`, `extension/` e `START.cmd` não ganhou dependência do laboratório. Nenhum código de navegação/preenchimento foi alterado.
- Task 6 RED: `node --test extension/tests/portal-contract.test.mjs` — 7 falharam inicialmente pela ausência do contrato, schema e fixtures.
- Task 6 GREEN: o mesmo comando — 7 passaram, incluindo paridade dos papéis, sentinelas e distinção FORM/BUTTONS.
- Task 6 extensão completa: `npm test --prefix extension` — 152 executados, 152 passaram, 0 falhas.
- Task 6 Portal Lab: `python -m unittest tests.test_portal_lab_contract -v` — 13 passaram, 0 falhas.
- Task 6 Python completo da raiz: `python -m unittest discover -s tests -p "test_*.py" -q` — 632 executados, 631 passaram, 0 falhas, 1 skip.
- Gate integrado: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; todos os sete estágios passaram.
- Task 7 gate focado: `python -m unittest tests.test_devtools_runtime_boundary tests.test_packaging_contract -v` — 15 executados, 14 passaram, 0 falhas, 1 skip (ZIP portátil ausente neste checkout).
- Task 7 gate integrado: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falhas, 2 skips; todos os sete estágios passaram.
- Skill pressure tests: baseline independente de três cenários encontrou lacunas em timeout-first e ownership de seletores; após a mudança, 3/3 cenários passaram com as decisões seguras esperadas. Nenhum avaliador abriu browser nem alterou arquivos.
- Conexão MCP/CDP: `Start-AtosChrome.ps1` iniciou PID 2272 no perfil `%LOCALAPPDATA%\Atos-TCE\Chrome-Debug`; `Test-CdpEndpoint.ps1 -Port 9222` passou e o marcador temporário foi encontrado nos dois lados e removido.
- Preflight do portal: GET à origem canônica terminou em `ERR_INVALID_AUTH_CREDENTIALS`; metadados MCP mostraram um GET com status 401. Causa específica não confirmada; nenhuma tentativa de fornecer ou recuperar credenciais foi feita.
- Task 8 sanitize: `python .\scripts\portal-lab\sanitize-capture.py .\tmp\portal-lab\2026-09-24-task8-l0\raw\menu-structure.json .\tmp\portal-lab\2026-09-24-task8-l0\sanitized\menu-structure-verified.json` — exit 0, saída de 4.263 bytes.
- Task 8 paridade: `Push-Location extension; node --test tests/portal-contract.test.mjs; Pop-Location` — 7 testes, 7 passaram, 0 falhas, 0 skips.
- Task 8 L0: leitura de páginas/frames, rede, console e snapshot concluída sem interação. Não houve captura de screenshot nem escrita de valores de formulário.

## Ambiente de laboratório observado

- Chrome instalado: `153.0.8010.53`.
- `playwright-cli` disponível, versão `0.1.13`.
- Ferramentas Chrome DevTools MCP, incluindo `install_extension` e `list_extensions`, aparecem nesta sessão.
- Chrome dedicado iniciado nesta retomada: PID 2272; perfil `%LOCALAPPDATA%\Atos-TCE\Chrome-Debug`; a porta responde em `127.0.0.1:9222`.
- Playwright CLI 0.1.13 e skill local instalados; snapshot gerado está em caminho `.playwright-cli/` ignorado pelo Git.
- O MCP DevTools já estava instalado e ativo; não foi reinstalado. As ferramentas MCP do app conectaram ao CDP alvo e a correspondência foi provada pelo marcador. `codex mcp get chrome-devtools` não encontra esse nome no registro do CLI, embora as ferramentas estejam disponíveis nesta sessão.
- Não houve login, observação do portal real, preenchimento ou clique final.

## Decisões

- O verificador de ZIP bloqueia `.agents`, `devtools`, `.playwright-cli`, `node_modules`, `tmp/portal-lab`, e nomes `chrome-devtools-mcp`/`playwright-cli` em qualquer caminho.
- O teste textual de dependência varre apenas os componentes distribuídos (`app/`, `extension/`, `START.cmd`). `packaging/` é verificado por comportamento, pois precisa conter os nomes proibidos para rejeitá-los.
- A configuração global do MCP usa `--browser-url=http://127.0.0.1:9222`, `--categoryExtensions`, `--no-usage-statistics` e `--no-performance-crux`; Chrome 153 atende ao requisito de versão indicado pelo CLI instalado.
- A skill Playwright fornecida inclui comandos genéricos de cookies/storage/close/kill; para o Portal Lab prevalece o workflow local restrito, que proíbe esses comandos e usa `detach`.
- `portal-contract.json` é oráculo documental/de teste, não configuração de runtime. `transitioning` e `ambiguous` são vocabulário permitido, mas não são emitidos pelo scanner atual.
- `.agents/skills/playwright-cli/` é uma instalação local do fornecedor, ignorada no Git; a skill/referências próprias em `.agents/skills/area-restrita/` continuam versionáveis.
- Trabalho permanece na branch canônica solicitada; nenhum branch paralelo foi criado.
- O launcher iniciou o perfil dedicado depois de o endpoint estar inativo; a conexão atual foi provada no mesmo CDP. Repetir a prova do alvo se o Chrome ou a sessão MCP forem reiniciados.

## GitHub

- No início: branch sincronizada com `origin/codex/atos-tce-unified` em `c477026`.
- Até Task 2, `6d809dc`, `f0354f8`, `777cab2`, `9d5a248` e `03afec2` estavam publicados em `origin/codex/atos-tce-unified`.
- `298cac1`, `d95b228` e `c3b2f42` estão publicados.
- `1a5250b`, `afd6fb4` e os fechamentos da Task 4 `022acee` estão publicados em `origin/codex/atos-tce-unified`; `022acee` era o HEAD local/remoto antes da Task 5.
- Task 5: implementação e testes validados no commit `c8cd3d0` (`dev: add sanitized portal structure capture`), com handoff `3fb664f`. Duas tentativas iniciais de push receberam `Internal Server Error`; a publicação foi aceita no push seguinte junto com Task 6.
- Task 6: contrato, schema, fixtures, teste de paridade e README publicados em `f9d62b4` (`test: codify Area Restrita portal contract`). `git status` confirmou checkout limpo e `git ls-remote` confirmou SHA `f9d62b4` no remoto.
- Task 7: commit `35ef33d5c14c6dcbb53fa334adac04ee08a3a967` (`dev: add Area Restrita reverse engineering skill`) publicado. `git ls-remote origin refs/heads/codex/atos-tce-unified` retornou o mesmo SHA.
- Task 8 L0 handoff: commit `90d61eb` (`docs: record authenticated portal L0 baseline`); `git push origin codex/atos-tce-unified` retornou sucesso e informou atualização `9598871..90d61eb`. O tracking local ficou em `90d61ebe989af59426cecba5deb5650b73fc445e`; duas consultas `git ls-remote` posteriores não conectaram à porta 443, então a SHA remota não pôde ser revalidada diretamente.

## Pendências e retomada

1. Task 8 L0 baseline está registrada; interessados/formulário não estavam abertos. Para continuar o mapeamento, o operador deve escolher um ato de teste autorizado. Depois, executar uma única transição L1 `LIST -> INTERESTED` conforme Task 9, capturar BEFORE/AFTER e não selecionar interessado nem preencher campos.
2. Não guardar ou enviar no chat número de processo, nome, CPF ou valores de campos. O alvo deve ser escolhido pelo operador; a extensão não escolhe uma linha por posição.
3. Prosseguir Tasks 9–12 em ordem; não implementar Próximo processo antes de Best-Effort Task 10 e Phase 0 estarem fechadas.
4. Para qualquer alteração de runtime, exigir captura real sanitizada, contrato/fixture e teste RED antes da implementação.

O login foi informado como manual pelo operador. Nenhum submit, envio, finalize ou clique final foi automatizado; nenhum campo foi preenchido. Chrome dedicado PID 2272 está em primeiro plano na página principal do portal. Runtime standalone e gates finais continuam pendentes.

## Atualização incremental — extensão instalada e fila segura (2026-09-24)

### Resumo e evidências

- O operador forneceu capturas do portal e do painel da extensão. A tela mostra a lista de processos com total 1.197; o painel mostra Área Restrita detectada e, após a Mesa subir, Mesa conectada. Nenhum identificador de processo ou nome foi copiado para este handoff.
- `chrome-devtools list_extensions` confirma `ATOS TCE — Ponte da Mesa` v0.1.0 habilitada no Chrome ligado ao CDP. A aba do portal e o service worker dessa extensão estão no mesmo Chrome DevTools alvo. Não reinstalar.
- Snapshot do side panel após iniciar o serviço: “Mesa conectada”, “Área Restrita detectada” e “Nenhum formulário de ato aberto”. Nenhum registro foi selecionado e nenhum formulário foi preenchido.
- Mesa em `127.0.0.1:18743`: `/api/v1/health` respondeu HTTP 200. O serviço permanece rodando, iniciado com o launcher normal; a abertura automática do dashboard ocorreu no navegador padrão e não apareceu como aba no alvo Chrome do MCP.
- Auditoria somente leitura de `data/atos-tce.db`: antes da inicialização, 22 comandos, sem `QUEUED` ou `CLAIMED` (3 `OPEN_ACT` e 14 `SCAN_AREA` falhos; 5 `SCAN_AREA` concluídos). Após a inicialização: 17 falhos, 5 concluídos, nenhum pendente/reivindicado; zero jobs `PENDING`/`RUNNING` e zero processos `ANALISANDO`.
- Nenhum `SCAN_AREA` novo foi enfileirado nesta retomada. A lista ainda não foi lida por uma varredura viva; o total 1.197 visto na captura ainda precisa ser reconciliado com a Mesa.

### Sessão e limite atual

- A extensão tem registro bearer próprio, mas a interface da Mesa usa sessão HttpOnly separada para ações que criam comandos. O painel conectado não prova que o dashboard no perfil CDP tem essa sessão.
- O launcher abriu o fluxo de bootstrap no navegador padrão; não foi possível confirmar essa sessão no perfil Chrome controlado pelo MCP.
- A revisão automática rejeitou, antes da execução, um helper que reiniciaria a Mesa e enviaria o token bootstrap temporário ao Chrome via endpoint CDP. Motivo informado: repasse de credencial fora da autorização expressa; a sessão deve ser autorizada diretamente pela interface. Nenhum helper foi criado; o agente não extraiu nem reutilizou o token (o launcher executou apenas seu bootstrap normal no navegador padrão), e nenhum reinício adicional ocorreu.

### Retomada

1. No navegador onde a Mesa abriu pelo launcher, abrir o dashboard local e concluir a sessão pela própria interface. Se a sessão já estiver aberta, usar o botão **Analisar Área Restrita** uma vez; esse comando apenas lê a página e persiste o snapshot local.
2. Avisar quando a análise terminar. Então verificar o resultado agregado e sanitizado na base local, sem expor conteúdo de processos; registrar marcador e contagens segundo a política do Portal Lab.
3. Continuar Task 8/9 em ordem. Não abrir ato, selecionar interessado, preencher campo ou clicar em ação final sem ato de teste autorizado pelo operador.

### Arquivos, validação e Git

- Fonte/runtime: nenhum arquivo alterado. A atualização deste documento será a única alteração versionada deste bloco. Logs de erro temporários ficam em `tmp/portal-lab/` (ignorados pelo Git); não contêm token na saída capturada.
- Testes: nenhum teste executado nesta retomada; não houve mudança de comportamento no código. A verificação do serviço, do side panel e da fila foi somente leitura.
- Git antes desta atualização: `codex/atos-tce-unified`, HEAD `47b25e9` (`docs: record portal lab push verification status`), sincronizado no tracking local com `origin/codex/atos-tce-unified`; revalidar status após o commit deste handoff.
- GitHub: pendente publicar o commit desta atualização; não afirmar push antes de verificar.


## Retomada — branch revalidada e baseline completa (2026-09-24)

### Evidência e testes

- Releitura integral do objetivo atual em `C:\Users\slvma\.codex\attachments\8a102f72-d19e-4bb7-8d65-90895d11475d\goal-objective.md` antes de prosseguir. O escopo completo permanece ativo.
- `git fetch origin codex/atos-tce-unified` confirmou o remoto no mesmo SHA local `7f2fe4c7707fe6a0bb65d238d2af581f80679f2b`; a branch canônica estava limpa antes desta atualização.
- `python -m unittest discover -s tests -p 'test_*.py' -q`: 632 executados, 631 passaram, 0 falharam, 1 skip.
- `npm test --prefix extension`: 152 executados, 152 passaram, 0 falharam, 0 skips.
- `node --test app/web/tests/*.test.mjs`: 28 executados, 28 passaram, 0 falharam, 0 skips. O Node emitiu aviso `MODULE_TYPELESS_PACKAGE_JSON` para `app/web/pdf-viewer.js`; os testes passaram.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1`: 7 estágios passaram; 1.259 executados, 1.257 passaram, 0 falharam, 2 skips. Inclui extensão (480), web (6), Python portable (6), PowerShell (603), pacote/auditoria (82, 2 skips), automação (81) e `git diff --check` (1).

### Estado externo revalidado

- A página autenticada permanece na rota principal do portal; o estado carregado tem quatro frames. Nenhuma linha foi aberta.
- O side panel da extensão mostra Mesa conectada, Área Restrita detectada e nenhum formulário aberto. Mesa health HTTP 200.
- Consulta SQLite em `mode=ro`: 0 comandos `QUEUED`/`CLAIMED`, 0 jobs `PENDING`/`RUNNING`, 0 processos `ANALISANDO`. Nenhuma varredura viva foi enfileirada.
- O browser que recebeu o bootstrap pelo launcher padrão não aparece nas abas que CUA ou Chrome DevTools MCP conseguem controlar. A sessão HttpOnly da Mesa nesse browser, portanto, não está demonstrada no perfil de laboratório do MCP.
- Nenhuma alteração em `app/`, `extension/` ou lógica de runtime. Nenhum teste real Best-Effort foi executado; não houve alvo de ato indicado.

### Bloqueios e retomada

- O auto-review rejeitou o transporte do token bootstrap para a aba DevTools por helper local; a tentativa foi rejeitada antes de executar e não será contornada. A sessão precisa ser concluída pela interface da Mesa no navegador que abriu pelo launcher.
- Próximo passo: no dashboard aberto pelo launcher, concluir/confirmar a sessão e acionar uma vez **Analisar Área Restrita**. Informar quando terminar para leitura agregada/sanitizada da varredura.
- Best-Effort Task 10 ainda exige os cinco casos jurídicos e o caso parcial supervisionados; operador também precisa indicar ato autorizado para observar interessado, formulário, retorno e resultado da conclusão manual. Não preencher nem acionar o clique final sem esse contexto.
- A implementação de Próximo processo permanece bloqueada até Task 10 e Phase 0 terem evidência real completa.

### Git

- Commit publicado anterior: `7f2fe4c` (`docs: record Mesa extension connection state`). Este adendo registra a baseline recém-executada; fazer commit/push e revalidar o SHA ao concluir este bloco.


## Retomada — confirmação da fronteira de sessão (2026-09-24)

- Foi aberto o dashboard local por uma aba CUA criada pelo agente, sem enviar token. O botão **Analisar Área Restrita** estava visível e habilitado; o clique normal pela interface respondeu `session_required`. Isso confirma que o perfil CUA/MCP não possui o cookie de sessão Mesa.
- Nenhum comando de extensão foi criado: consulta SQLite somente leitura confirmou 0 `QUEUED`/`CLAIMED`; o histórico `SCAN_AREA` permanece em 14 falhos e 5 concluídos. O serviço segue saudável (HTTP 200). A aba criada pelo agente foi fechada. Nenhum ato/formulário foi aberto.
- A interface que pode ter recebido a sessão pelo bootstrap automático é o navegador padrão aberto pelo launcher normal. Retomada manual: usar esse navegador/aba, não a aba do perfil de laboratório; se estiver autenticado, acionar **Analisar Área Restrita** uma vez e avisar quando terminar. Se aparecer `session_required`, parar e solicitar nova sessão pelo bootstrap oficial, sem transportar token via DevTools.
- Nenhuma alteração em código/runtime e nenhum teste adicional após a baseline verde registrada acima. `git diff --check` passou antes deste adendo.
- A branch continua em `codex/atos-tce-unified`. Fazer commit/push deste handoff e verificar SHA/status ao encerrar.


## Retomada — Portal Lab aguardando sessão Mesa oficial (2026-09-24)

- Foi tentada uma chamada DevTools direta ao handler de conteúdo `SCAN_PAGE`, com saída limitada a estrutura/contagens/marcador e destino local ignorado. O auto-review rejeitou antes da execução: leitura de página autenticada e gravação de captura fora do fluxo Mesa autenticado. A ferramenta determinou que a continuação use o workflow de scan autorizado pela sessão Mesa; nenhuma alternativa direta será tentada.
- Verificação posterior: health Mesa HTTP 200, 0 comandos `QUEUED`/`CLAIMED` e zero arquivos de captura bruta na nova pasta temporária. A recusa não gravou dados, não navegou o portal e não alterou a base.
- Único passo necessário para prosseguir: operador abrir a Mesa no navegador padrão iniciado pelo launcher, autorizar a sessão pela interface e acionar **Analisar Área Restrita** uma vez. A página portal permanece na rota principal autenticada; nenhum ato foi selecionado.
- Os gates automatizados completos continuam verdes conforme a atualização acima. Task 10 real, `SCAN_PAGE` via Mesa, reconciliação 1.198/1.197, Phase 0 e Next Process permanecem incompletos.
- Fazer commit e push deste registro, depois conferir `git status` e SHA remoto.


## Retomada — MCP 9222 ativo, sessão Mesa ainda ausente (2026-09-24)

- O objetivo em `goal-objective.md` foi relido antes de continuar. Branch canônica confirmada: `codex/atos-tce-unified`; HEAD e `origin` estavam em `c2f22b753304bf140349943cf6d5f267bf67ce89` no início deste bloco.
- Chrome DevTools MCP responde ao Chrome dedicado em `127.0.0.1:9222` (Chrome 153). A lista de páginas contém a aba autenticada do portal, o painel da extensão e o service worker da extensão. `list_extensions` confirma `ATOS TCE — Ponte da Mesa` v0.1.0 habilitada. Não reinstalar.
- O serviço Mesa responde HTTP 200 em `/api/v1/health`. O painel informa “Mesa conectada”, “Área Restrita detectada” e nenhum formulário aberto. **Abrir Mesa** pelo painel abriu o dashboard no mesmo Chrome.
- O dashboard exibe os totais salvos do último scan, mas indica que não foi analisado nesta sessão. A primeira tentativa de clique expirou; auditoria confirmou que não havia criado comando nem scan. Após selecionar a aba e atualizar o alvo de acessibilidade, o clique no botão oficial **Analisar Área Restrita** foi aceito e a interface respondeu `session_required`.
- Auditoria SQLite somente leitura após a tentativa: sem comandos `QUEUED`/`CLAIMED`, sem jobs `PENDING`/`RUNNING` e sem processos `ANALISANDO`; permanecem 5 scans históricos. O scan mais recente continua sendo o antigo, com 1.198 vistos (482 precisam complementar, 716 já complementados). Nenhum scan novo foi salvo. A captura do operador mostra 1.197 na lista; o delta permanece sem reconciliação. Nenhum marcador vivo foi confirmado.
- Não foi aberto processo, formulário ou interessado; nenhum campo foi preenchido e nenhum clique final ocorreu. Nenhuma captura bruta nova foi criada neste bloco e nenhum dado pessoal foi copiado para o handoff.
- Nenhum arquivo de runtime foi alterado e nenhum teste foi executado neste bloco. A baseline verde anterior continua sendo a última baseline; `git diff --check` passou nesta atualização. Commit/push deste adendo ainda pendentes.

### Retomada necessária

- O login do portal e a sessão da Mesa são estados separados. Para prosseguir, o operador deve usar a janela/perfil de navegador em que o launcher oficial da Mesa abriu o bootstrap e confirmar que a Mesa restaura a sessão nesse perfil. Depois, acionar **Analisar Área Restrita** uma vez no dashboard dessa mesma sessão e informar quando concluir.
- Não usar **Copiar sessão para outro Chrome**, não extrair/repassar token e não chamar diretamente o handler da extensão. Se a sessão oficial tiver expirado, iniciar novamente o launcher normal e concluir o bootstrap no navegador que ele abrir.
- Após confirmação do operador, verificar apenas agregados da nova varredura, registrar o marcador sem alterá-lo e continuar Task 8/9. Best-Effort Task 10 ainda requer os cinco casos reais e um ato de teste escolhido pelo operador; Next Process continua bloqueado até Task 10 e Phase 0 completos.


## Retomada — bootstrap da Mesa no Chrome QA (2026-09-24)

- O Chrome DevTools MCP em `127.0.0.1:9222` mostra a aba autenticada da Área Restrita, a Mesa Local e a extensão `ATOS TCE — Ponte da Mesa` habilitada no mesmo Chrome QA. A Mesa respondia HTTP 200, mas a interface indicava `session_required`: a sessão da Mesa é própria e não é herdada do login do portal.
- Auditoria somente leitura antes do reinício: SQLite `integrity_check=ok`; 0 jobs `PENDING`/`RUNNING`, 0 processos `ANALISANDO` e 0 comandos de extensão ativos. Permanecem 2 jobs `INTERRUPTED` com 1.273 itens `QUEUED`; esses estados históricos foram preservados.
- O processo anterior da Mesa foi encerrado e o servidor oficial foi iniciado de novo com `python -m app.main --data-root data --no-browser`, numa janela PowerShell visível. Health voltou a HTTP 200, schema v7, 1.232 processos. A sessão ainda não foi estabelecida na aba QA.
- O auto-review rejeitou o encaminhamento automatizado do token de bootstrap ao Chrome QA por script. A execução rejeitada não criou helper ou log transitório. Não contornar o bloqueio; o operador deve copiar localmente o URL de uso único da janela da Mesa para a barra de endereço do Chrome QA, sem enviá-lo no chat. Não usar `Copiar sessão para outro Chrome` nem ler/copiar cookies ou credenciais do portal.
- Nenhum código/runtime foi alterado; não foram executados testes. A validação após reinício foi health HTTP 200 e `sessionRequired=true` na aba da Mesa. O portal permaneceu na própria aba autenticada; nenhum ato foi aberto.

### Retomada necessária

- Operador: colar localmente o URL mostrado pela janela PowerShell na barra de endereço do Chrome QA e aguardar o retorno ao dashboard da Mesa.
- Depois da confirmação, verificar a sessão sem capturar dados pessoais, acionar uma vez **Analisar Área Restrita** pela interface oficial (ação de leitura autorizada) e conferir somente contagens agregadas. Continuar a reconciliação 1.198/1.197 e as fases pendentes do objetivo.
- O servidor está em execução na porta 18743. GitHub: commit `b931487` publicado na branch `codex/atos-tce-unified`; nesta retomada não houve alteração de código nem testes.

## Retomada — launcher Mesa no Chrome QA (2026-09-24)

- Diagnóstico confirmado: `app.main` abre o bootstrap de uso único com `webbrowser.open`, que delega ao navegador padrão do Windows. O login da Área Restrita e o cookie da Mesa são separados; páginas criadas no Chrome MCP não recebiam a sessão própria da Mesa.
- Adicionado `scripts/portal-lab/launch_mesa_in_qa_chrome.py`, ferramenta somente de desenvolvimento. Pré-valida CDP e WebSocket em loopback; substitui no processo da Mesa apenas a abertura do navegador e cria uma aba no Chrome QA usando o endpoint local `/json/new`. O alvo permitido é somente `http://127.0.0.1:<porta>/bootstrap#token=...`. A mensagem e erros não imprimem o token. Runtime e pacote portátil inalterados.
- TDD: três testes novos foram primeiro executados em RED pela ausência do launcher; após implementação, os três passaram. Regressão focada `python -m unittest tests.test_portal_lab_contract -v`: 16 executados, 16 passaram, 0 falhas. `py_compile` e `--help` passaram.
- Validação manual em banco descartável: o launcher abriu a URL de bootstrap no Chrome conectado ao CDP e a página foi redirecionada para o dashboard local, comprovando que a sessão foi aceita. A aba de smoke foi fechada, o processo/porta temporária não ficou ativo e o diretório temporário criado para o smoke foi removido com verificação do caminho.
- Rechecagem somente leitura do banco real: `PRAGMA integrity_check=ok`; a consulta de estados não encontrou jobs ou comandos ativos. As filas e jobs históricos foram preservados. No momento da verificação, não havia processo escutando em `18743`; nenhum serviço real foi encerrado por este bloco.
- Arquivos deste bloco: `scripts/portal-lab/launch_mesa_in_qa_chrome.py` (novo), `tests/test_portal_lab_contract.py`, `devtools/area-restrita/README.md` e este handoff. Nenhum código em `app/`, `extension/` ou runtime portátil foi alterado.
- Gates amplos ainda pendentes: suíte Python completa e `verify-project.ps1`; `git diff --check` passou após a integração documental.
- Próxima retomada: executar os gates; iniciar a Mesa real com `python .\\scripts\\portal-lab\\launch_mesa_in_qa_chrome.py --cdp-url http://127.0.0.1:9222 -- --data-root data --host 127.0.0.1 --port 18743`; verificar a nova aba do Chrome QA sem expor token ou dados pessoais; confirmar sessão da Mesa; então acionar uma vez **Analisar Área Restrita** e conferir somente contagens/estado agregado.
- Plano maior: Task 8 está em progresso; Task 9 e Task 10 reais e Next Process Phase 0 ainda precisam cumprir seus gates na ordem do plano. Próximo Processo não deve ser implementado antes de Task 10 e Phase 0 completos. Conclusão final da ação no portal continua manual.
- GitHub: implementação ainda sem commit/push; publicar somente após os gates e validar SHA remoto.


## Retomada — bootstrap, tab ativo e scan real (2026-09-24)

- Lido o objetivo solicitado em `C:\\Users\\slvma\\.codex\\attachments\\82e0b0b9-0d4e-4973-90a4-5794b6d71a3e\\goal-objective.md`; ele mantém as fases Best-Effort Task 10 + Phase 0 antes da implementação de Próximo Processo.
- O helper `scripts/portal-lab/launch_mesa_in_qa_chrome.py` foi integrado. Diagnóstico operacional: o primeiro bootstrap encontrou dois processos escutando em `127.0.0.1:18743`; o antigo respondeu ao token novo e retornou 401. Uma verificação via `Get-NetTCPConnection` havia sido negada e ocultada por `-ErrorAction SilentlyContinue`; `netstat -ano` mostrou os dois listeners. O processo antigo foi encerrado.
- Antes de reiniciar o processo novo que ainda falhava, foi criado backup SQLite consistente em `%TEMP%\Atos-TCE-Mesa-restart-safety-20260924.db` (`PRAGMA integrity_check=ok`, 15.130.624 bytes); o processo helper foi encerrado à força após `taskkill` normal ser recusado pelo Windows. O DB em `data/atos-tce.db` passou novamente em `integrity_check`; remover o backup temporário próprio após confirmar estabilidade final.
- Após confirmar zero listeners, o helper iniciou uma única Mesa na porta 18743 e o Chrome QA abriu o bootstrap em nova aba; a aba foi redirecionada para `/`, sem token na URL final. A Área Restrita permaneceu no mesmo Chrome. O launcher imprimiu somente mensagem sanitizada.
- A primeira ação oficial **Analisar Área Restrita** falhou porque a aba Mesa ficou ativa e a extensão não encontrou aba autenticada. A mensagem registrada foi classificada como `Nenhuma aba autenticada da Área Restrita está aberta.`; não houve scan salvo. Com a aba do portal ativa, o botão da Mesa foi acionado uma vez em background, mantendo o portal ativo, e o comando `SCAN_AREA` terminou `SUCCEEDED`.
- Evidência agregada do scan mais recente: origem `extension`, escopo `sector_finalistic`, 27 linhas únicas, 24 concluídas, 3 pendentes, 0 ambíguas/bloqueadas/não encontradas; a contagem não alcança os 1.197 itens informados na lista e, portanto, o delta com os 1.198 itens salvos continua aberto. A causa da paginação limitada ainda não foi observada; não afirmar scan completo. O marcador ativo foi retornado pela própria extensão sem alteração; o valor bruto permanece somente no artefato ignorado `tmp/portal-lab/2026-09-24-task8-live-scan/marker-private.json`, nunca no Git/handoff.
- SQLite permanece íntegro e não há jobs/comandos ativos após o scan. Nenhum ato foi aberto, nenhum interessado escolhido, nenhum campo preenchido e nenhum clique final ocorreu. A aba do portal ficou ativa; a Mesa continua aberta em outra aba no mesmo Chrome QA.
- README do Portal Lab agora registra a sequência de abertura e a necessidade de manter ativa a aba autenticada durante análise. Não foi alterado runtime/extensão.
- Validação: `python -m unittest tests.test_portal_lab_contract -v` — 16/16; `python -m py_compile scripts/portal-lab/launch_mesa_in_qa_chrome.py` — passou; `python scripts/portal-lab/launch_mesa_in_qa_chrome.py --help` — passou; Python completo — 635 executados, 634 passaram, 0 falharam, 1 skip; `verify-project.ps1` — 1.259 executados, 1.257 passaram, 0 falharam, 2 skips, todos os 7 estágios passaram; `git diff --check` passou.
- Arquivos versionados alterados neste bloco: `scripts/portal-lab/launch_mesa_in_qa_chrome.py` (novo), `tests/test_portal_lab_contract.py`, `devtools/area-restrita/README.md`, este handoff e ledger SDD. `app/`, `extension/` e pacote portátil continuam sem mudanças.
- GitHub ainda sem commit/push deste bloco; revalidar status/SHA, atualizar handoff/ledger e publicar.

### Retomada obrigatória

1. Revisar por que o scan oficial persistiu somente 27 itens; capturar evidência estrutural permitida e fechar a observação de paginação antes de qualquer correção runtime.
2. Reconciliar `1198` salvos versus `1197` atuais, confirmar ordem, frames, retorno de formulário, baseline e estado após conclusão manual; preservar o marcador selecionado.
3. Executar Best-Effort Task 10 nos cinco casos reais e no caso parcial supervisionado. Não escolher ato/interessado nem preencher formulário sem autorização contextual; o clique final segue humano.
4. Só após Task 10 + Phase 0 concluírem, considerar Próximo Processo Tasks 1–8. Repetir gates, revisão adversarial e packaging standalone ao final.


### Hardening do launcher e gates após o ajuste (2026-09-24)

- Novo contrato RED/GREEN: URLs de bootstrap com userinfo ou dados extras no fragmento eram aceitas; agora são recusadas antes de qualquer chamada CDP. O token permitido precisa ser exclusivamente URL-safe e ficar no fragmento `token=`.
- Focado final: `python -m unittest tests.test_portal_lab_contract -v` — 17 executados, 17 passaram, 0 falhas. `py_compile` e CLI help também passaram.
- Suíte completa após o ajuste: `python -m unittest discover -s tests -p "test_*.py" -q` — 636 executados, 635 passaram, 1 skip, 0 falhas. Gate `verify-project.ps1` — 1.259 executados, 1.257 passaram, 2 skips, 0 falhas; todos os 7 estágios passaram.
- O serviço real permanece aberto no Chrome QA; último scan estável continua sendo o scan de 27 itens acima. Nenhuma ação no portal foi repetida durante os testes.
- Backup SQLite temporário será removido após conferir que a base atual continua íntegra; artefato privado do marcador permanece ignorado localmente.


### Proteção contra instâncias duplicadas (2026-09-24)

- A causa operacional confirmou que dois processos podiam escutar em `18743`; o launcher agora exige host exatamente `127.0.0.1` e faz preflight de bind exclusivo da porta antes de iniciar `app.main`. Porta ocupada é recusada com exit 2, antes de criar outra Mesa/URL bootstrap.
- TDD: dois contratos de porta falharam por função ausente; após a proteção, os dois passaram. Teste de integração local com o servidor ativo confirmou `occupied_port_guard=passed`, exit 2, sem segunda instância.
- Root Python após a proteção: 638 executados, 637 passaram, 1 skip, 0 falhas. `verify-project.ps1`: 1.259 executados, 1.257 passaram, 2 skips, 0 falhas; todos os sete estágios passaram. `git diff --check` passou.
- README documenta host/porta e manter ativa a aba autenticada do portal. O serviço atual permanece único/saudável no Chrome QA; backup temporário removido após `integrity_check=ok`.


## Git closeout — launcher block (2026-09-24)

- Implementation commit: `331a7e001dacc2d850007c872cdeef616d79507e` (`dev: launch Mesa inside QA Chrome`). `git push` succeeded from `f235b46` to `331a7e0`; elevated `git ls-remote origin refs/heads/codex/atos-tce-unified` returned the same full SHA.
- The worktree was clean immediately after that push. The current handoff/ledger closeout update is being recorded separately.
- The broad goal is intentionally not marked complete: Task 10, full Phase 0, Next Process Tasks 1–8, adversarial review, and standalone packaging remain open.

## Diagnóstico L0 da paginação — 2026-09-24

- `playwright-cli -s=area-restrita attach --cdp=http://127.0.0.1:9222` conectou ao mesmo Chrome QA depois de redirecionar `LOCALAPPDATA` e `PLAYWRIGHT_DAEMON_SESSION_DIR` para `tmp/portal-lab/2026-09-24-task8-live-scan/`. O Chrome e a sessão do portal não foram encerrados nem recriados.
- Captura L0 por Playwright sobre todos os frames do portal: 1 página, 9 documentos, 41 controles estruturais. O inventário atual contém frames duplicados `iframeOBJ`, com `/Home.asp` e `/SISTEMAS/Processo/expirou.asp`; nenhum frame está em `ProcessonoSetor.asp`, portanto a lista e sua paginação não foram observadas. O coletor não interpretou `href` `javascript:`; ausência de destinos no artefato não é evidência de ausência de controles. O estado exato do frame de lista é ambíguo; não houve transição L1/L2.
- Bruto permanece ignorado em `tmp/portal-lab/2026-09-24-task8-live-scan/raw/portal-frames.json`; sanitizado e validado em `tmp/portal-lab/2026-09-24-task8-live-scan/sanitized/portal-frames-verified.json` (14.210 bytes). Sem valores de campos, texto de linhas, cookies, storage ou cabeçalhos na captura.
- Consulta SQLite somente leitura confirmou `integrity_check=ok`. A varredura mais recente tem 27 itens únicos (24 concluídos, 3 pendentes); as três varreduras completas anteriores têm 1.198 itens únicos cada. A sequência dos 27 itens recentes é idêntica ao sufixo nas posições 1.172–1.198 da varredura completa de 21/09: evidência forte de que o comando recente começou na última página e só leu esse trecho.
- Revisão estática confirmou que `extension/background/router.js::scanAreaPages` começa no estado atual de `SCAN_PAGE`, avança apenas para frente e encerra quando `page >= total_pages`; não volta à página 1 antes de coletar. Como o resultado persistido omite `page`/`total_pages`, o estado inicial do comando de 24/09 não pode ser provado retrospectivamente. A hipótese mais provável é a página final remanescente de uma varredura completa anterior; ainda não é confirmação live.
- Reprodução isolada com `node tmp\portal-lab\2026-09-24-task8-live-scan\reproduce-scan-start-state.mjs`: início sintético na página 40/40 retorna 27 linhas e faz 0 avanços; início em 1/40 retorna 1.197 linhas e faz 39 avanços. Confirma o comportamento do loop, não substitui evidência real da página inicial; nenhuma suíte foi executada nem runtime alterado.
- A diferença 1.198 armazenados versus 1.197 mostrados na captura continua sem reconciliação completa. A captura atual não mostra a lista, então não identificar qual item mudou nem declarar cobertura completa. Nenhuma alteração de runtime foi feita, conforme o gate que exige Best-Effort Task 10 + Next Process Phase 0 antes de implementação.
- Retomada: continuar a leitura/revisão dos documentos canônicos na ordem do objetivo; depois de a sessão de lista estar disponível novamente, capturar `SCAN_PAGE` e paginação L0. Só então executar os cinco casos reais e o caso best-effort parcial da Task 10, sob supervisão; concluir as transições e reconciliação da Phase 0 antes de iniciar Next Process.
