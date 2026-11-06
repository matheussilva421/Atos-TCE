# Diagnóstico final — campos ausentes e documentos (F3)

Data: 06/11/2026
Escopo: classificação sanitizada de `MISSING_FIELDS`; sem valores, nomes, CPF, matrícula ou datas.

## O que foi implementado

- `src/batch/missing-fields.mjs` classifica a causa a partir de nomes de campos, `proposalStatus`, `resolutionFound`, `guiaFound` e códigos sanitizados.
- `src/background/bridge.mjs` devolve `fieldDiagnostics` sem valores.
- O diário guarda `{ cause, fields[] }` por processo; o relatório expõe causa e campos.
- Categorias: `INTERESTED_MISMATCH`, `TIMEOUT`, `PDF_NOT_READABLE`, `UNSUPPORTED_FORMAT`, `DOCUMENT_NOT_FOUND`, `AMBIGUOUS_VALUE`, `RESOLUTION_NOT_MATCHED`, `GUIA_NOT_MATCHED`, `FIELD_NOT_PRESENT`, `OTHER`.

## Resultado real do lote 2.0

O lote de 25 processos gerou 15 revisões, todas com causa sanitizada:

| Causa | Quantidade |
| --- | ---: |
| `MULTIPLE_INTERESTED` | 9 |
| `DOCUMENT_NOT_FOUND` | 3 |
| `GUIA_NOT_MATCHED` | 2 |
| `FIELD_NOT_PRESENT` | 1 |

Campos ausentes observados nas revisões: `matricula`, `dataNascimento`, `cargo` e `modalidade`. Nenhum valor foi inventado e nenhuma revisão foi salva.

Os seis `MISSING_FIELDS` da tentativa anterior não foram reclassificados individualmente; o lote novo é a evidência atual e cobre casos de documento, guia e campo ausente. A antiga limitação `NOT_CLASSIFIED_REAL` está superada para o lote 2.0.

## Cobertura sintética

`tests/unit/batch-missing-fields.test.mjs` cobre todas as categorias e a remoção de campos desconhecidos. `batch-saving.test.mjs` cobre a gravação no diário; `batch-report.test.mjs` cobre a exposição no relatório.

## Limitações

- Documentos digitalizados sem texto continuam fora do escopo (sem OCR).
- A classificação depende do diagnóstico documental real; falhas anteriores ao `proposalStatus` podem cair em `OTHER`.
- O lote real teve 10 salvos e 15 revisões; a qualidade é medida pela redução de falhas corrigíveis, não por forçar 100% de preenchimento.
