# Inventário inicial — Fase 0 / Tarefa 0.1

Data da captura: `2026-09-10T13:18:22.016-03:00`

## Escopo e limite

Esta fotografia congela o checkout compartilhado antes de qualquer organização.
Foram feitas somente inspeções Git de leitura, uma cópia não destrutiva do diff
rastreado, cópias dos arquivos não rastreados e leituras SHA-256. Não houve
troca de branch, merge, push, alteração do Chrome, abertura de ZIP, leitura de
conteúdo privado ou organização/limpeza.

O brief dizia “dez arquivos não rastreados”. O estado real capturado contém 13
arquivos não rastreados: os 13 foram preservados em recovery para que nenhum
trabalho local fosse omitido. A divergência é mantida como risco explícito.

## Estado Git registrado

Todos os comandos Git abaixo foram executados com o `safe.directory` explícito
para este checkout.

| Comando | Resultado compacto |
|---|---|
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' status --porcelain=v2 --branch` | `branch.oid=16bf74ed59b49e331a4f0db4dd071d968c2543da`; `branch.head=codex/fundamentacao-automatico`; 32 caminhos rastreados modificados, 13 não rastreados, 0 staged; sem conflito. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' branch -vv` | ativa `codex/fundamentacao-automatico` em `16bf74e`; também listadas `codex/transfer-quiescence` em `ef7d44b` e `main` em `dc84402`. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' worktree list --porcelain` | um worktree: `C:/Users/slvma/Downloads/Github/Complementação de Atos`, branch `refs/heads/codex/fundamentacao-automatico`. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' log --graph --all -30` | executado com sucesso; 30 commits recentes percorridos; topo `16bf74e`, seguido por `d11886b`, `9feccd2` e `fd2bd20`. Saída completa está implicitamente recuperável pelos refs; não foi copiada para não tornar o inventário ruidoso. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' remote -v` | saída vazia; nenhum remoto configurado. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' fsck --no-dangling` | status 0, saída vazia; nenhum objeto dangling reportado. |
| `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' rev-parse HEAD` | `16bf74ed59b49e331a4f0db4dd071d968c2543da`. HEAD esperado `16bf74e`: confirmado, sem drift. |

O diff rastreado foi de 32 arquivos, 2.432 inserções e 102 remoções. O patch
binário completo está em `tmp/fase0-recovery/tracked.patch`; a lista de nomes
e o conteúdo de trabalho não foram reproduzidos neste inventário.

## Recuperação produzida

### Diff rastreado

Comando: `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' diff --binary HEAD --output=tmp/fase0-recovery/tracked.patch`

- caminho: `tmp/fase0-recovery/tracked.patch`
- tamanho: `196257` bytes; não vazio
- SHA-256: `743BA7CA84EADD84BDD67B3BAE7656F8BDAD23A3572080B7EE8D7DC09A6BCAFF`
- leitura de retorno: `196257` bytes lidos, igual ao tamanho do arquivo

### Arquivos não rastreados copiados

Origem e destino foram comparados por tamanho e SHA-256. Os destinos ficam em
`tmp/fase0-recovery/untracked/`, mantendo o caminho relativo.

| Caminho relativo | Bytes | SHA-256 |
|---|---:|---|
| `docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md` | 5409 | `8D952F0BD27613F1759FA3D4DFC65087F6F13B680159147BAF8D6DC316530109` |
| `docs/notes/2026-09-10-estado-atual-auditoria-handoff.md` | 4408 | `2DAC7C388E57AB7F9F120F133932BCE8F39A3E16CC750FD8B7C12347255458ED` |
| `docs/notes/2026-09-10-fase11-area-restrita-automacao-handoff.md` | 34392 | `AD1718797C227362B1CC68B40441977F2F67CA9B47443CA5674D3C5517B9FBCD` |
| `docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md` | 8738 | `7D120C33D2560D0CA962D084CCDD9966F81DC8CB2FD7E87A891DE16C0D2D32E2` |
| `docs/notes/2026-09-10-lote1-campos-incompletos.md` | 3104 | `DFCCF28EA0BDF1EEE0BFC80F21CB1D4E0FDD09E91AF29A003D31E494F6651911` |
| `docs/notes/2026-09-10-novo-plano-handoff.md` | 1549 | `DEE67ED8BB138650A984DBDCAA048099EFAD3514E1764BD1965250EB0A81699E` |
| `docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md` | 23813 | `7254B784B22891674A999856DC96AD3D322C5BDF188957F8B24A8AAF9DC3E9E0` |
| `work/tce-extractor/portable/TceFrozenQueue.psm1` | 5896 | `7B11436628176157A92F9CB20A52CB7242D41692881EF90C8613709BF718C68F` |
| `work/tce-extractor/portable/app/acquisition.py` | 2963 | `EA93EB6419C6FCA54AEA60CEFE245E9A144EA10419EF90588145A6426E2E1B1A` |
| `work/tce-extractor/portable/app/analysis_preview.py` | 5516 | `04FC66926E706A6D0CF236A35BA53669BA3BF75EAB31E7FD8306B0A3DC297B76` |
| `work/tce-extractor/portable/app/batch_scope.py` | 14161 | `179C8D20D8E103B01998242755155E8E402A01D14811D16E9B7D7D5D546D5F18` |
| `work/tce-extractor/portable/app/frozen_queue.py` | 8302 | `6E6E8E9FA723ACF34D507B50E94805FA063F38CDFED7982BCDB2CA27C5569448` |
| `work/tce-extractor/portable/app/source_reconciliation.py` | 8469 | `8AF8C1414D6A8EDC931D37C12C91B3E1CD8EC5F46AA0B9586880866DC77F1D53` |

