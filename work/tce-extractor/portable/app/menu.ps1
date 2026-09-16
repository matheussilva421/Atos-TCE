param(
    [string]$MenuRoot = '',
    [switch]$LaunchLocalService,
    [switch]$StopLocalService,
    [switch]$BridgeStatusOnly,
    [switch]$OpenReview
)

Set-StrictMode -Version 2.0

function Set-TceConsoleUtf8 {
    $utf8 = New-Object Text.UTF8Encoding($false)
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $script:OutputEncoding = $utf8
}

function Get-TceUtf8ScriptBlock {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Script UTF-8 ausente: $Path"
    }
    $encoding = New-Object Text.UTF8Encoding($false)
    return [ScriptBlock]::Create([IO.File]::ReadAllText([IO.Path]::GetFullPath($Path), $encoding))
}

Set-TceConsoleUtf8
$script:TceMenuAppRoot = if (-not [string]::IsNullOrWhiteSpace($MenuRoot)) {
    [IO.Path]::GetFullPath($MenuRoot)
} elseif (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    [IO.Path]::GetFullPath($PSScriptRoot)
} elseif (-not [string]::IsNullOrWhiteSpace($env:TCE_PORTABLE_PACKAGE_ROOT)) {
    [IO.Path]::GetFullPath((Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app'))
} else {
    throw 'Não foi possível localizar a pasta app do pacote portátil.'
}

function Get-TceExitCodes {
    [pscustomobject]@{ Runtime = 10; Authentication = 20; Collection = 30; Analysis = 40; Html = 50; ExtensionData = 60; Reset = 70; Bridge = 80; Acquisition = 90; ProcessList = 100 }
}

function Get-TceMenuOptions {
    @(
        [pscustomobject]@{ key = 1; label = 'Coletar processos selecionados' }
        [pscustomobject]@{ key = 2; label = 'Analisar acervo local' }
        [pscustomobject]@{ key = 3; label = 'Gerar HTML local' }
        [pscustomobject]@{ key = 4; label = 'Atualizar dados da extensão' }
        [pscustomobject]@{ key = 5; label = 'Abrir HTML existente' }
        [pscustomobject]@{ key = 6; label = 'Fluxo completo' }
        [pscustomobject]@{ key = 7; label = 'Diagnóstico do runtime' }
        [pscustomobject]@{ key = 8; label = 'Zerar acervo e iniciar novo lote' }
        [pscustomobject]@{ key = 9; label = 'Verificar ponte local' }
        [pscustomobject]@{ key = 10; label = 'Baixar e preparar OCR de lote congelado' }
        [pscustomobject]@{ key = 11; label = 'Analisar lista na Área Restrita e baixar em lotes de 300' }
    )
}

if (-not (Get-Command ConvertTo-TceSafeText -ErrorAction SilentlyContinue)) {
    function ConvertTo-TceSafeText {
        param([AllowNull()][object]$Value)
        if ($null -eq $Value) { return '' }
        $safe = [string]$Value
        $safe = $safe -replace '(?i)\b[a-z][a-z0-9+.-]{1,31}://[^\s"''<>]+', '[URL REMOVIDA]'
        $safe = $safe -replace '(?i)\b(?:authorization|cookie|token|credential|credencial|session|senha|password)\b\s*(?:(?:[:=]\s*)|(?:\s+))(?:bearer|basic)?\s*[^,\s;|]+', '[CREDENCIAL REMOVIDA]'
        $safe = $safe -replace '(?i)\b(?:url|authorization|cookie|token|credential|credencial|session|senha|password)\b', '[DADO SENSIVEL REMOVIDO]'
        return $safe
    }
}

function New-TceMenuException {
    param([string]$Message, [int]$Code)
    $exception = New-Object InvalidOperationException (ConvertTo-TceSafeText $Message)
    $exception.Data['TceExitCode'] = $Code
    return $exception
}

function Resolve-TcePortableRuntime {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $codes = Get-TceExitCodes
    $root = [IO.Path]::GetFullPath($PackageRoot)
    $python = Join-Path $root 'runtime\python\python.exe'
    $tesseract = Join-Path $root 'runtime\tesseract\tesseract.exe'
    $tessdata = Join-Path $root 'runtime\tesseract\tessdata'
    $required = @(
        $python,
        (Join-Path $root 'runtime\python\python314._pth'),
        $tesseract,
        (Join-Path $root 'runtime\tesseract\libtesseract-5.dll'),
        (Join-Path $root 'runtime\tesseract\libleptonica-6.dll'),
        (Join-Path $tessdata 'por.traineddata'),
        (Join-Path $tessdata 'eng.traineddata'),
        (Join-Path $tessdata 'osd.traineddata')
    )
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw (New-TceMenuException -Message "Runtime portátil incompleto: $path" -Code $codes.Runtime)
        }
    }
    [pscustomobject]@{ PackageRoot = $root; Python = $python; Tesseract = $tesseract; Tessdata = $tessdata }
}

