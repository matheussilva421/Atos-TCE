[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$portableRoot = Join-Path $projectRoot 'portable'
$extensionRoot = Join-Path $portableRoot 'extensao-complementar-ato'
$verifiedRoot = Join-Path $projectRoot 'staging-task5-verified'
$verifiedRuntime = Join-Path $verifiedRoot 'runtime'
$verifiedLicenses = Join-Path $verifiedRoot 'licenses'
$verifiedManifest = Join-Path $verifiedRoot 'runtime-manifest.json'
$defaultOutputRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '..\..\outputs'))
if ($OutputPath) {
    $outputZip = [IO.Path]::GetFullPath($OutputPath)
    $outputRoot = Split-Path -Parent $outputZip
}
else {
    $outputRoot = $defaultOutputRoot
    $outputZip = Join-Path $outputRoot 'tce-processos-completo-portatil.zip'
}
if ((Test-Path -LiteralPath $outputZip -PathType Leaf) -and -not $Force) {
    throw "ZIP existente; use -Force para substituir explicitamente: $outputZip"
}

# These are unique, project-local transaction paths.  The staging tree remains
# as evidence; only these exact per-run verification artifacts are cleaned.
$runId = [guid]::NewGuid().ToString('N')
$stage = Join-Path $projectRoot ('.package-staging-' + $runId)
$verificationRoot = Join-Path $projectRoot ('.package-verify-' + $runId)
$temporaryZip = Join-Path $projectRoot ('.tce-processos-completo-portatil-' + $runId + '.zip')
$expectedZipHash = $null
[long]$expectedZipLength = -1
$extensionFiles = @(
    'manifest.json',
    'package.json',
    'content/package.json',
    'content/form-detector.js',
    'content/portal-navigation.js',
    'content/portal-submit.js',
    'background/automation-controller.js',
    'background/service-worker.js',
    'lib/matcher.js',
    'lib/messages.js',
    'lib/bridge-client.js',
    'lib/normalizer.js',
    'lib/schema.js',
    'lib/automation-preflight.js',
    'lib/automation-schema.js',
    'lib/legal-foundation.js',
    'sidepanel/panel.css',
    'sidepanel/panel-tokens.css',
    'sidepanel/panel.html',
    'sidepanel/panel.js',
    'sidepanel/panel-view.js'
)

function Assert-NoReparseTree {
    param([Parameter(Mandatory)][string]$Path)

    try {
        $rootItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
    catch {
        throw ("Não foi possível inspecionar reparse points em {0}: {1}" -f $Path, $_.Exception.Message)
    }

    $items = @($rootItem)
    if ($rootItem.PSIsContainer) {
        try {
            $items += @(Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction Stop)
        }
        catch {
            throw ("Não foi possível enumerar a árvore para reparse points em {0}: {1}" -f $Path, $_.Exception.Message)
        }
    }

    foreach ($item in $items) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point não permitido: $($item.FullName)"
        }
    }
}

function Require-File {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Fonte obrigatória ausente: $Path"
    }
    Assert-NoReparseTree -Path $Path
}

function Require-Directory {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Diretório obrigatório ausente: $Path"
    }
    Assert-NoReparseTree -Path $Path
}

function Copy-PackageFile {
    param(
        [Parameter(Mandatory)][string]$SourcePath,
        [Parameter(Mandatory)][string]$RelativeDestination
    )
    Require-File -Path $SourcePath
    $destination = Join-Path $stage $RelativeDestination
    $parent = Split-Path -Parent $destination
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    Copy-Item -LiteralPath $SourcePath -Destination $destination -Force
}

function Copy-PackageDirectoryContents {
    param(
        [Parameter(Mandatory)][string]$SourcePath,
        [Parameter(Mandatory)][string]$RelativeDestination
    )
    Require-Directory -Path $SourcePath
    $destination = Join-Path $stage $RelativeDestination
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $SourcePath -Force)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Fonte reparse point não permitida: $($item.FullName)"
        }
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Recurse -Force
    }
}

