# Handoff — Best-Effort + Legal v4

**Data:** 2026-09-23
**Branch:** `codex/atos-tce-best-effort-v4`
**Base:** `b1d41e848c39cb61947b011501925c40f86793fb` (`origin/main` local tracking ref)

## Concluído

- Best-effort Task 1: adicionado `selectable_legal_options()` como filtro canônico de opções DOM reais. A função ignora placeholder, valor vazio, opção disabled/não selecionável, não usa label como fallback para value e preserva o `value` não vazio exatamente como recebido.
- Quatro testes novos em `tests/test_legal_rules.py` cobrem placeholder, ausência de value, valor literal do DOM e opções indisponíveis.
- Best-effort Task 2: `legal-foundation-v4` agora escolhe deterministicamente a melhor opção selecionável sempre que há texto documental e catálogo real. Baixa confiança/margem, empate, conflito, classe desconhecida e referência incompleta/contraditória ficam como warning. Valor de opção preserva a forma bruta do DOM.
- O seletor desempata primeiro por ausência de hard conflict, score, correspondência estrutural, crosswalk, discriminadores, lexical e por último `option_index`. A SPEC manda desempatar por componentes antes do índice, mesmo que o plano não enumere essa sequência.
- Oracles de decisão v3 seguem como histórico; os primitivos preservados continuam cobertos por paridade.
- Snapshot da extensão passa a reportar `disabled` por opção, inclusive quando o `<optgroup>` pai está desabilitado. Isso fecha a informação DOM necessária para o catálogo selecionável; a alteração está testada e será agrupada no commit de leitura de formulário do plano.
- Best-effort Task 3: `build_fill_plan()` agora bloqueia somente processo/identidade/generation, produz warnings de conteúdo por campo, preserva valores existentes divergentes e deixa campos independentes seguirem. `fundamento_legal` é resolvido antes de qualquer matching literal e validado contra as opções atuais selecionáveis.
- Best-effort Task 4: o leitor reconhece um formulário com âncoras de processo e pessoa interessada válidas mesmo se um controle de conteúdo estiver ausente; a propriedade daquele campo fica ausente no snapshot, sem fabricar estado vazio.
- Best-effort Task 5: `FILL_FORM` passou a validar e tentar cada campo independentemente. Falta de proposta/controle, controle disabled/read-only, opção indisponível, divergência não vazia e falha isolada de escrita/releitura ficam no resultado do campo. Valores divergentes são preservados; problemas de conteúdo não impedem os campos seguintes.
- O leitor DOM agora isola exceções de leitura em cada controle de conteúdo, mantendo identidade e os demais controles disponíveis. O preflight exclui do plano controles ilegíveis e registra `FIELD_READ_FAILED`.
- Best-effort Task 6: a solicitação de preenchimento termina `PREENCHIDO` com resumo mesmo se parcial; o processo só passa de `PRONTO` a `PREENCHIDO` se os seis campos obrigatórios estiverem satisfeitos. Estado de solicitação `ERRO`/`BLOQUEADO` gera evento sem alterar a classificação documental do processo.
- `STALE_GENERATION` permite exatamente uma nova leitura e planejamento com nova geração. Um segundo stale encerra a solicitação como `ERRO`; as duas tentativas mantêm o processo em `PRONTO` e o guard do content script escreve zero controles quando a geração já está stale.
- Best-effort Task 7: o resultado FILL_FORM aceita sucesso parcial estruturado; `GET /api/v1/fill-requests/{id}` retorna o resumo persistido (`changed`, `preserved`, `unresolved`, `warnings`, `complete`) mantendo sessão Mesa e contrato de autenticação existentes.
- Best-effort Task 8: a Mesa exibe contagens alteradas/preservadas/revisão, motivos por campo e instrução explícita de conclusão manual. O resumo é reaplicado após recarregar o detalhe; a ação permanece disponível quando o status documental é `PRONTO`, inclusive após resultado parcial/erro.
- Best-effort Task 9: integração com o preflight real cobre proposta legal documental não literal, escolha de valor presente no catálogo, controle `matricula` ausente, campos independentes preenchíveis e processo `PRONTO` com resultado parcial. O router MV3 conserva no relato tanto o campo `changed` quanto o campo `disabled`.

## Testes

