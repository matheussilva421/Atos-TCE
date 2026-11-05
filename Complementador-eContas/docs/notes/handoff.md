# Handoff — Complementador e-Contas

> PAUSA 05/11/2026 (GOAL pausado a pedido do usuário; PC será desligado). Esta seção é o ponto de retomada.

## Retomada após desligamento

### Estado do trabalho

- Objetivo: automação em lote do Complementador e-Contas (T00–T21 + preparação de T24), com H2/H3/G7 dependentes de autorização humana.
- Branch: `codex/complementador-e-contas`. HEAD desta pausa: consultar `git log -1` (últimos commits: `fb1e67e`, `d1d9359`, `a30cfc3`).
- Nada foi enviado ao GitHub; `main` permanece em `6e1acd5`.
- Árvore de trabalho: limpa (verificar com `git status --short --branch`).

### O que está implementado e testado

- Núcleo: fila e limites, máquina de estados, diário sanitizado, leitura da listagem, esperas, relatório.
- Fluxo: abas dedicadas com verificação de identidade, interessado único, validação de campos, adaptador de salvamento fail-closed, runner com checkpoint, recuperação e retry limitado.
- Interface: painel na listagem (pré-visualizar, iniciar, pausar, parar, continuar) e comandos de formulário do lote.
- Testes na última execução: **247 unitários PASS** e **21 de navegador PASS** (fixtures locais). Build `npm run build` PASS.

### Evidência real já obtida no QA

- Rota de Autos revalidada: `/#/dashboard/processos/<id>/autos` com `#iframe`, 54 cartões e content script ativo.
- Lote supervisionado 1 (limite 3): 3 processos recusados por múltiplos interessados, nenhum campo preenchido, nenhum salvamento.
- Lote supervisionado 2 (limite 10): 4 recusas por múltiplos, 1 sem interessado, 5 `DOCUMENT_NOT_READABLE` — origem do `BATCH_ENSURE_DOCUMENT`.
- Nenhum salvamento real em nenhuma execução (H2/H3 `NOT_RUN`).

### Pendência aberta (retomar por aqui)

As duas últimas tentativas criaram a fila (10 capturados) mas ficaram em `RUNNING` com **0 examinados** e sem evento `BEGIN_PROCESS`. Instrumentação temporária foi revertida e não conclusiva. O diagnóstico `driverEnabled`/`lastDrive` foi adicionado ao `BATCH_STATUS` e ainda não foi observado no navegador.

Suspeitas, em ordem: bundle antigo carregado pelo Chrome (execução desligada) e `runOneStep` retornando `IDLE`. Verificar primeiro qual é, com uma rodada de 1 processo.

### Atualização 05/11/2026 (retomada após o desligamento)

- **Causa do "0 examinados" encontrada**: o Chrome estava servindo um pacote antigo da extensão quando o mesmo caminho `dist` era reutilizado. Carregando uma cópia em caminho novo (`work/qa-run`), o driver passou a funcionar: lote de 1 processo examinado, abas de Autos e formulário abertas.
- **Regra prática**: a cada build novo, copiar `dist` para um caminho novo (`work/qa-run-N`) e passar esse caminho ao launcher. O caminho reutilizado pode entregar código velho.
- `BATCH_START` agora devolve `driverEnabled` e `lastDrive`; `BATCH_STATUS` também.
- Launcher corrigido para escolher o service worker cujo manifesto é o do Complementador (antes podia pegar workers embutidos do Chromium).
- `NO_DOCUMENT` continua: a aba de Autos real pode levar mais de 20 s para preencher o `iframe#ifrm`; a espera subiu para 30 s e o preenchimento repete a preparação uma vez após 4 s.
- Última tentativa com `work/qa-run3`: diário apareceu vazio e o painel travou; o QA foi encerrado e o build final voltou a `BATCH_EXECUTION_ENABLED=false`.

### Atualização 05/11/2026 (continuação)

- Aba de Autos real inspecionada: o portal **carrega o documento sozinho** (109 cartões, `#ifrm` com `src` após ~9 s) e os cartões **não têm `data-pdf`** (só `id` e `data-id`).
- Correção estrutural: o lote passou a **criar abas novas por processo** em vez de reaproveitar a mesma aba via hash (`openWorkspace({fresh:true})`, remove as anteriores). Motivo: a atualização de hash na SPA deixava o visualizador vazio.
- `ensureDocumentOpen` também usa `data-pdf` quando existir (não existe no portal real) e espera até 30 s; `deps.fill` repete a preparação após 4 s.
- Testes: 249 unitários PASS (novo caso de workspace novo por processo).
- Tentativa com `work/qa-run5`: novamente o diário apareceu vazio e o painel não respondeu; QA encerrado e build final em `BATCH_EXECUTION_ENABLED=false`.
- Ponto de retomada: rodar **1 processo** com a aba nova e confirmar no diário se `NO_DOCUMENT` desapareceu; se persistir, capturar o `iframe#ifrm.src` da aba do processo no momento da falha.

