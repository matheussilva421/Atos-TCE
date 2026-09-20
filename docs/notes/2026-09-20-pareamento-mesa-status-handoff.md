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

## Atualização — evidência da tentativa reportada (20/09/2026)

A evidência visual e o banco atual confirmam o estado intermediário descrito
acima:

- a Mesa estava em `127.0.0.1:18743` e mostrava `Mesa conectada`, mas não
  mostrava código porque o contrato oculta o código quando existe qualquer
  cliente persistido;
- o painel mostrava `Mesa indisponível ou token recusado`, com o campo de
  pareamento vazio;
- `data/atos-tce.db` contém uma única linha em `bridge_clients`, com
  `token_hash` de 64 caracteres, origem e ID de extensão coerentes entre si;
- a linha foi criada em `2026-09-20T13:32:55Z` e o `last_seen_at` permaneceu
  nesse mesmo instante. Assim, uma tentativa gravou um token, mas a instância
  atualmente aberta não conseguiu autenticar depois com o mesmo token/origem.

Essa combinação explica por que não apareceu um código novo: a Mesa considerou
que já havia uma extensão pareada, enquanto o painel atual não conseguiu provar
a posse do token. A correção operacional é usar **Reparear extensão** na seção
Área Restrita da Mesa, confirmar, aguardar o código novo e digitá-lo no painel
da mesma extensão/perfil; não reutilizar o código antigo.

Validação adicional, sem portal e sem credenciais:

- `py -3 -m unittest tests.test_bridge -q`: 30/30 aprovados;
- `py -3 -m unittest tests.test_bridge.ExtensionPairingTests.test_mesa_pairing_payload_hides_the_code_once_paired -v`: 1/1 aprovado;
- `py -3 -m unittest tests.test_bridge.ExtensionPairingTests.test_reset_revokes_the_old_client_and_offers_a_new_code -v`: 1/1 aprovado;
- `npm test --prefix extension`: 112/112 aprovados;
- `node --test app/web/tests/*.test.mjs`: 15/15 aprovados;
- `git diff --check`: verde.

No reset real foi executado nesta análise, porque a porta `18743` não estava
escutando no momento da verificação e a evidência disponível era uma captura
anterior. Não houve alteração de código, credenciais, portal ou dados privados.

## Atualização — recuperação da sessão visível na Mesa (20/09/2026)

A imagem seguinte mostrou que o bloco de pareamento inteiro não aparecia, e não
apenas o botão de reset. A causa está em `app/web/app.js`: qualquer erro ao
consultar `/api/v1/bridge/pairing` escondia o bloco. Como essa rota exige a
sessão bootstrap da Mesa, uma sessão ausente/expirada produzia exatamente a
tela mostrada, enquanto as rotas públicas de saúde e resumo continuavam
funcionando.

Correção aplicada:

- `refreshPairing()` mantém o bloco visível quando a consulta falha;
- em 401, informa `Sessão da Mesa expirada. Reabra a Mesa pelo START.cmd para
  gerar uma nova sessão.`;
- esconde código, renovar e resetar enquanto não houver sessão autorizada;
- outros erros exibem uma mensagem de consulta, sem sugerir que existe um
  código utilizável.

TDD e validação:

- RED: o novo teste de `app/web/tests/ui-wiring.test.mjs` falhou porque o
  bloco era escondido e não havia mensagem de sessão;
- GREEN: `node --test app/web/tests/*.test.mjs` — 16/16 aprovados;
- `git diff --check` — verde.

O operador deve reiniciar a Mesa pelo `START.cmd`, abrir a nova sessão que ela
lançar e então usar o bloco visível para resetar o pareamento e gerar o código.
O teste manual dessa sequência ainda depende da porta local estar ativa; nenhum
reset real, login, envio ou finalização foi executado nesta etapa.