- RED: `python -m unittest tests.test_legal_rules.SelectableLegalOptionsTests -v` — 4 erros esperados porque o helper ainda não existia.
- GREEN: `python -m unittest tests.test_legal_rules -v` — 28 testes, 28 aprovados, 0 falhas.
- RED: `python -m unittest tests.test_legal_rules.V4BestAvailableTests.test_equal_scores_use_semantic_components_before_catalog_index -v` — falhou como esperado, pois a primeira opção DOM ganhava o score empatado.
- GREEN: o mesmo teste direcionado passou; `python -m unittest tests.test_legal_rules -v` — 33 testes, 33 aprovados, 0 falhas.
- Snapshot DOM RED: `node --test extension/tests/detect-form.test.mjs` — 10/11 passaram; o novo teste falhou porque `disabled` não era reportado.
- Snapshot DOM GREEN: `node --test extension/tests/detect-form.test.mjs` — 11 testes, 11 aprovados, 0 falhas.
- RED: `python -m unittest tests.test_fill_service.PreflightTests -v` — 9 erros esperados nos contratos best-effort do preflight.
- RED adicional: um teste provou que controle legal disabled ainda entrava no plano; após incluir a guarda, passou.
- GREEN: `python -m unittest tests.test_fill_service.PreflightTests -v` — 21 testes, 21 aprovados, 0 falhas.
- GREEN da tarefa: `python -m unittest tests.test_fill_service -v` — 56 testes, 56 aprovados, 0 falhas.
- RED: `node --test extension/tests/detect-form.test.mjs` — o teste de formulário com `matricula` ausente falhou porque o leitor exigia todos os controles mapeados.
- GREEN: `node --test extension/tests/detect-form.test.mjs` — 11 testes, 11 aprovados, 0 falhas.
- RED Task 5: `node --test extension/tests/fill-form.test.mjs` — 17 testes, 8 aprovados, 9 falhas esperadas nas novas expectativas por campo; também revelou uma asserção antiga de opção ausente com bloqueio global, ajustada para `option_unavailable`.
- RED de releitura isolada: os novos testes do leitor e filler falharam por exceção propagada de getter; o teste do preflight incluiu um campo `readable=false` e falhou por esse controle ainda entrar no plano.
- GREEN extensão: `node --test extension/tests/detect-form.test.mjs extension/tests/fill-form.test.mjs` — 30/30; `npm test --prefix extension` — 141 testes, 141 aprovados, 0 falhas.
- RED Task 6: `python -m unittest tests.test_fill_service.BestEffortFillOutcomeTests -v` — falhas esperadas em partial/operational state e stale-replan antes da implementação.
- GREEN Task 6: `python -m unittest tests.test_fill_service -v` — 63 testes, 63 aprovados, 0 falhas; `python -m unittest tests.test_store -v` — 19 testes, 19 aprovados, 0 falhas.
- `git diff --check` passou após as mudanças de Tasks 5–6.
- RED Task 7: novo teste de API avançou pelo fluxo parcial e falhou apenas porque o GET não expunha `summary`.
- GREEN Task 7: `python -m unittest tests.test_api_server.FillOrchestrationTests.test_an_existing_divergent_value_is_preserved_while_other_fields_fill tests.test_api_server.FillOrchestrationTests.test_a_field_that_rereads_differently_remains_a_review_item tests.test_api_server.FillOrchestrationTests.test_partial_field_results_are_accepted_summarized_and_retryable -v` — 3/3.
- GREEN da suíte: `python -m unittest tests.test_api_server -q` — 86 testes, 86 aprovados, 0 falhas.
- RED Task 8: as asserções de interface falharam por não haver contagens, motivos, renderização após refresh nem resumo acessível ao operador.
- GREEN Task 8: `node --test app/web/tests/*.test.mjs` — 24 testes, 24 aprovados, 0 falhas; `python -m unittest tests.test_web_suite -v` — 2/2; `node --check app/web/app.js` passou.
- Regressão após detalhar alertas por campo: `python -m unittest tests.test_fill_service -q` — 63/63 e teste parcial de API 1/1 aprovados; `git diff --check` passou.
- GREEN Task 9: `python -m unittest tests.test_legal_rules tests.test_fill_service tests.test_api_server -q` — 183 testes, 183 aprovados, 0 falhas.
- GREEN extensão de integração: `node --test extension/tests/detect-form.test.mjs extension/tests/fill-form.test.mjs extension/tests/router.test.mjs` — 79/79.
- Guardas finais específicas: `node --test extension/tests/protocol.test.mjs` — 9/9; `python -m unittest tests.test_extension_parity -q` — 3/3; `git diff --check` passou.

