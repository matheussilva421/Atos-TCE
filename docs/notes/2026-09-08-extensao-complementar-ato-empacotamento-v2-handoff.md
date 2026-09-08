# Handoff — empacotamento v2 da extensão Complementar Ato — 08/09/2026

## Resumo

- Gerado um novo ZIP somente da extensão atual em `work/tce-extractor/portable/extensao-complementar-ato`.
- Nenhum arquivo-fonte foi alterado, revertido ou normalizado.
- O ZIP anterior foi preservado e não foi sobrescrito.
- A versão atual inclui a pesquisa manual, o botão explícito de sinalizar Complementar Ato, `bridge-client.js` e a UI opcional de pareamento.

## Artefato

- Caminho absoluto: `C:\Users\slvma\Downloads\Github\Complementação de Atos\artifacts\extensao-complementar-ato-2026-09-08-v2.zip`
- Tamanho: `32892` bytes
- SHA-256: `936472A38C70E21A184B2EF0961E659FAA7675655E2592F0E1C23B24777BE859`
- Raiz interna: `extensao-complementar-ato/`
- Arquivos: `11`
- O ZIP foi extraído em diretório temporário e conferido; os 11 hashes extraídos coincidiram com a fonte.
- Validação do manifest: `background/service-worker.js`, `sidepanel/panel.html` e `content/form-detector.js` presentes e referenciados corretamente.

## Allowlist incluída

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

## Arquivos excluídos

- `package.json`
- `content/package.json`
- Todos os 7 arquivos em `tests/`
- Nenhuma entrada de `docs/`, `work/` ou `acervo` foi incluída.

Auditoria: a fonte tinha 20 arquivos; 11 foram selecionados e 9 foram excluídos. O ZIP contém 11 entradas, 0 entradas fora da allowlist e 0 entradas ausentes.

## Testes

- Comando: `npm test`
- Diretório: `work/tce-extractor/portable/extensao-complementar-ato`
- Resultado da verificação final: `117` testes executados, `117` aprovados, `0` falhas, `0` cancelados, `0` ignorados.
- A primeira execução nesta sessão reportou 116 testes; a verificação final reportou 117, incluindo o teste adicional de pareamento presente no estado final. O resultado oficial é o da verificação final.

## Integridade do ZIP anterior

- Arquivo preservado: `artifacts/extensao-complementar-ato-2026-09-08.zip`
- SHA-256 antes/depois: `F6B54A0FCFDA4E669C21BAA4327DD86F37ABAE824E426D6668C627E5D5392C02`

## GitHub e estado do checkout

- Não houve `git add`, commit, push, reset, limpeza ou alteração de código-fonte.
- O checkout já possuía alterações de outros trabalhos, inclusive na extensão; elas foram preservadas.
- O novo artefato e este handoff foram produzidos conforme solicitado. Nenhum commit ou push foi feito.

## Problema encontrado e solução

- A primeira checagem pós-geração usou uma comparação de arrays incompatível com a semântica do PowerShell e interrompeu a validação após criar o ZIP.
- O ZIP não foi recriado nem sobrescrito; a auditoria foi repetida com `Compare-Object`, normalização de separadores, extração e comparação SHA-256, concluindo com sucesso.

## Retomada

1. Usar o ZIP v2 no caminho absoluto acima para instalação unpacked.
2. Se necessário, repetir `Get-FileHash -Algorithm SHA256` antes de distribuir.
3. Não incluir `package.json`, `tests/` ou arquivos do workspace em novas versões sem nova autorização.
