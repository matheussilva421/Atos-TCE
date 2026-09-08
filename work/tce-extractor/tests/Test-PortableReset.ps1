$ErrorActionPreference = 'Stop'

$script:passed = 0
$script:failed = 0

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)
    $actualJson = ConvertTo-Json -InputObject $Actual -Compress -Depth 20
    $expectedJson = ConvertTo-Json -InputObject $Expected -Compress -Depth 20
    if ($actualJson -ne $expectedJson) {
        $script:failed++
        Write-Host "FALHOU: $Name`n  esperado: $expectedJson`n  recebido: $actualJson" -ForegroundColor Red
    } else {
        $script:passed++
        Write-Host "PASSOU: $Name" -ForegroundColor Green
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Name)
    Assert-Equal $Condition $true $Name
}

function Assert-NotEqual {
    param($Actual, $Unexpected, [string]$Name)
    $same = (($Actual | ConvertTo-Json -Compress -Depth 20) -eq ($Unexpected | ConvertTo-Json -Compress -Depth 20))
    Assert-Equal $same $false $Name
}

function Invoke-ResetArchive {
    param(
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$ScriptPath,
        [Parameter(Mandatory)][string]$PackageRoot,
        [string]$ArchiveRoot
    )
    $arguments = @($ScriptPath, '--package-root', $PackageRoot)
    if ($ArchiveRoot) { $arguments += @('--archive-root', $ArchiveRoot) }
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Python
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = New-Object Text.UTF8Encoding($false)
    $startInfo.StandardErrorEncoding = New-Object Text.UTF8Encoding($false)
    $startInfo.Arguments = (($arguments | ForEach-Object { '"' + ([string]$_).Replace('"', '\"') + '"' }) -join ' ')
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        [pscustomobject]@{
            ExitCode = [int]$process.ExitCode
            Output = ($stdout + $stderr).Trim()
        }
    } finally {
        $process.Dispose()
    }
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$resetScript = Join-Path $projectRoot 'portable\app\reset_archive.py'
$pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $pythonCommand) { throw 'python.exe não encontrado para o teste do reset portátil.' }
$python = $pythonCommand.Source

Assert-True (Test-Path -LiteralPath $resetScript -PathType Leaf) 'existe o utilitário de reset do acervo'
if (-not (Test-Path -LiteralPath $resetScript -PathType Leaf)) {
    Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
    exit 1
}

$packageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-reset-fixture-' + [guid]::NewGuid().ToString('N'))
$archiveRoot = Join-Path $packageRoot 'acervo-tce'
$oldProcessRoot = Join-Path $archiveRoot 'processos\103365-2024'
$oldCycleId = '11111111-1111-1111-1111-111111111111'
New-Item -ItemType Directory -Path $oldProcessRoot -Force | Out-Null
foreach ($relative in @(
    'app\keep-app.txt',
    'runtime\keep-runtime.txt',
    'extensao-complementar-ato\manifest.json',
    'dados-locais\perfil-navegador\Default\keep-profile.txt',
    'acervo-tce\checkpoint.json',
    'acervo-tce\checkpoint-extracao.json',
    'acervo-tce\complementar-ato.html',
    'acervo-tce\dados-complementar-ato.json',
    'acervo-tce\indice-local.json',
    'acervo-tce\doc.md',
    'acervo-tce\processos\103365-2024\processo.json',
    'acervo-tce\processos\103365-2024\evento-0001\arquivo.pdf'
)) {
    $path = Join-Path $packageRoot $relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $path) -Force | Out-Null
    [IO.File]::WriteAllText($path, 'conteudo antigo')
}
[IO.File]::WriteAllText(
    (Join-Path $archiveRoot 'ciclo-acervo.json'),
    ('{"version":1,"id":"' + $oldCycleId + '"}'),
    (New-Object Text.UTF8Encoding($false))
)

