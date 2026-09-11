# Tarefa 0.8 — hardening r2 do cleaner (revisão independente 3)

Data: 2026-09-10  
Escopo: `work/tce-extractor/clean-local-workspace.ps1` e
`work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`.

## Resultado

Os achados N1–N6 foram cobertos no contrato e na suíte focal. O harness passou
a exigir uma contagem fixa de 307 casos. A suíte Windows PowerShell 5.1 passou
em duas execuções consecutivas:

```text
Resultado: 307 passaram; 0 falharam.
EXIT_CODE=0
```

O warning de recibo truncado foi emitido por `Write-Warning` no caminho de
fallback; a chamada que coleta o resultado recebeu somente JSON no stdout.

## Contratos implementados

- **N1 — origem pinada:** no movimento, o cleaner abre a origem com
  `FileShare.Read -bor FileShare.Delete`, calcula o SHA-256 no mesmo stream e
  mantém o handle até depois de `Move-Item`, do hash pós-movimento e do
  rollback. Falha ao abrir produz `source file is in use` e não move a origem.
  O cabeçalho documenta exatamente `Risco residual: a origem é pinada por
  handle` e preserva `Ordem: validar raiz/manifesto`.
- **N2 — recibo e Resume:** `Write-Receipt` grava
  `receipt.json.<guid>.tmp` no mesmo diretório, publica com
  `[System.IO.File]::Replace($tmp,$destino,$null)` quando aplicável e usa
  backup efêmero somente para a incompatibilidade do binder PS 5.1/.NET; todo
  temporário é removido em erro/finally. `Resume` tenta parse e estrutura do
  recibo, emite warning e cai para `journal.ndjson` se o recibo estiver
  ilegível/incompleto. Purge permanece estrito.
- **N3 — processos:** enumeração real agora é fail-closed com
  `browser process enumeration failed`. `Get-BrowserProcesses` retorna
  `{ name; user_data_dir }`, aceita as variantes de nomes dos campos, usa os
  dez nomes de navegador contratados e tenta obter `--user-data-dir` via CIM
  apenas como evidência suplementar. Sem posse comprovada, cada arquivo é
  testado com `FileShare.None`; diretórios percorrem todos os arquivos. Falha
  nessa prova bloqueia com `running browser process`. Os seams
  `-TestBrowserProcesses` e `-TestDenyProcessEnumeration` exigem
  `-TestTemporaryRoot`.
- **N4 — purge:** há preflight recursivo de reparse point antes de qualquer
  `Remove-Item`; junction na quarentena recusa a operação, preservando recibo
  e alvo externo.
- **N5 — WhatIf:** `-WhatIf` é parâmetro explícito; tanto `-WhatIf` quanto
  `-Apply -WhatIf` produzem `mode=whatif` e não criam quarentena.
- **N6 — raiz:** `Assert-NoReparsePath` normaliza a raiz antes das comparações,
  aceitando separador final.

## TDD: RED → GREEN

Baseline registrado no laudo da revisão independente 3: 279 casos, 0 falhas.
Após escrever os testes N1–N6 e antes da implementação, o RED foi observado:

```text
Resultado: 282 passaram; 15 falharam.
```

Falhas representativas: parâmetros `TestBrowserProcesses`,
`TestDenyProcessEnumeration` e `WhatIf` ausentes; origem travada sem a mensagem
contratada; Resume abortando no `ConvertFrom-Json` do recibo truncado; purge de
junction sem mensagem `reparse`. O caso de aborto foi tornado determinístico
no próprio harness para selecionar somente quarentenas com timestamp.

Depois da implementação mínima e dos ajustes de compatibilidade, o GREEN foi
confirmado duas vezes com o comando abaixo; ambos terminaram em 307/0 e exit 0:

```powershell
powershell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File work\tce-extractor\tests\Test-WorkspaceCleanup.ps1
```

Checagens adicionais:

```text
cleaner_parse_errors=0
harness_parse_errors=0
git diff --check  => sem saída
encoding         => BOM=False, CRLF=False nos dois arquivos
```

Não foi executado `verify-project.ps1`, conforme o limite de ownership da fase.
Nenhum `-Apply` ou `-PurgeQuarantine` foi executado na raiz real; todos os
fixtures e holders ficaram sob `%TEMP%` e foram limpos pelo harness.

## Arquivos e decisões

- Alterados: `work/tce-extractor/clean-local-workspace.ps1` e
  `work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`.
- Criado: este relatório.
- O harness mantém os seams de teste existentes, adiciona holder real com
  `FileShare.None`, cenários de posse/ausência de posse, recibo truncado,
  junction de purge, WhatIf explícito e a asserção de contagem fixa.
- Nenhum arquivo de código do outro agente foi tocado.
- O fallback com backup efêmero é uma decisão de portabilidade: neste host o
  overload de `File.Replace` com backup nulo rejeita o `null` no binder; a
  segunda publicação continua sendo `File.Replace` atômica no mesmo diretório.

## Riscos residuais

- A pinagem depende das garantias de compartilhamento do filesystem; um
  processo que já abriu a origem com compartilhamento de escrita ainda pode
  alterar o conteúdo, embora o hash pinado e o hash pós-movimento detectem a
  divergência.
- A descoberta de `user_data_dir` via CIM é best-effort. Quando CIM é negado,
  a decisão não assume posse: exige a prova de exclusividade por arquivo.
- Não foram verificadas ACLs, alias 8.3 efetivo ou long paths fora dos fixtures
  já existentes; o teste lexical de `~`, nomes reservados e pontos/espaços foi
  preservado.
- A validação aqui é focal e em fixtures TEMP. A raiz real continua protegida;
  o `-Apply` da fase 0.9 exige seus próprios gates e aprovação operacional.

## GitHub e retomada

O outro agente deixou modificações não commitadas em
`verify-project.ps1`, `Test-ProjectVerification.ps1` e `README.md`; elas devem
ser preservadas ao fazer staging. Para retomar, confira `git status --short`,
estagie somente os arquivos nominais desta entrega, rode novamente o harness
focal e então conclua os commits/push registrados na resposta final.