function Invoke-TceMenuStep {
    param([scriptblock]$Step, [string]$Argument, [int]$Code)
    if ($null -eq $Step) { throw (New-TceMenuException -Message 'Etapa não configurada.' -Code $Code) }
    try {
        $results = @(& $Step $Argument)
        if ($results.Count -gt 0) {
            $exitCode = 0
            $hasExitCode = [int]::TryParse([string]$results[-1], [ref]$exitCode)
            $informationalCount = if ($hasExitCode) { $results.Count - 1 } else { $results.Count }
            for ($index = 0; $index -lt $informationalCount; $index++) {
                Write-Host (ConvertTo-TceSafeText $results[$index])
            }
            if ($hasExitCode -and $exitCode -ne 0) {
                throw "Etapa terminou com código $exitCode"
            }
        }
    } catch {
        if ($_.Exception.Data['TceExitCode']) { throw }
        $codes = Get-TceExitCodes
        if ($Code -in @($codes.Collection, $codes.Acquisition) -and $_.Exception.Message -match '(?i)autentica|login|sess[aã]o') {
            throw (New-TceMenuException -Message $_.Exception.Message -Code $codes.Authentication)
        }
        throw (New-TceMenuException -Message $_.Exception.Message -Code $Code)
    }
}

function Confirm-TceArchiveReset {
    param(
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [scriptblock]$InputReader
    )
    $canonicalArchive = [IO.Path]::GetFullPath($ArchiveRoot)
    Write-Host ''
    Write-Host 'ATENÇÃO: esta ação inicia um novo lote local.' -ForegroundColor Yellow
    Write-Host "Alvo exato: $canonicalArchive" -ForegroundColor Yellow
    Write-Host 'Todos os processos e resultados locais dentro de acervo-tce serão substituídos; app, runtime, extensão e perfil do navegador serão preservados.' -ForegroundColor Yellow
    Write-Host 'O lote anterior será mantido em backup recuperável dentro de backups-acervo.' -ForegroundColor Yellow
    $prompt = 'Digite exatamente ZERAR ACERVO para confirmar'
    $answer = if ($null -eq $InputReader) { Read-Host $prompt } else { & $InputReader $prompt }
    if ([string]$answer -ceq 'ZERAR ACERVO') { return $true }
    Write-Host 'Reset cancelado; nenhum arquivo foi alterado.' -ForegroundColor Yellow
    return $false
}

function Resolve-TceArchiveResetPackageRoot {
    param(
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [string]$PackageRoot,
        [int]$ResetCode = 70
    )
    $canonicalArchive = [IO.Path]::GetFullPath($ArchiveRoot)
    $canonicalPackage = if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
        Split-Path -Parent $canonicalArchive
    } else {
        [IO.Path]::GetFullPath($PackageRoot)
    }
    $expectedArchive = [IO.Path]::GetFullPath((Join-Path $canonicalPackage 'acervo-tce'))
    if (-not [StringComparer]::OrdinalIgnoreCase.Equals($canonicalArchive, $expectedArchive)) {
        throw (New-TceMenuException -Message "Alvo recusado: ArchiveRoot deve ser exatamente $expectedArchive" -Code $ResetCode)
    }
    return $canonicalPackage
}

