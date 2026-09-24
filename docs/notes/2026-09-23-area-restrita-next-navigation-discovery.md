# Área Restrita — discovery de Próximo Processo

**Data:** 2026-09-23
**Branch:** `codex/next-process-navigation-discovery`
**Base:** `b1d41e848c39cb61947b011501925c40f86793fb` (`origin/main`)
**Estado:** Phase 0 parcial; Task 1 continua bloqueada até resolver os itens pendentes ao final.

Esta nota registra apenas evidência da sessão real. Nenhum código de navegação foi alterado. Identidades de processos/interessados foram comparadas localmente por hash composto e não são registradas aqui.

## Gate de Git

- `git fetch origin --prune` passou.
- `origin/main` e `origin/codex/mesa-local-refactor` apontavam para o mesmo SHA `b1d41e848c39cb61947b011501925c40f86793fb`.
- `git merge-base --is-ancestor origin/codex/mesa-local-refactor origin/main` retornou 0. A promoção já está contida; nenhuma ref foi movida.
- Esta branch de discovery deriva de `origin/main` nesse SHA.

## Sessão autenticada e página

- Chrome perfil Matheus já estava autenticado na Área Restrita. O tab superior permaneceu em `/telaPrincipalMenu.asp`; nenhuma navegação direta foi usada.
- A lista do setor estava selecionada no marcador normal do fluxo, rotulado `PROFESSOR - IPERN`. O cabeçalho da lista mostrou 1.197 itens.
- Lista aberta em `Proc./ Doc. Eletrônicos`; as abas nativas do portal `Proc./ Doc. Eletrônicos` e `Complementar Ato` coexistem no mesmo tab Chrome.
- Os controles de paginação observados foram `Próxima >`, `< Anterior` e seletor de página. Página 9 mostrou a faixa 241–270; página 10 mostrou 271–300. A ida à página 10 levou aproximadamente 5,3 s até ficar legível.

## Frames e transições observados

- Frame de notificações: `iframeNotificacoes`.
- A lista ficou visível em `iframeOBJ` com nome `iframe1`; a área de trabalho usa `/telaDeTrabalho.asp`, com conteúdo de lista em `ProcessonoSetor.asp`.
- A ação da linha com rótulo acessível `Complementar Ato` abriu o formulário no tab nativo existente, sem criar outro tab Chrome. O conteúdo apareceu em `ComplementarAto.asp` e os botões vieram do frame irmão `botoesNovo.asp`.
- Cada abertura observada criou um novo `iframeOBJ` visível (`iframe2` até `iframe6`); os frames usados antes permaneceram presentes e ocultos. O frame da lista `iframe1` foi preservado entre as alternâncias.
- Do formulário à lista, o controle nativo superior `Proc./ Doc. Eletrônicos` restaurou a página visitada e o marcador em cerca de 1,2 s. O frame de lista já existente reapareceu; não observamos reload completo.
- Um formulário aberto por linha tinha exatamente um radio de interessado, inicialmente desmarcado. Selecionar o radio mudou seu valor de 0 para 1; a identidade composta permaneceu correspondente ao destino e os campos do formulário ficaram legíveis. Nenhum campo foi preenchido.
- Não encontramos, nos itens amostrados, caso com mais de um interessado. O caso C que exigiria escolha entre várias pessoas não está coberto.

## Marcador e ordem do scan

- A lista conservou o rótulo do marcador ao alternar lista/formulário e ao mudar de página; não foi necessário restaurá-lo nos retornos nativos observados.
- A expansão da área de filtro mostrou o controle `cmbMarcadorFiltro`, mas o valor bruto atual do `<option>` não foi lido. O scan salvo mais recente (id 5, 2026-09-21) registra `marker_value=5159`; isso não comprova o valor vivo atual.
- O serviço local da Mesa não estava escutando em `127.0.0.1:18743` e a Mesa/painel da extensão não estava aberto no Chrome. Portanto, o snapshot vivo `SCAN_PAGE` ainda não foi verificado.
- Scan salvo: 1.198 itens. Lista atual: 1.197. Comparação composta anonimizada encontrou 30/30 identidades da página 9, em ordem, nas posições 239–268 do scan; página 10 coincidiu 30/30 com 269–298. A fronteira permaneceu contígua. Há diferença global de uma ocorrência; sua causa/localização não foi determinada.
- Amostras escolhidas a partir do scan provaram que a ação abre a identidade pedida em uma página e através da fronteira de página; a linha bloqueada imediatamente anterior não foi escolhida. A implementação deve sempre buscar identidade composta e não pode usar vizinho/posição como fallback.

