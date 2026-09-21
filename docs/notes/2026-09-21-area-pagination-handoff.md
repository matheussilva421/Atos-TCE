# Handoff — paginação da Área Restrita no portal legado (2026-09-21)

## Situação observada

Com a Mesa e a extensão conectadas, a análise real da Área Restrita falhou
com: paginação incoerente: página 1 depois de 1. O portal visualmente
avançava na lista, mas o scanner continuava lendo a página atual como 1.

## Causa raiz confirmada

O portal legado não usa aria-current=page para indicar a página atual. Ele usa
o controle NumeroPagina, um input/select cujo value muda de 1 para 2, enquanto
os links de navegação continuam sendo encontrados pelo adaptador. pageInfo()
ignorava esse controle e aplicava o fallback 1 em todas as leituras.

## Correção

- extension/lib/area-snapshot.js agora lê a página atual de aria-current=page
  ou, no portal legado, de NumeroPagina/input[name=NumeroPagina]/
  select[name=pagina].
- extension/tests/area-snapshot.test.mjs adiciona uma regressão que altera
  NumeroPagina de 1 para 2 e exige que o snapshot acompanhe a página.
- Nenhuma ação de ato, seleção de processo ou envio foi adicionado.

## Follow-up — CSP no avanço da página (2026-09-21)

O teste manual seguinte mostrou a causa que ainda impedia o avanço: o portal
usa links href="javascript: ..." e o content script chamava control.click().
O Chrome bloqueava a navegação pela CSP da página, em
extension/content/paging.js:34. Por isso o formulário permanecia na página 1
e o scanner corretamente abortava ao detectar a mesma página.

Correção aplicada:

- extension/lib/area-snapshot.js agora extrai apenas NumeroPagina,
  Paginacao e GrupoProcesso do comando legado e procura o form1.
- A navegação só é permitida quando Paginacao=S e GrupoProcesso=NS; o href
  nunca é executado.
- extension/content/paging.js submete o formulário nativamente para links
  legados e mantém o clique para controles modernos não legados.
- Foram adicionadas regressões para submissão segura, rejeição da allowlist e
  o caminho real LIST_PAGE sem chamar o clique CSP-bloqueado.

## Validação

- RED: o teste do controle legado falhou com 1 !== 2.
- GREEN focado: area-snapshot + paging — 19/19.
- Suíte completa da extensão: npm test --prefix extension — 128 testes, 128
  aprovados e 0 falhas.
- Gate oficial: verify-project.ps1 — 1.254 verificações, 1.252 aprovadas,
  0 falhas e 2 skips ambientais.

## Retomada manual

Depois de publicar a correção:

1. Mantenha a janela do START aberta ou reinicie-a se a branch ainda não foi
   atualizada.
2. Atualize a branch até o commit desta correção e reinicie a Mesa se
   necessário.
3. Em chrome://extensions, clique em Atualizar na extensão carregada de
   C:\Users\slvma\Downloads\Github\Atos-TCE\extension.
4. Recarregue a aba do portal com Ctrl+R para instalar o novo content script;
   deixe aberta a lista de processos, com a paginação visível.
5. Reabra o painel e clique em Analisar Área Restrita novamente.

O resultado esperado é a leitura sequencial das 40 páginas mostradas pelo
portal, sem o erro de CSP em content/paging.js e sem a mensagem de paginação
incoerente. A Mesa só deve persistir o retrato depois da varredura coerente.

M3, M5 e M6 continuam bloqueados pela validação humana correspondente no
portal.

## Follow-up — aguardar a recarga completa (2026-09-21)

O teste real avançou até a página 40, mas ainda acusou "página 40 depois de
2" e, numa nova tentativa, "página 40 depois de 40". Isso confirmou uma
segunda corrida: o submit atualizava NumeroPagina antes de o frame terminar
de trocar linhas e controles. Na última página, o botão Próxima também não
podia aumentar o total conhecido de 40 para 41.

Correção aplicada:

- extension/background/router.js agora aguarda a página esperada aparecer e
  exige duas leituras consecutivas estáveis de página, total e linhas antes de
  continuar; a espera é limitada e configurável por tentativa/intervalo.
- extension/content/paging.js informa page_after para que o roteador aguarde
  o destino correto.
- extension/lib/area-snapshot.js reconhece rótulos como "Próxima >", usa os
  destinos NumeroPagina para calcular o total e não inventa a página 41 no
  fim da lista.
- Os testes cobrem frame stale, seleção de Próxima contra Última e o limite
  final da página 40.

Validação desta etapa:

- RED: o teste de frame stale falhou com "página 1 depois de 1" e o teste do
  fim da lista observou 41 em vez de 40.
