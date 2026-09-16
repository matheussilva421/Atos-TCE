$ErrorActionPreference = 'Stop'

$menuPath = Join-Path $PSScriptRoot '..\portable\app\menu.ps1'
. $menuPath

$script:passed = 0
$script:failed = 0

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)
    $actualJson = $Actual | ConvertTo-Json -Compress -Depth 20
    $expectedJson = $Expected | ConvertTo-Json -Compress -Depth 20
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

function Assert-ThrowsCode {
    param([scriptblock]$ScriptBlock, [int]$ExpectedCode, [string]$Name)
    $actualCode = 0
    try {
        & $ScriptBlock
        $actualCode = 0
    } catch {
        $actualCode = [int]$_.Exception.Data['TceExitCode']
    }
    Assert-Equal $actualCode $ExpectedCode $Name
}

$encodingFixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-encoding-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $encodingFixtureRoot -Force | Out-Null
try {
    $encodingFixture = Join-Path $encodingFixtureRoot 'utf8-sem-bom.ps1'
    $encodingWord = 'a' + [char]0xE7 + [char]0xE3 + 'o'
    [IO.File]::WriteAllText($encodingFixture, "Write-Output '$encodingWord'", (New-Object Text.UTF8Encoding($false)))
    $loadedScript = Get-TceUtf8ScriptBlock -Path $encodingFixture
    Assert-Equal (@(& $loadedScript) -join '') $encodingWord 'launcher carrega script UTF-8 sem BOM com acentos intactos'
} finally {
    Remove-Item -LiteralPath $encodingFixtureRoot -Recurse -Force
}

