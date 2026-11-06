# Release final — Complementador e-Contas (F9)

Data: 05/11/2026
Versão: 0.1.1
Branch: `codex/complementador-e-contas`
HEAD de código/testes: `3bd2001`

## Estado

`PARTIAL_WITH_EVIDENCE` · `H2_ADAPTER_BLOCKED_EXTERNAL_AUTH` · `H3_NOT_RUN` · `PROFESSIONAL_BROWSER_NOT_RUN` · `G7_PENDING`

O núcleo local e sintético está implementado e verde. O salvamento automático nunca foi exercitado em ato real; os quatro atos existentes foram salvos de forma supervisionada em H2. O pacote abaixo é um **candidato seguro com o motor desligado**, não um release funcional homologado.

## Build de distribuição (motor desligado)

Gerado sem `BATCH_EXECUTION`, sem `BATCH_FILL_ONLY` e sem `BATCH_SAVE`.

| Arquivo | Bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 1.198 | `76B9D5D1B06633EE6CF6E1E2F7580AF4AA6804620879428837356EF648422641` |
| background.js | 132.376 | `901A8A9BAD4187866E06A47F575EBBD91B29249CBDCFF1DEFE203BAA58899062` |
| form-content.js | 57.831 | `544711B11E12963FFDB6092524AFEF1A7E36AE973C9B08423D8F8B1B002E5C9E` |
| autos-content.js | 984.542 | `F8A4496DC6AB8B218E40DB010B5A16BDA4E16EAF7C5FFD6E96FEBD59ED5F0FDB` |
| list-content.js | 27.760 | `52251C5E859BB929B58D991D6D639EBA53527D66B140214DB8044F165CCA91F8` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

## Zip candidato

| Item | Valor |
| --- | --- |
| Caminho | `release/Complementador-eContas-0.1.1-batch-safe.zip` |
| Bytes | 645.040 |
| SHA-256 | `D820E4A9E32FB66F99C27D5B8B2E777E65E901153BC9076DE05EE154A8319E0C` |
| Extração de ensaio | `work/release-safe-extract-2026-11-05` |
| Divergências de hash | **0** |

O ZIP contém apenas `manifest.json`, os quatro bundles e `vendor/pdf.worker.mjs`. Nenhum PDF, teste, documentação ou dado pessoal foi empacotado.

## Backup e rollback

- Baseline imutável: `work/batch-final-baseline-2026-11-05` (128 arquivos).
- ZIP do baseline: `work/batch-final-baseline-2026-11-05.zip` (915.327 bytes, SHA-256 `2AAF8D1449C838D9DFC42669622A0F30163E26FFE50652E1352960EF25FA3C1E`), extração conferida com 0 divergências.
- Rollback: desativar/remover a extensão candidata, apontar para a pasta baseline restaurada e recarregar. Isso não desfaz ato já gravado no e-Contas; reversão institucional segue o procedimento oficial.

## Por que este pacote não salva

- `BATCH_EXECUTION_ENABLED=false` (processamento desligado).
- `BATCH_FILL_ONLY=false`.
- `BATCH_SAVE_ENABLED=false` (capacidade de salvamento desligada).
- Mesmo em um build com `BATCH_EXECUTION=1`, o salvamento exige simultaneamente `BATCH_SAVE=1`, lote criado com `saveAuthorized=true` e clique consciente em Iniciar. O padrão e o build de distribuição nunca habilitam esses três.

## Build de QA preparado (não executado)

- Caminho: `work/qa-save-build-2026-11-05` (ignorado pelo Git, com aviso `NAO-DISTRIBUIR.txt`).
- Gerado com `BATCH_EXECUTION=1` e `BATCH_SAVE=1`, apenas para o futuro GATE A/F7.
- `background.js`: 132.374 bytes, SHA-256 `C69E92C062FE810F3C98F63CF8FDCCAC6F21FC2BE60C5F5EB23537B2A832CBDB`.
- Nunca foi carregado, executado ou instalado. O `dist` seguro foi restaurado depois; os hashes seguros continuam iguais aos do ZIP.
- Este build não é release, não é candidato de distribuição e não autoriza salvamento.

## Gates

| Gate | Estado |
| --- | --- |
| F0 baseline/backup | PASS |
| F1 reparos de salvamento/diário | PASS sintético |
| F2 experiência/estabilidade | PASS sintético |
| F3 classificação de campos | PASS sintético; seis casos reais `NOT_CLASSIFIED_REAL` |
| F4 MV3 | PARTIAL — lógica e estáticos; kill real não executado |
| F5 cache/segurança | PASS sintético; autosave `UNKNOWN` |
| F6 suítes consolidadas | PASS — 323 unitários, 24 navegador |
| F7 H2-adaptador | `H2_ADAPTER_BLOCKED_EXTERNAL_AUTH` — não executado; ver `batch-h2-adapter.md` |
| F8 H3-adaptador | `H3_NOT_RUN`; ver `batch-h3-adapter.md` |
| F9 Chrome profissional | `PROFESSIONAL_BROWSER_NOT_RUN` |
| G7 aceite | `G7_PENDING` |

## Próximo passo único

Quando o operador autorizar expressamente **um** ato novo elegível no Chrome QA, executar F7 com o runner/adaptador, checkpoint e verificação independente; sem essa autorização, o pacote seguro permanece o artefato de entrega.
