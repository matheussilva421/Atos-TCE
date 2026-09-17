# Handoff — gate TESTAR-PACOTE: canonicalização do hash lógico (2026-09-17)

## Contexto

Verificação pedida pelo operador ("verifique") sobre o pacote privado em
`outputs/tce-r3-completo` (código R3 + acervo completo). O `TESTAR-PACOTE.ps1`
reprovou com dois itens:

- `FALHOU: dados da extensao - batch.logical_sha256 nao corresponde ao conteudo do JSON`
- `FALHOU: auditoria private - auditoria private reprovada com 1 achado(s)`

O item `schema da extensao` nem chegou a rodar (depende de `dados da extensao`).

## Diagnóstico do hash (defeito do gate, não do dado)

Evidência de que o dataset está íntegro para os consumidores reais:

| Verificação | Resultado |
|---|---|
| `batch.logical_sha256` declarado | `81cf7eab4fd14db43c492db0a5f6e2944ac890cb251b16bc3fb14049defeba30` |
| `local_service._logical_dataset_sha256` (Python) | igual ao declarado |
| `fundamentos-contexto.v1.json` → `dataset_sha256` | igual ao declarado |
| cópia em `work/tce-extractor/acervo-tce/` | arquivo idêntico (sha256 `05f6a3757f5161ce07fb08a4105efcd6f385db1fae13fe6476041b573be2971a`) |
| convenção JS (`lib/schema.js` / `canonicalJson`) | mesma do Python (`ensure_ascii=False`) |

Primeira divergência byte a byte entre a canonicalização PowerShell e a Python:
`\u0027` na posição 196445 do JSON canônico — o PowerShell 5.1 escapa o apóstrofo
e o Python emite literal. O dataset tem 6 apóstrofos (ex.: `JOANA D'ARC SENA DE SOUSA`),
o que explica a diferença de exatamente 30 caracteres (6 × 5) entre as duas saídas.

Controle exaustivo (code points 0x0000–0x02FF + extras) comparando as duas
canonicalizações: o PowerShell 5.1 escapa `&` (0026), `'` (0027), `<` (003C),
`>` (003E), U+0085, U+2028 e U+2029; Python/JS emitem esses caracteres
literalmente. Nenhuma outra divergência.

## Correção (TDD)

1. RED — novo caso em `tests/Test-TcePortable.ps1`: dataset com
   `batch.id = "fixture-d'arc & cia <tce>"` e hash congelado
   `0b66db6d63fbff4109a94bcbe1c26dbc4aea084fabb38724bcb972a0da1b153c`
   (calculado pela convenção Python). Resultado: `136 passaram; 1 falharam` com
   `batch.logical_sha256 nao corresponde ao conteudo do JSON`.
2. GREEN — `ConvertTo-TcePortableCanonicalJson` em
   `portable/TESTAR-PACOTE.ps1`: normaliza os escapes espúrios do Windows
   PowerShell 5.1 preservando pares `\\` já escapados; `Get-TcePortableDatasetStatus`
   passou a usá-la. Resultado: `137 passaram; 0 falharam`.

Verificação no pacote real (`outputs/tce-r3-completo`), com o gate corrigido:

```
IsPresent=True
IsValid=True
LogicalSha256=81cf7eab4fd14db43c492db0a5f6e2944ac890cb251b16bc3fb14049defeba30
ProcessCount=724
RecordCount=739
Errors=
```

## Segundo achado (não é bug do gate)

A auditoria private acusa 1 achado real na pasta:
`acervo-tce/processos/100774-2023/evento-0001-4683626/documento-001-Documento_Processo_Portal_Gestor.pdf.d605102b0b0e4613958c35fd3d743870.part`
(`forbidden_file` — `.part`/`.tmp` não são distribuíveis).

O `.part` (0,17 MB) também existe no acervo fonte ao lado do PDF final (3,17 MB),
ou seja é sobra de download. O empacotador já exclui `.part`/`.tmp` do ZIP.
Ação tomada: removido **apenas da cópia de empacotamento**
(`outputs/tce-r3-completo`), com a fonte preservada em `work/tce-extractor/acervo-tce/`.

## Gates executados

| Gate | Resultado |
|---|---|
| `tests/Test-TcePortable.ps1` | 137 passaram; 0 falharam |
| `verify-project.ps1` | exit 0, 7 estágios verdes, 1244 executados, 1242 passaram, 0 falharam, 2 skips |
| `git diff --check` | limpo |

## Artefatos e estado do Git

- `work/tce-extractor/portable/TESTAR-PACOTE.ps1` (gate corrigido)
- `work/tce-extractor/tests/Test-TcePortable.ps1` (novo caso RED/GREEN)
- commit `e294f79` ("fix: align packaged dataset logical hash with python canonical json")
  enviado para `origin/main`; worktree limpo exceto o `work/tce-extractor/.codex-live-pilot.py`
  não rastreado (ferramenta local, não deve entrar no Git)
- cópias do gate atualizadas em `outputs/tce-r3-completo/` e `outputs/tce-r3-smoke/`
  (blob `2f612c3936c77d002c186609cf1719ae8f402e3f`), antes idênticas ao HEAD

### ZIP privado reconstruído (18:17:33)

`outputs/Atos-TCE-Professor-IPERN-completo-2026-09-17.zip`

| Campo | Valor |
|---|---|
| bytes | 5.845.381.507 (5,44 GiB) |
| SHA-256 | `cf64e3f8f5e5703fd6a2be11dea729458e816517a00e1958f56ad5088c8276bf` |
| entradas | 33.057 (9,31 GB descompactados) |
| conteúdo | 724 processos, 17.619 eventos, 14.179 PDFs, 26 arquivos de extensão, 739 registros |
| CRC | verificado pelo empacotador (`crc_ok: true`) |
| `.part`/`.tmp` | 0 entradas |
| módulos R3 | `background/legal-context-resolver.js` e `lib/catalog-option-signature.js` presentes |
| gate embarcado | `TESTAR-PACOTE.ps1` com SHA-256 `d0787867…` (versão corrigida) |

O build anterior foi interrompido de propósito: o staging dele já estava pronto com o gate
antigo, então o ZIP carregaria o gate defeituoso.

## Pendências

- `TESTAR-PACOTE` na extração do ZIP: extração em `outputs/qa-extract-2026-09-17` seguida do
  gate, em background (logs `%TEMP%\r3-zip-extract.log` e `%TEMP%\r3-zip-gate.log`);
- o gate na pasta `outputs/tce-r3-completo` foi interrompido no meio da auditoria (para não
  disputar I/O com o empacotamento); o item `dados da extensao` já havia sido validado com o
  gate corrigido antes disso;
- limpar stagings órfãos em `%TEMP%` (`tce-package-staging-9dduk0os` 8,67 GB,
  `-xvi4hh4n` 8,67 GB, `-zi1jed76` vazio): pertencem ao usuário real e exigem privilégio;
  `-0jum8bsv` já foi removido;
- smoke real supervisionado do R3 (operador, login manual, sem envio).
