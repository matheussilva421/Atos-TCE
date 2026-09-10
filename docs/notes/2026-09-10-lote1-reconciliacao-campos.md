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

Esta é a fotografia da revisão 120 antes da correção de extração da Fase 2.2;
os números finais após a reexecução direcionada estão registrados ao final.

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

Na fotografia inicial, ambos permaneciam bloqueados para preflight. A correção
de extração da Fase 2.2 recuperou somente os oito registros com evidência local
de nascimento; nenhum preenchimento, abertura ou envio foi executado.

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

## Fase 2.2 — revisão de evidências e reexecução direcionada

Data da medição: 10/09/2026.

### Veredito por registro

Os vereditos usam somente o acervo local já baixado. `gap de extração` (a)
significa que o campo está legível na evidência indicada, mas não era
selecionado pelo classificador; `dado inexistente` (b) significa que a
evidência vinculada àquele ordinal não contém o campo; `documento
insuficiente` (c) significa que há menções ou documentos relacionados, mas
não uma fonte suficiente para preencher o campo com segurança. Nenhuma data,
identidade ou valor pessoal foi copiado para este relatório.

| Processo | Registro | Campo | Veredito | Evidência local medida |
|---|---:|---|---|---|
| `100012/2026` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 9, páginas 1–3: `processos/100012-2026/evento-0009-7047323/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `101577/2026` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 8, páginas 1, 3 e 5: `processos/101577-2026/evento-0008-7315930/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `102260/2026` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 11, página 2: `processos/102260-2026/evento-0011-7433089/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `102326/2026` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 10, página 2: `processos/102326-2026/evento-0010-7437132/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `102381/2026` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 9, páginas 2–4: `processos/102381-2026/evento-0009-7439847/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `103777/2025` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 9, páginas 1, 3 e 5: `processos/103777-2025/evento-0009-6920658/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `104280/2025` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 10, páginas 1–3: `processos/104280-2025/evento-0010-6959751/documento-001-Documento_Processo_Portal_Gestor.pdf` |
| `104338/2025` | 1 | `data_nascimento` | gap de extração (a) | Guia do Evento 11, páginas 1, 3 e 5: `processos/104338-2025/evento-0011-6961081/documento-001-Documento_Processo_Portal_Gestor.pdf`; o Evento 12 é uma guia corroborante nas mesmas páginas. |
| `104956/2025` | 1 | `data_nascimento` | dado inexistente (b) | Nos documentos vinculados ao ordinal 1 — Eventos 3 e 6 — não há rótulo/evidência de nascimento. Foram inspecionados 17/17 PDFs locais com texto nativo; a guia do Evento 10 pertence ao ordinal 2 e não foi transferida. |
| `104956/2025` | 2 | `modalidade` | documento insuficiente (c) | Despacho do Evento 4: `processos/104956-2025/evento-0004-6998772/documento-001-Documento_Processo_Portal_Gestor.pdf`; a menção narrativa não fornece campo canônico. A guia do Evento 10 também não fornece este campo. |
| `104956/2025` | 2 | `fundamento_legal` | documento insuficiente (c) | Despacho do Evento 4 e guia do Evento 10 não fornecem fundamento legal canônico para o ordinal 2. A resolução do Evento 6 foi conferida por identidade como ordinal 1 e foi excluída, sem transferência entre interessados. |

O classificador passou a reconhecer as duas variações locais de guia
financeira: o cabeçalho de planilha/composição da última remuneração e o
layout longo com remuneração do servidor no cargo efetivo. A extração
continuou exigindo o rótulo de nascimento e a data na própria página; não
houve inferência por idade, identificador, outro interessado ou evento.

### Reexecução somente do escopo afetado

O manifesto temporário `work/tce-extractor/tmp/fase22-reexec/manifest.json`
continha somente os 9 processos afetados e 19 documentos prioritários
classificados. A varredura de seleção mediu 190/190 PDFs locais dos nove
processos com texto nativo; nenhum dos 41 processos íntegros foi incluído no
manifesto ou no checkpoint temporário. A execução retornou `total=9`,
`completed=0`, `partial=9`; `partial` é o status interno do runner porque
`genero` opcional continua vazio, e não substitui a matriz dos seis campos
obrigatórios.

Fonte imutável antes/depois da execução:

`182742bac0ae070fb8b9ffcb3573f1843fe3fbaa82bf5201618ce6bed78f0d2b`.

O conjunto estrutural dos 41 processos não afetados produziu o hash
`237209cea95c83b2756d5c6947d1135a546911903f07e103e28eaf0b7269cdfe` em duas
leituras; a interseção entre processos íntegros e o checkpoint direcionado
foi `0`.

### Contagem final derivada

| `ready_for_preflight` | `blocked_fields` | Registros finais |
|---|---|---:|
| `true` | nenhum | 49 |
| `false` | `data_nascimento` | 1 |
| `false` | `modalidade`, `fundamento_legal` | 1 |

Assim, a correção recuperou oito registros e reduziu o lote de 10 para 2
registros bloqueados. Em nível de processo, há 49 processos elegíveis e um
processo com bloqueios (`104956/2025`). `genero` permanece ausente nos 51
registros, mas continua opcional. Nenhum preflight, preenchimento, abertura
ou envio foi executado.
