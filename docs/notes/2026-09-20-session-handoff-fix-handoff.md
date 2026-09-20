# Handoff — transferência de sessão da Mesa entre perfis Chrome (2026-09-20)

## Problema

O launcher abria a Mesa no Chrome pessoal e imprimia a URL inicial de
bootstrap. Essa URL usa um token de uso único; depois de ser consumida pelo
Chrome pessoal, copiá-la para o Chrome QA respondia `401`/sessão expirada.
Copiar apenas a raiz também não funciona porque o cookie HttpOnly fica preso ao
perfil do navegador.

## Correção implementada

- `Bridge` agora emite tokens de transferência de sessão com validade de cinco
  minutos e consumo único.
- `POST /api/v1/session/handoff` exige a sessão autenticada da Mesa e devolve
  uma nova URL `/bootstrap#token=...`.
- O bootstrap aceita tanto o token inicial quanto o token de transferência,
  sempre abrindo um cookie novo no perfil que o consumiu.
- A Área Restrita da Mesa ganhou **Copiar sessão para outro Chrome**. O botão
  copia a URL para a área de transferência e tem fallback por prompt.
- O launcher e o README passaram a explicar que a URL inicial é de uso único e
  que a transferência deve ser feita pelo botão depois da abertura inicial.
- O texto do painel da extensão mantém a orientação para usar a URL completa
  quando a Mesa for aberta em outro perfil.

## Arquivos alterados

- `app/api/bridge.py`
- `app/api/server.py`
- `app/main.py`
- `app/web/app.js`
- `app/web/index.html`
- `app/web/tests/ui-wiring.test.mjs`
- `README.md`
- `tests/test_bridge.py`
- `tests/test_main.py`
- `extension/sidepanel/panel.html`

O arquivo não rastreado `work/tce-extractor/.codex-live-pilot.py` foi
preservado e não pertence a este bloco.

## TDD e validação

- RED: o novo teste HTTP recebeu `404` para `/api/v1/session/handoff`; o teste
  da UI não encontrou o botão; o teste do launcher não encontrou a mensagem de
  uso único.
- GREEN focalizado: ponte/API 116/116, launcher 1/1 e web 8/8 no arquivo de
  wiring.
- `node --test app/web/tests/*.test.mjs`: 17/17 aprovados.
- `npm test --prefix extension`: 112/112 aprovados.
- `py -3 -m unittest tests.test_bridge tests.test_api_server tests.test_main -q`:
  116/116 aprovados.
- `py -3 -m unittest discover -s . -p 'test_*.py' -q` em
  `work/tce-extractor`: 528/528 aprovados, 8 skips.
- `verify-project.ps1`: 1.254 verificações, 1.252 aprovadas, 0 falhas, 2
  skips.
- `git diff --check`: verde.

## Validação manual pendente

O processo Mesa/Chrome já aberto não foi reiniciado automaticamente. Para
validar a correção no ambiente do operador:

1. Encerre a Mesa atual pelo `Ctrl+C` do terminal dela.
2. Execute `.\START.cmd --data-root data --port 18743`.
3. Na Mesa aberta no Chrome pessoal, clique em **Copiar sessão para outro
   Chrome**.
4. Cole a URL copiada no Chrome QA e aguarde a Mesa carregar.
5. Use o código exibido pela Mesa no painel da extensão do mesmo perfil QA.
6. Se a Mesa mostrar **Extensão pareada** sem oferecer código, clique em
   **Reparear extensão**, confirme a revogação do token antigo e repita o
   pareamento no painel QA.

Não reutilizar a URL inicial já consumida nem abrir somente a raiz
`http://127.0.0.1:18743/`. Nenhuma credencial do portal foi digitada e nenhum
ato foi enviado ou finalizado.

## GitHub e retomada

- Branch: `codex/mesa-local-refactor`.
- Estado antes do commit deste bloco: alterações locais da correção e o
  handoff; o arquivo `.codex-live-pilot.py` continua fora do commit.
- Próximo passo: revisar `git diff`, criar o commit da correção, fazer `git
  push` e atualizar este handoff com o SHA.