### Bloqueio 05/11/2026 (sessão QA sem resposta)

- A página do e-Contas no perfil QA passou a não responder a `Runtime.evaluate` via CDP: até `location.href` trava, e o clique scriptado no painel não inicia o lote.
- Foi pedido ao operador que clicasse em ⚡ Rodar automação com 10/1; não houve resposta até o encerramento.
- Nenhum código mudou desde `9a141d1`; suíte em 249 PASS e build final com execução desligada.
- Para retomar: reabrir o QA (`scripts/portal-lab/launch-qa-chromium.mjs`, porta 9333, perfil `C:\Users\slvma\.codex\qa-econtas`), carregar uma cópia nova do build (`work/qa-run-N`), fazer login, recarregar a listagem e rodar **um** processo. Se o clique pelo painel funcionar mas o CDP continuar travando, ler o diário pelo content script com `chrome.storage.local` (script `work/qa-state-via-content.mjs`).

### Marco 05/11/2026 — preenchimento real comprovado

- Causas encontradas e corrigidas em sequência: listener `BATCH_ENSURE_DOCUMENT` aninhado (nunca registrado), `tabs.remove()` sem Promise quebrando do segundo processo em diante, envio de mensagem aceitando `undefined` como sucesso e `FETCH_PDF` exigindo transação que o lote não abria.
- Tempos ampliados: mensagem 60 s, documentos 300 s, preparação do documento 30 s com repetição.
- Execução com o filtro do operador: 10 capturados, 7 examinados, 6 recusas corretas, **1 processo em `VALIDATING` com os quatro campos e a modalidade preenchidos**, 0 salvamentos, lote `SUSPENDED` no gate.
- A aba do formulário confirma comprimentos 10/26/10/10 e modalidade selecionada; nenhum clique em Complementar ato.
- Build final em `dist` com `BATCH_EXECUTION_ENABLED=false`; Chrome QA encerrado.
- Próximo passo: repetir com poucos processos para confirmar estabilidade e, se o usuário autorizar, avaliar H2 (um salvamento real). H2/H3/G7 seguem `NOT_RUN`.

### Atualização 05/11/2026 — filtros persistentes e preenchimento sem salvar

- Filtros: o painel ganhou `Salvar filtros` e `Restaurar filtros`; o estado fica em `chrome.storage.local` (chave `complementadorFilterPreset`) e é reaplicado automaticamente ao abrir a listagem. O restauro automático **não** clica em BUSCAR (evita laço de recarga); o clique de busca fica no roteiro do teste.
- Preset já semeado no perfil QA com o filtro do operador: marcador *Mutirão - Educação*, ATO COMPLEMENTADO = *Não*, ordenação e os checkboxes (ProcessosNoSetor e semDistribuicao).
- Modo preenchimento: quando o salvamento está desligado, o lote marca o processo como `FILLED`, mantém a aba do formulário aberta e segue para o próximo (até 10). Nenhum salvamento.
- Testes: 263 unitários PASS (novos casos de filtro, sanitização e `MARK_FILLED`).
- Ambiente: o Chrome QA voltou a ficar sem resposta ao CDP durante a rodada; browser encerrado e build final com `BATCH_EXECUTION_ENABLED=false`.

### Atualização 05/11/2026 — auto-busca dos filtros e perfil QA novo

- Filtros totalmente automáticos: o conteúdo pede autorização por aba (`FILTER_AUTO_CLAIM`), aplica o preset, confirma (`FILTER_AUTO_DONE`) e só então clica em BUSCAR. A confirmação evita laço de recarga quando o BUSCAR provoca navegação.
- Modo estruturalmente só-preenchimento: `BATCH_FILL_ONLY=1` no build liga o motor e **força** `saveEnabled=false`; o caminho de salvamento não pode ser ativado nesse modo.
- Perfil QA antigo (`C:\Users\slvma\.codex\qa-econtas`) corrompeu após encerramentos forçados e passou a mostrar "erro ao abrir seu perfil". A cópia de cookies para recuperar a sessão foi bloqueada pelo revisor automático por envolver autenticação; **não insistir**.
- Perfil novo e vazio: `C:\Users\slvma\.codex\qa-econtas-fresh`, com a extensão `work/qa-run24` (só-preenchimento). Está na tela de login aguardando um login manual único.
- Após o login: semear o preset com `work/qa-seed-preset.mjs` (aponta para a chave `complementadorFilterPreset`), recarregar a página e o painel aplica filtro + BUSCAR sozinho; então iniciar o lote 10/1.

