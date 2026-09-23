# Atos-TCE M5, fundamento v4 e próximo processo — handoff

Data: 2026-09-23

## Estado atual

- `origin/main` foi promovida por fast-forward de `ffa208f6782cff080df4c84fd8c60b2a1932a246` para `b1d41e848c39cb61947b011501925c40f86793fb`, igual a `origin/codex/mesa-local-refactor`.
- Ancestralidade confirmada após novo fetch: `git merge-base --is-ancestor origin/codex/mesa-local-refactor origin/main` retornou 0. Push normal concluído; sem force-push.
- Implementação iniciada na branch `codex/best-effort-form-filling`, criada do `main` promovido, no clone isolado `.worktrees/atos-tce-baseline`.
- Checkout original preservado sem alterações por esta execução. Ele já continha 17 arquivos modificados e `work/tce-extractor/.codex-live-pilot.py` não rastreado.

## Gates de baseline antes da promoção

- `python -m unittest discover -s tests -p "test_*.py" -q`: 573 executados, 573 passaram incluindo 1 skip. A primeira tentativa no worktree gerenciado falhou em 3 testes de empacotamento por restrição de escrita; repetida com permissão no mesmo commit e passou.
- `npm test --prefix extension`: 135 passaram, 0 falhas.
- `node --test app/web/tests/*.test.mjs`: 20 passaram, 0 falhas; houve aviso não bloqueante `MODULE_TYPELESS_PACKAGE_JSON`.
- `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1`: 1258 verificações, 1256 passaram, 0 falhas, 2 skips. Todos os 7 estágios passaram. Logs temporários em `%TEMP%\tce-project-verification-7b4e29484dfb4e9fbc527902c3fb93ee`.
- `git diff --check`: passou.
- Observação de layout: o gate oficial deste checkout é `work/tce-extractor/verify-project.ps1`, conforme `AGENTS.md`.

## Task 1 do plano — catálogo selecionável

- Criados 3 testes para excluir placeholders e valores/rótulos vazios, impedir fallback do label para `value`, e preservar valor bruto/índice original.
- RED confirmado: os 3 testes falharam por `AttributeError` porque `selectable_legal_options` ainda não existia.
- GREEN: helper implementado em `app/analysis/legal.py`; os 3 testes passaram e `python -m unittest tests.test_legal_rules -v` passou (27 testes, 0 falhas).
- Nenhum oracle v3 foi alterado; a escolha final ainda permanece v3 até completar o Task 2.

## Task 2 do plano — legal-foundation-v4

- RED confirmado nos contratos para fonte incompleta/contraditória, classe desconhecida, hard conflicts, thresholds, empate e catálogo vazio.
- Implementado `legal-foundation-v4`: texto documental é ranqueador; opções reais são filtradas pelo helper canônico; hard conflicts preferem candidatas sem conflito quando disponíveis e, caso contrário, a melhor candidata real é selecionada. Empate termina pelo índice original e produz warnings. Confiança/margem continuam diagnósticos.
- A decisão passa a `selected/AUTO_SELECTED` somente com `option_value` selecionável no catálogo; a validação de membership também existe no resolver. Sem texto ou sem opção real, não inventa seleção.
- O teste v3 deixou de exigir igualdade da decisão final. Harness e README identificam o JS como histórico v3; parser, normalizador, perfil e assinatura de catálogo continuam em paridade. Nenhum oracle JS foi alterado.
- O fixture com placeholder mostrou divergência preexistente: o oracle JS preserva `value=""`, mas `_option_parts()` Python o substituía pelo label. Corrigido para preservar o valor bruto e manter a paridade histórica.
- GREEN: `python -m unittest tests.test_legal_rules -q` — 32 testes, 32 passaram, 0 falhas. `git diff --check` passou.

## Task 3 do plano — preflight best-effort

