# Diagnóstico final — campos ausentes e documentos (F3)

Data: 05/11/2026
Escopo: classificação sanitizada de `MISSING_FIELDS`; sem valores, nomes, CPF, matrícula ou datas.

## O que foi implementado

- `src/batch/missing-fields.mjs` classifica a causa a partir de:
  - nomes de campos devolvidos pela validação do formulário;
  - `proposalStatus` por campo (`exact`, `ambiguous`, `absent`);
  - `resolutionFound` e `guiaFound`;
  - códigos de erro sanitizados.
- `src/background/bridge.mjs` devolve `fieldDiagnostics` sem valores: status por campo, `resolutionFound`, `guiaFound`, `skipped` e `errors`.
- `src/batch/runner.mjs` persiste em `batch.diagnostics[processId]`:
  `{ cause, fields[], at }`.
- `src/batch/journal.mjs` aceita apenas os cinco nomes de campo conhecidos e limita a causa a 40 caracteres.
- `src/batch/report.mjs` expõe `cause` e `fields` por item, mantendo `reasonCode` genérico.

## Categorias

| Causa | Quando é usada |
| --- | --- |
| `INTERESTED_MISMATCH` | identidade do interessado mudou ou não confere |
| `TIMEOUT` | leitura/aplicação excedeu o tempo |
| `PDF_NOT_READABLE` | PDF ausente, inválido ou sem texto |
| `UNSUPPORTED_FORMAT` | formato documental não suportado |
| `DOCUMENT_NOT_FOUND` | nem Resolução nem Guia foram encontradas |
| `AMBIGUOUS_VALUE` | mais de um valor possível para o campo |
| `RESOLUTION_NOT_MATCHED` | Resolução não localizada, mas Guia/outros documentos presentes |
| `GUIA_NOT_MATCHED` | somente a data de nascimento falta e a Guia não foi localizada |
| `FIELD_NOT_PRESENT` | documento correto, mas o campo não existe/está vazio |
| `OTHER` | caso não classificado |

## Os seis processos reais de 05/11/2026

O lote real registrou 6 `REVIEW_REQUIRED/MISSING_FIELDS`, mas o diário daquela execução não guardava a causa por campo. Não houve nova sessão read-only no QA nesta fase; portanto os seis permanecem `NOT_CLASSIFIED_REAL`. O código novo passa a gravar a causa e os campos no próximo lote sintético ou read-only autorizado.

Isso não é falha de implementação: é uma limitação de evidência. Não foram inventadas causas nem recuperados dados pessoais.

## Cobertura sintética

`tests/unit/batch-missing-fields.test.mjs` cobre todas as categorias acima, prioridade de identidade/timeout e a remoção de nomes de campo desconhecidos. `batch-saving.test.mjs` cobre a gravação de `GUIA_NOT_MATCHED` em `batch.diagnostics`; `batch-report.test.mjs` cobre a exposição sanitizada no relatório.

## Limitações

- A classificação depende do diagnóstico documental real; se a extração falhar antes de produzir `proposalStatus`, o código usa os campos devolvidos pela validação e pode cair em `OTHER`.
- Documentos digitalizados sem texto continuam fora do escopo (sem OCR).
- O próximo passo read-only deve abrir os seis processos, sem preencher nem salvar, e confirmar a categoria de cada um.