## Arquivos

- `app/analysis/legal.py`
- `tests/test_legal_rules.py`
- `tests/fixtures/legal-cases.json`
- `tests/legal_parity_harness.mjs`
- `tests/oracles/legal/README.md`
- `extension/content/detect-form.js`
- `extension/tests/detect-form.test.mjs`
- `extension/tests/fake-dom.mjs`
- `app/area_restrita/preflight.py`
- `tests/test_fill_service.py`
- `extension/content/fill-form.js`
- `extension/tests/fill-form.test.mjs`
- `app/area_restrita/fill_service.py`
- `app/api/server.py`
- `tests/test_api_server.py`
- `app/web/app.js`
- `app/web/app.css`
- `app/web/tests/ui-wiring.test.mjs`
- Este handoff.

## Git e ambiente

- A ref local `origin/main` coincide com `origin/codex/mesa-local-refactor`; o branch de implementação parte desse SHA. `git fetch --prune origin` falhou por indisponibilidade de conexão com GitHub, então não foi possível refrescar refs remotas nesta sessão.
- O checkout original `codex/mesa-local-refactor` permanece intacto, com suas alterações preexistentes.
- O código de navegação ainda não foi alterado: Phase 0 exige concluir a observação real do formulário e do retorno antes de qualquer implementação dessa função.

## Discovery real em andamento

- Chrome perfil Matheus autenticado; lista do setor aberta no marcador normal, página 1/40, contagem visível 1.197.
- A leitura somente observacional dos frames detectou lista em frame interno e quadro de botões irmão; o scanner read-only existente confirmou 30 linhas na página 1.
- Comparação composta processo+interessado com o scan local de 21/09: 29/30 identidades correspondem; há drift de contagem/ordem. A página 1 contém apenas itens já concluídos. Primeiro `PRONTO` no scan salvo: posição 227 (página 8). Nenhum nome ou identificador individual foi registrado.
- A leitura atual confirmou novamente página 1/40, 30 linhas e total 1.197. A consulta por avaliação de DOM do tab de topo não atravessa os documentos de frame usados pela árvore de acessibilidade; requer diagnóstico pelo frame/CDP já permitido no plano. A divergência histórica segue sem resolução; não abrir processo por posição.
- Nenhuma ação de conclusão/envio foi executada.

## Próxima retomada

1. Executar integralmente os gates finais da Task 10, `verify-project.ps1`, `git diff --check` e revisão da branch contra SPEC + planos.
2. Prosseguir PHASE 0 em portal real: estabelecer Mesa/extensão atuais, reconciliar a sequência/página de limite e observar fluxo de interessado/formulário/retorno/estabilidade. Não clicar no botão final `Complementar Ato`.
3. A promoção e criação do branch de descoberta continuam limitadas pela impossibilidade de atualizar refs do GitHub; usar apenas os SHAs locais comprovados e registrar essa restrição.

## Atualização — auditoria de identidade e discovery real (23/09/2026)

### Correção de segurança em andamento

- Revisão independente encontrou que um `FILL_FORM` `ok=true` podia ser aceito sem eco de identidade ou `generation_after`, e que a resposta podia pertencer a outro interessado.
- Red confirmado: três testes novos falharam antes da correção — ausência de identidade, ausência de geração posterior e interessado divergente.
- Correção: API exige identidade e `generation_after` inteiro positivo; `FillService` compara a identidade de sucesso com o processo solicitado antes de resumir/promover. Divergência deixa o pedido `BLOQUEADO` e o processo documental `PRONTO`.
- Green atual: testes novos 3/3; `tests.test_fill_service` 64/64; `tests.test_api_server` 89/89; `git diff --check` passou. O commit da correção ainda não foi feito.

### Phase 0 — estado real observado