- RED confirmado ao substituir os contratos antigos de bloqueio global: proposta obrigatória ausente, controle ausente/read-only, divergência existente e opção legal não literal falharam pelos `FillBlocked`/matcher anteriores.
- `build_fill_plan()` agora mantém hard blocks apenas para processo/formulário sem identidade suficiente, incompatibilidade de identidade e generation inválida. Proposta/controle ausente, disabled/read-only, divergência e opção comum indisponível viram warnings de campo e os demais campos permanecem no plano.
- Valores divergentes são registrados em `preserved` sem reescrita. A modalidade usa apenas valor/label de opção real; valor vazio e placeholder não podem vencer. Fundamento legal passa primeiro pelo resolver v4, valida membership no catálogo selecionável e nunca cai no matcher literal genérico; catálogo placeholder-only deixa o campo pendente e mantém os demais.
- RED adicional confirmou que o matcher comum aceitava um `<option>` com valor vazio por label; corrigido e coberto.
- Atualizados testes de preflight, fallback manual e orquestração API para parcial best-effort. A identity ausente na origem também bloqueia explicitamente.
- GREEN: `python -m unittest tests.test_fill_service -q` — 57 testes, 57 passaram; `python -m unittest tests.test_legal_rules -q` — 32/32; `python -m unittest tests.test_api_server -q` — 85/85. `git diff --check` passou.
- Arquivos alterados: `app/area_restrita/preflight.py`, `tests/test_fill_service.py`, `tests/test_api_server.py`.

## Task 4 do plano — leitor com controles parciais

- RED confirmado: leitor retornou `null` para formulário com identidade válida e controle `matricula` ausente, pois a versão anterior exigia todos os controles mapeados.
- Separadas as sentinelas de identidade (`txtNumeroProcesso`, `txtAnoProcesso`) dos controles de conteúdo. O formulário também precisa de uma raiz do ato, e os dois campos de identidade devem pertencer a ela; rádio de interessado selecionado continua obrigatório para identidade.
- `readForm()` inclui cada controle presente e omite campos ausentes, permitindo que o backend registre o controle como faltante. Sem âncoras de identidade, interessado selecionado ou raiz de formulário, a leitura continua recusada.
- RED adicional provou que números de processo fora da raiz de formulário não qualificam a página; a validação da raiz foi mantida fail-closed.
- GREEN: `node --test extension/tests/detect-form.test.mjs` — 12 testes, 12 passaram.
- Arquivos alterados: `extension/content/detect-form.js`, `extension/tests/detect-form.test.mjs`, `extension/tests/fake-dom.mjs`.

## Task 5 do plano — filler independente por campo

- RED confirmado em oito casos que antes recusavam o request ou mudavam campos válidos para `skipped`: select indisponível, disabled/read-only, proposta vazia, ausência de controle, falhas de escrita/releitura e valor divergente.
- Guardas globais de formulário, identidade e generation continuam antes de qualquer escrita. Identity incompleta/mismatch, reader ausente e generation ausente/stale retornam `ok:false` sem writes.
- Após os guardas, cada proposta recebe `field_results` próprio: `changed`, `preserved`, `missing_proposal`, `not_found`, `disabled`, `option_unavailable` ou `failed`. Divergência existente fica preservada com `existing_value_divergence`; placeholder selecionado é tratado como vazio; valor de select deve pertencer ao catálogo atual e não pode ser placeholder/disabled.
- Campos graváveis são escritos, relidos individualmente e a execução continua após falha daquele campo. Exceção de releitura permite continuar somente quando visibilidade e identidade do formulário continuam confirmadas.
- `ok:true` indica que os guards passaram e o passe por campo terminou; resultados parciais permanecem nos campos/warnings. Nenhuma capacidade de submit/finalização foi adicionada.
- GREEN: `node --test extension/tests/fill-form.test.mjs` — 17/17; `npm test --prefix extension` — 140/140; `git diff --check` passou.
- Arquivos alterados: `extension/content/fill-form.js`, `extension/tests/fill-form.test.mjs`.

## Task 6 do plano — resultado da tentativa separado do status do processo

