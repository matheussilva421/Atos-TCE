# Handoff — análise do pareamento Mesa × extensão (2026-09-20)

## Resumo

Analisada a evidência visual em que um código de seis dígitos é rejeitado, um
novo código faz a Mesa mostrar `Extensão pareada`, mas o painel da extensão
continua em `Mesa indisponível ou token recusado`.

Não houve alteração de código. A reprodução mínima confirmou que essa
combinação é possível pelo contrato atual: a Mesa calcula `paired` pela
existência de uma linha em `bridge_clients`, enquanto a extensão só mostra
`Mesa conectada` depois que o bearer, o `client_id`, a origem e o ID da
extensão passam na autenticação.

## Evidências técnicas

- `app/api/bridge.py` usa código de seis dígitos, TTL de 120 segundos, limite
  de cinco tentativas e consumo no primeiro sucesso.
- `app/api/server.py` grava o hash do novo token e a origem/ID derivados do
  cabeçalho `Origin`; `/api/v1/bridge/pairing` expõe `paired` pela lista
  persistida, sem validar um token da extensão.
- `extension/lib/api.js` persiste `client_id` e token em
  `chrome.storage.local`; `status()` chama `/api/v1/bridge/status` com ambos.
- `extension/sidepanel/panel.js` reduz qualquer falha dessa chamada — 401,
  indisponibilidade ou falha de CORS — à mensagem genérica observada.
- O banco local contém uma única linha de cliente, com origem/ID redigidos e
  hash de token com 64 caracteres. O último `last_seen_at` observado foi
  recente, indicando que algum cliente compatível autenticou nessa instância.
  A porta 18743 não estava escutando no momento da análise.

Reprodução mínima, sem persistir segredo:

```text
Mesa: linha persistida => paired=True
mesmo token + mesma origem/ID => status=True
token antigo => status=False
outra origem/ID => status=False
```

## Diagnóstico

O cenário mais provável é token persistido antigo, extensão carregada de outro
perfil/cópia e origem/ID diferentes, ou pareamento concluído por outra instância
da extensão. A Mesa continua mostrando o cliente persistido mesmo quando o
painel atual não consegue provar posse do token.

O primeiro código pode ter sido rejeitado por expiração, código de outra
instância/servidor ou limite de tentativas. O código de seis dígitos mostrado
nas imagens é compatível com a implementação suportada na raiz (`app/` e
`extension/`).

## Validação

- `npm test --prefix extension`: 112 passaram, 0 falharam.
- `node --test app/web/tests/*.test.mjs`: 15 passaram, 0 falharam.
- `python -m unittest tests.test_bridge -q`: 30 passaram, 0 falharam.
- `python -m unittest tests.test_bridge tests.test_api_server -q`: 114
  passaram, 0 falharam.
- `git diff --check`: verde.

## Estado Git e retomada

- Branch: `codex/mesa-local-refactor`, alinhada com `origin/codex/mesa-local-refactor`.
- Alteração desta análise: somente este handoff.
- Commit publicado: `6673a37` (`docs: record pairing status diagnosis`).
- Arquivo não rastreado preexistente preservado:
  `work/tce-extractor/.codex-live-pilot.py`.
- Para confirmar o caso real, iniciar a mesma Mesa, usar a extensão carregada
  do diretório raiz `extension/` e observar no painel a resposta de
  `/api/v1/bridge/status`. Se a Mesa disser `Extensão pareada` e o painel der
  401, usar o botão `Reparear a extensão?`, depois parear o código novo na
  mesma extensão/perfil. Não reutilizar código antigo.
- Se o problema persistir após o reset, coletar somente status HTTP, origem da
  extensão e `client_id` redigidos; não coletar token, cookies ou credenciais.