function Get-TceLocalServiceMetadataPath {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $canonicalPackage = [IO.Path]::GetFullPath($PackageRoot)
    return Join-Path $canonicalPackage 'dados-locais\bridge\service.json'
}

function Remove-TceStaleOperationLock {
    param([Parameter(Mandatory)][string]$LockPath)
    if (-not (Test-Path -LiteralPath $LockPath -PathType Leaf)) { return }
    try {
        $lock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -eq $lock -or $lock.pid -isnot [int] -or [int]$lock.pid -le 0) {
            throw 'metadado de lock inválido'
        }
    } catch {
        throw 'Lock de operação inválido; o serviço local não será iniciado.'
    }
    $owner = Get-Process -Id ([int]$lock.pid) -ErrorAction SilentlyContinue
    if ($null -ne $owner -and -not $owner.HasExited) {
        throw "Transferência ou outra operação portátil em andamento (PID $($lock.pid)); o serviço local não será iniciado."
    }
    try {
        Remove-Item -LiteralPath $LockPath -Force -ErrorAction Stop
    } catch {
        throw 'Lock obsoleto não pôde ser removido; o serviço local não será iniciado.'
    }
}

function Wait-TceLocalServiceReady {
    param(
        [Parameter(Mandatory)][string]$MetadataPath,
        [Parameter(Mandatory)][object]$Process,
        [int]$TimeoutSeconds = 3
    )
    $readyUntil = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $readyUntil) {
        if ($Process.PSObject.Properties.Name -contains 'HasExited' -and $Process.HasExited) {
            throw 'O serviço local encerrou antes de confirmar a ponte.'
        }
        if (Test-Path -LiteralPath $MetadataPath -PathType Leaf) {
            try {
                $ready = Get-Content -LiteralPath $MetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([int]$ready.pid -eq [int]$Process.Id -and [int]$ready.port -gt 0) { return $ready }
            } catch { }
        }
        Start-Sleep -Milliseconds 100
    }
    if ($Process.PSObject.Properties.Name -contains 'HasExited' -and $Process.HasExited) {
        throw 'O serviço local encerrou sem confirmar a ponte.'
    }
    throw 'O serviço local não confirmou a ponte dentro do prazo.'
}