### Resultado do preenchimento em lote (05/11/2026)

- Perfil QA novo (`qa-econtas-fresh`) com login do operador; preset de filtros semeado e aplicado automaticamente, incluindo BUSCAR (chips confirmam marcador).
- Lote 10/1 em modo só-preenchimento: **4 processos `FILLED`**, 6 em `REVIEW_REQUIRED` por `MISSING_FIELDS`, 0 salvamentos, estado `COMPLETED`.
- Quatro abas de formulário permaneceram abertas, cada uma com um interessado selecionado, modalidade escolhida e os quatro campos preenchidos.
- Teste de navegador novo `tests/browser/batch-filters.spec.mjs` cobre preset + aplicação + BUSCAR automáticos.
- Próxima fase (somente com autorização expressa): ligar o adaptador de salvamento, aprender o diálogo real na primeira gravação e então salvar os 4 preenchidos.
- Caminho de salvamento preparado e **desligado por padrão**: `BATCH_SAVE` no formulário usa `clickComplementarAtoOnce` com tentativa única; diálogo desconhecido retorna `DIALOG_UNKNOWN` com título e botões (dígitos mascarados) para aprendizagem. `deps.save` só usa `saveTransaction` quando `executionEnabled` é verdadeiro; o diálogo aprendido ficaria em `complementadorKnownDialog` no `chrome.storage.local`. Testes: 266 PASS.

### H2/H3 executados (05/11/2026)

- O usuário autorizou salvar os quatro atos preenchidos. Cada um foi confirmado uma única vez no diálogo padrão (“Complementar ato” → “sim, complementar”).
- Verificação independente: as quatro URLs, reabertas em aba nova, não exibem mais o botão “Complementar ato”. Quatro de quatro salvos.
- O diálogo real ficou conhecido: título **Complementar ato**, confirmação **sim, complementar**, cancelamento **NÃO**. Esse é o contrato a usar em `complementadorKnownDialog`.
- O salvamento foi supervisionado pelo operador; o adaptador automático continua desligado. Evidência sanitizada em `docs/evidence/batch-h2.md`.

### Ambiente

- Chrome QA: perfil em `C:\Users\slvma\.codex\qa-econtas`, porta CDP 9333, encerrado nesta pausa.
- Build `dist` atual: **execução do lote desligada** (`BATCH_EXECUTION` não definido no build).
- Estado dos filtros do operador: `work/qa-filters.json` (marcador *Mutirão - Educação*, ATO COMPLEMENTADO = *Não*, ordenação e dois checkboxes).
- Scripts auxiliares (não versionados) em `work/`: `qa-refresh.mjs`, `qa-soft-reload.mjs`, `qa-page-reload.mjs`, `qa-filters-save.mjs`, `qa-filters-restore3.mjs`, `qa-filters-exact.mjs`, `qa-batch-run.mjs`, `qa-batch-step.mjs`, `qa-batch-stop.mjs`, `qa-panel-status.mjs`, `qa-inspect.mjs`, `qa-flag-check.mjs`.

### Comandos para retomar

1. `cd C:\Users\slvma\Downloads\Github\Atos-TCE\Complementador-eContas`
2. `node --test tests/unit/*.test.mjs` (esperado: 247 PASS).
3. Para repetir o teste real: `$env:BATCH_EXECUTION='1'; npm run build` e subir o QA com `scripts/portal-lab/launch-qa-chromium.mjs` (porta 9333, perfil `C:\Users\slvma\.codex\qa-econtas`, `--extension-root ...\dist`).
4. Login manual, `node work\qa-soft-reload.mjs`, `node work\qa-filters-restore3.mjs`.
5. Iniciar lote com limites 1/1 e ler o `BATCH_STATUS` pelo mundo isolado do content script: conferir `driverEnabled` e `lastDrive`.
6. Ao terminar, `node work\qa-batch-stop.mjs` e `node work\qa-cleanup.mjs`; rebuild sem `BATCH_EXECUTION` para deixar a execução desligada.

### Limites que continuam valendo

- Não salvar ato real (H2), não rodar lote real (H3) e não publicar release (G7) sem autorização específica.
- Não fazer push, merge ou force-push; `main` intocada.
- Nunca clicar em Complementar ato com diálogo desconhecido; `SAVE_GATE_CLOSED` permanece.

> Atualização 05/11/2026 (automação em lote): esta seção prevalece sobre todo o histórico abaixo.

## Automação em lote — checkpoint 05/11/2026