- `git fetch origin --prune` passou. `origin/main` e `origin/codex/mesa-local-refactor` são ambos `b1d41e848c39cb61947b011501925c40f86793fb`; `origin/codex/mesa-local-refactor` já é ancestral de `origin/main`. Promoção já contida; nenhuma ref foi movida.
- Branch de discovery criado no worktree isolado `C:\Users\slvma\.codex\worktrees\next-process-discovery\Atos-TCE`, a partir de `origin/main`: `codex/next-process-navigation-discovery`.
- Chrome Matheus autenticado, uma aba da Área Restrita, URL superior `/telaPrincipalMenu.asp`. Lista restaurada e visível na página 9; marcador normal mantido.
- Lista real: página 9, faixa 241–270, total 1.197; página 10, faixa 271–300, total 1.197. Scan local mais recente id 5 é de 21/09, total 1.198 e marcador salvo `5159`; valor bruto atual do DOM ainda não confirmado.
- Com identidade composta processo+interessado hasheada localmente, as 30 linhas da página 9 coincidem em ordem com as posições 239–268 do scan; as 30 da página 10 coincidem com 269–298. A fronteira é contígua. Há drift global de contagem de um item; causa não localizada. Não usar posição visual como identidade.
- Controle observado na linha: link `Complementar Ato`. Abre o formulário no mesmo tab nativo do portal, sem nova aba Chrome. Para os alvos testados, processo e interessado foram relidos por identidade composta; um radio de interessado vinha desmarcado e precisou ser selecionado. Nenhum campo foi preenchido.
- Frames observados: notificação `iframeNotificacoes`; lista em `iframeOBJ`/`iframe1`; cada abertura de formulário cria um novo `iframeOBJ` (`iframe2`…`iframe6`) e preserva anteriores escondidos. Rotas internas observadas: `ProcessonoSetor.asp`, `ComplementarAto.asp` e frame irmão `botoesNovo.asp` (queries omitidas).
- Retorno escolhido: `navigation_strategy: native_control`. O controle superior `Proc./ Doc. Eletrônicos` restaura lista, página e marcador; `iframe1` continua presente. `marker_restore: not_needed` para o retorno nativo testado. Troca lista/formulário ficou legível em cerca de 1,2 s; ações de linha até formulário com radio selecionado: 4,5 s, 3,0 s e 4,9 s; virar de página levou cerca de 5,3 s. São tempos de navegação, sem completar ato.
- Nos 60 itens verificados não apareceu processo com mais de um interessado. Não houve um caso C de escolha entre múltiplos interessados.
- Nenhum clique no botão final `Complementar Ato`; nenhum `SUBMIT`, envio ou finalização ocorreu.

### Phase 0 ainda incompleta — não iniciar código de navegação

- Serviço local da Mesa não está escutando em `127.0.0.1:18743`; a aba/painel da Mesa não estava aberta. Assim, o snapshot vivo `SCAN_PAGE` e o valor bruto atual do marcador continuam pendentes.
- A tentativa de abrir `chrome://extensions` foi bloqueada pela política de URL do Chrome; nenhuma alternativa para inspecionar essa página foi tentada.
- Ainda falta observar o retorno após uma conclusão real supervisionada. Essa ação é manual do operador em um processo controlado; não clicar pelo agente. Os três tempos acima não satisfazem a baseline estrita de partir de ato concluído/revisado.
- Nota de discovery fica no branch `codex/next-process-navigation-discovery`. Até concluir os itens acima e commitar a nota completa, nenhum código de navegação é permitido.

### Retomada

1. Usuário abre a Mesa Local e o painel da extensão existente no Chrome Matheus, sem trocar o marcador nem clicar no botão final.
2. Ler o snapshot `SCAN_PAGE` e confirmar marcador/ordem. Se o drift global permanecer, atualizar a estratégia SPEC antes da Task 1, conforme gate 0.5.
3. Fazer apenas uma validação de conclusão em processo de teste controlado sob decisão manual do operador; registrar o retorno resultante sem automação de submit.
4. Atualizar e commitar a nota Phase 0 completa no branch discovery. Só então criar `codex/next-process-navigation` a partir do commit de discovery e incorporar o branch de best-effort.

### Gate amplo e commit de segurança (23/09/2026)

- API: `python -m unittest tests.test_api_server -q` — 89/89 passou.
- Serviço de preenchimento: `python -m unittest tests.test_fill_service -q` — 64/64 passou.
- `git diff --check` passou antes da atualização deste handoff.
- Uma execução de `verify-project.ps1` em sandbox executou 952 testes/validações: 947 passaram, 3 falharam e 2 foram ignorados. Os três erros foram de permissão ao criar fixtures temporárias em `work/tmp` e pastas de staging `.extension-staging-*`; não foram falhas de assertion funcionais. O gate amplo segue pendente de execução completa com as escritas temporárias permitidas.
- A correção TDD de identidade/generation será registrada em commit separado após estes testes focalizados verdes; nenhuma alegação de gate completo é feita aqui.
