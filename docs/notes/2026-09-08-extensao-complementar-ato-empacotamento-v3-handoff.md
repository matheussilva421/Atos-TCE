# Handoff — empacotamento v3 da extensão Complementar Ato — 08/09/2026

## Resumo

- Reempacotada a extensão depois da sincronização incremental de dataset e da correção de revisão do bridge.
- A fonte foi preservada; o ZIP contém somente a allowlist operacional da extensão.
- O v2 continua preservado como artefato anterior.

## Artefato

- Caminho: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v3.zip`
- Tamanho: `33440` bytes
- SHA-256: `8B0BBBA8131EA1D9B8156AAC60D374A85ED1D16D2AF1B55C77D1809ADCF61E46`
- Raiz interna: `extensao-complementar-ato/`
- Entradas: `11`

## Conteúdo

```text
manifest.json
background/service-worker.js
content/form-detector.js
lib/bridge-client.js
lib/matcher.js
lib/messages.js
lib/normalizer.js
lib/schema.js
sidepanel/panel.css
sidepanel/panel.html
sidepanel/panel.js
```

Não inclui `package.json`, testes, `docs`, `work`, acervo, runtime ou credenciais.

## Verificação

- Entrada ZIP: 11.
- Arquivos fora da allowlist: 0.
- O hash foi calculado após a compressão.
- `node --test` na fonte: `118` testes executados, `118` aprovados, `0` falhas, `0` ignorados.
- QA autenticada no portal continua pendente.

## Retomada

1. Conferir o SHA-256 antes da distribuição.
2. Instalar a pasta `extensao-complementar-ato` via “Carregar sem compactação”.
3. Parear novamente com o serviço local; tokens não são transportados no ZIP.
