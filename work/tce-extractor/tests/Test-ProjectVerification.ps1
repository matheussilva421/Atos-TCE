$ErrorActionPreference = 'Stop'

$script:passed = 0
$script:failed = 0

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)

    $actualText = $Actual | ConvertTo-Json -Compress -Depth 20
    $expectedText = $Expected | ConvertTo-Json -Compress -Depth 20
    if ($actualText -ne $expectedText) {
        $script:failed++
        Write-Host "FAIL: $Name`n  expected: $expectedText`n  actual: $actualText" -ForegroundColor Red
    } else {
        $script:passed++
        Write-Host "PASS: $Name" -ForegroundColor Green
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Name)
    Assert-Equal $Condition $true $Name
}

function Assert-Contains {
    param([string]$Text, [string]$Needle, [string]$Name)
    Assert-True ($Text.IndexOf($Needle, [StringComparison]::OrdinalIgnoreCase) -ge 0) $Name
}

function Get-TestPowerShell {
    $windowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf) { return $windowsPowerShell }
    $pwsh = Join-Path $PSHOME 'pwsh.exe'
    if (Test-Path -LiteralPath $pwsh -PathType Leaf) { return $pwsh }
    return (Get-Command powershell.exe -ErrorAction Stop).Source
}

function Invoke-TestScript {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][AllowEmptyCollection()][string[]]$Arguments
    )

    $shell = Get-TestPowerShell
    $output = @(& $shell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $FilePath @Arguments 2>&1)
    [pscustomobject]@{
        ExitCode = [int]$LASTEXITCODE
        Output = (($output | ForEach-Object { [string]$_ }) -join "`n")
    }
}