function Start-TceLocalService {
    param(
        [Parameter(Mandatory)][string]$PackageRoot,
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [Parameter(Mandatory)][string]$Python,
        [scriptblock]$ProcessStarter
    )
    $canonicalPackage = [IO.Path]::GetFullPath($PackageRoot)
    $canonicalArchive = [IO.Path]::GetFullPath($ArchiveRoot)
    $bridgeRoot = Join-Path $canonicalPackage 'dados-locais\bridge'
    $metadataPath = Get-TceLocalServiceMetadataPath -PackageRoot $canonicalPackage
    $operationLockPath = Join-Path $bridgeRoot '.operation.lock'
    Remove-TceStaleOperationLock -LockPath $operationLockPath
    New-Item -ItemType Directory -Path $bridgeRoot -Force | Out-Null

    if (Test-Path -LiteralPath $metadataPath -PathType Leaf) {
        try {
            $existing = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $existingProcess = Get-Process -Id ([int]$existing.pid) -ErrorAction Stop
            if (-not $existingProcess.HasExited) { return $existing }
        } catch {
            Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
        }
    }

    $serviceScript = Join-Path $canonicalPackage 'app\local_service.py'
    if (-not (Test-Path -LiteralPath $serviceScript -PathType Leaf)) {
        throw 'Helper do serviço local ausente; o modo manual permanece disponível.'
    }
    # Start-Process concatenates ArgumentList items before handing them to the
    # Windows command line. Quote every filesystem path so extracted packages
    # continue to work from paths containing spaces or Unicode characters.
    $quoteArgument = {
        param([Parameter(Mandatory)][string]$Value)
        return '"' + $Value.Replace('"', '\"') + '"'
    }
    $arguments = @(
        '-B', (& $quoteArgument $serviceScript),
        '--root', (& $quoteArgument $canonicalArchive),
        '--bridge-root', (& $quoteArgument $bridgeRoot),
        '--port', '18743'
    )
    try {
        $process = if ($null -ne $ProcessStarter) {
            & $ProcessStarter $Python $arguments (Join-Path $canonicalPackage 'app')
        } else {
            Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory (Join-Path $canonicalPackage 'app') -WindowStyle Hidden -PassThru
        }
    } catch {
        throw 'Não foi possível iniciar o serviço local; use o HTML/JSON manual.'
    }
    if ($null -eq $process -or -not ($process.PSObject.Properties.Name -contains 'Id')) {
        throw 'O serviço local não retornou um PID; use o HTML/JSON manual.'
    }

    if ($null -eq $ProcessStarter) {
        try {
            return Wait-TceLocalServiceReady -MetadataPath $metadataPath -Process $process
        } catch {
            try {
                if (-not $process.HasExited) { $process.Kill() }
            } catch { }
            throw
        }
    }

    $metadata = [ordered]@{
        schema_version = 1
        pid = [int]$process.Id
        port = 18743
        executable = [IO.Path]::GetFullPath($Python)
        started_at = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($metadataPath, (($metadata | ConvertTo-Json -Compress) + "`n"), (New-Object Text.UTF8Encoding($false)))
    return [pscustomobject]$metadata
}

function Stop-TceLocalService {
    param(
        [Parameter(Mandatory)][string]$PackageRoot,
        [Parameter(Mandatory)][string]$Python,
        [scriptblock]$ProcessResolver,
        [scriptblock]$ProcessStopper
    )
    $metadataPath = Get-TceLocalServiceMetadataPath -PackageRoot $PackageRoot
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) { return $false }
    try {
        $metadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $expectedPython = [IO.Path]::GetFullPath($Python)
        if (-not [StringComparer]::OrdinalIgnoreCase.Equals([IO.Path]::GetFullPath([string]$metadata.executable), $expectedPython)) { return $false }
        $process = if ($null -ne $ProcessResolver) { & $ProcessResolver ([int]$metadata.pid) } else { Get-Process -Id ([int]$metadata.pid) -ErrorAction SilentlyContinue }
        if ($null -eq $process) {
            Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
            return $true
        }
        if ($process.PSObject.Properties.Name -contains 'HasExited' -and $process.HasExited) {
            Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
            return $true
        }
        $actualPath = $null
        try { $actualPath = [IO.Path]::GetFullPath([string]$process.Path) } catch { return $false }
        if (-not [StringComparer]::OrdinalIgnoreCase.Equals($actualPath, $expectedPython)) { return $false }
        if ($null -ne $ProcessStopper) { & $ProcessStopper $process } else { Stop-Process -Id ([int]$metadata.pid) -Force -ErrorAction Stop }
        $operationLockPath = Join-Path ([IO.Path]::GetDirectoryName($metadataPath)) '.operation.lock'
        if (Test-Path -LiteralPath $operationLockPath -PathType Leaf) {
            try {
                $operationLock = Get-Content -LiteralPath $operationLockPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([int]$operationLock.pid -eq [int]$metadata.pid) {
                    Remove-Item -LiteralPath $operationLockPath -Force -ErrorAction SilentlyContinue
                }
            } catch { }
        }
        Remove-Item -LiteralPath $metadataPath -Force -ErrorAction SilentlyContinue
        return $true
    } catch {
        return $false
    }
}

