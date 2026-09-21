# Handoff — recuperação do pareamento recusado no painel (2026-09-21)

## Situação observada

Após o código ser aceito pela Mesa, o painel da extensão continuava exibindo
`Mesa indisponível ou token recusado`. A inspeção somente de estado confirmou
que o registro do cliente existia no banco, com a origem e o ID da extensão
carregada no Chrome QA, mas `last_seen_at` não avançava após as consultas do
painel. Isso caracteriza recusa do token salvo neste perfil.

## Correção implementada

- `extension/lib/api.js` agora expõe o erro retornado por
  `/api/v1/bridge/status`, incluindo `401/unauthorized`.
- `extension/sidepanel/state.js` centraliza a mensagem de estado e orienta a
  recuperação quando o token do perfil foi recusado.
- `extension/sidepanel/panel.js` detecta `401`, remove somente o `clientId` e
  o token locais recusados e mantém o painel em modo de novo pareamento.
- Depois da limpeza, a interface informa: clique em **Reparar extensão** na
  Mesa, confirme e digite o novo código neste painel.

## Arquivos alterados

- `extension/lib/api.js`
- `extension/sidepanel/panel.js`
- `extension/sidepanel/state.js`
- `extension/tests/api.test.mjs`
- `extension/tests/sidepanel-state.test.mjs`

O arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py` foi
preservado e não pertence a este bloco.

## TDD e validação

- RED: o teste de status 401 falhou porque `api.status()` não expunha o erro.
- GREEN: `npm test --prefix extension` — 115 testes, 115 aprovados, 0 falhas.
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
- Antes do commit desta atualização, a árvore rastreada contém somente este
  bloco de correção; o `.codex-live-pilot.py` permanece não rastreado.
- Próximo passo: conferir o diff, criar commit da correção e deste handoff,
  fazer push e depois repetir a validação manual no Chrome QA.
