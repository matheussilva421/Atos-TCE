# Lote 1 — reconciliação de campos obrigatórios

Data da medição: 10/09/2026.

## Fonte e estrutura observada

Fonte somente leitura: `work/tce-extractor/outputs/live-real-fase11h-sector-lot50/publicacoes/120/resultados.json`.

- `schema_version`: 1.
- `revision`: 120.
- Raiz: objeto com as chaves `published_at`, `results`, `revision` e
  `schema_version`.
- `results`: objeto/dicionário com 50 chaves de processo.
- Cada valor de `results`: objeto com `blocks`, `pending`, `process` e `status`.
- `blocks`: 49 processos têm um bloco e `104956/2025` tem dois, totalizando
  51 registros de interessado.
- Cada bloco: `fields`, `interested` e `pending`; `fields` contém as sete
  chaves analisadas.
- Todos os 50 resultados têm status `partial`; as listas `pending` estão
  vazias.

O campo `interested` foi usado apenas para contar identidades normalizadas.
Nenhum valor de identidade foi emitido pelo script ou copiado para este
relatório. A fonte tem 51 registros com identidade e 51 identidades distintas
na contagem normalizada; por processo, 49 têm uma identidade e
`104956/2025` tem duas.

## Contagem reconciliada

| Unidade medida | Quantidade |
|---|---:|
| Chaves de processo em `results` | 50 |
| Processos com um registro | 49 |
| Processos com dois registros | 1 |
| Registros de interessado | 51 |
| Registros além da contagem de processos | 1 |
| Identidades de interessado presentes | 51 |
| Identidades distintas na contagem normalizada | 51 |

Assim, a estrutura não é um registro por processo: é um registro por bloco de
interessado. A explicação numérica é `49 × 1 + 1 × 2 = 51` registros para 50
processos. O registro adicional pertence ao segundo bloco de `104956/2025`.

## Campos e prontidão

Campos obrigatórios: `modalidade`, `fundamento_legal`, `data_publicacao_doe`,
`cargo`, `matricula` e `data_nascimento`. `genero` é opcional e não bloqueia o
preflight.

Medição por registro:

| Campo | Encontrado | Ausente |
|---|---:|---:|
| `modalidade` | 50 | 1 |
| `fundamento_legal` | 50 | 1 |
| `data_publicacao_doe` | 51 | 0 |
| `cargo` | 51 | 0 |
| `matricula` | 51 | 0 |
| `data_nascimento` | 42 | 9 |
| `genero` (opcional) | 0 | 51 |

Registros com campos obrigatórios ausentes, identificados somente por processo
e ordinal interno:

- `100012/2026` — registro #1: `data_nascimento`.
- `101577/2026` — registro #1: `data_nascimento`.
- `102260/2026` — registro #1: `data_nascimento`.
- `102326/2026` — registro #1: `data_nascimento`.
- `102381/2026` — registro #1: `data_nascimento`.
- `103777/2025` — registro #1: `data_nascimento`.
- `104280/2025` — registro #1: `data_nascimento`.
- `104338/2025` — registro #1: `data_nascimento`.
- `104956/2025` — registro #1: `data_nascimento`.
- `104956/2025` — registro #2: `modalidade`, `fundamento_legal`.

### Matriz agregada

| `ready_for_preflight` | `blocked_fields` | Registros |
|---|---|---:|
| `true` | nenhum | 41 |
| `false` | `data_nascimento` | 9 |
| `false` | `modalidade`, `fundamento_legal` | 1 |

Portanto, há 41 registros prontos e 10 registros bloqueados. Os 10 registros
bloqueados pertencem a 9 processos, porque `104956/2025` contribui com dois
registros bloqueados.

## Diferença entre “40 somente gênero”, 9 sem nascimento e 50 processos

A lista anterior de 40 processos classificados como “somente gênero” estava
incompleta. A revisão 120 mede 41 registros/processos com todos os seis campos
obrigatórios encontrados e somente `genero` ausente. O processo restante é
`104611/2025`, que pertence à categoria “somente gênero”.

A contagem corrigida por registro é:

`41 somente gênero + 9 sem data de nascimento + 1 sem modalidade/fundamento legal = 51 registros`.

A contagem por processo é:

`41 processos prontos + 9 processos com bloqueio = 50 processos`.

Os nove processos com bloqueio são `100012/2026`, `101577/2026`,
`102260/2026`, `102326/2026`, `102381/2026`, `103777/2025`, `104280/2025`,
`104338/2025` e `104956/2025`.

## Caso `104956/2025`

O processo possui dois interessados/registros. Para não publicar dado pessoal,
eles são referidos apenas por ordinal interno:

- registro #1: falta `data_nascimento`; `modalidade` e `fundamento_legal` estão
  presentes;
- registro #2: faltam `modalidade` e `fundamento_legal`; os demais campos
  obrigatórios, inclusive `data_nascimento`, estão presentes.

Ambos permanecem bloqueados para preflight. Nenhuma correção de extração,
preenchimento, abertura ou envio foi executada.

## Comandos e evidência

Comando da reconciliação, executado em
`C:\Users\slvma\Downloads\Github\Complementação de Atos\work\tce-extractor`:

```powershell
& 'C:\Python314\python.exe' reconcile_lote1.py
```

Resultado: exit 0; JSON emitido em stdout com `process_key_count=50`,
`interested_identity_count=51`, `record_count=51`, `processes_with_one_record=49`,
`processes_with_two_records=1` e a matriz `41 / 9 / 1` acima. Duas execuções
consecutivas produziram stdout idêntico. O hash SHA-256 observado da fonte foi
`182742bac0ae070fb8b9ffcb3573f1843fe3fbaa82bf5201618ce6bed78f0d2b`; o hash
antes/depois das duas execuções foi igual.

Teste TDD, executado no mesmo diretório:

```powershell
& 'C:\Python314\python.exe' -m unittest test_reconcile_lote1
```

Resultado final: 1 teste executado, 1 aprovado, 0 falhos. O primeiro RED foi
observado antes do script existir (`ModuleNotFoundError: No module named
'reconcile_lote1'`, 0 testes executados). Após a implementação mínima, o teste
ficou GREEN. Uma segunda asserção estrutural produziu RED pela repetição das
chaves; a deduplicação ordenada foi aplicada e o GREEN final permaneceu em
1/1.
