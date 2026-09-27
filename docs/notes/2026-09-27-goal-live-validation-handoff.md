# Goal live-validation handoff — 2026-09-27

## Repository and branch

- Repository: `Atos-TCE`.
- Branch: `codex/atos-tce-unified`.
- Starting HEAD: `3be93e1350cc24fa4ee8f9472dfebfc41d79e832`.
- Source code was not changed in this checkpoint.
- The prior scan remains scan 10; no new official scan was run.

## Live state and safety

- Chrome QA is the active DevTools target on loopback CDP `127.0.0.1:9222`; Mesa and the extension remain open.
- At the start of this checkpoint, Área Restrita was authenticated, scan 10's selected marker matched the live marker, and the form at scan position 301 was open.
- The scan still records 1,197 rows: 354 pending and 843 complemented; zero ambiguous, blocked, or not-found rows.
- No act was finalized, submitted, signed, or tramited. The portal's final **Complementar Ato** action remains manual.
- After one `OPEN_NEXT_ACT` failure, the active work frame remained empty. A single reload of the portal shell then showed login/password controls. The portal must be reauthenticated manually before live work resumes. No credentials or session material were read or handled.

## Live Próximo Processo evidence

- Previously recorded commands 59 and 60 succeeded: 298 → 300 on the same page (17.532 s upper bound) and 300 → 301 across a page boundary (24.442 s upper bound). Both reread the exact process/interested identity; command 60 had no following fill request.
- This checkpoint: commands 62–65 succeeded and each target matched exactly one scan identity; the stored scan marker matched the command context.
  - 301 → 302, same page; command 62.
  - 302 → 303, same page; command 63; click-to-ready upper bound 5.7 s.
  - 303 → 304, same page; command 64; click-to-ready upper bound 6.0 s.
  - 304 → 306, same page; command 65; the intervening row was not eligible; click-to-ready upper bound 5.4 s.
- Command 66, from 306 toward 307, failed closed with `FORM_NOT_AVAILABLE`. It created no fill request and no final action. The result does **not** establish a stale-target refusal: the command code was specifically `FORM_NOT_AVAILABLE`.
- Read-only diagnostics after command 66 found document requests returning HTTP 200 and no explicit login/expired-session text before reload. The active work frame had no body or form controls. A native list-tab click did not make the frame's DOM usable. The subsequent portal-shell reload exposed login/password controls, so live navigation must wait for manual reauthentication and a fresh structural check.
- No natural stale-ready process or ambiguous scan item exists in the persisted snapshot (`stale_ready_groups=[]`, scan ambiguous count 0). Do not edit the database or create ambiguity to force those cases.
- The last eligible scan position is 1083. The live end-of-queue case remains unrun.

## Best-Effort Task 10 real sample

- One authorized real fill was run for the eligible case at scan position 301, whose documentary evidence includes ECE/RN 20/2020.
- Request 20 / extension command 61 completed successfully. Exact identity echo matched the unique scan row. All six proposed fields were marked `changed`, and each stored `after` value equaled `proposed`; 0 fields were preserved and 0 unresolved. `mandatory_satisfied=true`; local process status is `PREENCHIDO`.
- Legal decision used `legal-foundation-v4`, method `best-available`, selected a catalog option, confidence `0.779545`, margin `0.000598`, and `hard_conflict=true`. Warnings: `low-confidence`, `low-margin`, `hard-conflict`. This is also evidence for the weak/nonliteral-match review case; preserve the warnings in the report.
- The portal's final action was not clicked. The Area Restrita scan still reflects the original pending state because no final act was completed.
- Remaining real Task 10 coverage: isolated EC 41/2003, isolated CF art. 40, preserve a previously valid EC 47/2005 value, and a genuine partial A/B/C case. Do not manufacture missing/disabled/divergent portal state with script.

## Tests, package, and GitHub

- No tests were run in this checkpoint; it made no source change. Previously recorded offline gates are historical and must not be presented as this checkpoint's final gate.
- ZIP and clean-extraction smoke remain pending for the final closeout sequence.
- Before this handoff edit, the checkout was clean and synced with `origin/codex/atos-tce-unified` at the starting HEAD above. This handoff still needs its own commit and push.

## Resume instructions

1. If the session expires, have the operator authenticate in the already-open Chrome QA window; do not handle credentials or session tokens.
2. The sector process list has been restored through the portal UI. Recheck its page/frame structure and compare the selected marker with scan 10 before any further queue navigation; do not rerun the official scan.
3. Do not repeat command 66 or the later accepted-but-unconfirmed request. Reconcile the pending target through the official UI before any new **Próximo processo** action.
4. Continue Task 10 only on exact eligible identities, filling and rereading only; leave the final portal action manual.
5. Cover live stale/ambiguous/end-of-queue only if a natural safe case is available. Keep the already green automated fixtures distinct from portal-real evidence.
6. After all live work, perform adversarial review, final test gates, standalone ZIP verification, clean-extraction smoke, update this handoff, and push only `codex/atos-tce-unified`.

## 2026-09-27 — reauthenticated queue and accepted-but-unconfirmed navigation