- GOAL vigente: automação em lote (T00–T21 e preparação de T24), com H2/H3/G7 dependentes de autorização humana separada.
- Branch: `codex/complementador-e-contas`. Nenhum push, merge ou alteração em `main` nesta rodada.
- Baseline T00: 114 testes unitários e 19 de navegador PASS, build PASS; backup em `work/batch-baseline-2026-11-05` (59 arquivos de fonte + 5 do build, `SHA256SUMS.txt` com 64 linhas, restauração de amostra conferida).
- Ambiente de teste novo: o Chrome de marca não aceita `--load-extension`; a suíte de navegador passou a usar `C:\Users\slvma\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe` com `TEST_BROWSER_HEADLESS=1`.
- G1 (listagem): rota `#/dashboard/processos-no-setor/no-setor` e contrato de tabela, link, status e filtros confirmados no Chrome QA; detalhes em `docs/evidence/batch-f0-sanitized.md`.
- Implementado e testado: T02 (leitor da listagem), T03 (fila e limites), T04 (máquina de estados), T05 (diário sanitizado), T07 (abas dedicadas), T08 (interessado único), T10 (campos preexistentes), T12 (adaptador de salvamento com diálogo desconhecido falhando fechado), T14 (recuperação), T15 (esperas), T19 (relatório).
- Testes: `node --test tests/unit/*.test.mjs` com 185 testes PASS (114 originais + 71 novos). Nenhum teste de navegador novo nesta rodada.
- Validação no DOM real: o leitor devolveu 10 linhas da página atual, todas `pending`, com paginação detectada, IDs numéricos e rótulos normalizados; nenhum dado pessoal foi impresso.
- Concluídos também: T06/T17 (protocolo e comandos no background) e T18 (painel na listagem). Verificado no Chrome QA: painel injetado, pré-visualização de 10 pendentes, início com 10 na fila e parada sem examinar nem salvar.
- T13: núcleo do runner implementado e testado (checkpoint SAVE_PENDING antes do clique, tentativa única, SAVE_UNCERTAIN, reconciliação e gate de salvamento fechado). Falta ligar o runner ao background com as dependências reais (T09/T11) e o ciclo MV3 (T16).
- T11 (lado formulário): comandos `BATCH_SELECT_INTERESTED` e `BATCH_VALIDATE_FORM` implementados em `src/form/batch-content.mjs` e registrados no content script, com 5 testes. Devolvem apenas códigos, booleanos e a chave transitória do interessado.
- T09 (adaptador): `src/batch/deps.mjs` conecta abas, mensagens de formulário e preenchimento injetado às dependências do runner, com 5 testes. O salvamento continua fechado (`SAVE_GATE_CLOSED`) e o adaptador real não está ligado.
- Falta para executar de fato: ligar `runOneStep` + `createRunnerDeps` ao background com o `runFillTransaction` real e o ciclo MV3 (T16); o flag de execução permanece desligado até lá.
- T20 concluído: testes travam o botão individual, o fluxo `REQUEST_FILL`, a preservação de valores existentes, a rejeição de remetente não confiável e a separação das chaves de armazenamento do lote e do cache de documentos.
- T16 (parte pura): `runOneStep` ignora despertar concorrente do mesmo lote (`BUSY`) e há teste garantindo que dois eventos não avançam duas fases.
- T21 (parcial): `tests/browser/batch-panel.spec.mjs` roda o painel em fixtures locais — pré-visualizar (1 pendente, 1 concluído, 1 sem status), iniciar (3 capturados, 1 na fila) e parar, sem requisição não-GET. Suíte de navegador com 20 testes PASS.
- Caminho de aplicação do lote: `BATCH_APPLY` no formulário usa o mesmo `handleApplyPlan` do modo manual, mas sem o gate de transação do botão; `runFillTransaction` aceita `applyMessageType`. O gate manual (`STALE_TRANSACTION`) continua intacto e há teste estático cobrindo a separação.
- Driver do background: `src/background/batch-runner.mjs` monta abas, snapshot do formulário, preenchimento e validação e chama `runOneStep`. Criado desligado (`driveEnabled=false`, `saveEnabled=false`) e ainda não registrado no service worker; há 2 testes cobrindo o estado desligado e a execução completa até o gate de salvamento.
- Novo evento `SAVE_NOT_DISPATCHED`: quando o clique não chega a ser disparado, a tentativa armada é limpa e o processo vai para `FAILED`; falha depois do clique continua indo para `SAVE_UNCERTAIN`.
- Driver registrado no service worker: `BATCH_START` e `BATCH_RESUME` chamam `driver.drive(batchId)`, mas `BATCH_EXECUTION_ENABLED` é `false` e `drive` retorna `DISABLED` antes de tocar em abas ou mensagens. Teste de gate garante o flag fechado e a ausência de permissão `alarms`.
- Rota de Autos: observada em 03/11/2026 (`docs/evidence/dom-contract.md`), não revalidada em 05/11/2026. A varredura de chunks não a contradiz. Revalidar no QA abrindo um processo antes de virar o gate de execução.
- Corrida de aba nova: o envio de mensagens do driver usa `retryAsync` (20 tentativas, 250 ms) para aguardar o content script após criar/reaproveitar a aba; 3 testes cobrem sucesso imediato, retry e esgotamento.
- Verificação de abas: `createRunnerDeps.openWorkspace` agora chama `verifyWorkspace` e recusa operar se a aba não estiver no processo correto (`WRONG_PROCESS_TAB`), antes de qualquer mensagem. Teste cobre a recusa sem envio.
- T24 (preparação): `docs/evidence/batch-release-candidate.md` registra hashes do build candidato e o ensaio de rollback — 64 hashes do backup conferidos, 0 divergências. Nada foi empacotado, publicado ou instalado.
- T21 (formulário): `tests/browser/batch-form.spec.mjs` comprova no navegador a seleção do interessado único, o bloqueio por campos vazios, a aplicação do plano (`BATCH_APPLY`) e a validação final com os cinco campos. Suíte de navegador com 21 PASS.
- Correção de UI: o polling do painel preferia o lote cru (`response.batch`) e zerava os contadores; agora prefere o payload com relatório. O teste do painel aguarda um ciclo de polling (3,5 s) e exige "3 capturados"/"1 na fila".
- Diagnóstico: o diário agora guarda o código sanitizado do motivo (`reason`) nos eventos de falha, útil para o relatório e para depurar fluxo real.
- Tentativa de E2E completo do lote (lista → abas → documentos → formulário) foi descartada: habilitar execução no build de teste quebra o teste do painel e a descoberta de service worker é instável nesse harness. As mudanças experimentais foram revertidas; `BATCH_EXECUTION_ENABLED` segue `false`.
- Portal voltou e o QA foi retomado em 05/11/2026: filtros salvos e reaplicados (marcador, ato, ordenação, dois checkboxes), painel reinjetado e rota de Autos **revalidada** — `/#/dashboard/processos/<id>/autos` carrega com `#ifrm`, 54 cartões de evento e autos pronto.
- Correção adicional: `waitForWorkspace` aguarda a aba recém-criada expor a URL antes de verificar (`tab.url` pode vir vazio), com 2 testes; o adaptador aceita `workspaceTimeoutMs`.
- Build aceita `BATCH_EXECUTION=1` via ambiente (fora do build de teste) para habilitar a execução do lote pontualmente; padrão continua desligado.
- Execução real supervisionada no QA (05/11): 10 processos capturados; com limite 3, três foram recusados por múltiplos interessados e nenhum campo foi preenchido. Com limite 10, 4 recusas por múltiplos, 1 sem interessado e 5 falhas `DOCUMENT_NOT_READABLE` (aba de Autos sem documento). Nenhum salvamento.
- Correções: `maxSteps` 200, dependências do driver reaproveitadas, avanço disparado também pelo polling de status e `BATCH_ENSURE_DOCUMENT` para abrir o primeiro evento quando o visualizador está vazio.
- Repetição com as correções (05/11, sessão restabelecida): o lote criou a fila (10 capturados) mas permaneceu em `RUNNING` com 0 examinados; nenhum evento `BEGIN_PROCESS`. A causa não foi isolada: a tentativa de instrumentar o retorno do driver ficou inconclusiva porque o painel desapareceu após o BUSCAR e o script de diagnóstico travou. Instrumentação revertida; build final voltou a `BATCH_EXECUTION_ENABLED=false`.
- Estado final do QA: lote `STOPPED`, painel ativo, filtros reaplicados (marcador, ato, ordenação, dois checkboxes) e 10 linhas. Suíte unitária com 244 PASS.
- Próximo diagnóstico recomendado: registrar o retorno de `drive()` em `chrome.storage.local` (chave temporária) ou expor `BATCH_DRIVE_STATE`, antes de novas rodadas reais; suspeita principal é o driver não habilitado no bundle carregado ou `runOneStep` retornando `IDLE`.
- Pendente: T09 (integração documental), T11 (readback pré-save no content script), T16 (ciclo MV3), T20/T21 (regressão do modo manual e E2E sintético).
- Estado dos filtros do operador salvo em `work/qa-filters.json` e reaplicado por script após reiniciar o Chrome QA.
- Gate de salvamento: o diálogo real de confirmação e a prova pós-salvamento continuam `UNKNOWN_UNTIL_H2`; por isso o adaptador não confirma diálogo desconhecido e retorna `unknown`.
- Nenhum salvamento real foi executado. H2, H3 e G7 permanecem `NOT_RUN`.