try {
    $reset = Invoke-ResetArchive -Python $python -ScriptPath $resetScript -PackageRoot $packageRoot
    Assert-Equal $reset.ExitCode 0 'reset de fixture termina com código zero'
    $summary = $null
    try { $summary = $reset.Output | ConvertFrom-Json } catch { }
    Assert-True ($null -ne $summary) 'reset informa resumo JSON legível'
    Assert-True (Test-Path -LiteralPath $archiveRoot -PathType Container) 'reset recria acervo-tce vazio'
    Assert-True (Test-Path -LiteralPath (Join-Path $archiveRoot 'ciclo-acervo.json') -PathType Leaf) 'reset cria ciclo-acervo.json no novo acervo'

    $cycle = Get-Content -LiteralPath (Join-Path $archiveRoot 'ciclo-acervo.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Equal $cycle.version 1 'ciclo novo usa versão 1'
    $parsedCycleId = [guid]::Empty
    Assert-True ([guid]::TryParse([string]$cycle.id, [ref]$parsedCycleId)) 'ciclo novo possui UUID válido'
    Assert-NotEqual ([string]$cycle.id) $oldCycleId 'ciclo novo nunca reutiliza o ID anterior'

    $newFiles = @(Get-ChildItem -LiteralPath $archiveRoot -Recurse -Force -File)
    Assert-Equal $newFiles.Count 2 'novo acervo contém marcador e progresso portátil'
    $progress = Get-Content -LiteralPath (Join-Path $archiveRoot 'progresso.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Equal $progress.schema_version 1 'progresso novo usa schema v1'
    Assert-Equal $progress.revision 0 'progresso novo começa na revisão zero'
    Assert-Equal @($progress.processes.PSObject.Properties).Count 0 'progresso novo não promove marcas legadas'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $archiveRoot 'checkpoint-extracao.json'))) 'checkpoint anterior não reaparece no novo acervo'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $archiveRoot 'complementar-ato.html'))) 'HTML anterior não reaparece no novo acervo'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $archiveRoot 'dados-complementar-ato.json'))) 'JSON anterior não reaparece no novo acervo'

    $backupRoot = [string]$summary.backup_root
    Assert-True ($backupRoot -and (Test-Path -LiteralPath $backupRoot -PathType Container)) 'acervo anterior fica em backup recuperável'
    Assert-True ($backupRoot -like ((Join-Path $packageRoot 'backups-acervo') + '\*')) 'backup fica sob backups-acervo do pacote'
    $backupCycle = Get-Content -LiteralPath (Join-Path $backupRoot 'acervo-tce\ciclo-acervo.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Equal ([string]$backupCycle.id) $oldCycleId 'backup preserva o ciclo anterior'
    $backupProcessText = [IO.File]::ReadAllText((Join-Path $backupRoot 'acervo-tce\processos\103365-2024\processo.json'))
    Assert-Equal $backupProcessText 'conteudo antigo' 'backup preserva processos anteriores'

    Assert-Equal ([IO.File]::ReadAllText((Join-Path $packageRoot 'app\keep-app.txt'))) 'conteudo antigo' 'reset preserva app'
    Assert-Equal ([IO.File]::ReadAllText((Join-Path $packageRoot 'runtime\keep-runtime.txt'))) 'conteudo antigo' 'reset preserva runtime'
    Assert-Equal ([IO.File]::ReadAllText((Join-Path $packageRoot 'extensao-complementar-ato\manifest.json'))) 'conteudo antigo' 'reset preserva extensão'
    Assert-Equal ([IO.File]::ReadAllText((Join-Path $packageRoot 'dados-locais\perfil-navegador\Default\keep-profile.txt'))) 'conteudo antigo' 'reset preserva perfil browser'

    foreach ($broadTarget in @($packageRoot, (Join-Path $packageRoot 'downloads'), (Join-Path $packageRoot 'acervo-tce\processos'), (Join-Path $packageRoot 'acervo-tce-other'))) {
        $rejected = Invoke-ResetArchive -Python $python -ScriptPath $resetScript -PackageRoot $packageRoot -ArchiveRoot $broadTarget
        Assert-True ($rejected.ExitCode -ne 0) "recusa alvo amplo ou fora de acervo-tce: $broadTarget"
    }

    $reparseRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-reset-reparse-' + [guid]::NewGuid().ToString('N'))
    $reparseArchive = Join-Path $reparseRoot 'acervo-tce'
    $reparseOutside = Join-Path ([IO.Path]::GetTempPath()) ('tce-reset-reparse-outside-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $reparseRoot, $reparseOutside -Force | Out-Null
    try {
        try {
            $symlinkProbe = @(& $python -B -s -c "import os,sys; os.symlink(sys.argv[1],sys.argv[2],target_is_directory=True)" $reparseOutside $reparseArchive 2>&1)
            if (Test-Path -LiteralPath $reparseArchive) {
                $reparseResult = Invoke-ResetArchive -Python $python -ScriptPath $resetScript -PackageRoot $reparseRoot
                Assert-True ($reparseResult.ExitCode -ne 0) 'recusa acervo-tce que é junction/reparse point'
                Assert-True (-not (Test-Path -LiteralPath (Join-Path $reparseOutside 'ciclo-acervo.json'))) 'reparse point recusado sem escrever fora do pacote'
            } else {
                Write-Host 'SKIP: ambiente não permitiu criar symlink/reparse point para o teste.' -ForegroundColor Yellow
            }
        } catch {
            Write-Host 'SKIP: ambiente não permitiu criar symlink/reparse point para o teste.' -ForegroundColor Yellow
        }
    } finally {
        if (Test-Path -LiteralPath $reparseArchive) { Remove-Item -LiteralPath $reparseArchive -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $reparseRoot) { Remove-Item -LiteralPath $reparseRoot -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $reparseOutside) { Remove-Item -LiteralPath $reparseOutside -Recurse -Force -ErrorAction SilentlyContinue }
    }
} finally {
    if (Test-Path -LiteralPath $packageRoot) { Remove-Item -LiteralPath $packageRoot -Recurse -Force }
}

$emptyPackageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-reset-empty-fixture-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $emptyPackageRoot | Out-Null
try {
    $emptyReset = Invoke-ResetArchive -Python $python -ScriptPath $resetScript -PackageRoot $emptyPackageRoot
    Assert-Equal $emptyReset.ExitCode 0 'reset sem acervo anterior termina com código zero'
    Assert-True (Test-Path -LiteralPath (Join-Path $emptyPackageRoot 'acervo-tce\ciclo-acervo.json') -PathType Leaf) 'reset sem acervo cria marcador novo'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $emptyPackageRoot 'backups-acervo\acervo-tce'))) 'reset sem acervo não cria backup falso'
    $transactionDirectories = @()
    $backupParent = Join-Path $emptyPackageRoot 'backups-acervo'
    if (Test-Path -LiteralPath $backupParent) { $transactionDirectories = @(Get-ChildItem -LiteralPath $backupParent -Force -Directory) }
    Assert-Equal $transactionDirectories.Count 0 'reset sem acervo não deixa diretório de transação vazio'
} finally {
    if (Test-Path -LiteralPath $emptyPackageRoot) { Remove-Item -LiteralPath $emptyPackageRoot -Recurse -Force }
}

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
