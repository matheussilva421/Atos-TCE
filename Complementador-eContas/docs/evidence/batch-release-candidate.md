# Candidato local de release — automação em lote

Data: 05/11/2026
Estado: `PARTIAL_WITH_EVIDENCE` / `H2_ADAPTER_BLOCKED_EXTERNAL_AUTH` / `H3_NOT_RUN` / `G7_PENDING`

Este documento prepara a entrega (T24) sem publicar, instalar em perfil profissional ou declarar homologação. A versão do manifesto permanece 0.1.1. O release detalhado está em `docs/evidence/batch-final-release.md`.

## Build candidato (dist)

Build seguro, sem `BATCH_EXECUTION`, `BATCH_FILL_ONLY` ou `BATCH_SAVE`.

| Arquivo | Bytes | SHA-256 |
| --- | --- | --- |
| manifest.json | 1.198 | `76B9D5D1B06633EE6CF6E1E2F7580AF4AA6804620879428837356EF648422641` |
| background.js | 132.376 | `901A8A9BAD4187866E06A47F575EBBD91B29249CBDCFF1DEFE203BAA58899062` |
| form-content.js | 57.831 | `544711B11E12963FFDB6092524AFEF1A7E36AE973C9B08423D8F8B1B002E5C9E` |
| autos-content.js | 984.542 | `F8A4496DC6AB8B218E40DB010B5A16BDA4E16EAF7C5FFD6E96FEBD59ED5F0FDB` |
| list-content.js | 27.760 | `52251C5E859BB929B58D991D6D639EBA53527D66B140214DB8044F165CCA91F8` |
| vendor/pdf.worker.mjs | 1.417.586 | `BD88805178A26C729DB8C0107A5B630CB900EC070F4D8C7529A3E45530AFD41D` |

ZIP: `release/Complementador-eContas-0.1.1-batch-safe.zip` (645.040 bytes; SHA-256 `D820E4A9E32FB66F99C27D5B8B2E777E65E901153BC9076DE05EE154A8319E0C`), extração conferida com 0 divergências.

## Backup e rollback

- Backup imutável: `work/batch-final-baseline-2026-11-05` (128 arquivos; ZIP 915.327 bytes, SHA-256 `2AAF8D1449C838D9DFC42669622A0F30163E26FFE50652E1352960EF25FA3C1E`).
- Rollback: desativar/remover a extensão candidata, apontar para a pasta restaurada do backup e recarregar. Reverter código não desfaz ato já gravado no e-Contas.

## Instalação do candidato (quando autorizada)

1. Extrair o ZIP apenas em diretório local de homologação.
2. Abrir `chrome://extensions`, ativar modo desenvolvedor, carregar a pasta extraída.
3. Confirmar versão 0.1.1 e que o painel aparece apenas na listagem de processos.
4. Manter o pacote desligado; ele não salva sem os três controles (`BATCH_EXECUTION`, `BATCH_SAVE`, `saveAuthorized` do lote).

Política institucional pode bloquear extensões não empacotadas; a instalação depende de aprovação interna e não deve ser contornada.

## O que está comprovado

- Preenchimento em lote no QA: 10 examinados, 4 `FILLED`, 6 `REVIEW_REQUIRED`, 0 salvamentos automáticos.
- Quatro atos salvos de forma supervisionada, uma confirmação cada, verificação independente 4/4.
- Diálogo real: título **Complementar ato**, confirmação **sim, complementar**, cancelamento **NÃO**.
- Suítes finais: 322 unitários PASS; 24 navegador PASS em um ciclo.
- Verificação pós-save em aba nova, classificação de campos ausentes e retomada manual após incerteza implementadas e testadas sinteticamente.

## O que não está homologado

- Salvamento automático em ato real (F7/H2-adaptador).
- Lote automático real (F8/H3-adaptador).
- Kill físico do service worker/reinício do navegador; a lógica de suspensão está testada em unidade.
- Reclassificação dos seis `MISSING_FIELDS` reais.
- Autosave do portal e Chrome profissional.
- G7: aceite formal e release funcional habilitado.

`AUTOMATED_SAVE_NOT_RUN`. Este candidato não deve ser tratado como release aprovado.