function Assert-StagingPathsSafe {
    Assert-NoReparseTree -Path $stage
    $forbiddenRelativePatterns = @(
        '(?i)(^|[\\/])downloads([\\/]|$)',
        '(?i)(^|[\\/])dados-locais([\\/]|$)',
        '(?i)(^|[\\/])acervo-tce([\\/]|$)',
        '(?i)checkpoint',
        '(?i)\.pdf$',
        '(?i)\.part$',
        '(?i)\.tmp$'
    )
    foreach ($item in @(Get-ChildItem -LiteralPath $stage -Recurse -Force)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point no staging: $($item.FullName)"
        }
        $relative = $item.FullName.Substring($stage.TrimEnd('\').Length).TrimStart('\')
        foreach ($pattern in $forbiddenRelativePatterns) {
            if ($relative -match $pattern) {
                throw "Caminho proibido no staging: $relative"
            }
        }
    }
}

function Get-FileInventory {
    param([Parameter(Mandatory)][string]$Root)
    Require-Directory -Path $Root
    Assert-NoReparseTree -Path $Root
    $items = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Force | ForEach-Object {
        if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point na árvore verificada: $($_.FullName)"
        }
        $relative = $_.FullName.Substring($Root.TrimEnd('\').Length).TrimStart('\').Replace('\', '/')
        [pscustomobject]@{
            Path = $relative
            Length = [long]$_.Length
            Sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    } | Sort-Object Path)
    return $items
}

function Assert-SameInventory {
    param(
        [Parameter(Mandatory)][string]$LeftRoot,
        [Parameter(Mandatory)][string]$RightRoot,
        [Parameter(Mandatory)][string]$Context
    )
    $left = @(Get-FileInventory -Root $LeftRoot)
    $right = @(Get-FileInventory -Root $RightRoot)
    $leftJson = $left | ConvertTo-Json -Depth 4 -Compress
    $rightJson = $right | ConvertTo-Json -Depth 4 -Compress
    if ($leftJson -ne $rightJson) {
        $differences = @(Compare-Object -ReferenceObject ($left | Out-String) -DifferenceObject ($right | Out-String))
        throw "Inventário $Context diverge; Compare-Object: $($differences | Out-String)"
    }
}

function Assert-ZipHashAndSize {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$ExpectedHash,
        [long]$ExpectedLength = -1
    )
    Require-File -Path $Path
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    }
    catch {
        throw ("Não foi possível validar hash/tamanho do ZIP {0}: {1}" -f $Path, $_.Exception.Message)
    }
    if ($item.Length -le 0 -or $hash -notmatch '^[0-9a-f]{64}$') {
        throw "ZIP promovido sem tamanho/hash válidos: $Path"
    }
    if ($ExpectedLength -ge 0 -and $item.Length -ne $ExpectedLength) {
        throw "Tamanho do ZIP divergente: esperado $ExpectedLength, observado $($item.Length)"
    }
    if ($ExpectedHash -and $hash -ne $ExpectedHash.ToLowerInvariant()) {
        throw "SHA-256 do ZIP divergente: esperado $ExpectedHash, observado $hash"
    }
    [pscustomobject]@{
        Length = [long]$item.Length
        Sha256 = $hash
    }
}