- Chrome QA was already running under the DevTools connection. The user had reauthenticated manually; the portal shell and process list were reachable. No credentials or session material were read.
- Restored the sector process list by opening the portal's **Proc./Doc. Eletrônicos no Setor** view. One informational “Limite de 10 Abas” dialog appeared and was accepted. The list loaded; no official scan was rerun and scan 10 remains the source snapshot.
- The extension and Mesa both reported connected. Clicked **Próximo processo** exactly once. The extension accepted a target request, then completed its bounded wait without confirming the target form. Its diagnostic was `accepted_unconfirmed`; the portal remained on the list and no act form was confirmed.
- The extension kept both **Preencher formulário atual** and **Próximo processo** disabled after that result. Do not retry or submit another target request until the accepted request is reconciled through the normal portal/extension UI. Do not read or copy the target identity from extension state.
- No fill request was issued by this click, no act fields were changed, and no final action was taken. The previously recorded Task 10 fill remains the only real fill evidence.
- Structural check: the authenticated portal page and sector list frames were complete; no act form was found. The selected marker was not independently re-compared to scan 10 in this checkpoint.
- No source code changed and no tests ran. Before this handoff update, Git was clean on `codex/atos-tce-unified` at `cb1d305e47aba80dcb0e41342c6b22c7fe29fde3`, equal to `origin/codex/atos-tce-unified`.

### Resume from this checkpoint

1. Keep the current Chrome QA session and do not repeat the accepted navigation request. First inspect the extension diagnostic and portal frame state through the official UI; continue only after the pending target is resolved or safely reset and exact identity is confirmed.
2. Recompare the selected portal marker with scan 10 before any further queue navigation. Do not rerun the official scan.
3. Continue the remaining real Task 10 cases only after the portal opens an exact, eligible case; fill and reread only, with final **Complementar Ato** kept manual.
4. Complete live Next Process matrix cases only when naturally available; retain fail-closed status for stale/ambiguous and end-of-queue unless the live portal provides safe evidence.
5. Finish final review, all project gates, standalone ZIP verification, and clean-extraction smoke; then update this handoff and push only `codex/atos-tce-unified`.

## 2026-09-27 — offline gates and standalone package

