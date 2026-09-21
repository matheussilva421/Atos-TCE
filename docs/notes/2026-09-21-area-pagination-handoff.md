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