- GREEN: area-snapshot, paging e router — 68/68.
- Suíte completa da extensão: npm test --prefix extension — 131 testes,
  131 aprovados e 0 falhas.
- Gate oficial: verify-project.ps1 — 1.254 verificações, 1.252 aprovadas,
  0 falhas e 2 skips ambientais.

## GitHub

- Branch: codex/mesa-local-refactor.
- Correção publicada no commit 27a5f32 (`fix: submit legacy area pagination safely`).
- Correção de espera publicada no commit 4f7b05a (`fix: wait for stable area pagination`).
- Push confirmado em origin/codex/mesa-local-refactor.
- O arquivo local não rastreado work/tce-extractor/.codex-live-pilot.py foi
  preservado.

## Follow-up — diagnóstico direto no Chrome QA e correção final (2026-09-21)

Foi feita inspeção CDP somente leitura na aba QA aberta, sem abrir processo,
selecionar interessado ou enviar ato. A moldura real da lista foi identificada
como frame 65. O portal usa `form1`, `NumeroPagina` oculto, `Paginacao`,
`GrupoProcesso` e `select[name="pagina"]` com 40 opções.

O diagnóstico reproduziu a corrida: depois de `form.submit()`,
`NumeroPagina` mudava imediatamente para o destino, enquanto as 30 linhas e os
links ainda pertenciam à página anterior por mais de dois segundos. O scanner
considerava essa leitura falsa como página pronta e enviava o próximo avanço.
Também foi observado que o total era calculado a partir dos números dos
processos, chegando a 104949/105323 em vez de 40.

Correção aplicada:

- `extension/lib/area-snapshot.js` prioriza o `select[name="pagina"]`, que só
  muda quando a página renderizada chegou, e usa `NumeroPagina` como fallback.
- Os controles de total ficam restritos à navegação legada/opções da página;
  links de processos deixam de ser interpretados como números de página.
- `extension/tests/area-snapshot.test.mjs` adiciona regressões para os dois
  comportamentos observados ao vivo.

Validação desta etapa:

- RED: 2 testes falharam pelos sintomas reais (`2 !== 1` e `105323 !== 40`).
- GREEN focado: area-snapshot — 22/22.
- Suíte completa da extensão: `npm test` — 133 testes, 133 aprovados, 0
  falhas.
- A extensão carregada no Chrome QA foi recarregada pelo botão Atualizar do
  modo desenvolvedor após a alteração.

Validação live final:

- A extensão foi recarregada no Chrome QA e a aba autenticada do portal foi
  recarregada para reinstalar os content scripts.
- A análise foi iniciada na Mesa e observada por CDP sem nova interação.
- Resultado visível: `Análise concluída`; 1.198 processos vistos, 483
  `PRECISA_COMPLEMENTAR`, 715 `ATO_COMPLEMENTADO`, 0 ambíguos, 0 bloqueados,
  0 não encontrados e 17 pendentes de download.
- O erro de corrida `página 2 depois de 2` não reapareceu.


Validação final e GitHub:

- `npm test` na extensão: 133 testes, 133 aprovados, 0 falhas.
- `verify-project.ps1`: 1.254 verificações, 1.252 aprovadas, 0 falhas e 2
  skips ambientais.
- `git diff --check`: passou.
- Branch de trabalho: `codex/mesa-local-refactor`; o commit/push deste bloco
  foi publicado em `2d4d9c6` (`fix: stabilize legacy area pagination
  snapshots`) no remoto `origin/codex/mesa-local-refactor`.

## Follow-up — contadores durante nova análise (2026-09-21)

O diagnóstico da tela confirmou que `GET /api/v1/area/latest` sempre retorna a
última análise persistida. Ao iniciar uma nova leitura, `app/web/app.js` apenas
alterava o status para aguardando a extensão e deixava os contadores antigos
visíveis. Por isso os números 1.198, 483 e 715 apareceram durante a espera; a
análise seguinte terminou com os mesmos valores, mas a tela não permitia
separar visualmente retrato anterior de resultado em andamento.

Correção aplicada:

- `app/web/app.js` agora substitui os contadores por `—` ao iniciar tanto a
  análise principal quanto o modo de compatibilidade.
- A última análise continua preservada no banco e é recarregada ao concluir ou
  quando a tentativa falha; nenhum dado histórico é apagado.
- `app/web/tests/ui-wiring.test.mjs` cobre a limpeza visual durante a execução.

Validação desta etapa:

- RED: o novo teste falhou porque a tela ainda não tinha `clearAreaCounters`.
- GREEN focado: `node --test app/web/tests/ui-wiring.test.mjs` — 8 testes, 8
  aprovados, 0 falhas.
