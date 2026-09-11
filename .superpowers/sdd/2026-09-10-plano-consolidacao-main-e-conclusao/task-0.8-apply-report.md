# Relatório — Tarefa 0.8 (`-Apply`) e validação pós-quarentena

Data: 2026-09-10  
Repositório: `C:\Users\slvma\Downloads\Github\Complementação de Atos`  
Executor: Windows PowerShell 5.1 (`C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`)

## Resultado final

O `-Apply` corrigido foi executado com sucesso e moveu todos os itens aprovados. O passo 4 passou e a reanálise do passo 5 terminou com exit code 0. A execução parou no passo 6 porque o script `verify-post-quarantine.ps1`, usando seus parâmetros padrão conforme o brief, contém um `RepoRoot` corrompido (`ComplementaÃ§Ã£o de Atos`) e falha no `Set-Location`. O passo 7 não foi executado. Não houve purge.

## Estado de partida medido

- `git status --short --branch`: `## main...origin/main` (limpo antes dos relatórios).
- `HEAD`: `d297b6644a19033d30a8e463585067f42e408a79`.
- `origin/main`: `d297b6644a19033d30a8e463585067f42e408a79`.
- Manifesto `tmp\fase0\workspace-cleanup-approved-r2.json`:
  - SHA-256: `A7994FF698DFABC690A0A50654D0C3A68996677DE4E336FF0AF6075DA11E492F`;
  - revisão: `r2`;
  - itens: `16074`;
  - bytes: `23126367618`.

## Passos e medições

### 1. Preflight read-only A

Comando:

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\tmp\fase0\probe-browser-blockers.ps1'
```

Exit code `0`:

- `approved_entries=16074`;
- `browser_area_candidates=794`;
- `owned=0`;
- `exclusive_ok=794`;
- `locked=0`;
- `absent=0`.

### 2. Preflight read-only B (`-WhatIf`)

Comando:

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\work\tce-extractor\clean-local-workspace.ps1' -Root 'C:\Users\slvma\Downloads\Github\Complementação de Atos' -ManifestPath 'tmp\fase0\workspace-cleanup-approved-r2.json' -WhatIf
```

Exit code `0`; `mode=whatif`, `approved_items=16074`, `approved_bytes=23126367618`.

### 3. `-Apply`

Houve uma tentativa anterior sem `-Apply`, que retornou `mode=whatif` e não moveu nada. Ela foi corrigida conforme autorização do usuário com este comando exato:

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\work\tce-extractor\clean-local-workspace.ps1' -Root 'C:\Users\slvma\Downloads\Github\Complementação de Atos' -ManifestPath 'tmp\fase0\workspace-cleanup-approved-r2.json' -Apply 2>&1 | Tee-Object -FilePath '.\tmp\fase0\apply-run.log'
```

Exit code `0`. Resumo emitido:

```json
{"mode":"apply","approved_items":16074,"approved_bytes":23126367618,"receipt":"C:\\Users\\slvma\\Downloads\\Github\\Complementação de Atos\\tmp\\quarantine\\20260911-012750-653\\receipt.json","quarantine_root":"C:\\Users\\slvma\\Downloads\\Github\\Complementação de Atos\\tmp\\quarantine\\20260911-012750-653"}
```

### 4. Conferência do recibo

Recibo conferido em `tmp\quarantine\20260911-012750-653\receipt.json`.

Exit code `0`:

- `items=16074`;
- `moved=16074`;
- `not_moved=0`;
- `moved_bytes=23126367618`.

Gate do recibo: verde.

### 5. Reanálise read-only (Tarefa 0.9)

O cabeçalho confirmou os parâmetros `-Root` e `-ManifestPath`. Comando:

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\work\tce-extractor\analyze-local-workspace.ps1' -Root 'C:\Users\slvma\Downloads\Github\Complementação de Atos' -ManifestPath 'tmp\fase0\workspace-manifest-r3.json'
```

Exit code `0`; resumo: `entries=31721`, `manifest=written`, `skipped_directories=4`, `warnings=4`, `git_state_source=queried`.

### 6. Verificação pós-quarentena

Comando exigido pelo brief:

```powershell
& 'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File '.\tmp\fase0\verify-post-quarantine.ps1'
```

Exit code `1`. O script não chegou a calcular `preserved_missing`, `preserved_hash_changed`, `approved_still_present` ou `not_moved`: falhou no início em:

```text
Set-Location : Não é possível localizar o caminho 'C:\Users\slvma\Downloads\Github\ComplementaÃ§Ã£o de Atos' porque ele não existe.
No ...\tmp\fase0\verify-post-quarantine.ps1:9 caractere:1
```

O default do script é:

```powershell
[string]$RepoRoot = 'C:\Users\slvma\Downloads\Github\ComplementaÃ§Ã£o de Atos'
```

Conforme o brief, a execução foi interrompida sem alterar o script e sem tentar parâmetros alternativos.

### 7. Testes focais

Não executados porque o passo 6 falhou e o brief determina parar no primeiro gate falho. O esperado continua sendo `307/307`, mas não há medição nesta execução.

## Purge e estado final

- `-PurgeQuarantine`: não executado.
- `-Resume` de purge: não executado.
- Itens movidos: `16074`.
- Bytes movidos: `23126367618`.
- `not_moved`: `0`.
- Quarentena: `tmp\quarantine\20260911-012750-653`.
- O `apply-run.log` foi atualizado pela execução corrigida via `Tee-Object`.

## Fechamento pelo controlador (2026-09-10 23:10)

- Causa do passo 6: `tmp/fase0/verify-post-quarantine.ps1` estava em UTF-8 sem
  BOM; em Windows PowerShell 5.1 o literal acentuado era decodificado como
  Windows-1252 (`ComplementaÃ§Ã£o de Atos`). Correção mecânica: reescrita dos
  mesmos bytes como UTF-8 com BOM (3.131 bytes); nenhuma lógica alterada.
- Passo 6 reexecutado:
  `receipt_stamp=20260911-012750-653 items=16074 moved=16074 not_moved=0 moved_bytes=23126367618`;
  `preserved_checked=13485 preserved_missing=0 preserved_hash_changed=58 approved_still_present=0`.
  O exit 1 remanescente deve-se exclusivamente aos 58 hashes alterados, todos
  auditados: 38 caches `.pyc`, 19 arquivos rastreados e limpos frente ao Git
  (edições do dia já commitadas antes do `-Apply`) e 1 log ignorado; mtime
  máxima `21:27:00`, anterior ao início do `-Apply` (`22:13:39`), com zero
  arquivos `dirty` frente ao Git — nenhuma alteração causada pela quarentena.
- Passo 7 executado: `Test-WorkspaceCleanup.ps1` 307/307, 0 falhas, exit 0, em
  duas execuções (log em `tmp/fase0/tests-after-apply.log`).
- Purge permanece não executado; quarentena preservada para a Fase 9.3.
