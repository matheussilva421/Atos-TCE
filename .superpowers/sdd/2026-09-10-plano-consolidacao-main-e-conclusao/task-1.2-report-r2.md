# Task 1.2 - project verification gate (r2)

## Status

Concluída. O comando único offline executa extensão, web, Python amplo,
PowerShell, empacotamento/auditoria e `git diff --check`, preserva códigos de
falha por etapa e termina com exit code 0 em duas execuções completas
consecutivas.

O gate não abre Chrome autenticado, não coleta/download/OCR e não envia ou
finaliza atos. Os logs brutos usados para a prova ficaram fora do repositório,
em `%TEMP%`.

## Causa raiz das falhas

O baseline informado para esta retomada era 931 executados, 925 aprovados e 4
falhas contextuais: uma asserção PowerShell sobre referência contendo somente
arquivo/linha e três casos `TransferBusyError` no bloco de pacote.

A reprodução dirigida de 2026-09-10 às 20:33:06 executou os blocos na ordem do
gate. Ela produziu 931 executados, 924 aprovados, 5 falhas e 2 skips:

- extensão: 290/290;
- web: 6/6;
- Python amplo: 34/34;
- PowerShell: 19/19, 83/83, 31/31, 1/1, 114/114 e a suíte de cleanup do
  outro agente em 279 executados, 277 aprovados e 2 falhas transitórias;
- package/audit: 73 executados, 68 aprovados, 3 falhas e 2 skips;
- diff: 1/1.

As três falhas de pacote foram reproduzidas somente quando o Python era criado
com o runner em `System.Diagnostics.ProcessStartInfo` usando
`UseShellExecute=false`, stdout/stderr redirecionados e
`CreateNoWindow=true`. Nesse modo, Python 3.14 no Windows retorna
`OSError: [WinError 87] Parâmetro incorreto` para
`os.kill(os.getpid(), 0)`. O helper `prepare_transfer._pid_is_alive` tratava
esse resultado como PID morto; por isso removia os marcadores vivos
`service.json`/`collector.json` e não levantava `TransferBusyError` nos três
cenários.

O mesmo teste isolado no console passou: `test_prepare_transfer` 10/10 e o
bloco completo de pacote 73/73 com 2 skips. Um probe mínimo com o mesmo
`ProcessStartInfo` confirmou exit 1 com `CreateNoWindow=true` e exit 0 com
`CreateNoWindow=false`. Esta é a causa concreta do vazamento aparente de estado;
não havia lock, `%TEMP%` ou processo residual do pacote a limpar.

A falha PowerShell observada na reprodução não era causada por esta tarefa: a
suíte `Test-WorkspaceCleanup.ps1` estava sendo ampliada pelo outro agente. Em
execuções intermediárias ela variou de 2 a 5 falhas e chegou a abortar por
parâmetros ainda não sincronizados (`TestBrowserProcesses`). Esse arquivo e
`clean-local-workspace.ps1` não foram modificados por este trabalho. Depois da
estabilização do agente paralelo, a suíte externa passou 307/307.

## RED -> GREEN

### RED

Foi adicionada primeiro uma regressão em
`work/tce-extractor/tests/Test-ProjectVerification.ps1`: um probe Python chama
`os.kill(os.getpid(), 0)` e imprime uma linha de teste somente se a liveness do
PID funcionar através do runner.

Com o runner original, o teste focal retornou:

```text
FAIL: python PID liveness probe passes through the verification runner
  expected: 0
  actual: 12
FAIL: python PID liveness probe does not create a runner failure
Test-ProjectVerification: 41 passed; 2 failed.
```

O exit 12 é o código distinto do estágio Python, portanto a regressão captura
o defeito real e não apenas a mensagem do pacote.

### GREEN

A correção mínima foi alterar somente `CreateNoWindow` para `$false` em
`Invoke-VerificationProcess`. Não foram adicionados retry, sleep global, skip,
redução de cobertura ou alteração em `prepare_transfer.py`.

O teste focal passou 43/43 em Windows PowerShell 5.1 e 43/43 em PowerShell 7.
O probe Python passou pelo runner e os testes existentes de códigos distintos,
timeout, encerramento de PID, dry-run e recusa de `Authenticated`, `Collect` e
`Send` permaneceram verdes.

## Prova final do gate

Comando de cada execução:

```powershell
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\work\tce-extractor\verify-project.ps1 -TimeoutSeconds 180 -LogRoot <log-root>
```

As duas execuções foram disparadas em sequência pelo mesmo comando controlador,
com diretórios de log independentes.

| Rodada | Extensão | Web | Python | PowerShell | Package/audit | Diff | Total | Tempo | Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 290/290 | 6/6 | 34/34 | 307/307 | 73 exec., 71 aprov., 2 skips | 1/1 | 959 exec., 957 aprov., 0 falhas, 2 skips | 108,97 s | 0 |
| 2 | 290/290 | 6/6 | 34/34 | 307/307 | 73 exec., 71 aprov., 2 skips | 1/1 | 959 exec., 957 aprov., 0 falhas, 2 skips | 108,12 s | 0 |

O bloco PowerShell inclui os seis scripts disponíveis, inclusive
`Test-ProjectVerification.ps1`; o verificador contabiliza essa invocação como
um comando observado, enquanto a suíte focal interna registra 43/43.

Logs da rodada 1:

`C:\Users\slvma\AppData\Local\Temp\tce-project-verification-r2-final-1-20260910-205849`

Logs da rodada 2:

`C:\Users\slvma\AppData\Local\Temp\tce-project-verification-r2-final-2-20260910-210038`

Ambas as saídas finais contêm `Executed: 959`, `Passed: 957`, `Failed: 0`,
`Skips: 2`, e todas as seis etapas em `passed code=0`.

## Arquivos e estado Git

Alterados nesta rodada sob ownership da tarefa:

- `work/tce-extractor/verify-project.ps1`;
- `work/tce-extractor/tests/Test-ProjectVerification.ps1`;
- `README.md`;
- este relatório;
- `progress.md` da pasta SDD.

Preservados sem edição, embora ainda modificados no checkout pelo outro agente:

- `work/tce-extractor/clean-local-workspace.ps1`;
- `work/tce-extractor/tests/Test-WorkspaceCleanup.ps1`.

Antes do commit, o stage deve conter somente os arquivos nominais desta tarefa
e o relatório/progresso. Não usar `git add .`, `git reset`, `git checkout` ou
`git clean`.

## Retomada

Se a sessão for interrompida antes do commit/push, executar `git status
--short --branch`, confirmar que os dois arquivos de cleanup continuam fora do
stage, e repetir somente a validação final se os logs não estiverem disponíveis.
Depois fazer stage nominal, commit com a mensagem
`test: add reproducible project verification gate`, `git push origin main` e
verificar `git status`/`git log`/`git ls-remote`.
