# Handoff — recuperação do pareamento recusado no painel (2026-09-21)

## Situação observada

Após o código ser aceito pela Mesa, o painel da extensão continuava exibindo
`Mesa: pareamento deste perfil recusado`. A inspeção do perfil atual confirmou
que o token do cliente `c566cd58-cc7a-4f72-9e36-4e3cdfe68aba` estava salvo,
seu hash batia com o banco e uma chamada equivalente retornava `200` com
`paired=true`.

## Causa raiz confirmada

O Chrome QA real usa o perfil
`C:\\Users\\slvma\\AppData\\Local\\AtosTCE\\perfil-qa-20260921`, com a
extensão carregada de `Downloads\\Github\\Atos-TCE\\extension`. O token
emitido para o último `client_id` foi localizado nesse perfil e seu hash bateu
com o hash persistido na Mesa. Uma chamada HTTP com o mesmo token, origem e
`X-TCE-Client` retornou `200` e `paired=true`.

A falha final era uma corrida entre instâncias do painel combinada com cache
local: uma instância antiga detectava o token anterior recusado, enquanto outra
já havia salvo o token novo. A limpeza condicional passou a preservar o token
novo, mas o painel antigo ignorava o retorno `false`, mantinha o token recusado
em memória e continuava exibindo vermelho. Por isso a Mesa e a API mostravam
um cliente pareado enquanto a interface permanecia em `pareamento recusado`.

## Correção implementada

- `extension/lib/api.js` agora expõe o erro retornado por
  `/api/v1/bridge/status`, incluindo `401/unauthorized`.
- `extension/sidepanel/state.js` centraliza a mensagem de estado e orienta a
  recuperação quando o token do perfil foi recusado.
- `extension/sidepanel/panel.js` detecta `401`, remove somente o `clientId` e
  o token locais recusados e mantém o painel em modo de novo pareamento.
- `extension/sidepanel/operation-queue.js` serializa a limpeza automática, a
  consulta de estado e o pareamento para impedir que uma operação antiga apague
  credenciais novas.
- `extension/lib/api.js` faz a limpeza condicional consultando o armazenamento
  atual; um painel antigo não pode remover credenciais gravadas por outro
  painel depois da resposta 401.
- `extension/lib/api.js` agora expõe `reload()` para sincronizar uma instância
  antiga com as credenciais atuais do `chrome.storage.local`.
- `extension/sidepanel/panel.js` verifica o retorno da limpeza; quando outra
  instância já trocou o token, recarrega as credenciais e volta para
  `Mesa conectada` sem exigir novo pareamento.
- `extension/tests/operation-queue.test.mjs` trava a ordem de limpeza seguida
  de pareamento em um teste de regressão.
- `extension/tests/api.test.mjs` cobre a troca de credenciais entre instâncias
  e a recuperação de uma instância com token antigo.
- Depois da limpeza, a interface informa: clique em **Reparar extensão** na
  Mesa, confirme e digite o novo código neste painel.

## Arquivos alterados

- `extension/lib/api.js`
- `extension/sidepanel/panel.js`
- `extension/sidepanel/state.js`
- `extension/sidepanel/operation-queue.js`
- `extension/tests/api.test.mjs`
- `extension/tests/sidepanel-state.test.mjs`
- `extension/tests/operation-queue.test.mjs`

O arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py` foi
preservado e não pertence a este bloco.

## TDD e validação

- RED: o teste da instância antiga falhou com `TypeError: api.reload is not a
  function`.
- GREEN: `npm test --prefix extension` — 118 testes, 118 aprovados, 0 falhas.
- Diagnóstico ao vivo: hash do token confere, origem/ID conferem e status HTTP
  equivalente retornou `200` com `paired=true`.
- `verify-project.ps1` após a correção: 1.254 verificações, 1.252 aprovadas,
  0 falhas e 2 skips; web 6/6, Python 6/6, PowerShell 599/599, pacote 80/82
  com 2 skips, automação 81/81 e `git diff --check` verde.

## Validação manual pendente

O Chrome QA precisa recarregar a extensão pelo botão **Atualizar** em
`chrome://extensions` usando a origem mostrada no painel:
`Downloads\\Github\\Atos-TCE\\extension`.

Depois:

1. Volte à Mesa em `http://127.0.0.1:18743`.
2. Clique em **Reparar extensão** e confirme.
3. Abra o painel da extensão no mesmo Chrome QA.
4. Digite o novo código de seis dígitos e clique em **Parear**.
5. Confirme que aparece `Mesa conectada`. Se o painel antigo estiver aberto,
   feche e reabra o painel lateral uma vez; a correção também sincroniza a
   instância antiga automaticamente no próximo ciclo de consulta.

Se o painel ainda mostrar a mensagem antiga depois de **Atualizar**, feche e
reabra o painel lateral; o código novo deve ser digitado no painel do mesmo
perfil que carregou a extensão.

Nenhuma credencial do portal foi digitada e nenhum ato foi enviado ou
finalizado.

## GitHub e retomada

- Branch: `codex/mesa-local-refactor`.
- A alteração de sincronização ainda precisa ser commitada e publicada.
- O `work/tce-extractor/.codex-live-pilot.py` permanece não rastreado e
  preservado.
- Pendência: recarregar a extensão no Chrome QA e confirmar `Mesa conectada`
  no painel real.
