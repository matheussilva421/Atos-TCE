param([string]$MenuRoot = '')

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
    [pscustomobject]@{ Runtime = 10; Authentication = 20; Collection = 30; Analysis = 40; Html = 50; ExtensionData = 60; Reset = 70 }
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
        if ($Code -eq $codes.Collection -and $_.Exception.Message -match '(?i)autentica|login|sess[aã]o') {
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

function Invoke-TceMenuAction {
    param(
        [Parameter(Mandatory)][ValidateRange(1,8)][int]$Action,
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [string]$PackageRoot,
        [scriptblock]$Collector,
        [scriptblock]$Analyzer,
        [scriptblock]$HtmlGenerator,
        [scriptblock]$Opener,
        [scriptblock]$ExtensionExporter,
        [scriptblock]$Diagnostics,
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
    $appRoot = $script:TceMenuAppRoot
    $packageRoot = Split-Path -Parent $appRoot
    $archiveRoot = Join-Path $packageRoot 'acervo-tce'
    $runtime = Resolve-TcePortableRuntime -PackageRoot $packageRoot
    $collectorPath = Join-Path $packageRoot 'Coletar-Processos-TCE.ps1'
    $pipelinePath = Join-Path $appRoot 'analysis_pipeline.py'
    $extensionExporterPath = Join-Path $appRoot 'extension_exporter.py'
    $resetArchivePath = Join-Path $appRoot 'reset_archive.py'
    $htmlPath = Join-Path $archiveRoot 'complementar-ato.html'

    $collector = { param($root) & $collectorPath -Destino $root -ManterNavegadorAberto; return $LASTEXITCODE }.GetNewClosure()
    $analyzer = {
        param($root)
        & $runtime.Python $pipelinePath --archive-root $root --tesseract $runtime.Tesseract --tessdata $runtime.Tessdata
        return $LASTEXITCODE
    }.GetNewClosure()
    $html = { param($root) & $analyzer $root; return $LASTEXITCODE }.GetNewClosure()
    $open = { param($path) if (-not (Test-Path -LiteralPath $path)) { throw 'HTML local ausente.' }; Start-Process -FilePath $path; return 0 }
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
        & $runtime.Python -s -c 'import pymupdf; print(pymupdf.__version__)'
        if ($LASTEXITCODE -ne 0) { return $LASTEXITCODE }
        & $runtime.Tesseract --tessdata-dir $runtime.Tessdata --list-langs
        return $LASTEXITCODE
    }.GetNewClosure()

    Write-Host 'TCE/RN - pacote portátil (somente leitura)' -ForegroundColor Cyan
    foreach ($option in Get-TceMenuOptions) { Write-Host "$($option.key). $($option.label)" }
    $choice = [int](Read-Host 'Escolha uma opção')
    return Invoke-TceMenuAction -Action $choice -ArchiveRoot $archiveRoot -PackageRoot $packageRoot -Collector $collector -Analyzer $analyzer -HtmlGenerator $html -Opener $open -ExtensionExporter $extension -Diagnostics $diagnose -Resetter $resetter
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Start-TcePortableMenu)
}