> Atualização 04/11/2026: esta seção prevalece sobre o histórico abaixo.

## Correção final — descoberta automática de Resolução e Guia (04/11/2026)

- Estado: implementação concluída e validada no Chrome QA isolado; falta apenas recarga manual no Chrome profissional, que não foi tocado.
- Repositório de trabalho: `<projeto>`; clone do repositório: `<clone>`.
- Branch publicada: `codex/complementador-e-contas`; HEAD anterior `b8ceb0d`; esta rodada gera um commit próprio. `main` do Atos-TCE permanece em `6e1acd5`.
- Build final: `background.js` 62.394 bytes, `form-content.js` 40.608, `autos-content.js` 981.475, `manifest.json` 1.030, `vendor/pdf.worker.mjs` 1.417.586.
- Hashes finais: manifest `91E2D154...`, background `91281F9B...`, form `BBFFC7ED...`, autos `CDA81850...`, worker `BD888051...` (valores completos em `docs/evidence/qa-real-2026-11-04.md`).
- Release: `release/Complementador-eContas-0.1.1.zip`, 619.972 bytes, SHA-256 `D44B37192B49CDE6F5245AF1F84176227C6C89AB0D449C601BC651FE240601EB`; extração independente com hashes iguais a `dist`.
- Testes: `npm test` 114 PASS; `npm run test:browser` 19 PASS (Chrome for Testing 157.0.8103.38, 22,4 s). O `withStack` foi corrigido para fechar o servidor de fixtures mesmo quando a inicialização do navegador falha.
- Descoberta real: 20 eventos com nomes genéricos; Resolução correta no evento 6 (1.812 caracteres), decoys nos eventos 7 e 14, Guia no evento 10 (1.247 caracteres), documento inicial diverso com 1.201 caracteres.
- Performance real: primeiro clique a partir do documento diverso em 14,3–14,5 s; primeiro clique com a Resolução aberta e cache limpo em 7,096 s; com cache, p50 3,026 s e p95 6,729 s (amostras 6.729/3.026/2.833 ms; uma amostra posterior de 8.190 ms).
- Resultado: cinco campos preenchidos em um clique, readback sem pendências, origem Resolução + Guia, Autos restaurados com mesmo `src` e 2 eventos selecionados, cache com os dois ids. Nenhum save/submit.
- Aceite: `REAL_END_TO_END_PASS` no Chrome QA e `NO_SAVE_OR_SUBMIT_VERIFIED`; o Chrome profissional permanece `PROFESSIONAL_BROWSER_PENDING`.
- Verificação de build no QA: os cinco recursos carregados no service worker coincidem byte a byte com `dist`.
- Pendências: recarga manual no Chrome profissional (não autorizada nesta sessão); teste real do isolamento de cache entre dois processos distintos; comportamento de autosave do portal continua desconhecido.