function New-TestCommandOverrides {
    param(
        [Parameter(Mandatory)][string]$FixturePath,
        [Parameter(Mandatory)][string]$Root,
        [string]$FailStage = '',
        [int]$FailCode = 7,
        [int]$SleepSeconds = 0,
        [string]$PidPath = '',
        [string]$MarkerPath = ''
    )

    $shell = Get-TestPowerShell
    $stages = @('extension', 'web', 'python', 'powershell', 'package', 'automation', 'diff')
    $overrides = [ordered]@{}
    foreach ($stage in $stages) {
        $exitCode = if ($stage -eq $FailStage) { $FailCode } else { 0 }
        $arguments = @(
            '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
            '-File', $FixturePath, '-Stage', $stage, '-ExitCode', [string]$exitCode
        )
        if ($SleepSeconds -gt 0 -and $stage -eq $FailStage) { $arguments += @('-SleepSeconds', [string]$SleepSeconds) }
        if (-not [string]::IsNullOrWhiteSpace($PidPath) -and $stage -eq $FailStage) { $arguments += @('-PidPath', $PidPath) }
        if (-not [string]::IsNullOrWhiteSpace($MarkerPath)) { $arguments += @('-MarkerPath', $MarkerPath) }
        $overrides[$stage] = [ordered]@{
            filePath = $shell
            arguments = $arguments
            workingDirectory = $Root
            displayCommand = 'test double ' + $stage
        }
    }
    return $overrides
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$verifierPath = Join-Path $projectRoot 'work\tce-extractor\verify-project.ps1'
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-project-verification-test-' + [guid]::NewGuid().ToString('N'))
$fixturePath = Join-Path $fixtureRoot 'stage-double.ps1'
$overridePath = Join-Path $fixtureRoot 'overrides.json'
$markerPath = Join-Path $fixtureRoot 'executed.marker'
New-Item -ItemType Directory -Path $fixtureRoot -Force | Out-Null

try {
    Assert-True (Test-Path -LiteralPath $verifierPath -PathType Leaf) 'verifier script exists'
    $verifierText = Get-Content -LiteralPath $verifierPath -Raw -Encoding UTF8
    foreach ($forbiddenReference in @('Coletar-Processos-TCE', 'real_portal_session', 'chrome.exe', 'https://', 'http://')) {
        Assert-True ($verifierText.IndexOf($forbiddenReference, [StringComparison]::OrdinalIgnoreCase) -lt 0) ('verifier has no offline boundary escape: ' + $forbiddenReference)
    }

    $fixtureText = @'
param(
    [string]$Stage,
    [int]$ExitCode = 0,
    [int]$SleepSeconds = 0,
    [string]$PidPath = '',
    [string]$MarkerPath = ''
)
if (-not [string]::IsNullOrWhiteSpace($PidPath)) {
    [IO.File]::WriteAllText($PidPath, [string]$PID)
}
if (-not [string]::IsNullOrWhiteSpace($MarkerPath)) {
    [IO.File]::AppendAllText($MarkerPath, $Stage + "`n")
}
Write-Output '1 passed, 0 failed, 0 skipped'
if ($SleepSeconds -gt 0) { Start-Sleep -Seconds $SleepSeconds }
exit $ExitCode
'@
    [IO.File]::WriteAllText($fixturePath, $fixtureText, (New-Object Text.UTF8Encoding($false)))

    $dryRunOverrides = New-TestCommandOverrides -FixturePath $fixturePath -Root $projectRoot -FailStage 'extension' -MarkerPath $markerPath
    $dryRunOverrides | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $overridePath -Encoding UTF8
    $dryRun = Invoke-TestScript -FilePath $verifierPath -Arguments @('-DryRun', '-CommandOverridesPath', $overridePath)
    Assert-Equal $dryRun.ExitCode 0 'dry run exits zero'
    foreach ($stage in @('extension', 'web', 'python', 'powershell', 'package', 'automation', 'diff')) {
        Assert-Contains $dryRun.Output $stage ('dry run lists ' + $stage + ' stage')
    }
    Assert-Contains $dryRun.Output 'Executed: 0' 'dry run reports zero executed commands'
    Assert-Contains $dryRun.Output 'Skips: 7' 'dry run reports seven skips'
    Assert-True (-not (Test-Path -LiteralPath $markerPath)) 'dry run does not execute command doubles'

    $greenOverrides = New-TestCommandOverrides -FixturePath $fixturePath -Root $projectRoot -MarkerPath $markerPath
    $greenOverrides | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $overridePath -Encoding UTF8
    $green = Invoke-TestScript -FilePath $verifierPath -Arguments @('-CommandOverridesPath', $overridePath, '-LogRoot', (Join-Path $fixtureRoot 'green-logs'))
    Assert-Equal $green.ExitCode 0 'all stages green exits zero'
    Assert-Contains $green.Output 'Executed: 7' 'green summary reports seven executed stages'
    Assert-Contains $green.Output 'Passed: 7' 'green summary reports seven passed stages'
    Assert-Contains $green.Output 'Failed: 0' 'green summary reports zero failed stages'
    Assert-Contains $green.Output 'Skips: 0' 'green summary reports zero skips'
    Assert-Contains $green.Output 'Command:' 'green summary includes command field'
    Assert-True ((Get-Content -LiteralPath $markerPath).Count -eq 7) 'all seven command doubles executed once'

    # Python em Windows precisa de um processo com console herdado para que
    # os.kill(pid, 0) consiga validar marcadores de runtime. O runner não pode
    # usar o modo CREATE_NO_WINDOW nesse caminho: Python 3.14 retorna
    # WinError 87 e a transferência passa a interpretar um processo vivo como
    # morto.
    $pidProbePath = Join-Path $fixtureRoot 'pid-liveness-probe.py'
    $pidProbeText = @'
import os
os.kill(os.getpid(), 0)
print("1 passed, 0 failed, 0 skipped")
'@
    [IO.File]::WriteAllText($pidProbePath, $pidProbeText, (New-Object Text.UTF8Encoding($false)))
    $pidProbeOverrides = New-TestCommandOverrides -FixturePath $fixturePath -Root $projectRoot
    $pidProbeOverrides['python'] = [ordered]@{
        filePath = (Get-Command python.exe -ErrorAction Stop).Source
        arguments = @($pidProbePath)
        workingDirectory = $fixtureRoot
        displayCommand = 'python PID liveness probe'
    }
    $pidProbeOverrides | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $overridePath -Encoding UTF8
    $pidProbe = Invoke-TestScript -FilePath $verifierPath -Arguments @('-CommandOverridesPath', $overridePath, '-LogRoot', (Join-Path $fixtureRoot 'pid-probe-logs'))
    Assert-Equal $pidProbe.ExitCode 0 'python PID liveness probe passes through the verification runner'
    Assert-Contains $pidProbe.Output 'Failed: 0' 'python PID liveness probe does not create a runner failure'

    $expectedCodes = [ordered]@{
        extension = 10
        web = 11
        python = 12
        powershell = 13
        package = 14
        automation = 16
        diff = 15
    }
    foreach ($stage in $expectedCodes.Keys) {
        $failureOverrides = New-TestCommandOverrides -FixturePath $fixturePath -Root $projectRoot -FailStage $stage -MarkerPath $markerPath
        $failureOverrides | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $overridePath -Encoding UTF8
        $failedRun = Invoke-TestScript -FilePath $verifierPath -Arguments @('-CommandOverridesPath', $overridePath, '-LogRoot', (Join-Path $fixtureRoot ('failure-' + $stage)))
        Assert-Equal $failedRun.ExitCode $expectedCodes[$stage] ('failed ' + $stage + ' preserves distinct exit code')
    }

    $pidPath = Join-Path $fixtureRoot 'timed-out.pid'
    $timeoutOverrides = New-TestCommandOverrides -FixturePath $fixturePath -Root $projectRoot -FailStage 'python' -SleepSeconds 30 -PidPath $pidPath -MarkerPath $markerPath
    $timeoutOverrides | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $overridePath -Encoding UTF8
    $timeout = Invoke-TestScript -FilePath $verifierPath -Arguments @('-CommandOverridesPath', $overridePath, '-TimeoutSeconds', '1', '-LogRoot', (Join-Path $fixtureRoot 'timeout-logs'))
    Assert-Equal $timeout.ExitCode 124 'timeout exits with distinct timeout code'
    Assert-True (Test-Path -LiteralPath $pidPath -PathType Leaf) 'timeout double recorded its process id'
    if (Test-Path -LiteralPath $pidPath -PathType Leaf) {
        $timedOutPid = [int](Get-Content -LiteralPath $pidPath -Raw)
        $stopped = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            if ($null -eq (Get-Process -Id $timedOutPid -ErrorAction SilentlyContinue)) { $stopped = $true; break }
            Start-Sleep -Milliseconds 250
        }
        Assert-True $stopped 'timeout kills the timed out process'
    }

    foreach ($mode in @('Authenticated', 'Collect', 'Send')) {
        $refused = Invoke-TestScript -FilePath $verifierPath -Arguments @('-' + $mode)
        Assert-Equal $refused.ExitCode 64 ('rejects ' + $mode + ' mode')
        Assert-Contains $refused.Output 'offline only' ('explains offline refusal for ' + $mode)
    }

    # Regression: verify-project.ps1 executa os testes PowerShell a partir de
    # work/tce-extractor, portanto nenhum deles pode depender do diretorio de
    # trabalho herdado do chamador.
    $extractorRoot = Join-Path $projectRoot 'work\tce-extractor'
    $documentationTest = Join-Path $extractorRoot 'tests\Test-DocumentationTracking.ps1'
    Push-Location $extractorRoot
    try {
        $documentationRun = Invoke-TestScript -FilePath $documentationTest -Arguments @()
    } finally {
        Pop-Location
    }
    Assert-Equal $documentationRun.ExitCode 0 'documentation tracking passes when started from work/tce-extractor'
    Assert-Contains $documentationRun.Output '0 falharam.' 'documentation tracking reports no failure when started from work/tce-extractor'

    # O gate precisa executar todos os testes PowerShell disponiveis; uma lista
    # manual que esqueca um arquivo deixa contrato sem cobertura.
    $verifierText = [IO.File]::ReadAllText($verifierPath)
    $enumeratedTests = @([regex]::Matches($verifierText, "'(Test-[A-Za-z]+\.ps1)'") | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    $availableTests = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'work\tce-extractor\tests') -Filter 'Test-*.ps1' | Select-Object -ExpandProperty Name | Sort-Object)
    Assert-Equal ($enumeratedTests -join ',') ($availableTests -join ',') 'verifier executes every PowerShell test script under work/tce-extractor/tests'
} finally {
    if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
}

Write-Host "`nTest-ProjectVerification: $script:passed passed; $script:failed failed."
if ($script:failed -gt 0) { exit 1 }