## Estratégia e tempos observados

```yaml
navigation_strategy: native_control
marker_restore: not_needed
```

Controle de retorno implementável observado: aba superior `Proc./ Doc. Eletrônicos`. A seleção do próximo item permanece responsabilidade da Mesa e a extensão deve abrir a identidade explícita recebida.

Três medições manuais somente de navegação, desde clique na ação da linha até formulário legível com o interessado selecionado: **4,5 s**, **3,0 s** (destino após virar página) e **4,9 s**. Retorno nativo medido em aproximadamente **1,2 s**. Nenhuma medição percorreu um ato concluído/revisado nem incluiu a ação final; portanto, elas não satisfazem a baseline estrita da Phase 0.

## Casos de ambiguidade e limites

- O total da lista e o total do scan salvo diferem em um item, embora as duas páginas amostradas e a fronteira estejam em ordem relativa contínua. O drift precisa ser explicado ou mitigado antes de Task 1; não presumir que o número exibido no cabeçalho seja o offset do scan.
- A consulta do DOM superior não atravessou os documentos dos frames do portal. A árvore de acessibilidade identificou rotas internas, mas não expôs o valor bruto atual do marcador.
- A tentativa de abrir `chrome://extensions` foi bloqueada pela política de URL do Chrome. Nenhuma tentativa por outro meio foi feita.
- O botão final `Complementar Ato` ficou visível em formulários de destino, mas não foi clicado. Não houve `SUBMIT`, envio ou finalização.

## Pendências que bloqueiam o fim da Phase 0

1. Operador abrir a Mesa Local e o painel atual da extensão no Chrome Matheus, preservar o marcador e permitir a leitura do `SCAN_PAGE` vivo, inclusive rótulo/valor e identidade do snapshot.
2. Reconciliar o delta global de um item entre o scan salvo e a lista. Se a inserção não preservar a ordem do portal, revisar a SPEC/seleção antes da Task 1.
3. Para observar o retorno após `Complementar Ato`, o operador deve escolher um caso de teste controlado e realizar manualmente a ação final após conferir os dados. O agente não deve clicar no botão final.
4. Repetir a baseline a partir de ato concluído/revisado quando houver um caso controlado disponível.
5. Atualizar esta nota, registrar os resultados faltantes e fazer um commit final com a evidência completa. Só então criar `codex/next-process-navigation` a partir desse commit e começar código de produção.

## Evidência de retomada

- A lista foi deixada visível no Chrome na página 9; o marcador normal foi preservado.
- As aberturas de formulário não preencheram campos. Formulários anteriores ficaram em frames ocultos; alternar para `Proc./ Doc. Eletrônicos` restaura a lista sem submeter.
- Última conferência local do branch de discovery: derivado de `origin/main`; ainda não contém implementação de navegação.

## Observação complementar da sessão Chrome (23/09/2026)

- A aba autenticada permaneceu na lista da página 9, com o marcador normal selecionado. A árvore de acessibilidade confirmou o rótulo `PROFESSOR - IPERN` e contagem 1.197 no filtro, coincidente com o cabeçalho; o filtro foi recolhido após a leitura, sem mudar o marcador.
- O valor bruto do `<option>` não foi obtido: a avaliação DOM do frame não ficou acessível pela ferramenta de browser desta sessão. Não se infere o valor salvo no scan como valor vivo.
- A porta `127.0.0.1:18743` segue sem listener, portanto não há Mesa ativa para ler `SCAN_PAGE`. O Chrome DevTools MCP/extensão também não está disponível nesta sessão; nenhuma rota alternativa de inspeção interna do Chrome foi tentada.
- O bloqueio de Phase 0 permanece: falta abrir a Mesa/painel atual da extensão e observar um caso de retorno após conclusão manual supervisionada. Nenhum botão de conclusão foi acionado.

