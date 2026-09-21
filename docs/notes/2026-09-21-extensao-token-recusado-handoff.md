# Handoff — recuperação do pareamento recusado no painel (2026-09-21)

## Situação observada

Após o código ser aceito pela Mesa, o painel da extensão continuava exibindo
`Mesa indisponível ou token recusado`. A inspeção somente de estado confirmou
que o registro do cliente existia no banco, com a origem e o ID da extensão
carregada no Chrome QA, mas `last_seen_at` não avançava após as consultas do
painel. Isso caracteriza recusa do token salvo neste perfil.

## Causa raiz confirmada

O Chrome QA real usa o perfil
`C:\\Users\\slvma\\AppData\\Local\\AtosTCE\\perfil-qa-20260921`. O token
emitido para o último `client_id` foi localizado nesse perfil e seu hash bateu
com o hash persistido na Mesa. Uma chamada HTTP com o mesmo token, origem e
`X-TCE-Client` retornou `200` e `paired=true`.

A falha era uma corrida entre instâncias do painel: uma atualização automática
detectava o token anterior recusado e iniciava `api.clear()` enquanto o usuário
já estava executando um novo pareamento. A limpeza terminava depois do novo
`api.pair()` e removia o token recém-salvo. Por isso cada tentativa mostrava
um novo cliente pareado na Mesa, mas o painel voltava imediatamente para
token recusado.

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
- `extension/tests/operation-queue.test.mjs` trava a ordem de limpeza seguida
  de pareamento em um teste de regressão.
- `extension/tests/api.test.mjs` cobre a troca de credenciais entre instâncias.
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

- RED: o teste de status 401 falhou porque `api.status()` não expunha o erro.
- GREEN: `npm test --prefix extension` — 117 testes, 117 aprovados, 0 falhas.
- `verify-project.ps1` — 1.254 verificações, 1.252 aprovadas, 0 falhas, 2
  skips.
- O gate também confirmou web 6/6, Python 6/6, PowerShell 599/599,
  pacote 80/82 com 2 skips, automação 81/81 e `git diff --check` verde.

## Validação manual pendente

O Chrome QA precisa recarregar a extensão pelo botão **Atualizar** em
`chrome://extensions` usando a origem mostrada no painel:
`Downloads\\Github\\Atos-TCE\\extension`.

Depois:

1. Volte à Mesa em `http://127.0.0.1:18743`.
2. Clique em **Reparar extensão** e confirme.
3. Abra o painel da extensão no mesmo Chrome QA.
4. Digite o novo código de seis dígitos e clique em **Parear**.
5. Confirme que aparece `Mesa conectada`.

Se o painel ainda mostrar a mensagem antiga depois de **Atualizar**, feche e
reabra o painel lateral; o código novo deve ser digitado no painel do mesmo
perfil que carregou a extensão.

Nenhuma credencial do portal foi digitada e nenhum ato foi enviado ou
finalizado.

## GitHub e retomada

- Branch: `codex/mesa-local-refactor`.
- Correção final publicada no commit `2d85c48`
  (`fix: guard pairing cleanup against newer tokens`).
- Push confirmado no remoto com o SHA
  `2d85c482e21432eed828d89e95156ca2749e251b`.
- O checkout está limpo em arquivos rastreados; o
  `work/tce-extractor/.codex-live-pilot.py` permanece não rastreado e
  preservado.
- Pendência: recarregar a extensão no Chrome QA e confirmar `Mesa conectada`.