function Test-TceLocalBridge {
    param([Parameter(Mandatory)][string]$PackageRoot)
    $metadataPath = Get-TceLocalServiceMetadataPath -PackageRoot $PackageRoot
    if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
        throw 'Ponte local não iniciada; execute INICIAR.cmd sem argumentos primeiro.'
    }
    try {
        $metadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $port = [int]$metadata.port
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -UseBasicParsing -TimeoutSec 5
        if ([int]$health.api_version -ne 1 -or [string]$health.service -ne 'tce-portable') {
            throw 'resposta de saúde incompatível'
        }
        Write-Host "Ponte local conectada: 127.0.0.1:$port (PID $($metadata.pid))." -ForegroundColor Green
        Write-Host 'A extensão ainda precisa usar o código temporário mostrado pelo iniciador para parear.' -ForegroundColor Yellow
        return 0
    } catch {
        throw "Ponte local não respondeu: $($_.Exception.Message)"
    }
}

function Invoke-TceMenuAction {
    param(
        [Parameter(Mandatory)][ValidateRange(1,11)][int]$Action,
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [string]$PackageRoot,
        [scriptblock]$Collector,
        [scriptblock]$Analyzer,
        [scriptblock]$HtmlGenerator,
        [scriptblock]$Opener,
        [scriptblock]$ExtensionExporter,
        [scriptblock]$Diagnostics,
        [scriptblock]$BridgeStatus,
        [scriptblock]$FrozenAcquisition,
        [scriptblock]$ProcessListAnalysis,
        [scriptblock]$Resetter,
        [scriptblock]$ConfirmationReader
    )
    $codes = Get-TceExitCodes
    $resetCompleted = $false
    try {
        switch ($Action) {
            1 { Invoke-TceMenuStep $Collector $ArchiveRoot $codes.Collection }
            2 { Invoke-TceMenuStep $Analyzer $ArchiveRoot $codes.Analysis }
            3 { Invoke-TceMenuStep $HtmlGenerator $ArchiveRoot $codes.Html }
            4 { Invoke-TceMenuStep $ExtensionExporter $ArchiveRoot $codes.ExtensionData }
            5 { Invoke-TceMenuStep $Opener (Join-Path $ArchiveRoot 'complementar-ato.html') $codes.Html }
            6 {
                Invoke-TceMenuStep $Collector $ArchiveRoot $codes.Collection
                Invoke-TceMenuStep $Analyzer $ArchiveRoot $codes.Analysis
                Invoke-TceMenuStep $Opener (Join-Path $ArchiveRoot 'complementar-ato.html') $codes.Html
            }
            7 { Invoke-TceMenuStep $Diagnostics $ArchiveRoot $codes.Runtime }
            8 {
                $resetRoot = Resolve-TceArchiveResetPackageRoot -ArchiveRoot $ArchiveRoot -PackageRoot $PackageRoot -ResetCode $codes.Reset
                if (-not (Confirm-TceArchiveReset -ArchiveRoot $ArchiveRoot -InputReader $ConfirmationReader)) { return 0 }
                Invoke-TceMenuStep $Resetter $resetRoot $codes.Reset
                $resetCompleted = $true
                Invoke-TceMenuStep $Collector $ArchiveRoot $codes.Collection
                Invoke-TceMenuStep $Analyzer $ArchiveRoot $codes.Analysis
                Invoke-TceMenuStep $Opener (Join-Path $ArchiveRoot 'complementar-ato.html') $codes.Html
            }
            9 { Invoke-TceMenuStep $BridgeStatus $PackageRoot $codes.Bridge }
            10 { Invoke-TceMenuStep $FrozenAcquisition $ArchiveRoot $codes.Acquisition }
            11 { Invoke-TceMenuStep $ProcessListAnalysis $ArchiveRoot $codes.ProcessList }
        }
        return 0
    } catch {
        $code = $_.Exception.Data['TceExitCode']
        Write-Warning (ConvertTo-TceSafeText $_.Exception.Message)
        if ($resetCompleted) {
            Write-Host 'O novo ciclo já foi criado, mas a etapa seguinte falhou. O backup anterior permanece em backups-acervo; retome pela opção 6 e não use 8 novamente.' -ForegroundColor Yellow
        }
        if ($code) { return [int]$code }
        return 1
    }
}