## Retomada na branch unificada — 24/09/2026

### Git e referências lidas

- `git fetch origin --prune` concluiu após repetir com permissão para atualizar `.git/FETCH_HEAD`.
- Checkout limpo em `codex/atos-tce-unified`, rastreando `origin/codex/atos-tce-unified`, no SHA `b937b99ab9a160d821f23f0a24348579a9d6ca60`; não foi criada branch nem worktree.
- A SPEC, os dois planos canônicos e os handoffs foram lidos antes de qualquer alteração. As três cópias na raiz têm o mesmo conteúdo semântico dos arquivos canônicos após decodificar a cópia CP850 apenas para comparação; não substituem a SPEC canônica.
- Nenhum código de produção foi alterado. A implementação de navegação continua não iniciada.

### Estado local observado

- No começo desta retomada, não havia listener em `127.0.0.1:18743` nem aba do portal no Chrome `Matheus`.
- A Mesa foi iniciada com o banco existente (`python -m app.main --data-root data --port 18743`), PID `18296`. `GET /api/v1/health` respondeu HTTP 200. A tela informou API v1, schema v7, 1.232 processos locais e os contadores salvos de 1.198 vistos, 482 pendentes e 716 concluídos.
- O botão **Analisar Área Restrita** não foi acionado; nenhum scan completo foi iniciado.
- O banco, lido em modo SQLite read-only, confirma que o scan mais recente é o id 5, de `2026-09-21T18:39:27Z`, com 1.198 itens, marcador salvo `PROFESSOR - IPERN (1198)` / value bruto `5159`, 482 pendentes e 716 concluídos. Isso continua sendo evidência salva, não o marcador vivo atual.
- `data/logs/area-compare.json` contém uma comparação anterior de uma página com 30 itens contra os 1.198 itens salvos; não determina a causa do delta global. `fotografia-area-restrita-1227.json` tem 1.227 linhas e outro formato de identidade (`interested_key`), por isso não foi usado como scan compatível para reconciliar o delta.
- A navegação para `https://novaarearestrita.tce.rn.gov.br` no Chrome `Matheus` retornou `net::ERR_BLOCKED_BY_CLIENT`. Não houve nova tentativa por outro navegador nem contorno do bloqueio. Não foi obtido `SCAN_PAGE` vivo, e o valor bruto do marcador atual continua sem confirmação.

### Gate e retomada

- Phase 0 permanece aberta: delta 1.198/1.197 sem causa, `SCAN_PAGE` vivo ausente e baseline após conclusão/revisão manual ainda não observada. A amostra histórica de páginas 9–10 não fecha esses gates.
- Não clicar em **Analisar Área Restrita** para substituir o snapshot de página, não iniciar Tasks 1–8 e não inferir que a ordem é segura com base apenas no scan salvo.
- A Mesa local está aberta no Chrome para continuação. Próximo passo: operador abrir a Área Restrita autenticada no perfil `Matheus`, manter o marcador normal selecionado e abrir o painel da extensão. Se o bloqueio do navegador persistir, a intervenção deve ser resolver o acesso pelo fluxo normal do operador; a automação não deve contorná-lo. Depois, obter somente o `SCAN_PAGE` vivo e comparar identidades anonimizadas com o scan salvo.
- Após esses dados, ainda será necessária a validação supervisionada em que o operador faz manualmente o clique final em um processo controlado; então medir o retorno/estado posterior. Nenhum clique final foi feito nesta retomada.
- Testes: nenhum executado nesta retomada; não houve alteração de código. Handoff atualizado; commit/push desta atualização devem ser registrados após a validação documental.