$options = @(Get-TceMenuOptions | ForEach-Object key)
Assert-Equal $options @(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11) 'oferece as opções legadas e o fluxo híbrido'
Assert-Equal ((Get-TceMenuOptions | Where-Object key -eq 7).label) 'Diagnóstico do runtime' 'opção 7 descreve somente o diagnóstico do runtime'
Assert-Equal ((Get-TceMenuOptions | Where-Object key -eq 9).label) 'Verificar ponte local' 'opção 9 verifica a conexão da ponte'
Assert-Equal ((Get-TceMenuOptions | Where-Object key -eq 10).label) 'Baixar e preparar OCR de lote congelado' 'opção 10 executa aquisição/OCR do lote'
Assert-Equal ((Get-TceMenuOptions | Where-Object key -eq 11).label) 'Analisar lista na Área Restrita e baixar em lotes de 300' 'opção 11 inicia o fluxo autoritativo da planilha'
$menuText = Get-Content -LiteralPath $menuPath -Raw
Assert-True ($menuText -match '\.operation\.lock') 'menu não inicia o serviço durante transferência do pacote'
$choicePosition = $menuText.IndexOf('$choice = [int](Read-Host ''Escolha uma opção'')', [StringComparison]::Ordinal)
$listPromptPosition = $menuText.IndexOf('$processListInputPath = ''''', [StringComparison]::Ordinal)
Assert-True ($choicePosition -ge 0 -and $listPromptPosition -gt $choicePosition) 'menu somente solicita a planilha depois de selecionar a opção 11'

$codes = Get-TceExitCodes
$distinctCodes = @(
    $codes.Runtime,
    $codes.Authentication,
    $codes.Collection,
    $codes.Analysis,
    $codes.Html,
    $codes.ExtensionData,
    $codes.Reset,
    $codes.Bridge,
    $codes.Acquisition,
    $codes.ProcessList
) | Sort-Object -Unique
Assert-Equal $distinctCodes.Count 10 'códigos de runtime, autenticação, coleta, análise, HTML, extensão, reset, ponte, aquisição e lista são distintos'

$bridgePackageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-bridge-' + [guid]::NewGuid().ToString('N'))
$bridgeArchiveRoot = Join-Path $bridgePackageRoot 'acervo-tce'
$bridgePython = Join-Path $bridgePackageRoot 'runtime\python\python.exe'
New-Item -ItemType Directory -Path $bridgeArchiveRoot, (Join-Path $bridgePackageRoot 'app') -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $bridgePackageRoot 'app\local_service.py'), 'fixture')
try {
    $startCalls = New-Object System.Collections.ArrayList
    $fakeStarter = {
        param([string]$FilePath, [object]$ArgumentList, [string]$WorkingDirectory)
        [void]$startCalls.Add(@($FilePath, $ArgumentList, $WorkingDirectory))
        return [pscustomobject]@{ Id = 4321 }
    }
    $started = Start-TceLocalService -PackageRoot $bridgePackageRoot -ArchiveRoot $bridgeArchiveRoot -Python $bridgePython -ProcessStarter $fakeStarter
    $bridgePath = Get-TceLocalServiceMetadataPath -PackageRoot $bridgePackageRoot
    $bridgeLockPath = Join-Path $bridgePackageRoot 'dados-locais\bridge\.operation.lock'
    [IO.File]::WriteAllText($bridgeLockPath, '{"pid":4321,"token":"fixture"}')
    Assert-True (Test-Path -LiteralPath $bridgePath -PathType Leaf) 'iniciar serviço registra estado somente na ponte local'
    Assert-Equal $started.pid 4321 'iniciar serviço registra o PID retornado pelo processo'
    Assert-True ((($startCalls | Select-Object -First 1)[1] -join ' ') -match '(?i)--bridge-root') 'iniciar serviço passa a ponte fora do acervo'
    Assert-True ((($startCalls | Select-Object -First 1)[1] -join ' ') -match '(?i)--root') 'iniciar serviço passa a raiz do acervo ao helper'

    $stopCalls = New-Object System.Collections.ArrayList
    $fakeResolver = { param([int]$Id) return [pscustomobject]@{ Id = $Id; Path = $bridgePython; HasExited = $false } }
    $fakeStopper = { param($Process) [void]$stopCalls.Add($Process.Id) }
    Assert-True (Stop-TceLocalService -PackageRoot $bridgePackageRoot -Python $bridgePython -ProcessResolver $fakeResolver -ProcessStopper $fakeStopper) 'parar serviço encerra somente o helper identificado'
    Assert-Equal ($stopCalls -join ',') '4321' 'parar serviço usa o PID registrado'
    Assert-True (-not (Test-Path -LiteralPath $bridgePath)) 'parar serviço remove metadados da ponte'
    Assert-True (-not (Test-Path -LiteralPath $bridgeLockPath)) 'parar serviço remove o lock órfão do próprio PID'

    $readinessError = $null
    try {
        Wait-TceLocalServiceReady -MetadataPath $bridgePath -Process ([pscustomobject]@{ Id = 9876; HasExited = $true })
    } catch {
        $readinessError = $_.Exception.Message
    }
    Assert-True ($readinessError -match '(?i)encerrou|confirmou') 'falha de prontidão não é convertida em metadata falso'
} finally {
    if (Test-Path -LiteralPath $bridgePackageRoot) { Remove-Item -LiteralPath $bridgePackageRoot -Recurse -Force }
}

$launcherText = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\portable\INICIAR.cmd') -Raw
Assert-True ($launcherText -match '(?i)parar') 'iniciador oferece comando explícito para parar o serviço'
Assert-True ($launcherText -match '(?i)Hidden') 'iniciador solicita helper oculto'
Assert-True ($launcherText -match '(?i)LaunchLocalService') 'iniciador inicia a ponte local antes do menu híbrido'
Assert-True ($launcherText -notmatch '(?i)netsh|firewall|RunOnce|Startup') 'iniciador não cria firewall nem inicialização automática'
Assert-True ($launcherText -match '(?i)abrir-mesa') 'iniciador oferece comando público abrir-mesa'
Assert-True ($launcherText -match '(?i)OpenReview') 'abrir-mesa delega para a validação HTTP da mesa'
$reviewLauncher = Join-Path $PSScriptRoot '..\portable\ABRIR-MESA.cmd'
Assert-True (Test-Path -LiteralPath $reviewLauncher -PathType Leaf) 'pacote inclui ABRIR-MESA.cmd'
$reviewLauncherText = if (Test-Path -LiteralPath $reviewLauncher) { Get-Content -LiteralPath $reviewLauncher -Raw } else { '' }
Assert-True ($reviewLauncherText -match '(?i)INICIAR\.cmd"? abrir-mesa') 'ABRIR-MESA.cmd chama o comando público abrir-mesa'
$reviewBatchLauncher = Join-Path $PSScriptRoot '..\portable\ABRIR-MESA.bat'
Assert-True (Test-Path -LiteralPath $reviewBatchLauncher -PathType Leaf) 'pacote inclui o alias ABRIR-MESA.bat'
$reviewBatchLauncherText = if (Test-Path -LiteralPath $reviewBatchLauncher) { Get-Content -LiteralPath $reviewBatchLauncher -Raw } else { '' }
Assert-True ($reviewBatchLauncherText -match '(?i)ABRIR-MESA\.cmd') 'ABRIR-MESA.bat delega para o launcher validado'

$reviewIntegrationRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-review-' + [guid]::NewGuid().ToString('N'))
$reviewIntegrationApp = Join-Path $reviewIntegrationRoot 'app'
$reviewIntegrationArchive = Join-Path $reviewIntegrationRoot 'acervo-tce'
$reviewIntegrationRuntime = Join-Path $reviewIntegrationRoot 'runtime'
New-Item -ItemType Directory -Path @(
    $reviewIntegrationApp,
    (Join-Path $reviewIntegrationApp 'web\vendor\pdfjs'),
    $reviewIntegrationArchive,
    (Join-Path $reviewIntegrationRuntime 'python'),
    (Join-Path $reviewIntegrationRuntime 'tesseract\tessdata')
) -Force | Out-Null
foreach ($relative in @(
    'acervo-tce\complementar-ato.html',
    'acervo-tce\dados-complementar-ato.json',
    'app\local_service.py',
    'app\web\vendor\pdfjs\pdf.mjs',
    'app\web\vendor\pdfjs\pdf.worker.mjs',
    'runtime\python\python.exe',
    'runtime\python\python314._pth',
    'runtime\tesseract\tesseract.exe',
    'runtime\tesseract\libtesseract-5.dll',
    'runtime\tesseract\libleptonica-6.dll',
    'runtime\tesseract\tessdata\por.traineddata',
    'runtime\tesseract\tessdata\eng.traineddata',
    'runtime\tesseract\tessdata\osd.traineddata'
)) {
    [IO.File]::WriteAllText((Join-Path $reviewIntegrationRoot $relative), '')
}
$originalMenuAppRoot = $script:TceMenuAppRoot
$originalLocalServiceStarter = ${function:Start-TceLocalService}
$reviewOpenedTarget = $null
function Start-TceLocalService {
    param([string]$PackageRoot, [string]$ArchiveRoot, [string]$Python)
    $metadataRoot = Join-Path $PackageRoot 'dados-locais\bridge'
    New-Item -ItemType Directory -Path $metadataRoot -Force | Out-Null
    [IO.File]::WriteAllText(
        (Join-Path $metadataRoot 'service.json'),
        (@{
            pid = 1
            port = 18743
            review_url = 'http://127.0.0.1:18743/review#bootstrap=fixture'
        } | ConvertTo-Json -Compress)
    )
    return [pscustomobject]@{
        port = 18743
        review_url = 'http://127.0.0.1:18743/review#bootstrap=fixture'
    }
}
function Start-Process {
    param([string]$FilePath)
    $script:reviewOpenedTarget = $FilePath
    return [pscustomobject]@{ Id = 1 }
}
try {
    $script:TceMenuAppRoot = $reviewIntegrationApp
    $reviewCode = Start-TcePortableMenu -OpenReview
    Assert-Equal $reviewCode 0 'abrir-mesa retorna sucesso depois de iniciar a ponte'
    Assert-Equal $reviewOpenedTarget 'http://127.0.0.1:18743/review#bootstrap=fixture' 'abrir-mesa abre a URL HTTP autenticada da mesa'
    Set-Item -Path Function:\Start-Process -Value {
        param([string]$FilePath)
        throw [System.ComponentModel.Win32Exception]::new(5, 'Acesso negado')
    }
    $reviewFallbackCode = Start-TcePortableMenu -OpenReview
    Assert-Equal $reviewFallbackCode 0 'abrir-mesa não falha quando o shell não abre o navegador'
} finally {
    $script:TceMenuAppRoot = $originalMenuAppRoot
    Set-Item -Path Function:\Start-TceLocalService -Value $originalLocalServiceStarter
    Remove-Item -Path Function:\Start-Process -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $reviewIntegrationRoot) { Remove-Item -LiteralPath $reviewIntegrationRoot -Recurse -Force }
}

$safe = ConvertTo-TceSafeText 'warning token=secret Authorization: Bearer header-secret https://temporary.invalid/download?id=1'
Assert-True ($safe -notmatch 'secret|temporary\.invalid|Authorization|token|Bearer') 'sanitiza mensagem antes de exibir ou persistir'

$packageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-runtime-' + [guid]::NewGuid().ToString('N'))
$runtimeRoot = Join-Path $packageRoot 'runtime'
$pythonRoot = Join-Path $runtimeRoot 'python'
$tesseractRoot = Join-Path $runtimeRoot 'tesseract'
$tessdataRoot = Join-Path $tesseractRoot 'tessdata'
New-Item -ItemType Directory -Path $pythonRoot, $tessdataRoot -Force | Out-Null
foreach ($relative in @(
    'runtime\python\python.exe',
    'runtime\python\python314._pth',
    'runtime\tesseract\tesseract.exe',
    'runtime\tesseract\libtesseract-5.dll',
    'runtime\tesseract\libleptonica-6.dll',
    'runtime\tesseract\tessdata\por.traineddata',
    'runtime\tesseract\tessdata\eng.traineddata',
    'runtime\tesseract\tessdata\osd.traineddata'
)) {
    [IO.File]::WriteAllText((Join-Path $packageRoot $relative), 'fixture')
}
try {
    $runtime = Resolve-TcePortableRuntime -PackageRoot $packageRoot
    Assert-Equal $runtime.Python (Join-Path $packageRoot 'runtime\python\python.exe') 'usa Python explícito do runtime portátil'
    Assert-Equal $runtime.Tesseract (Join-Path $packageRoot 'runtime\tesseract\tesseract.exe') 'usa Tesseract explícito do runtime portátil'
    Assert-Equal $runtime.Tessdata (Join-Path $packageRoot 'runtime\tesseract\tessdata') 'usa tessdata explícito do runtime portátil'

    $missingRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-runtime-missing-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $missingRoot | Out-Null
    try {
        Assert-ThrowsCode { Resolve-TcePortableRuntime -PackageRoot $missingRoot } $codes.Runtime 'runtime ausente recebe código próprio'
    } finally {
        Remove-Item -LiteralPath $missingRoot -Recurse -Force
    }
} finally {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}

$actionPackageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-action-' + [guid]::NewGuid().ToString('N'))
$archiveRoot = Join-Path $actionPackageRoot 'acervo-tce'
New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
$checkpointPath = Join-Path $archiveRoot 'checkpoint-extracao.json'
$checkpointBefore = '{"version":1,"processes":{"103439/2023":{"status":"partial"}}}'
[IO.File]::WriteAllText($checkpointPath, $checkpointBefore)

try {
    $calls = New-Object System.Collections.ArrayList
    $collector = { param([string]$ArchiveRoot) [void]$calls.Add('collect'); return 0 }
    $analyzer = { param([string]$ArchiveRoot) [void]$calls.Add('analyze'); return 0 }
    $htmlGenerator = { param([string]$ArchiveRoot) [void]$calls.Add('html'); return 0 }
    $opener = { param([string]$HtmlPath) [void]$calls.Add('open'); return 0 }
    $extension = { param([string]$ArchiveRoot) [void]$calls.Add('extension'); return 0 }
    $diagnostics = { param([string]$PackageRoot) [void]$calls.Add('diagnose'); return 0 }
    $bridgeStatus = { param([string]$PackageRoot) [void]$calls.Add('bridge'); return 0 }
    $frozenAcquisition = { param([string]$ArchiveRoot) [void]$calls.Add('acquire'); return 0 }
    $processListAnalysis = { param([string]$ArchiveRoot, [string]$PackageRoot) [void]$calls.Add('process-list'); return 0 }

    $common = @{
        ArchiveRoot = $archiveRoot
        Collector = $collector
        Analyzer = $analyzer
        HtmlGenerator = $htmlGenerator
        Opener = $opener
        ExtensionExporter = $extension
        Diagnostics = $diagnostics
        BridgeStatus = $bridgeStatus
        FrozenAcquisition = $frozenAcquisition
        ProcessListAnalysis = $processListAnalysis
    }

    Assert-Equal (Invoke-TceMenuAction -Action 1 @common) 0 'ação 1 conclui coleta'
    Assert-Equal ($calls -join ',') 'collect' 'ação 1 não executa etapas posteriores'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 2 @common) 0 'ação 2 conclui análise local'
    Assert-Equal ($calls -join ',') 'analyze' 'ação 2 não chama navegador/coleta'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 3 @common) 0 'ação 3 conclui geração do HTML'
    Assert-Equal ($calls -join ',') 'html' 'ação 3 executa somente geração do HTML'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 4 @common) 0 'ação 4 atualiza dados da extensão'
    Assert-Equal ($calls -join ',') 'extension' 'ação 4 executa somente a exportação da extensão'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 5 @common) 0 'ação 5 abre HTML existente'
    Assert-Equal ($calls -join ',') 'open' 'ação 5 executa somente abertura do HTML'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 6 @common) 0 'ação 6 conclui fluxo completo'
    Assert-Equal ($calls -join ',') 'collect,analyze,open' 'ação 6 preserva ordem coleta, análise e abertura'
    [void]$calls.Clear()

    Assert-Equal (Invoke-TceMenuAction -Action 7 @common) 0 'ação 7 conclui diagnóstico'
    Assert-Equal ($calls -join ',') 'diagnose' 'ação 7 executa somente diagnóstico'

    [void]$calls.Clear()
    Assert-Equal (Invoke-TceMenuAction -Action 9 @common) 0 'ação 9 verifica a ponte local'
    Assert-Equal ($calls -join ',') 'bridge' 'ação 9 executa somente verificação da ponte'

    [void]$calls.Clear()
    Assert-Equal (Invoke-TceMenuAction -Action 10 @common) 0 'ação 10 executa aquisição do lote congelado'
    Assert-Equal ($calls -join ',') 'acquire' 'ação 10 executa somente download e OCR do lote'

    [void]$calls.Clear()
    Assert-Equal (Invoke-TceMenuAction -Action 11 @common) 0 'ação 11 importa a lista e prepara a análise da Área Restrita'
    Assert-Equal ($calls -join ',') 'process-list' 'ação 11 executa somente o fluxo de lista autoritativa'

    [void]$calls.Clear()
    $resetter = { param([string]$ArchiveRoot) [void]$calls.Add('reset'); return 0 }
    $confirmReset = { param([string]$Prompt) [void]$calls.Add('confirm'); return 'ZERAR ACERVO' }
    Assert-Equal (Invoke-TceMenuAction -Action 8 @common -Resetter $resetter -ConfirmationReader $confirmReset) 0 'ação 8 confirma, zera e conclui o novo lote'
    Assert-Equal ($calls -join ',') 'confirm,reset,collect,analyze,open' 'ação 8 executa reset, coleta, análise e abertura em ordem'

    [void]$calls.Clear()
    $cancelReset = { param([string]$Prompt) [void]$calls.Add('confirm'); return 'CANCELAR' }
    Assert-Equal (Invoke-TceMenuAction -Action 8 @common -Resetter $resetter -ConfirmationReader $cancelReset) 0 'ação 8 cancelada não falha o menu'
    Assert-Equal ($calls -join ',') 'confirm' 'confirmação negativa não executa reset nem etapas do lote'

    [void]$calls.Clear()
    $failedResetCollector = { [void]$calls.Add('collect'); throw 'falha de coleta após novo ciclo' }
    $resumeOutput = @(
        Invoke-TceMenuAction -Action 8 -ArchiveRoot $archiveRoot -PackageRoot (Split-Path -Parent $archiveRoot) -Collector $failedResetCollector -Resetter $resetter -ConfirmationReader $confirmReset 3>&1 4>&1 6>&1
    )
    $resumeCode = [int]$resumeOutput[-1]
    Assert-Equal $resumeCode $codes.Collection 'falha depois do reset retorna código da etapa que falhou'
    Assert-Equal ($calls -join ',') 'confirm,reset,collect' 'falha depois do reset interrompe sem analisar ou abrir'
    Assert-True ((($resumeOutput | ForEach-Object { [string]$_ }) -join "`n") -match '(?i)opção 6|opcao 6') 'falha depois do reset explica retomada pela opção 6'

    $mismatchedPackageRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-menu-mismatched-package-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $mismatchedPackageRoot | Out-Null
    try {
        [void]$calls.Clear()
        $mismatchConfirmation = { param([string]$Prompt) [void]$calls.Add('confirm'); return 'ZERAR ACERVO' }
        $mismatchCode = Invoke-TceMenuAction -Action 8 -ArchiveRoot $archiveRoot -PackageRoot $mismatchedPackageRoot -Collector $collector -Resetter $resetter -ConfirmationReader $mismatchConfirmation
        Assert-Equal $mismatchCode $codes.Reset 'ação 8 recusa packageRoot divergente antes da confirmação'
        Assert-Equal ($calls -join ',') '' 'ação 8 divergente não pede confirmação nem executa reset'
    } finally {
        Remove-Item -LiteralPath $mismatchedPackageRoot -Recurse -Force
    }

    $noisyAnalyzer = { Write-Output 'progresso local'; return 0 }
    Assert-Equal (Invoke-TceMenuAction -Action 2 -ArchiveRoot $archiveRoot -Analyzer $noisyAnalyzer) 0 'saída informativa antes do código não quebra o menu'

    $authenticationFailure = { throw 'Sessão autenticada não detectada; faça login novamente.' }
    Assert-Equal (Invoke-TceMenuAction -Action 1 -ArchiveRoot $archiveRoot -Collector $authenticationFailure) $codes.Authentication 'falha de autenticação recebe código próprio'

    $failedAnalysis = { throw 'falha de análise token=secret https://temporary.invalid/failure' }
    $failureCode = Invoke-TceMenuAction -Action 2 -ArchiveRoot $archiveRoot -Analyzer $failedAnalysis
    Assert-Equal $failureCode $codes.Analysis 'falha de análise recebe código distinto'
    Assert-Equal ([IO.File]::ReadAllText($checkpointPath)) $checkpointBefore 'falha preserva checkpoint existente'

    [void]$calls.Clear()
    $failedCollector = { [void]$calls.Add('collect'); throw 'falha de coleta' }
    $skippedAnalyzer = { [void]$calls.Add('analyze'); return 0 }
    $skippedOpener = { [void]$calls.Add('open'); return 0 }
    $collectionCode = Invoke-TceMenuAction -Action 6 -ArchiveRoot $archiveRoot -Collector $failedCollector -Analyzer $skippedAnalyzer -Opener $skippedOpener
    Assert-Equal $collectionCode $codes.Collection 'falha de coleta recebe código distinto'
    Assert-Equal ($calls -join ',') 'collect' 'falha interrompe cadeia sem abrir HTML'
    Assert-Equal ([IO.File]::ReadAllText($checkpointPath)) $checkpointBefore 'falha de coleta preserva checkpoint existente'

    [void]$calls.Clear()
    $failedExtension = { throw 'falha de exportação token=secret https://temporary.invalid/failure' }
    $extensionCode = Invoke-TceMenuAction -Action 4 -ArchiveRoot $archiveRoot -ExtensionExporter $failedExtension -Opener $skippedOpener
    Assert-Equal $extensionCode $codes.ExtensionData 'falha de exportação recebe código próprio'
    Assert-Equal ($calls -join ',') '' 'falha de exportação não abre navegador'
} finally {
    Remove-Item -LiteralPath $actionPackageRoot -Recurse -Force
}

$readmePath = Join-Path $PSScriptRoot '..\portable\README.md'
$readmeText = Get-Content -LiteralPath $readmePath -Raw -Encoding UTF8
$cedilha = [char]0xE7
$tildeA = [char]0xE3
$agudoU = [char]0xFA
$circunflexoE = [char]0xEA
$nao = 'n' + $tildeA + 'o'
foreach ($requiredText in @(
    'chrome://extensions',
    'Modo do desenvolvedor',
    ('Carregar sem compacta' + $cedilha + $tildeA + 'o'),
    'extensao-complementar-ato',
    ('fa' + $cedilha + 'a login novamente'),
    'novos',
    '-BaseConcluidos',
    ('a' + $cedilha + $tildeA + 'o 4'),
    'dados-complementar-ato.json',
    ($agudoU + 'nico JSON'),
    'sete campos',
    'amarelos',
    ('Diverg' + $circunflexoE + 'ncias'),
    'Revisado',
    ($nao + ' submete'),
    ($nao + ' limpa'),
    ($nao + ' assina'),
    ($nao + ' tramita'),
    ($nao + ' conclui'),
    ($nao + ' publique')
)) {
    Assert-True ($readmeText.IndexOf($requiredText, [StringComparison]::OrdinalIgnoreCase) -ge 0) "README documenta: $requiredText"
}
Assert-True ($readmeText -match 'opções 1[–-]11') 'README reflete as onze opções atuais'
Assert-True ($readmeText.IndexOf(($nao + ' submete'), [StringComparison]::OrdinalIgnoreCase) -ge 0) 'README atribui o limite à extensão'

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