- Gate oficial: `verify-project.ps1` — 1.254 verificações, 1.252 aprovadas,
  0 falhas e 2 skips ambientais.
- O servidor local respondeu `app.js` contendo a nova limpeza visual.

Retomada manual: recarregar a aba `http://127.0.0.1:18743/` antes da próxima
análise. Durante a execução, os seis contadores devem mostrar `—`; somente ao
final devem voltar a exibir o novo retrato.

Publicação desta etapa:

- Commit: `1f614c6` (`fix: clear stale area counters during scans`).
- Push confirmado em `origin/codex/mesa-local-refactor`.
- O arquivo local não rastreado `work/tce-extractor/.codex-live-pilot.py` foi
  preservado.

## Follow-up — atraso além do prazo e avanço de página ignorado (2026-09-21)

O último teste live terminou com a mensagem `A análise não respondeu a tempo`.
A inspeção somente leitura do banco separou os dois eventos: a Mesa desistiu
de esperar após 180 segundos, mas o comando 17 continuou até 4min41s e então
falhou com `PAGINATION_STALLED` na página 37 de 40. Nenhum resultado parcial
foi persistido; os números 1.198 vistos, 482 pendentes e 716 complementados
continuam sendo o último snapshot bem-sucedido do comando 16.

A causa é compatível com o comportamento observado no portal legado: uma
submissão de troca de página pode retornar sucesso sem que a lista seja
substituída. O roteador aguardava uma janela de aproximadamente 20 segundos e
tentava o avanço uma única vez. A interface também tinha um limite fixo de
três minutos, menor que uma análise completa real.

Correção aplicada na fonte da extensão e da Mesa:

- `extension/background/router.js` mantém a leitura estável por até 40
  amostras de 500 ms e repete o mesmo avanço até três vezes, com 750 ms entre
  tentativas; a página só é aceita após duas amostras idênticas da página
  esperada.
- `app/web/app.js` aguarda até 15 minutos pela conclusão do comando e informa
  explicitamente esse limite ao usuário.
- `app/web/tests/ui-wiring.test.mjs` verifica o novo prazo e
  `extension/tests/router.test.mjs` cobre tanto uma renderização lenta quanto
  uma primeira submissão que não altera a página.

Validação local desta etapa:

- Roteador focado: 49 testes, 49 aprovados e 0 falhas.
- UI focada: 9 testes, 9 aprovados e 0 falhas.
- Suíte completa da extensão: 135 testes, 135 aprovados e 0 falhas.
- Gate oficial: 1.254 verificações, 1.252 aprovadas, 0 falhas e 2 skips
  ambientais.

Pendência desta etapa: recarregar a extensão e repetir a análise no Chrome QA
autenticado, aguardando a conclusão sem `PAGINATION_STALLED`.

Validação live após a correção:

- A extensão foi recarregada no Chrome QA e a aba autenticada do portal foi
  recarregada antes do teste.
- O comando 18 terminou como `SUCCEEDED` em 3min09s, sem erro; o banco criou o
  snapshot 4 com 1.198 processos, 482 pendentes, 716 complementados e zero
  ambíguos, bloqueados ou não encontrados.
- A Mesa mostrou `Análise concluída` e `Baixar 17 processos`. O limite de 15
  minutos não foi atingido.

Essa validação confirma o fluxo completo de leitura no portal QA lento. Não
houve abertura de ato, preenchimento de formulário ou envio real.

## Follow-up — preparação manual do e-Contas antes da aquisição (2026-09-21)

O clique real em `Baixar 17 processos` abriu a aba do e-Contas, mas o coletor
tentou validar uma sessão inexistente e o job terminou com 17 falhas. O banco
registrou o job de aquisição como `COMPLETED_WITH_ERRORS`, sem processos
baixados.

Correção aplicada:

- mensagens como `Login não detectado` agora pausam o job em
  `WAITING_FOR_LOGIN`, em vez de transformá-lo em falha final;
- a Mesa informa que está abrindo o e-Contas e exibe a ação `Retomar após
  login` quando a sessão precisa ser preparada;
- o coletor mantém a aba aberta para o operador fazer login e exige a tela de
  processos do e-Contas e o marcador capturado na análise já selecionados;
- a seleção do marcador não é mais alterada automaticamente e a navegação
  para outra aba/tela não é feita pelo coletor;
- depois que o operador prepara a sessão, `Retomar após login` inicia a fila
  congelada e somente então começam os downloads.

Validação desta etapa:

- aquisição: 80 testes, 80 aprovados e 0 falhas;
- UI da Mesa: 10 testes, 10 aprovados e 0 falhas;
- equivalência do runtime promovido: aprovada;
- gate oficial: 1.254 verificações, 1.252 aprovadas, 0 falhas e 2 skips
  ambientais.

Próximo teste manual: reiniciar a Mesa, clicar em `Baixar 17 processos`, fazer
login no e-Contas, deixar a tela de processos aberta com o marcador correto e
clicar em `Retomar após login`. O primeiro indicador esperado é
`WAITING_FOR_LOGIN`/a mensagem de preparação; nenhum download deve ocorrer
antes da retomada.

## Follow-up — pausa de login não deve contar falhas (2026-09-21)

No teste manual do job 2, a aba existente do e-Contas foi encontrada pela porta
DevTools 9222. A página atual tinha usuário autenticado, setor CBP e o marcador
`PROFESSOR - IPERN`; a inspeção foi somente leitura. Durante a primeira tentativa
o coletor detectou a sessão como não pronta e o job chegou a
`WAITING_FOR_LOGIN`, mas a Mesa mostrou `0 de 17 baixados · 17 com falha`.

A causa foi a ordem das transições em `app/econtas/service.py`: o lote era
registrado antes de tratar `auth_required`, então a ausência de recibo era
classificada como falha item a item. A correção agora trata a autenticação antes
do registro do lote e devolve todos os itens interrompidos para `QUEUED`; a
retomada continua usando a mesma fila congelada.

Validação desta correção:

- RED: o teste atualizado falhou com `FAILED` em vez de `QUEUED`;
- GREEN focado: 15 testes de aquisição, 15 aprovados e 0 falhas.

Pendência: reiniciar a Mesa para carregar a correção, observar o job pausado e
clicar em `Retomar após login` somente depois de confirmar login, tela de
processos e marcador no e-Contas. O contador esperado durante a pausa é `0 de
17 baixados`, sem falhas.

## Follow-up — recuperar job pausado depois de reiniciar a Mesa (2026-09-21)

Após reiniciar o servidor com o commit `2635d4a`, a página da Mesa perdeu o
botão de retomada porque `acquisitionJob` existia apenas no estado JavaScript da
página. O job continuava no SQLite e uma nova tentativa pelo botão de download
seria recusada como aquisição ativa.

Correção aplicada:

- `/api/v1/acquisition/plan` agora inclui o job de aquisição ativo, sem expor
  itens ou credenciais;
- `app/web/app.js` recupera `WAITING_FOR_LOGIN` e `INTERRUPTED` após reload,
  restaura o progresso e exibe `Retomar após login`;
- jobs `PENDING`/`RUNNING` voltam a ser acompanhados automaticamente depois da
  recarga, evitando uma segunda aquisição.

Validação:

- RED: o teste de recuperação falhou porque o payload não tinha `active_job`;
- API focada: passou;
- UI focada: 11 testes, 11 aprovados e 0 falhas;
- API completa: 85 testes, 85 aprovados e 0 falhas.

O servidor foi relançado antes desta segunda correção; é necessário reiniciá-lo
novamente depois do commit seguinte. A aba autenticada do e-Contas deve ser
reutilizada, sem automação de credenciais.

## Follow-up — aquisição real e isolamento do estado de análise (2026-09-21)

Depois da renovação da sessão local e da retomada, a aquisição real reutilizou
a aba já aberta do e-Contas, confirmou a sessão e manteve o marcador
`PROFESSOR - IPERN`. O job 2 terminou em aproximadamente 36 minutos com 15 de
17 processos baixados e 2 falhas. Os dois processos foram
`100437/2025` e `004731/2024`; os manifestos registram `Impossível conectar-se
ao servidor remoto` ao consultar PDFs específicos, portanto a ausência de
arquivos é uma falha de rede/documento e foi mantida como falha explícita.

O teste live também revelou que `JobManager` compartilhava a transição de
`job_items` entre aquisição e análise. O worker de análise estava escrevendo
`ANALISADO` ou `FAILED` em `processes.acquisition_state`, fazendo a Mesa voltar a
oferecer todos os 17 processos. A correção em `app/core/store.py` atualiza
`acquisition_state` somente para jobs de aquisição; jobs de análise continuam
isolados. A retomada também limpa o erro antigo de autenticação do job.

Estado local reparado após essa descoberta:

- 15 itens do job 2: `DOWNLOADED`;
- 2 itens do job 2: `FAILED` com motivo preservado;
- plano da Mesa: `Baixar 2 processos`.

Próximo passo manual opcional: tentar novamente somente os 2 processos
pendentes quando o e-Contas estiver respondendo aos endpoints de PDF. Nenhum ato
foi aberto, preenchido ou enviado.