## QA real 04/11/2026

- Chrome for Testing 157.0.8103.38 em perfil QA isolado (`<QA>/profile-debug-20261104`), CDP apenas em `127.0.0.1:9222`; Chrome profissional e Atos-TCE intocados.
- Extensão `Complementador e-Contas` 0.1.1 carregada de `dist` (ID `hfnkjnnoinedjeakknfdaofgggjolehc`, `COMMAND_LINE`, `ENABLED`, sem `disable_reasons`).
- Duas abas do mesmo processo (`QA-PROC-55cab267`), um interessado selecionado, quatro campos presentes, editáveis e vazios.
- Leitura real 1 (`DOC-0f9827c7`): `L1_SUCCESS`, 1 página, 1.874 caracteres, 54.627 bytes, 502 ms; etapas até `PDF_VALIDATED` e `PDF_TEXT_EXTRACTED`.
- Leitura real 2 (`DOC-4840252c`, reseleção do operador): `L1_SUCCESS`, mesmas páginas/caracteres/bytes, 1.026 ms; rede `GET` 200 `application/pdf`; `GET_DIAGNOSTIC` recuperou `L1_SUCCESS` em nova aba.
- Fingerprint do formulário `32e6adbe` antes/depois das duas leituras; nenhum campo escrito; modalidade não selecionada; nenhum ato salvo ou concluído.
- Defeito comprovado: a aba Complementar Ato aberta pelo SPA não recebia o painel porque o Angular usa `pushState` e o content script só ouvia `hashchange`. Correção em `src/form/content.mjs` e `src/autos/content.mjs` com `navigation.navigatesuccess`, mantendo `hashchange`.
- Testes: 100 unitários PASS; 15 de navegador PASS (pushState, replaceState, hashchange, saída de rota, L1, L1 multi-página, recuperação, CPF concatenado, prioridade de data, readback da modalidade, marcador assíncrono e busca da Guia). `git diff --check` PASS.
- Correções do follow-up: CPF colado ao último nome no cartão; prioridade da data do cabeçalho sobre datas do corpo; `revisionMarker` assíncrono estabilizado; `.ng-value` com ícone `×` lido via `.ng-value-label`. Teste controlado final: um clique preencheu modalidade + DOE + cargo + matrícula em 683 ms; nascimento ausente no PDF.
- Busca da Guia implementada: 21 eventos varridos; primeiro clique real em 8,9 s e segundo em 1,1 s com cache de sessão; 5 campos preenchidos, incluindo nascimento; documento original restaurado. O cache guarda apenas `eventId`/`updatedAt`, sem URL ou conteúdo.
- Revisão independente: o achado Critical contra `navigatesuccess` foi refutado em runtime (probe Chromium, RED→GREEN e portal real); `replaceState`, `hashchange` e saída de rota foram adicionados como testes. Nenhum achado de segurança confirmado.
- Pendências: recarga da build no Chrome profissional (não autorizada); L2 real foi executado somente no QA com autorização explícita desta continuação; salvar/complementar o ato continua fora do escopo. Após reload da extensão, as duas abas do portal precisam ser recarregadas.