- Integrated gate: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\verify-project.ps1` from `work/tce-extractor` exited 0. Seven stages passed; 1,260 checks executed, 1,258 passed, 0 failed, 2 skipped.
- Full supplemental Python suite: `python -m unittest discover -s . -p 'test_*.py' -q` from `work/tce-extractor` exited 0; 529 tests ran, 520 passed, 0 failed, 9 skipped. The run emitted the existing PyMuPDF deprecation and expected simulated HTTP/CLI warnings.
- Built a fresh standalone package to `tmp/goal-package-2026-09-27.zip`, leaving `dist/Atos-TCE-portable.zip` untouched. The builder reused the pinned runtime. Package: 96,155,474 bytes, 516 entries, runtime included (430 files), extension version 0.1.0; SHA-256 `216f10546370c1215ee0aef6554b397c33b4c562fa4b46bf98409b8c47f55627`.
- The fresh package hash is identical to the existing `dist/Atos-TCE-portable.zip`; no promotion/rotation or overwrite was needed. `START.cmd` selects the bundled Python runtime.
- `verify-package.ps1` passed twice without `-SkipSmoke`; each clean extraction reported health `ok`, API v1/schema 7, zero process data, and extension 0.1.0. Both runs printed a `taskkill` Access Denied warning, then cleanup checks confirmed the exact extraction root removed, no package child process, and the smoke port closed. Record that warning alongside the passing result.
- Final two-axis review against `origin/main...HEAD` completed with read-only Standards and Spec reviewers; findings are recorded below.
- The live accepted-but-unconfirmed navigation and remaining Task 10 cases are unchanged and remain the only real-portal blockers. No source code changed in this block.

## 2026-09-27 — final two-axis review

- Fixed point: `origin/main` at `b1d41e848c39cb61947b011501925c40f86793fb`; merge-base equals that SHA. Review diff was `git diff origin/main...HEAD` (151 commits at review time).
- Standards axis: the repo's `AGENTS.md` says the code source of truth is `work/tce-extractor`, while `docs/ESTRUTURA.md` and `README.md` say root `app/` and `extension/` are supported and `work/tce-extractor` is legacy. This is an unresolved documentation authority conflict; no code change was made. The reviewer also noted a judgement-call Data Clumps smell for the process/interested identity pair across navigation layers; no functional defect was established.
- Spec axis: live stale/ambiguous/end-of-queue Next Process cases and the remaining Task 10 cases are incomplete. No high-confidence out-of-scope or incorrect implementation finding was reported. The spec does not define an expected decision status for weak legal matches with hard conflicts.
- The reviewer initially marked package acceptance pending based on the earlier handoff text. Two subsequent clean-extraction smokes passed with health `ok`; that package finding is superseded by the later evidence above.
- Overall goal remains active because portal-real acceptance is incomplete. Do not promote to `main` or claim completion.

## 2026-09-27 — Chrome QA foreground e marcador divergente

- O Chrome QA já estava conectado ao MCP em `127.0.0.1:9222`; a página da Área Restrita foi selecionada e trazida para primeiro plano. A Mesa Local e a extensão `ATOS TCE — Ponte da Mesa` v0.1.0 Enabled continuam abertas no mesmo perfil.
- A página autenticada está na lista de processos (`ProcessonoSetor.asp`); o frame da lista está completo e contém a tabela. Não foi aberto formulário de ato neste checkpoint.
- Comparação somente de leitura entre o scan oficial 10 e os controles da lista: o seletor que `extension/lib/area-snapshot.js` identifica por metadados como marcador (índice DOM 7, 73 opções, seleção na posição 0) não corresponde ao marcador persistido no scan 10, nem pelo rótulo normalizado nem pelo valor. Os outros dois candidatos (índices 8 e 11) só correspondem porque o texto da linha ancestral menciona marcador; também não correspondem ao scan.
- A checagem usou hashes locais para comparar os valores, sem imprimir os identificadores do marcador. Nenhum seletor foi alterado. Não foi repetido o scan oficial, o comando Próximo Processo, nem qualquer preenchimento ou ação final.
- Este estado bloqueia navegação/fill live seguros até que a operadora restaure manualmente na Área Restrita o mesmo marcador usado pelo scan 10. Depois, revalidar a correspondência e reconciliar a navegação aceita anteriormente antes de emitir qualquer novo comando.
- Nenhum código/teste foi alterado ou executado neste checkpoint. A janela do Chrome QA está aberta e em primeiro plano; a intervenção humana necessária é somente selecionar novamente o marcador correto na lista e avisar quando a página terminar de carregar.

- A captura estrutural L0 previamente autorizada foi salva em `tmp/portal-lab/2026-09-27-foreground-session/raw/area-restrita-l0.json` (9 frames; 1 seletor de marcador; 5.061 bytes). O caminho está coberto por `.gitignore`; verificação confirmou ausência de valores, texto de página e campos de sessão.


## 2026-09-27 — rechecagem do marcador e diagnóstico da extensão

- Releitura do objetivo e do estado atual: HEAD `6443dcfe4a261be85e5dd5cc3c12f60e1821b77d`, branch `codex/atos-tce-unified`; Mesa, Área Restrita e extensão seguem abertas no Chrome QA.
- A leitura atual do seletor que o código identifica como marcador mostra índice selecionado 0 de 73 opções, rótulo vazio e divergência de rótulo/valor em relação ao scan 10. Portanto, o contexto do scan não está selecionado no portal.
- O painel da extensão indica Mesa conectada e Área Restrita detectada. Os botões **Preencher formulário atual** e **Próximo processo** estão desabilitados; não confirmei formulário de ato.
- Não li armazenamento do navegador nem identidade de processo/interessado. Não houve scan, navegação, preenchimento ou ação final neste checkpoint.
- Próxima ação: a operadora seleciona manualmente na lista o marcador usado no scan 10 e avisa quando terminar; então comparar novamente e reconciliar a solicitação aceita antes de emitir qualquer novo comando.
- Código e testes não mudaram. `git diff --check` será verificado após este registro.

## 2026-09-27 — Próximo Processo 68 e preenchimento real 21

- Correção do estado do checkpoint anterior: a operadora selecionou o marcador correto. A comparação local por SHA entre a seleção no frame da lista e o scan 10 confirmou rótulo e valor iguais; o contexto do comando também corresponde ao scan 10. Nenhum marcador foi alterado pelo agente e nenhum novo scan foi executado.
- A navegação oficial `OPEN_NEXT_ACT` 68 terminou `SUCCEEDED`, `action=next_act_ready`, `screen=form`. O servidor validou que processo e interessado relidos eram exatamente o alvo enfileirado. O alvo estava presente no scan 10 como `PRECISA_COMPLEMENTAR`; o scan continua com 1.197 registros, 354 pendentes e 843 complementados, sem ambíguos, bloqueados ou não encontrados.
- A transição abriu `/SISTEMAS/PROCESSO/ComplementarAto.asp` em frame aninhado, com estado `complete`, formulário e controles de processo visíveis. O identificador de formulário `complementarAtoForm` documentado não foi observado; não foi criado seletor nem feita alteração de runtime. A página shell permaneceu em `/telaPrincipalMenu.asp`.
- Tempo medido clique→documento do formulário pronto: 56.676 ms; duração arredondada nos registros do servidor: 57 s. A captura L0 sanitizada, sem valores ou texto de página, está em `tmp/portal-lab/2026-09-27-foreground-session/raw/next-process-after.json`; `git check-ignore` confirmou a exclusão por `.gitignore`.
- O clique do MCP no botão oficial falhou antes de executar (`handle.asLocator is not a function`). Depois de confirmar a presença única e habilitada do botão **Preencher formulário atual**, o evento de clique foi disparado no próprio botão visível do painel da extensão. A solicitação manual 21 terminou `PREENCHIDO`; o comando `FILL_FORM` associado terminou `SUCCEEDED`, geração 7, identidade ligada ao mesmo registro do alvo.
- Releitura: 6 campos, todos `changed`; em todos, `after == proposed`; zero preservados e zero não resolvidos; `mandatory_satisfied=true`. O scan continua marcando o ato como pendente porque a ação final não foi executada. A operação avisou que não havia proposta para gênero.
- Decisão legal: `AUTO_SELECTED`, classe `EC41_TRANSITION_GENERAL`, método `best-available`, confiança 0,775581, margem 0,001257, `hard_conflict=false`, avisos `low-confidence` e `low-margin`. As referências estruturadas incluem CE 20/2020, arts. 6º e 7º; esta evidência não constitui aprovação jurídica humana. Modalidade ficou `selected`/`AUTO_SELECTED`, confiança 0,84, margem 0, com candidatos equivalentes e desempate por índice; manter para revisão.
- Classificação de cobertura: amostra real útil para revisar ECE/RN 20/2020 e correspondência fraca/não literal, ainda pendente de revisão humana. Não fecha isoladamente EC 41/2003, CF art. 40, preservação de EC 47/2005 nem o caso parcial A/B/C. Nenhuma ação **Complementar Ato**, envio, assinatura ou tramitação foi executada.
- Arquivos: fonte/runtime inalterados; este handoff foi atualizado. A captura acima permanece ignorada/local. Nenhum teste foi executado neste bloco; a validação foi pelo portal real e releitura local. `git diff --check` e a sincronização do handoff são os gates deste checkpoint.

### Retomada

1. Não repetir o preenchimento 21. Deixar esse ato preenchido para revisão humana e manter o clique final manual.
2. Continuar pelo botão oficial **Próximo processo**, uma transição por vez, validando frame, identidade composta, marcador e elegibilidade antes de cada preenchimento.
3. Priorizar casos reais isolados EC 41/2003 e CF art. 40, evidência de preservação EC 47/2005 e um parcial A/B/C genuíno; não fabricar estado de portal.
4. Prosseguir com a matriz Next Process natural disponível; casos stale, ambíguo e fim da fila ficam pendentes se não surgirem com segurança.
5. Depois da cobertura live, fazer revisão adversarial, gates finais, ZIP/smoke standalone e atualizar/push somente `codex/atos-tce-unified`.

## 2026-09-27 — Próximo Processo 72 e preenchimento real 23

- A operadora selecionou manualmente o marcador. Comparação local por fingerprint confirmou que rótulo e valor do seletor atual correspondem ao scan 10; não foi executado outro scan.
- Antes de avançar, os dois frames antigos foram reconciliados: o formulário visível correspondia ao preenchimento 22 e o oculto ao 21. Ambos seguem sem ação final.
- A ação oficial **Próximo processo** foi acionada uma vez. O comando 72 terminou `SUCCEEDED`, `next_act_ready`, tela `form`, em 2 s. O servidor releu a identidade exata do alvo solicitado; ela pertence ao scan 10 como `PRECISA_COMPLEMENTAR`, e o contexto/marcador do comando coincide com o scan. A releitura do frame visível confirmou a mesma identidade composta; os outros dois formulários ficaram ocultos.
- O botão oficial **Preencher formulário atual** foi acionado uma vez. O preenchimento manual 23 terminou `PREENCHIDO`: seis campos alterados, os seis com `after == proposed`, zero preservados, zero não resolvidos e obrigatórios satisfeitos. A classificação continua pendente no scan, pois não houve ação final.
- Decisão legal: `EC41_TRANSITION_GENERAL`, `selected`, automática pelo método `rule`, confiança 0,983333, margem 0,213889, sem hard conflict nem avisos da decisão; três referências documentais incluem ECE/RN 20/2020. É evidência de cobertura EC 41 e revisão ECE/RN 20/2020, não aprovação jurídica humana.
- Modalidade: `selected`, automática via `catalog-token-overlap`, confiança 0,84, margem 0 e quatro avisos; revisar a escolha. Houve cinco avisos operacionais. O ato continua aberto e não finalizado.
- A fila permanece com 1.197 itens, 354 pendentes e 843 complementados, sem ambíguos, bloqueados ou não encontrados. Nenhuma identidade de processo/interessado foi registrada neste handoff.
- Nenhum código foi alterado e nenhum teste foi executado; a validação deste bloco foi live e por releitura local. A comparação exploratória de identidade por argumento MCP foi rejeitada antes da execução; foi substituída por comparação local hash-only, sem efeito no portal.

### Retomada

1. Não repetir os preenchimentos 21, 22 ou 23; deixá-los pendentes para conferência/finalização manual.
2. Manter o marcador atual e conferir que continua igual ao scan 10 antes de qualquer nova navegação.
3. Os candidatos nas posições 704 e 829 foram preenchidos para investigação, mas não são casos CF art. 40 isolados; encontrar outra amostra antes de marcar essa cobertura como concluída.
4. Revisar o resultado 23 e continuar procurando um caso parcial A/B/C genuíno e evidência EC 47 já validada; não fabricar estados.
5. Prosseguir com a matriz live de Próximo Processo apenas quando útil; stale, ambíguo e fim da fila continuam pendentes se não aparecer caso seguro.
6. Depois da cobertura, fazer revisão adversarial, gates finais, ZIP/smoke standalone, atualizar o handoff e push somente `codex/atos-tce-unified`.

## 2026-09-27 — Task 10: CF art. 40 misto e preenchimentos 24/25

- A lista oficial foi usada para navegar da página 11 à 24 e depois à 28, pelo seletor de página nativo. Antes de cada salto, o marcador continuou igual ao scan 10.
- Nas posições 704 e 829, a linha da Área Restrita coincidiu unicamente com a identidade composta do scan e ambas estavam pendentes. O preenchimento rápido pela tabela local de campos as havia classificado como candidatas CF art. 40 isolado.
- A abertura direta pelo ícone **Complementar Ato** cria um formulário sem interessado selecionado. Em cada caso havia exatamente um rádio com interessado igual ao alvo; a seleção explícita desse rádio fez `READ_CURRENT_FORM` confirmar identidade e habilitou o preenchimento. Não selecionar nenhum vizinho.
- Os preenchimentos manuais 24 e 25 terminaram `PREENCHIDO`, seis campos alterados e seis relidos iguais à proposta, zero preservados, zero não resolvidos e obrigatórios satisfeitos. Ambos permanecem pendentes; não houve **Complementar Ato**, envio, assinatura ou tramitação final.
- A evidência completa do plano de preenchimento mostrou que os dois casos não são isolados: referências incluem EC 41/2003 (arts. 6 e 7), CF art. 40 (§ 5) e LCE 308/2005 (art. 87). Ambos selecionaram `EC41_TRANSITION_TEACHER`, método de regra, confiança 0,982258, margem 0,007730, `hard_conflict=false` e aviso `low-margin`. Portanto, são evidência útil para correspondência de baixa margem, mas não fecham CF art. 40 isolado.
- Em ambos a modalidade foi selecionada automaticamente por `catalog-token-overlap`, confiança 0,84, margem 0 e quatro avisos (`equivalent-candidates`, desempate por índice, baixa confiança e baixa margem). A escolha continua para revisão humana.
- A divergência entre a pré-triagem da tabela `fields` e as referências completas do plano foi concreta: não usar apenas as linhas rápidas para declarar uma base isolada. Nenhum código foi alterado; não há defeito confirmado que justifique correção sem reprodução RED.
- Nenhum teste foi executado. Validação foi portal real, identidade hash-only contra scan 10 e releitura local. Capturas do processo permanecem ignoradas em `tmp/`.

### Retomada

1. Não repetir preenchimentos 24/25; manter os formulários pendentes para revisão e conclusão manual.
2. Encontrar outra amostra real de CF art. 40 isolado por análise estruturada dos documentos já baixados; não usar apenas `fields` para afirmar isolamento e não rodar OCR quando houver texto embutido.
3. Manter o scan 10/marcador como contexto; qualquer nova linha deve bater processo + interessado, estar `PRECISA_COMPLEMENTAR`, e o frame ativo deve ser confirmado antes do fill.
4. Continuar o parcial A/B/C e revisar os casos EC41/ECE20 já preenchidos; stale, ambíguo e fim da fila ficam pendentes se não surgirem naturalmente.
5. Depois da cobertura live, fazer revisão adversarial, gates finais, ZIP/smoke standalone, atualizar o handoff e push somente `codex/atos-tce-unified`.

## 2026-09-27 — parcial A/B/C e busca textual CF art. 40

- O marcador foi selecionado manualmente pela operadora; manter a seleção e conferir por fingerprint contra o scan 10 antes de novo comando. Não repetir o scan.
- A busca local sem OCR percorreu 117 PDFs com texto embutido (342 páginas com texto). Os seis candidatos filtrados por referência rápida a CF art. 40 continham referências legais adicionais; nenhum confirmou CF art. 40 isolado. A lista `fields` é apenas triagem e não prova isolamento.
- Uma amostra pendente com conflito em data de publicação foi aberta pela navegação oficial. A identidade composta foi confirmada localmente contra o scan e o interessado único foi selecionado. O campo em conflito estava presente, habilitado e vazio; o processo está em `REVISAR`, não `PRONTO`.
- O serviço recusou a solicitação de preenchimento manual antes de criar pedido ou alterar campo, pois exige correspondência única em `PRONTO`. Os demais três casos com conflito obrigatório também estão `REVISAR`; não há candidato `PRONTO` com falta/conflito nos campos obrigatórios. Não contornar esse gate.
- O formulário permanece sem campos preenchidos. Nenhuma ação final ocorreu. Os preenchimentos 21–25 omitiram a proposta opcional de gênero; isso é sinal parcial, mas não demonstra comportamento real de preenchimento parcial com conflito/controle obrigatório. A cobertura A/B/C permanece aberta.
- Nenhum código ou teste foi alterado/executado. Sem defeito confirmado, não iniciar correção por hipótese; a validação desta etapa foi leitura do estado local e do formulário live.

### Retomada

1. Validar Próximo Processo entre páginas com correspondência exata da identidade composta, elegibilidade pendente e fingerprint do marcador; não finalizar formulário algum.
2. Procurar um CF art. 40 isolado usando referências completas dos documentos baixados, sem OCR quando o PDF já contém texto.
3. Manter o caso `REVISAR` sem preenchimento; só executar teste A/B/C se surgir um caso elegível suportado pelo serviço.
4. Continuar a revisão de EC 41/2003, ECE/RN 20/2020, baixa margem e preservação EC 47/2005 com evidência de plano completo.
5. Ao terminar os casos live viáveis, executar revisão adversarial, gates finais, smoke de extração limpa e registrar o status real; push apenas em `codex/atos-tce-unified`.

## 2026-09-27 — Próximo Processo cruza página 11 → 12

- A operadora confirmou que o marcador estava selecionado. Fingerprint local do seletor atual correspondeu ao scan 10 sem ler ou exibir o rótulo/valor.
- A leitura da página 11 encontrou 30 linhas. Comparação hash-only de processo + interessado conferiu as 30 contra a fatia correspondente do scan 10; havia pendências na página e a última linha pendente era a posição 330. O próximo registro pendente do scan é a posição 340, página 12.
- A ação oficial da linha abriu a posição 330. A tela de seleção tinha um único rádio; após selecioná-lo, `READ_CURRENT_FORM` confirmou por fingerprint a identidade exata da posição 330, com sete controles de formulário. Nenhum campo foi escrito.
- O botão oficial **Próximo processo** foi acionado com essa identidade atual confirmada. A solicitação `OPEN_NEXT_ACT` terminou `SUCCEEDED`, `action=next_act_ready`, `screen=form`; a identidade relida correspondeu por hash à próxima pendência esperada da posição 340. O comando preservou contexto do scan 10. Isso demonstra avanço até a página 12 sem wrap.
- Depois da abertura, o formulário alvo ficou ativo e o content snapshot não expôs uma lista visível para confirmar independentemente o número da página; a evidência do cruzamento é a sequência da página 11, o comando concluído e o alvo exato da posição 340 (página 12). Nenhum preenchimento, complemento, envio, assinatura ou tramitação foi realizado.
- Estado atual: formulário da posição 340 aberto, vazio e pendente para eventual revisão; atos 21–25 continuam sem ação final. Não repetir a abertura nem avançar novamente sem primeiro confirmar o contexto atual.
- Código e testes inalterados neste checkpoint. A validação foi live com fingerprints e resultado estruturado local, sem reproduzir identidades.

### Retomada

1. Registrar e preservar este formulário vazio; não finalizar.
2. Prosseguir a busca local estruturada por candidato EC 41/2003 isolado, CF art. 40 isolado, EC 47/2005 e parcial A/B/C. CF art. 40 isolado ainda não encontrado; o parcial com conflito permanece `REVISAR` e sem alteração.
3. Se continuar matriz Próximo Processo, exigir identidade exata atual + pendência + marcador antes de cada avanço; stale, ambíguo e fim da fila ficam pendentes se não ocorrerem naturalmente.
4. Completar revisão adversarial, gates pedidos, smoke de extração limpa e o handoff final; fazer push somente para `codex/atos-tce-unified`.

## 2026-09-27 — Task 10: preenchimento 26 e evidência parcial

- A identidade aberta na posição 340 foi confirmada hash-only contra o scan 10, pendente e `PRONTO`; 17 PDFs locais do processo continham texto pesquisável (46 páginas), sem OCR. A base documental inclui EC 41/2003 e LCE 308/2005, portanto é mista.
- O preenchimento manual 26 terminou `PREENCHIDO`; o comando `FILL_FORM` terminou `SUCCEEDED`, identidade exata, seis campos obrigatórios alterados e os seis `after == proposed`; zero preservados/não resolvidos; `mandatory_satisfied=true`. O processo segue pendente no scan 10 porque o clique final não ocorreu.
- Decisão legal: `EC41_TRANSITION_GENERAL`, método `rule`, confiança 0,976, margem 0,205545, sem hard conflict/avisos. A opção do portal selecionada combina EC 41/2003 (arts. 6 e 7) com EC 47/2005 (art. 2); não é EC 41 isolada. A evidência de documentos do caso também contém LCE 308/2005.
- Modalidade: `selected` por `catalog-token-overlap`, confiança 0,84, margem 0, quatro avisos de equivalência/desempate/baixa confiança/baixa margem. Revisão humana da opção permanece necessária. O portal não foi complementado, enviado, assinado ou tramitado.
- Evidência parcial A/B/C já presente em execução live anterior: o pedido manual 11 concluiu `FILL_FORM` com cinco campos gravados e relidos iguais; `modalidade` ficou `option_unavailable`, o resumo registrou obrigatório não satisfeito e evento `form_filled_partial`; o processo permaneceu `PRONTO`. Isso confirma escrita parcial sem rollback e retry do processo. Diferenciar o estado terminal do pedido do estado do processo.
- A pesquisa robusta dos 354 pendentes não encontrou fundamento EC 41 isolado nos campos estruturados. Dois candidatos com CF art. 40 isolado na pré-triagem (posições 379 e 797) foram conferidos em 44 PDFs com texto (90 páginas); ambos tinham documento adicional com EC 41 + CF art. 40 + LCE 308. A posição 379 está `PENDENTE`; 797 está `PRONTO`, mas nenhum deles prova CF art. 40 isolado.
- A evidência EC 47 previamente preservada permanece válida: pedidos 12 e 15 mantiveram `fundamento_legal` com `before == after` e evidência EC 47. Os resultados ECE/RN 20/2020 e correspondência fraca/não literal já registrados nos pedidos 21/23 continuam como revisão, não aprovação jurídica.
- Não houve mudança de código nem testes neste bloco; os dados/capturas são locais e ignorados. `git diff --check` será executado junto do commit do handoff.

### Retomada

1. Não repetir o preenchimento 26 nem clicar o botão final; deixar o formulário pendente para revisão humana.
2. EC 41 isolada e CF art. 40 isolada continuam sem amostra real comprovada; os candidatos examinados são mistos. Não promover uma amostra mista a isolada.
3. Parcial A/B/C, EC 47 preservada, ECE/RN 20/2020 e correspondência fraca têm evidência registrada; manter as ressalvas de revisão humana.
4. Concluir revisão adversarial, gates finais, ZIP standalone e smoke em extração limpa. Não promover `main`; stale/ambíguo/fim de fila só se valida por caso real natural ou pelos testes focados sem alterar o portal.

## 2026-09-27 — Bloqueio de navegação e revisão offline

- A operadora confirmou que o marcador estava selecionado. A página do Chrome DevTools estava autenticada, mas no menu inicial da Área Restrita, sem lista/formulário de processo ativo.
- Foi acionado uma vez o botão oficial **Próximo processo** usando a fila local já existente (scan 10, sem novo scan). O portal mostrou **Acesso negado** para `pessoas-associadas`. A navegação foi interrompida nesse ponto; não insistir no mesmo caminho nem contornar permissões. Nenhum campo foi preenchido e nenhuma ação final ocorreu.
- e-Contas não foi aberto nem usado. Ele serve à aquisição/baixamento; esta etapa trata somente da Área Restrita, Mesa Local e extensão.
- Baseline offline da extensão: `npm test --prefix extension` — 190 testes, 190 aprovados, 0 falhas.
- Revisão adversarial sintética reproduziu uma falha em `findInterestedRadio`: quando duas linhas têm nomes que normalizam para a mesma identidade, `openAct` retorna sucesso e clica na primeira correspondência. A asserção de falha fechada falhou como esperado. Isso é evidência de teste sintético, não observação do portal real.
- Naquele checkpoint não houve mudança de código. O objetivo V1 atualizado lido nesta retomada aceita a evidência live existente e limita mudanças a blockers reproduzíveis; não repetir discovery nem busca por casos jurídicos raros. Para a V1, o README, o empacotador e o objetivo apontam `extension/` como runtime distribuído.
- O marcador permaneceu intocado. O scan 10 continua sendo a fila local de referência. Dados privados e identidades não foram incluídos neste handoff.

### Retomada

1. Não repetir a navegação que recebeu **Acesso negado**; a V1 já aceita as evidências same-page/cross-page anteriores e não requer nova rodada live.
2. e-Contas é somente para baixar processos; não faz parte da complementação de atos.
3. O próximo marco é fechar gates, pacote e transferência do `data` separadamente; promover para `main` somente após o teste de dados em layout limpo.

## 2026-09-27 — Correção de blockers e pacote V1

- O objetivo V1 atualizado foi lido. Ele aceita a evidência live já registrada, considera EC 41/CF art. 40 mistos como limitação de backlog e orienta não repetir discovery ou casos já comprovados.
- A revisão adversarial isolada reproduziu um blocker de identidade: duas linhas de interessados normalizadas para a mesma identidade faziam `openAct` clicar na primeira. O teste novo falhou antes da correção; `findInterestedRadioCandidates` agora enumera os matches e `openAct` retorna `INTERESTED_AMBIGUOUS` sem clicar quando há mais de um. O caminho exato único continua selecionando apenas seu rádio.
- Incluído `LEIA-ME-OUTRO-PC.txt`; builder e verificador agora exigem e empacotam o guia junto do programa.
- Gates no estado atual: Python raiz 663/663; extensão 191/191; web 32/32; contrato de pacote 15/15; `verify-project.ps1` executou 1.260 verificações, 1.258 aprovadas, 0 falhas, 2 skips; `git diff --check` passou.
- `verify-package.ps1` passou com smoke de extração limpa: health `ok`, schema 7, extensão 0.1.0, 517 entradas e 430 arquivos de runtime. O cleanup emitiu aviso de acesso negado ao encerrar; confirmação independente mostrou porta fechada e diretório temporário removido.
- ZIP gerado em `dist/Atos-TCE-portable.zip`: 96.156.289 bytes; SHA-256 `ee917bddd7b113f78ab03e86332368c6e33f88a45d0cd0b849f0c9444bfd92bc`. O ZIP não contém `data`, PDFs ou ferramentas de desenvolvimento; inclui o guia.
- Health da Mesa confirma `data` relativo ao projeto (`C:\Users\slvma\Downloads\Github\Atos-TCE\data`) e 1.294 processos. A base tem 15.923 registros de documentos, todos com arquivo existente dentro de `data`, sem caminho absoluto/externo ou PDF ausente. `archive` contém 15.392 PDFs em `blobs` e 15.392 em `processos`; 30.784 arquivos PDF no total. A pasta completa ocupa 20.471.032.764 bytes. Portanto, nenhuma outra pasta do acervo é necessária.
- A cópia completa para `C:\TCE-Atos` não foi iniciada: o auto-review recusou a duplicação de 20,47 GB de dados privados fora do workspace e instruiu pedir aprovação explícita. O destino estava ausente; o acervo original não foi alterado.
- O checkpoint de código/documentação foi commitado e enviado ao GitHub: `a45bcb828cab30cb1cb0820de76b1748beef1c9c` em `codex/atos-tce-unified`. `origin/main` continua em `b1d41e848c39cb61947b011501925c40f86793fb`; a promoção está pendente do teste separado de `data`.

### Retomada

1. Solicitar aprovação explícita para criar `C:\TCE-Atos` e copiar a pasta `data` inteira para o teste de transferência. Gerar snapshots SQLite consistentes na cópia, sem tocar na origem.
2. Nesse layout, iniciar o ZIP, confirmar health e contagem, abrir um processo, um documento e um PDF; confirmar que a extensão do ZIP carrega.
3. Depois do teste, atualizar este handoff, commit/push no branch `codex/atos-tce-unified` e promover para `main` somente por fast-forward se `origin/main` ainda permitir.

## 2026-09-27 — Mesa original: leitura de documento/PDF

- Validação somente leitura no Chrome da Mesa original: uma tela de detalhes de processo já estava aberta, com seis ações **ver fonte**. Acionei uma delas; o visualizador renderizou canvas visível e carregou um recurso PDF.
- Isso confirma que a Mesa atual consegue exibir documento/PDF do acervo original. Não valida a cópia de `data` em `C:\TCE-Atos`; essa cópia segue sem aprovação e não foi criada. Nenhuma identidade foi registrada e nenhuma análise/ato foi alterado.

## 2026-09-27 — Separação dos portais no guia

- Esclarecido que e-Contas serve apenas para adquirir/baixar processos; a complementação assistida é feita na Área Restrita com a Mesa Local e a extensão.
- README e guia de outro PC agora dizem explicitamente que o login no e-Contas não é uma etapa da complementação de atos.
- ZIP regenerado com os documentos atualizados: `dist/Atos-TCE-portable.zip`, 96.156.444 bytes, SHA-256 `62371e9ca0e9a304996510f3afee1d5a627358cc787a6be3745bfdf48451187b`. Verificação de pacote: 517 entradas, 430 arquivos de runtime; smoke de extração limpa `health=ok`, schema 7 e extensão 0.1.0. O script avisou `Acesso negado` ao encerrar; confirmei em seguida que o processo/porta do smoke e a pasta temporária foram removidos.
- Nenhum código, sessão autenticada, processo ou ato foi alterado. Validação documental por leitura do diff e `git diff --check`; sem testes de código por ser ajuste somente de documentação.
- Retomada: concluir o teste do ZIP com uma cópia separada da pasta `data` após autorização para criar o destino/cópia, então fast-forward seguro para `main`.

## 2026-09-27 — Revalidação final no HEAD 3bae5a0

- O health live em `127.0.0.1:18743/api/v1/health` respondeu `ok`, schema 7, `data_root=data`, `database=data\atos-tce.db`, 1.294 processos. No diretório de trabalho do projeto, o root resolvido é `C:\Users\slvma\Downloads\Github\Atos-TCE\data`.
- Inventário somente leitura atualizado: 15.923 linhas de documentos; todos os caminhos são relativos, internos a `data` e existem. A árvore contém 36.043 arquivos, 20.722.449.992 bytes e 33.158 PDFs. `archive/` tem 30.784 PDFs; `econtas-preparacao-2026-09-25/` tem outros 2.374 PDFs e é conteúdo de aquisição/download, separado da complementação de atos conforme esclarecimento do usuário. Ambos estão dentro do `data` que o plano manda transferir integralmente.
- Gates pedidos no HEAD `3bae5a02785febff84ca56de9df1eb613a97cb54`: Python raiz 663/663; extensão 191/191; web 32/32. `verify-project.ps1`: 1.260 executados, 1.258 aprovados, 0 falhas, 2 skips; todos os sete estágios passaram. `git diff --check` passou.
- O ZIP atual permanece em 96.156.444 bytes, SHA-256 `62371e9ca0e9a304996510f3afee1d5a627358cc787a6be3745bfdf48451187b`; seu smoke real de extração limpa já passou com health `ok`, schema 7, 517 entradas, 430 arquivos de runtime e extensão 0.1.0. A verificação live anterior confirmou visualização de documento/PDF no acervo original.
- `C:\TCE-Atos` continua ausente. Nenhuma cópia de `data` foi criada. O teste ZIP + acervo separado e a promoção fast-forward para `main` continuam dependentes de autorização específica para essa cópia temporária integral; o pedido anterior permanece sem resposta.
- Retomada exata: após aprovação, copiar `data` inteira uma vez para `C:\TCE-Atos\data`, iniciar o ZIP nesse layout, verificar health/Mesa/contagem, abrir processo/documento/PDF, status/análises e extensão carregada; atualizar handoff e só então promover unified para `main` por fast-forward.