try {
    Require-Directory -Path $portableRoot
    Require-Directory -Path $verifiedRuntime
    Require-Directory -Path $verifiedLicenses
    Require-File -Path $verifiedManifest
    Require-File -Path (Join-Path $portableRoot 'README.md')

    [IO.Directory]::CreateDirectory($stage) | Out-Null
    [IO.Directory]::CreateDirectory($verificationRoot) | Out-Null

    # Explicit launcher allowlist.  No other portable child is copied.
    foreach ($name in @(
        'INICIAR.bat',
        'INICIAR.cmd',
        'ABRIR-MESA.cmd',
        'Coletar-Processos-TCE.ps1',
        'TcePortable.Core.psm1',
        'TceFrozenQueue.psm1',
        'TcePortal.Driver.js',
        'TESTAR-PACOTE.ps1',
        'Empacotar-Acervo-Completo.ps1',
        'GUIA-RAPIDO.html',
        'GUIA-RAPIDO.md',
        'README.md'
    )) {
        Copy-PackageFile -SourcePath (Join-Path $portableRoot $name) -RelativeDestination $name
    }

    foreach ($name in @(
        'archive_index.py',
        'analysis_preview.py',
        'materialize_area_analysis.py',
        'acquisition.py',
        'analysis_pipeline.py',
        'batch_scope.py',
        'evidence_geometry.py',
        'bridge_auth.py',
        'automation_report.py',
        'automation_store.py',
        'legal_context.py',
        'qualification.py',
        'local_service.py',
        'workflow_state.py',
        'filter_new_batch.py',
        'frozen_queue.py',
        'incremental_pipeline.py',
        'prepare_transfer.py',
        'runtime_paths.py',
        'source_reconciliation.py',
        'menu.ps1',
        'reset_archive.py',
        'package_audit.py',
        'extension_exporter.py',
        'process_list.py',
        'register_process_list.py'
    )) {
        Copy-PackageFile -SourcePath (Join-Path $portableRoot ('app\' + $name)) -RelativeDestination ('app\' + $name)
    }

    Copy-PackageFile -SourcePath (Join-Path $portableRoot 'app\area_snapshot_transfer.html') -RelativeDestination 'app\area_snapshot_transfer.html'
    Copy-PackageFile -SourcePath (Join-Path $portableRoot 'app\area_snapshot_receiver.py') -RelativeDestination 'app\area_snapshot_receiver.py'

    # The extension is a deployment inventory, not a recursive copy of the
    # portable directory. Every allowlisted production asset is required.
    Require-Directory -Path $extensionRoot
    foreach ($name in $extensionFiles) {
        $sourceName = $name.Replace('/', '\')
        Copy-PackageFile -SourcePath (Join-Path $extensionRoot $sourceName) -RelativeDestination ('extensao-complementar-ato\' + $sourceName)
    }

    Copy-PackageFile -SourcePath (Join-Path $projectRoot 'package_complete_archive.py') -RelativeDestination 'app\package_complete_archive.py'

    foreach ($name in @('batch_runner.py', 'html_generator.py', 'tce_extractor.py')) {
        Copy-PackageFile -SourcePath (Join-Path $projectRoot $name) -RelativeDestination ('app\' + $name)
    }

    foreach ($relative in @('web\review-app.js', 'web\pdf-viewer.js', 'web\review.css', 'web\package.json', 'web\vendor\pdfjs\README.md', 'web\vendor\pdfjs\manifest.json', 'web\vendor\pdfjs\pdf.mjs', 'web\vendor\pdfjs\pdf.worker.mjs', 'web\vendor\pdfjs\LICENSE')) {
        Copy-PackageFile -SourcePath (Join-Path $portableRoot ('app\' + $relative)) -RelativeDestination ('app\' + $relative)
    }

    Copy-PackageDirectoryContents -SourcePath $verifiedRuntime -RelativeDestination 'runtime'
    Copy-PackageDirectoryContents -SourcePath $verifiedLicenses -RelativeDestination 'licenses'
    Copy-PackageFile -SourcePath $verifiedManifest -RelativeDestination 'runtime-manifest.json'
    Assert-StagingPathsSafe

    # Audit the exact staging tree with the embedded interpreter.
    $auditPython = Join-Path $verifiedRuntime 'python\python.exe'
    $auditScript = Join-Path $stage 'app\package_audit.py'
    Require-File -Path $auditPython
    Require-File -Path $auditScript
    $auditOutput = (& $auditPython $auditScript $stage '--distribution' 'public' 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Auditoria do staging falhou; ZIP não promovido: $auditOutput"
    }

    # Create the archive only at a private temporary path.
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $temporaryZip -CompressionLevel Optimal
    $temporaryFingerprint = Assert-ZipHashAndSize -Path $temporaryZip
    $expectedZipHash = $temporaryFingerprint.Sha256
    $expectedZipLength = $temporaryFingerprint.Length

    # Re-extract and audit the bytes which will be promoted.  This catches ZIP
    # path transformations, omissions, and post-compression corruption.
    $extractedRoot = Join-Path $verificationRoot 'extracted'
    [IO.Directory]::CreateDirectory($extractedRoot) | Out-Null
    Expand-Archive -LiteralPath $temporaryZip -DestinationPath $extractedRoot -Force
    Assert-NoReparseTree -Path $extractedRoot
    $extractedAudit = (& $auditPython $auditScript $extractedRoot 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "Auditoria da árvore extraída falhou; ZIP não promovido: $extractedAudit"
    }
    Assert-SameInventory -LeftRoot $stage -RightRoot $extractedRoot -Context 'staging versus extração'

    [IO.Directory]::CreateDirectory($outputRoot) | Out-Null
    if ($Force) {
        Move-Item -LiteralPath $temporaryZip -Destination $outputZip -Force
    }
    else {
        Move-Item -LiteralPath $temporaryZip -Destination $outputZip
    }
    [void](Assert-ZipHashAndSize -Path $outputZip -ExpectedHash $expectedZipHash -ExpectedLength $expectedZipLength)
    Write-Output $outputZip
}
finally {
    # Preserve $stage as evidence.  These are exact, unique paths owned by this
    # invocation; no existing output, staging, or legacy ZIP is removed.
    if (Test-Path -LiteralPath $temporaryZip -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryZip -Force
    }
    if (Test-Path -LiteralPath $verificationRoot -PathType Container) {
        Remove-Item -LiteralPath $verificationRoot -Recurse -Force
    }
}