Resultado: 13/13 cópias concluídas e verificadas; não houve falha de cópia ou
de hash.

### ZIPs essenciais e candidatos

Os ZIPs foram tratados como bytes opacos: somente existência, tamanho e
SHA-256 foram lidos. Nenhum conteúdo de arquivo ou entrada de ZIP foi aberto no
relatório.

| Rótulo | Caminho relativo | Bytes | SHA-256 |
|---|---|---:|---|
| `fase11k` | `work/tce-extractor/outputs/tce-processos-completo-portatil-fase11k.zip` | 95877835 | `85BAD2192F6F3C7289F574D4EF126F4700565843AFB5793E61E49CD47DE05FBB` |
| `acervo-autorizado-05-09-outputs` | `outputs/TCE-Acervo-Atualizado-227-2026-09-05.zip` | 1737402229 | `A621791800A24AB6292B755D473AEF6B3F407E167A4BF4BEB8272ACB68FF1720` |
| `acervo-autorizado-05-09-root-v2-duplicate` | `TCE-Acervo-Atualizado-227-2026-09-05 - v2.zip` | 1737402229 | `A621791800A24AB6292B755D473AEF6B3F407E167A4BF4BEB8272ACB68FF1720` |
| `candidate-portable-v6` | `artifacts/pacote-portatil-completo-2026-09-08-acervo-2026-09-05-v6.zip` | 1739036921 | `9CAEC8F5A8D0C0B3EB6CE80E541B2C6E050CBD8BD1905D5BB23FD2F1337A4B42` |
| `candidate-extension-v5` | `artifacts/extensao-complementar-ato-2026-09-08-v5.zip` | 34364 | `4CA334FECA7483B44429C12C6A6DFAAB126202F03D64F3296B3463F33B019E98` |

O ZIP raiz `- v2` e o ZIP do acervo em `outputs/` são cópias byte a byte
equivalentes pelo tamanho e hash. O v6 é o candidato portátil mais novo; o v5
é o candidato adicional mais novo da extensão. Revisões históricas anteriores
não foram abertas nem classificadas como retenção nesta tarefa.

## Verificação de whitespace

Comando: `git -c safe.directory='C:/Users/slvma/Downloads/Github/Complementação de Atos' diff --check`

- status: `0`
- único aviso aceito: `work/tce-extractor/portable/INICIAR.cmd`: “LF will be
  replaced by CRLF the next time Git touches it”
- erros de whitespace: nenhum

## Checklist do brief

- [x] Diagnósticos Git solicitados registrados com resultados compactos.
- [x] `HEAD=16bf74e` confirmado.
- [x] `tracked.patch` gerado com `git diff --binary HEAD`, não vazio e lido de
  volta integralmente.
- [x] Todos os arquivos não rastreados presentes no estado real foram copiados
  com caminhos relativos e hashes. O brief dizia dez, mas havia 13; os três
  adicionais foram preservados, não descartados.
- [x] SHA-256 do `fase11k`, do acervo autorizado de 05/09 e dos ZIPs candidatos
  relevantes foi registrado sem expor conteúdo privado.
- [x] `git diff --check` aprovado com apenas o aviso EOL conhecido de
  `INICIAR.cmd`.
- [x] Condição STOP satisfeita: cópias, hashes e leitura de retorno passaram;
  nenhuma organização foi iniciada.

## Estado de continuidade

O checkout permanece na branch `codex/fundamentacao-automatico`, com as 32
alterações rastreadas e os 13 arquivos não rastreados originais preservados.
Não há remoto configurado. O próximo agente deve reexecutar `git status
--porcelain=v2 --branch`, verificar os hashes deste inventário e só então
iniciar a Tarefa 0.2; não deve remover, mover, reverter ou organizar esses
artefatos sem aprovação e sem usar este recovery.