## Objetivo

Entregar uma extensão Chrome/Edge Manifest V3 independente para complementação assistida de atos no e-Contas do TCE/RN, com um clique, leitura do documento atual, extração determinística, preenchimento seguro e nenhuma submissão.

## Estado

- Repositório de trabalho: `<projeto>`; versão 0.1.1.
- Clone do repositório: `<clone>`, subpasta `Complementador-eContas`.
- Branch: `codex/complementador-e-contas`; `main` do Atos-TCE intocada em `6e1acd5`.
- Publicação: branch publicada; esta rodada consolida os commits locais e o push da mesma branch, sem merge.
- Atos - TCE: não alterado pelo projeto; os documentos aprovados foram apenas copiados para o novo repositório.

## Concluído

- F0 sanitizada, com observação somente leitura das duas abas.
- F1: MV3, rotas, seleção de abas, protocolo e transação única.
- F2: leitura do PDF atual por bytes com PDF.js, parser de datas e campos com proveniência.
- F3: leitura/escrita do formulário com identidade, preservação, readback e sem submit.
- F4: testes unitários, testes de navegador no Edge, auditoria de segurança, benchmark e build.
- Diagnóstico L1 somente leitura (commit c23d9d2), testado em fixtures.
- Correções da revisão independente: clique trusted, vínculo de processo por títulos, cancelamento, listener de autos e permissão de PDF restrita (commit bf70743).
- Diagnóstico L1 recuperável em chrome.storage.session, com estados e métricas sanitizadas e recuperação após reload (commit 734263d).
- README e documentação de evidências.

## Evidências

- npm test: 88 PASS, 0 FAIL.
- npm run test:browser: 10 PASS, 0 FAIL (Edge 156, versão 0.1.1, diagnóstico multi-página, HTTP/login, clique sintético e recuperação após reload).
- npm run build: dist gerado com background.js, form-content.js, autos-content.js, manifest.json e vendor/pdf.worker.mjs.
- benchmark: amostras 232, 192, 156, 138, 133, 111, 116 ms; p50 138 ms; p95 232 ms.
- PDF sintético de 877 bytes: L1_SUCCESS com 1 página, 271 caracteres e 877 bytes; resultado recuperado após recarregar a aba, sem alterar campos.

## Gates e bloqueios