function Start-TcePortableMenu {
    param([switch]$LaunchLocalService, [switch]$StopLocalService, [switch]$BridgeStatusOnly, [switch]$OpenReview)
    $appRoot = $script:TceMenuAppRoot
    $codes = Get-TceExitCodes
    $packageRoot = Split-Path -Parent $appRoot
    $archiveRoot = Join-Path $packageRoot 'acervo-tce'
    $pythonPath = Join-Path $packageRoot 'runtime\python\python.exe'
    if ($StopLocalService) {
        if (Stop-TceLocalService -PackageRoot $packageRoot -Python $pythonPath) {
            Write-Host 'Serviço local parado.' -ForegroundColor Green
        } else {
            Write-Host 'Nenhum serviço local identificado foi parado; o modo manual permanece disponível.' -ForegroundColor Yellow
        }
        return 0
    }
    $runtime = Resolve-TcePortableRuntime -PackageRoot $packageRoot
    $collectorPath = Join-Path $packageRoot 'Coletar-Processos-TCE.ps1'
    $pipelinePath = Join-Path $appRoot 'analysis_pipeline.py'
    $extensionExporterPath = Join-Path $appRoot 'extension_exporter.py'
    $resetArchivePath = Join-Path $appRoot 'reset_archive.py'
    $processListRegistrarPath = Join-Path $appRoot 'register_process_list.py'
    $htmlPath = Join-Path $archiveRoot 'complementar-ato.html'
    $reviewMetadataPath = Join-Path $packageRoot 'dados-locais\bridge\service.json'

    if ($OpenReview) {
        $requiredReviewFiles = @(
            $htmlPath,
            (Join-Path $archiveRoot 'dados-complementar-ato.json'),
            (Join-Path $appRoot 'local_service.py'),
            (Join-Path $appRoot 'web\vendor\pdfjs\pdf.mjs'),
            (Join-Path $appRoot 'web\vendor\pdfjs\pdf.worker.mjs')
        )
        $missingReviewFiles = @($requiredReviewFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
        if ($missingReviewFiles.Count) {
            throw "Mesa incompleta. Extraia o ZIP inteiro antes de abrir. Ausente: $([IO.Path]::GetFileName($missingReviewFiles[0]))"
        }
        $LaunchLocalService = $true
    }

    $preparationMode = 'progressivo'
    $analyzer = {
        param($root)
        & $runtime.Python $pipelinePath --archive-root $root --tesseract $runtime.Tesseract --tessdata $runtime.Tessdata
        return $LASTEXITCODE
    }.GetNewClosure()
    $html = { param($root) & $analyzer $root; return $LASTEXITCODE }.GetNewClosure()
    $open = {
        param($path)
        $target = $path
        if ([IO.Path]::GetFullPath($path) -eq [IO.Path]::GetFullPath($htmlPath)) {
            if (Test-Path -LiteralPath $reviewMetadataPath -PathType Leaf) {
                try {
                    $serviceMetadata = Get-Content -LiteralPath $reviewMetadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
                    if ($serviceMetadata.review_url) { $target = [string]$serviceMetadata.review_url }
                } catch { }
            }
        }
        if ($target -is [string] -and $target -match '^http://127\.0\.0\.1:\d+/review(?:#|$)') {
            try {
                Start-Process -FilePath $target
            } catch {
                try {
                    Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') -ArgumentList @($target)
                } catch {
                    Write-Warning 'Não foi possível abrir a mesa no navegador deste ambiente.'
                    Write-Host 'A ponte local continua disponível; abra o HTML/JSON manual ou tente ABRIR-MESA novamente.'
                }
            }
            return 0
        }
        if (-not (Test-Path -LiteralPath $target)) { throw 'HTML local ausente.' }
        try {
            Start-Process -FilePath $target
        } catch {
            try {
                Start-Process -FilePath (Join-Path $env:SystemRoot 'explorer.exe') -ArgumentList @($target)
            } catch {
                Write-Warning 'Não foi possível abrir o HTML neste ambiente.'
                Write-Host 'Abra o arquivo manualmente pelo Explorer.'
            }
        }
        return 0
    }.GetNewClosure()
    $extension = {
        param($root)
        & $runtime.Python $extensionExporterPath --checkpoint (Join-Path $root 'checkpoint-extracao.json') --output (Join-Path $root 'dados-complementar-ato.json')
        return $LASTEXITCODE
    }.GetNewClosure()
    $resetter = {
        param($root)
        & $runtime.Python -B -s $resetArchivePath --package-root $root
        return $LASTEXITCODE
    }.GetNewClosure()
    $diagnose = {
        param($root)
        & $runtime.Python -B -s -c 'import et_xmlfile, openpyxl, pymupdf; print("pymupdf=" + pymupdf.__version__); print("openpyxl=" + openpyxl.__version__); print("et_xmlfile=" + et_xmlfile.__version__)'
        if ($LASTEXITCODE -ne 0) { return $LASTEXITCODE }
        & $runtime.Tesseract --tessdata-dir $runtime.Tessdata --list-langs
        return $LASTEXITCODE
    }.GetNewClosure()
    $bridgeCheck = ${function:Test-TceLocalBridge}
    $bridgeStatus = {
        param($root)
        & $bridgeCheck -PackageRoot $root
        return $LASTEXITCODE
    }.GetNewClosure()
    $service = $null
    if ($LaunchLocalService) {
        try {
            $service = Start-TceLocalService -PackageRoot $packageRoot -ArchiveRoot $archiveRoot -Python $runtime.Python
            Write-Host "Serviço local disponível na porta $($service.port)." -ForegroundColor Green
            if ($service.pairing_code) {
                Write-Host "Código temporário para a extensão: $($service.pairing_code)" -ForegroundColor Yellow
                Write-Host 'Informe-o no painel da extensão; ele expira e não entra no ZIP.' -ForegroundColor Yellow
            }
        } catch {
            Write-Warning 'Serviço local indisponível; continue pelo HTML/JSON manual.'
        }
    }

    if ($OpenReview) {
        if ($null -eq $service -or -not $service.review_url) {
            throw 'Serviço HTTP da mesa não iniciou. Execute DIAGNOSTICAR.cmd e tente novamente.'
        }
        Invoke-TceMenuStep $open $htmlPath $codes.Html
        return 0
    }

    if ($BridgeStatusOnly) {
        Invoke-TceMenuStep $bridgeStatus $packageRoot $codes.Bridge
        return 0
    }

    Write-Host 'TCE/RN - pacote portátil (somente leitura)' -ForegroundColor Cyan
    foreach ($option in Get-TceMenuOptions) { Write-Host "$($option.key). $($option.label)" }
    $choice = [int](Read-Host 'Escolha uma opção')
    $processListInputPath = ''
    if ($choice -eq 11) {
        $defaultListPath = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Downloads\Github\Atos-TCE\Complementar Ato - Professor IPERN.xlsx'
        $processListInputPath = (Read-Host "Caminho da planilha .xlsx (ENTER usa $defaultListPath)").Trim()
        if ([string]::IsNullOrWhiteSpace($processListInputPath)) { $processListInputPath = $defaultListPath }
    }
    if ($choice -in @(1, 6, 8)) {
        $preparationMode = (Read-Host 'Modo de preparação [progressivo/completo] (progressivo)').Trim().ToLowerInvariant()
        if ([string]::IsNullOrWhiteSpace($preparationMode)) { $preparationMode = 'progressivo' }
        if ($preparationMode -notin @('progressivo', 'completo')) {
            Write-Warning 'Modo inválido; usando progressivo.'
            $preparationMode = 'progressivo'
        }
    }
    $processListAnalysis = {
        param($root)
        if (-not (Test-Path -LiteralPath $processListInputPath -PathType Leaf)) {
            throw "Planilha da lista não encontrada: $processListInputPath"
        }
        & $runtime.Python -B -s $processListRegistrarPath --root $root --input $processListInputPath
        if ($LASTEXITCODE -ne 0) { return $LASTEXITCODE }
        $metadataPath = Get-TceLocalServiceMetadataPath -PackageRoot $packageRoot
        if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) {
            $started = Start-TceLocalService -PackageRoot $packageRoot -ArchiveRoot $archiveRoot -Python $runtime.Python
            Write-Host "Ponte local iniciada na porta $($started.port); pareie a extensão com o código mostrado." -ForegroundColor Yellow
        }
        Write-Host 'Lista registrada. Abra o painel da extensão e use a análise da Área Restrita; a fase de download exigirá confirmação para cada lote de até 300.' -ForegroundColor Green
        return 0
    }.GetNewClosure()
    $collector = {
        param($root)
        & $collectorPath -Destino $root -ManterNavegadorAberto -ModoPreparacao $preparationMode -MaxDownloads 2 -Python $runtime.Python -Tesseract $runtime.Tesseract -Tessdata $runtime.Tessdata
        return $LASTEXITCODE
    }.GetNewClosure()
    $frozenAcquisition = {
        param($root)
        $analysisDirectory = Join-Path $root 'automacao\analises'
        $analysisFiles = @(Get-ChildItem -LiteralPath $analysisDirectory -Filter 'analysis-*.json' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTimeUtc -Descending)
        if (-not $analysisFiles.Count) { throw 'Nenhuma análise congelada encontrada; analise a lista na extensão e crie os lotes primeiro.' }
        Write-Host 'Análises congeladas disponíveis:' -ForegroundColor Cyan
        foreach ($file in $analysisFiles) { Write-Host "- $($file.Name)" }
        $requestedName = (Read-Host 'Nome do arquivo analysis-...json (ENTER usa o mais recente)').Trim()
        $selectedFile = if ([string]::IsNullOrWhiteSpace($requestedName) -and $analysisFiles.Count -eq 1) {
            $analysisFiles[0]
        } elseif ([string]::IsNullOrWhiteSpace($requestedName)) {
            $analysisFiles[0]
        } else {
            $analysisFiles | Where-Object Name -eq ([IO.Path]::GetFileName($requestedName)) | Select-Object -First 1
        }
        if ($null -eq $selectedFile) { throw 'análise selecionada não pertence à pasta automacao\analises.' }
        try {
            $analysisPayload = Get-Content -LiteralPath $selectedFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
            $sourceScope = [string]$analysisPayload.spec.source_scope
        } catch {
            throw 'análise selecionada não contém uma especificação JSON legível.'
        }
        if ($sourceScope -notin @('sector_finalistic', 'my_processes')) {
            throw 'source_scope da análise deve ser sector_finalistic ou my_processes.'
        }
        $lotText = (Read-Host 'Número do lote congelado').Trim()
        $lotNumber = 0
        if (-not [int]::TryParse($lotText, [ref]$lotNumber) -or $lotNumber -lt 1 -or $lotNumber -gt 1000) {
            throw 'Número do lote inválido; informe um inteiro entre 1 e 1000.'
        }
        & $collectorPath -Destino $root -FilaCongelada $selectedFile.FullName -NumeroLote $lotNumber -EscopoPortal $sourceScope -NaoInterativo -ServiceChild -ManterNavegadorAberto -ModoPreparacao $preparationMode -MaxDownloads 2 -Python $runtime.Python -Tesseract $runtime.Tesseract -Tessdata $runtime.Tessdata
        return $LASTEXITCODE
    }.GetNewClosure()
    return Invoke-TceMenuAction -Action $choice -ArchiveRoot $archiveRoot -PackageRoot $packageRoot -Collector $collector -Analyzer $analyzer -HtmlGenerator $html -Opener $open -ExtensionExporter $extension -Diagnostics $diagnose -BridgeStatus $bridgeStatus -FrozenAcquisition $frozenAcquisition -ProcessListAnalysis $processListAnalysis -Resetter $resetter
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Start-TcePortableMenu -LaunchLocalService:$LaunchLocalService -StopLocalService:$StopLocalService -BridgeStatusOnly:$BridgeStatusOnly -OpenReview:$OpenReview)
}
