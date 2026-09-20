# Handoff — abertura do painel da extensão pelo ícone (20/09/2026)

## Problema

No Chrome, a extensão `ATOS TCE — Ponte da Mesa` aparecia instalada e ativada
em `chrome://extensions`, mas o clique no ícone não abria a interface para
digitar o código de pareamento.

## Causa

`extension/manifest.json` declarava `side_panel/panel.html`, porém o service
worker não chamava `chrome.sidePanel.setPanelBehavior` para associar a ação da
extensão à abertura do painel. O campo de pareamento existe no side panel, não
no cartão de `chrome://extensions`.

## Correção

- `extension/background/router.js` configura
  `{ openPanelOnActionClick: true }` quando instala o router.
- `extension/tests/helpers.mjs` passou a registrar a configuração do side panel
  no mock do Chrome.
- `extension/tests/router.test.mjs` ganhou o teste de regressão que exige que o
  ícone da extensão abra o painel operacional.

## Validação

- RED: o teste novo falhou com configuração vazia (`actual: []`).
- GREEN focado: 7 testes executados, 7 aprovados.
- Suíte da extensão: 112 testes executados, 112 aprovados, 0 falhas.
- Validação manual no Chrome: pendente de recarregar a extensão instalada e
  clicar novamente no ícone.
- Nenhuma credencial foi digitada e nenhuma ação do portal foi enviada ou
  finalizada.

## Retomada manual

1. Na mesma janela Chrome isolada, abra `chrome://extensions`.
2. No cartão **ATOS TCE — Ponte da Mesa**, clique no ícone circular de recarga.
3. Se o ícone não estiver na barra, abra o menu de extensões (peça de quebra-
   cabeça), localize **ATOS TCE** e fixe-o.
4. Clique no ícone fixado; o painel lateral deve abrir.
5. Com a Mesa em execução, o campo de seis dígitos aparecerá enquanto a
   extensão não estiver pareada. Digite o código mostrado pela Mesa e clique
   em **Parear**.

Se o painel ainda não abrir depois da recarga, abrir manualmente o painel
lateral do Chrome e selecionar **ATOS TCE** é o próximo diagnóstico; então
verificar o link **service worker** no cartão da extensão para erro de
inicialização.