- REAL_VIEWER_UNVERIFIED: o PDF real não foi lido; o iframe é cross-origin e o fetch real não foi provado.
- DIAGNOSTIC_OBSERVABILITY_VERIFIED: PASS sintético; o resultado é recuperado após reload via chrome.storage.session.
- EXTENSION_RELOAD_VERIFIED (build L1 anterior): os dois botões apareceram após recarregar a aba; FINAL_BUILD_RELOAD_PENDING para a build com recovery.
- Cópia instalada: release/Complementador-eContas-0.1.0 foi substituída pela build atual; os hashes coincidem com dist. A build final com recovery ainda não foi recarregada no Chrome profissional.
- Causa: atualizar dist não atualizava a cópia extraída que o Chrome carregava. Chrome mantém o código já carregado em memória; ainda é necessário recarregar a extensão e a aba Complementar Ato.
- A build L1 anterior chegou a ser injetada e o botão apareceu; a build final com recovery está pronta no disco. Nenhum campo foi alterado.
- Verificação final: hasDiagnosticPanel=false na aba atual; a build carregada é a L1 anterior, não a final com recovery. Nenhum campo foi alterado.
- Tentativas oficiais: DevTools MCP sem CDP em 9222; aba chrome://extensions não reivindicável pela automação; controle nativo interrompido pela política do Computer Use por incerteza de URL no Windows. Não houve contorno.
- Estado: SAFE_PARTIAL; DIAGNOSTIC_OBSERVABILITY_VERIFIED; EXTENSION_RELOAD_VERIFIED apenas para a build L1 anterior; FINAL_BUILD_RELOAD_PENDING; REAL_READ_PASS não declarado; REAL_VIEWER_UNVERIFIED; L2_NOT_AUTHORIZED.
- Tentativa L1: clique trusted no diagnóstico disparado; o depurador da automação caiu e a aba de autos ficou Debugger unattached. Nenhum resultado foi obtido.
- Reconexão tentada após 15 s e 30 s: mesmo timeout de CDP; nenhuma métrica real.
- Reconexão posterior: controle voltou e a aba de autos tinha marker ready; clique trusted no Diagnóstico L1 retornou Falha de comunicação com a extensão e nenhum estado final no storage. A build final com recovery continua não confirmada no Chrome.
- L2_NOT_AUTHORIZED: nenhuma escrita real em formulário profissional.
- MULTI_PERSON_UNVERIFIED: só um interessado foi observado no portal.
- AUTOSAVE_UNKNOWN: nenhuma digitação real; se houver autosave, interromper.
- REA_CDP_UNAVAILABLE: não havia endpoint CDP; a observação foi feita com CUA/Playwright read-only, não com REA.
- Chrome gerenciado bloqueia extensões unpacked por linha de comando; testes de navegador usam Edge.
- Chromium do Playwright não foi baixado; o download foi recusado pelo revisor automático.

## Incidente de ambiente

O primeiro comando de git init foi executado por engano em `Downloads/Github` e criou um diretório .git vazio nessa pasta. A remoção foi recusada pelo revisor automático de segurança. O .git do projeto correto está em `<projeto>/.git`. O operador pode remover manualmente o .git acidental de `Downloads/Github` se desejar; nenhum arquivo de projeto foi alterado por ele.

## Próximos passos

1. Revisar o README e a pasta dist.
2. Recarregar a build final em um Chrome autorizado e recarregar somente a aba Complementar Ato; manter a aba de autos e o documento intactos.
3. Clicar apenas em Diagnóstico L1 (somente leitura) e verificar páginas, caracteres, tamanho e tempo; não clicar em Preencher.
4. Se a leitura real passar, registrar REAL_READ_PASS.
5. Só depois, se houver autorização L2 separada, testar escrita apenas nos campos de UI, sem salvar; monitorar autosave.
6. Nunca clicar em Complementar ato, Salvar, Confirmar ou submeter formulário.

## Comandos úteis

    cd <projeto>
    npm test
    npm run test:browser
    npm run build
    npm run benchmark
    git status --short --branch
    git log --oneline

## Arquivos-chave

- extension/manifest.json
- src/background/index.mjs
- src/background/bridge.mjs
- src/autos/document-reader.mjs
- src/extract/dates.mjs
- src/extract/fields.mjs
- src/form/form-reader.mjs
- src/form/form-writer.mjs
- src/form/content.mjs
- src/autos/content.mjs
- docs/evidence/f0-sanitized.md
- docs/evidence/dom-contract.md
- docs/evidence/security-audit.md
- docs/evidence/live-verification.md
- docs/evidence/benchmarks.md
## Build final — 04/11/2026

- manifest.json: 91E2D154D9E8E6C02A5CAC6EEF645F71ED15E74CF4ED030AF6B28C7EC3DF6834
- background.js: 91281F9B92720DE84CD3FBE6BF49214CB26136646C7BB79F3BC0414A1600234A
- form-content.js: BBFFC7ED4B4286C44FD372032F215BCCDB51CB9E69108199A7557BA1207CCBD2
- autos-content.js: CDA8185074184171CA299E035AEFD463DAFFB38C5A8AEF5565C553F3F3E69A90
- vendor/pdf.worker.mjs: BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D
- ZIP: release/Complementador-eContas-0.1.1.zip (619.972 bytes; SHA-256 D44B37192B49CDE6F5245AF1F84176227C6C89AB0D449C601BC651FE240601EB)