- RED: os novos testes não importaram porque `summarize_field_results` ainda não existia; após a implementação mínima, testes de ordenação e um caso de catálogo jurídico apenas com placeholder falharam com expectativas comportamentais, e foram corrigidos antes de prosseguir.
- O serviço agora produz resumo determinístico por campo (`changed`, `preserved`, `unresolved`, `warnings`, `mandatory_satisfied`). Divergência de valor preservado e falha de releitura não são confundidas com sucesso; proposta/controle/opção ausente gera resultado local e os demais campos continuam.
- Uma tentativa completa pode terminar `PREENCHIDO` com warnings. O processo só passa a `PREENCHIDO` se todos os campos obrigatórios forem satisfeitos; em resultado parcial, erro técnico ou bloqueio, o processo continua `PRONTO` e pode iniciar nova tentativa.
- `_block()` e `_fail()` agora atualizam somente a fill request e acrescentam eventos (`fill_blocked` / `fill_failed`). Erros de identidade/formulário/processo classificam a request como `BLOQUEADO`; falha de preflight não identitária termina em `ERRO`.
- `STALE_GENERATION` agenda exatamente um novo `READ_FORM`, guarda o contador no `form_snapshot` e reexecuta preflight. Uma segunda ocorrência encerra a request em `ERRO`; identidade divergente nunca recebe retry.
- Não houve migração/schema: o retry counter e o resumo usam o JSON de `form_snapshot` existente.
- RED/GREEN focal: `python -m unittest discover -s tests -p 'test_fill_service.py' -q` — 66 testes, 66 passaram; `python -m unittest discover -s tests -p 'test_store.py' -q` — 19/19.
- Atualizado o contrato de integração que antes bloqueava divergência de releitura: `python -m unittest discover -s tests -p 'test_api_server.py' -q` — 85 testes, 85 passaram. A primeira execução encontrou só a expectativa antiga; após atualizar o teste, a repetição completa passou.
- `git diff --check`: passou.
- Ruling: uma rejeição de preflight fora de identidade/formulário/processo termina como `ERRO` da tentativa, não `BLOQUEADO` — isso mantém BLOQUEADO reservado ao risco de alvo errado e o processo retryable — custo se incorreto: uma recusa preventiva pode aparecer como falha técnica.
- Ruling: `python -m unittest tests.test_fill_service/test_store/test_api_server/test_web_suite -v` não importa porque `tests/` neste checkout é diretório plano sem pacote Python; usar descoberta explícita `-s tests -p <arquivo>` executa os mesmos módulos — custo se incorreto: a descoberta pode omitir testes, mitigado pela confirmação do padrão e contagem dos módulos.
- Arquivos alterados: `app/area_restrita/fill_service.py`, `tests/test_fill_service.py`, `tests/test_api_server.py` e este handoff.

## Task 7 do plano — API de resultado parcial

- RED: o teste end-to-end aceitou `changed` + `disabled`, avançou a fill request e preservou o processo como `PRONTO`, mas falhou com `KeyError` porque o GET autenticado ainda não projetava `summary`.
- A rota existente `/api/v1/fill-requests/{id}` agora retorna o resumo já persistido e `operation_warnings`; não retorna `form_snapshot` bruto e não cria rota de mutação nova.
- O teste verifica campos `changed`, `preserved`, `unresolved`, warning por campo, warnings operacionais e status `PRONTO`; outro teste confirma que ausência de `field_results` continua sendo HTTP 400.
- Ruling: `_fill_result_problem()` já validava estrutura e presença de `status` sem exigir sucesso de todos os campos; mantido sem alteração redundante, com teste HTTP provando aceitação de `disabled` — custo se incorreto: uma futura restrição de status pode reintroduzir rejeição global.
- GREEN: teste focal `partial_fill_results` — 1/1; teste de `field_results` ausente — 1/1; `python -m unittest discover -s tests -p 'test_api_server.py' -q` — 86/86; `git diff --check` passou.
- Arquivos alterados: `app/api/server.py`, `tests/test_api_server.py` e este handoff.

## Task 8 do plano — resumo parcial na Mesa

- RED: os asserts de wiring falharam porque a Mesa não possuía `renderFillSummary` nem uma lista de avisos para o resultado da request.
- A Mesa agora mostra contagens de alterados, preservados e pendentes de revisão, com instrução explícita para conferir o formulário e concluir manualmente no portal. A lista identifica campo + código/motivo e cria os nós com `textContent`.
- O resumo da última tentativa é mantido por processo enquanto a tela de detalhes é atualizada. O botão continua elegível apenas pelo status documental `PRONTO`, mesmo após request parcial/técnica; processo `PREENCHIDO` pode continuar exibindo o resumo sem ação de preenchimento.
- Nenhum controle ou endpoint de submit/send/finalize foi adicionado; `index.html` não precisou mudar.
- GREEN: `node --test app/web/tests/*.test.mjs` — 24/24; wrapper `python -m unittest discover -s tests -p 'test_web_suite.py' -v` com `PYTHONUTF8=1` — 2/2; `git diff --check` passou. O wrapper sem UTF-8 falhou na captura de saída Node devido à página de código cp1252 do Windows; rerun UTF-8 passou. O warning Node `MODULE_TYPELESS_PACKAGE_JSON` preexistente continua não bloqueante.
- Arquivos alterados: `app/web/app.js`, `app/web/app.css`, `app/web/tests/ui-wiring.test.mjs` e este handoff.

## Task 9 do plano — contrato integrado backend/extensão

- Ruling: a Task 9 é explicitamente test-only após Tasks 1–8 e não prevê correção de produção; portanto, os novos testes servem como hardening de uma cadeia já implementada, sem introduzir falha artificial — custo se incorreto: uma falha latente poderia passar; mitigação: a combinação ponta a ponta foi assertada junto dos cenários de filler/roteador e dos gates proibidos.
- O teste de `FillService` cobre `READ_FORM -> build_fill_plan -> FILL_FORM -> field_results -> summary`: texto legal documental diferente do rótulo, option value selecionável `EC41`, controle obrigatório ausente, matrícula divergente preservada, campos independentes relidos com o proposto e processo mantido `PRONTO` por pendências mandatórias.
- Testes do filler cobrem duas escritas válidas junto de controle ausente e valor real divergente; o roteador mantém o resultado parcial `ok:true` e propaga statuses/warning intactos.
- Primeiro run Node encontrou erro no próprio fixture (ID de teste `txtDataPublicacaoDOE` não existe); atualizado para o ID canônico `txtDataDOE`, sem mudança de produção.
- GREEN focado: descoberta Python de legal `32/32`, fill service `67/67`, API `86/86`; Node `detect-form + fill-form + router` `80/80`; protocolo proibido `9/9`; parity `3/3`.
- Arquivos alterados: `tests/test_fill_service.py`, `extension/tests/router.test.mjs`, `extension/tests/fill-form.test.mjs` e este handoff.

## Proteções e decisões

- Os anexos do goal são as fontes canônicas desta execução: design best-effort como SPEC e os dois documentos de implementação como planos obrigatórios. Foram lidos diretamente como entradas do usuário; não é necessário criar cópias no repositório.
- O diff original de melhor-esforço foi inspecionado e não foi portado: parte dele permite escrita em formulário com identidade divergente e substitui valor real divergente, contradizendo a SPEC. Mantê-lo preservado no checkout original; implementar no branch limpo com TDD.
- Não iniciar código de navegação até completar e registrar toda a PHASE 0 observada na Área Restrita real. A descoberta deve preceder qualquer implementação dessa função.
- Ainda não foi feita validação real supervisionada nem login nesta sessão.

## Pendências e retomada

1. Executar Task 10 do plano best-effort: gates completos, cinco casos supervisionados no portal real e criar `docs/notes/2026-09-23-best-effort-fill-validation-handoff.md`; login/ações no portal continuam humanos.
2. Criar branch de discovery a partir do `main` promovido; usar a sessão real da Área Restrita para concluir PHASE 0 e commitar somente a nota de discovery antes de qualquer código de navegação.
3. A partir do commit de discovery, criar a branch de navegação; integrar nela os commits Best-Effort/v4 sem perder a ordem de base exigida pelos planos.
4. Executar as suítes/gates de navegação, `verify-project.ps1`, `git diff --check`, validações reais supervisionadas e revisão final; publicar as branches.

## GitHub

- `main`: promoção publicada e verificada em `b1d41e8`.
- Branch de implementação: `.worktrees/atos-tce-baseline`, Tasks 1–9 publicadas em `origin/codex/best-effort-form-filling` até `1e7cb2b`; Task 6 `0cc808b`, Task 7 `c7c8edc`, Task 8 `258fb23`, Task 9 `1e7cb2b`.
