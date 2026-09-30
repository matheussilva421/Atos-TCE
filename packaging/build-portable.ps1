[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$StagingRoot = 'staging-package',
    [string]$RuntimeStaging = 'staging-runtime',
    [switch]$SkipRuntime,
    [switch]$Force,
    [switch]$KeepStaging,
    [switch]$AllowDirtySource
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

function Assert-ValidStagingRoot {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$RepositoryRoot
    )

    $candidate = if ([IO.Path]::IsPathRooted($Path)) { [IO.Path]::GetFullPath($Path) } else { [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $Path)) }
    $candidate = $candidate.TrimEnd('\')
    $repository = [IO.Path]::GetFullPath($RepositoryRoot).TrimEnd('\')
    $parent = [IO.Path]::GetDirectoryName($candidate)
    $leaf = [IO.Path]::GetFileName($candidate)
    if ($null -eq $parent -or -not $parent.Equals($repository, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Staging rejeitado: use uma pasta diretamente sob a raiz do projeto; recebido: $candidate"
    }
    if ($leaf -notmatch '^staging-[^\\/:]+$') {
        throw "Staging rejeitado: o nome precisa começar com staging-; recebido: $leaf"
    }
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        throw "Staging rejeitado: o destino existente não é uma pasta: $candidate"
    }
    if (Test-Path -LiteralPath $candidate) {
        $item = Get-Item -LiteralPath $candidate -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Staging rejeitado: reparse point não é um alvo de staging: $candidate"
        }
    }
    return $candidate
}

function Assert-NoReparseTree {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($item in @(Get-ChildItem -LiteralPath $Path -Recurse -Force)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point não permitido na árvore empacotada: $($item.FullName)"
        }
    }
}

# Bytecode caches and build scratch never belong to a release artefact. A
# private artefact (PDF, database, HAR, trace) aborts the build instead: the
# package contract forbids shipping one, so silently skipping would hide a real
# mistake in the source tree. The verified runtime and its licences are copied
# verbatim, because the runtime manifest inventories every one of their files.
$sourceExcludedDirectories = @('__pycache__', 'node_modules', '.git', '.pytest_cache')
$sourceExcludedSuffixes = @('.pyc', '.pyo', '.log', '.tmp', '.part')
$sourceForbiddenSuffixes = @('.pdf', '.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm', '.har', '.trace', '.zip')
$privateOnlySuffixes = @('.pdf', '.db', '.sqlite', '.sqlite3', '.db-wal', '.db-shm', '.har', '.trace')

function Copy-Tree {
    param(
        [Parameter(Mandatory)][string]$SourcePath,
        [Parameter(Mandatory)][string]$DestinationPath,
        [Parameter(Mandatory)][string]$Label,
        [string[]]$ExcludedDirectoryNames = @(),
        [string[]]$ExcludedFileSuffixes = @(),
        [string[]]$ForbiddenFileSuffixes = @()
    )

    if (-not (Test-Path -LiteralPath $SourcePath -PathType Container)) {
        throw "Fonte obrigatória ausente para ${Label}: $SourcePath"
    }
    [IO.Directory]::CreateDirectory($DestinationPath) | Out-Null
    foreach ($item in @(Get-ChildItem -LiteralPath $SourcePath -Force -Recurse)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse point não permitido na origem de ${Label}: $($item.FullName)"
        }
        $relative = $item.FullName.Substring($SourcePath.TrimEnd('\').Length).TrimStart('\')
        if ($item.PSIsContainer) {
            if ($excludedDirectoryNames -contains $item.Name) {
                continue
            }
            [IO.Directory]::CreateDirectory((Join-Path $DestinationPath $relative)) | Out-Null
            continue
        }
        $parentRelative = Split-Path -Parent $relative
        if (-not [string]::IsNullOrWhiteSpace($parentRelative)) {
            $segments = $parentRelative -split '[\\/]'
            $skip = $false
            foreach ($segment in $segments) {
                if ($excludedDirectoryNames -contains $segment) { $skip = $true; break }
            }
            if ($skip) { continue }
        }
        $suffix = $item.Extension.ToLowerInvariant()
        if ($forbiddenFileSuffixes -contains $suffix) {
            throw "Artefato privado não pode entrar no pacote (${Label}): $relative"
        }
        if ($excludedFileSuffixes -contains $suffix) { continue }
        $destination = Join-Path $DestinationPath $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
    }
}

function Assert-PackageStagingSafe {
    param([Parameter(Mandatory)][string]$Root)

    Assert-NoReparseTree -Path $Root
    $forbiddenRelativePatterns = @(
        '(?i)(^|[\\/])data([\\/]|$)',
        '(?i)(^|[\\/])acervo-tce([\\/]|$)',
        '(?i)(^|[\\/])dados-locais([\\/]|$)',
        '(?i)(^|[\\/])profile([\\/]|$)',
        '(?i)(^|[\\/])outputs([\\/]|$)',
        '(?i)(^|[\\/])downloads([\\/]|$)',
        '(?i)(^|[\\/])__pycache__([\\/]|$)',
        '(?i)checkpoint',
        '(?i)\.pdf$',
        '(?i)\.db$',
        '(?i)\.har$',
        '(?i)\.trace$',
        '(?i)\.pyc$',
        '(?i)\.part$',
        '(?i)\.tmp$'
    )
    foreach ($item in @(Get-ChildItem -LiteralPath $Root -Recurse -Force)) {
        $relative = $item.FullName.Substring($Root.TrimEnd('\').Length).TrimStart('\')
        foreach ($pattern in $forbiddenRelativePatterns) {
            if ($relative -match $pattern) {
                throw "Caminho proibido no staging do pacote: $relative"
            }
        }
    }
    foreach ($required in @('app\main.py', 'extension\manifest.json', 'START.cmd', 'README.md', 'LEIA-ME-OUTRO-PC.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $required) -PathType Leaf)) {
            throw "Pacote incompleto: falta $required"
        }
    }
}

function Assert-NotInside {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Directory,
        [Parameter(Mandatory)][string]$Label
    )
    $candidate = [IO.Path]::GetFullPath($Path)
    $parent = [IO.Path]::GetFullPath($Directory).TrimEnd('\')
    if ($candidate -eq $parent -or $candidate.StartsWith($parent + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino do pacote não pode ficar dentro de ${Label}: $candidate"
    }
}

$outputZip = if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    Join-Path $RepositoryRoot 'dist\Atos-TCE-portable.zip'
} else {
    [IO.Path]::GetFullPath($OutputPath)
}
if (-not $outputZip.ToLowerInvariant().EndsWith('.zip')) {
    throw "Destino do pacote precisa terminar em .zip: $outputZip"
}
if ((Test-Path -LiteralPath $outputZip) -and (Test-Path -LiteralPath $outputZip -PathType Container)) {
    throw "Destino do pacote é uma pasta: $outputZip"
}
if ((Test-Path -LiteralPath $outputZip) -and -not $Force) {
    throw "ZIP existente; use -Force para substituir explicitamente: $outputZip"
}
foreach ($protected in @('data', 'work', 'app', 'extension', 'packaging', 'tests', 'docs', 'scripts')) {
    Assert-NotInside -Path $outputZip -Directory (Join-Path $RepositoryRoot $protected) -Label $protected
}
[IO.Directory]::CreateDirectory((Split-Path -Parent $outputZip)) | Out-Null

# ---------------------------------------------------------------- provenance
# The build id is the commit this artefact was produced from. Without it a
# stale ZIP keeps verifying while shipping code older than the fixes it claims
# to contain, so a normal build refuses to run without a resolvable SHA or on a
# tree that still has uncommitted source changes.
$gitOutput = @(& git -C $RepositoryRoot rev-parse HEAD 2>$null)
$buildId = if ($gitOutput.Count -gt 0) { ([string]$gitOutput[0]).Trim() } else { '' }
if ($buildId -notmatch '^[0-9a-fA-F]{7,64}$') {
    throw 'Pacote de release recusado: não foi possível resolver o SHA do Git (git rev-parse HEAD).'
}
if (-not $AllowDirtySource) {
    $pendingChanges = @(& git -C $RepositoryRoot status --porcelain 2>$null)
    if ($pendingChanges.Count -gt 0) {
        throw 'Pacote de release recusado: working tree contém alterações não commitadas.'
    }
}
if ($AllowDirtySource -and -not $SkipRuntime) {
    throw 'AllowDirtySource é apenas para fixtures de contrato (-SkipRuntime); um artefato de release precisa de árvore commitada.'
}

$packageStaging = Assert-ValidStagingRoot -Path $StagingRoot -RepositoryRoot $RepositoryRoot
$runtimeStagingRoot = Assert-ValidStagingRoot -Path $RuntimeStaging -RepositoryRoot $RepositoryRoot

$runtimeManifest = Join-Path $runtimeStagingRoot 'runtime-manifest.json'
$runtimeState = 'skipped'

function Test-PublishedRuntimeMatchesPin {
    param([Parameter(Mandatory)][string]$PublishedManifest)

    $pinned = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $published = Get-Content -LiteralPath $PublishedManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($component in @('python', 'pymupdf', 'openpyxl', 'et_xmlfile', 'tesseract', 'sevenzip')) {
        $pinnedComponent = $pinned.$component
        $publishedComponent = $published.$component
        if ($null -eq $pinnedComponent -or $null -eq $publishedComponent) { return $false }
        if ([string]$pinnedComponent.version -ne [string]$publishedComponent.version) { return $false }
        if ([string]$pinnedComponent.sha256 -ne [string]$publishedComponent.sha256) { return $false }
    }
    return $true
}

if (-not $SkipRuntime) {
    $reusable = (Test-Path -LiteralPath $runtimeManifest -PathType Leaf) -and (Test-PublishedRuntimeMatchesPin -PublishedManifest $runtimeManifest)
    if ($reusable) {
        $runtimeState = 'reused'
        Write-Host "Runtime verificado reutilizado de $runtimeStagingRoot"
    } else {
        if (Test-Path -LiteralPath $runtimeManifest -PathType Leaf) {
            Write-Warning 'Runtime publicado não corresponde às versões/hashes fixadas agora; reconstruindo.'
        }
        Write-Host "Construindo runtime fixo em $runtimeStagingRoot ..."
        $builderOutput = & (Join-Path $PSScriptRoot 'runtime-builder.ps1') -StagingRoot $runtimeStagingRoot
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $runtimeManifest -PathType Leaf)) {
            throw "Construtor de runtime não publicou runtime-manifest.json em $runtimeStagingRoot"
        }
        $runtimeState = 'built'
        $builderOutput | Out-Null
    }
}

if (Test-Path -LiteralPath $packageStaging) {
    Write-Host "Removendo staging efêmero anterior: $packageStaging"
    Assert-NoReparseTree -Path $packageStaging
    Remove-Item -LiteralPath $packageStaging -Recurse -Force
}
[IO.Directory]::CreateDirectory($packageStaging) | Out-Null

$temporaryZip = $outputZip + '.tmp'
if (Test-Path -LiteralPath $temporaryZip) { Remove-Item -LiteralPath $temporaryZip -Force }

try {
    Copy-Tree -SourcePath (Join-Path $RepositoryRoot 'app') -DestinationPath (Join-Path $packageStaging 'app') -Label 'app' -ExcludedDirectoryNames $sourceExcludedDirectories -ExcludedFileSuffixes $sourceExcludedSuffixes -ForbiddenFileSuffixes $sourceForbiddenSuffixes
    Copy-Tree -SourcePath (Join-Path $RepositoryRoot 'extension') -DestinationPath (Join-Path $packageStaging 'extension') -Label 'extension' -ExcludedDirectoryNames $sourceExcludedDirectories -ExcludedFileSuffixes $sourceExcludedSuffixes -ForbiddenFileSuffixes $sourceForbiddenSuffixes
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'START.cmd') -Destination (Join-Path $packageStaging 'START.cmd') -Force
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'README.md') -Destination (Join-Path $packageStaging 'README.md') -Force
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'LEIA-ME-OUTRO-PC.txt') -Destination (Join-Path $packageStaging 'LEIA-ME-OUTRO-PC.txt') -Force
    # The Mesa compatibility endpoint resolves this single read-only scanner
    # from the repository/package root; do not copy the development scripts tree.
    [IO.Directory]::CreateDirectory((Join-Path $packageStaging 'scripts')) | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot 'scripts\scan-area-cdp.ps1') -Destination (Join-Path $packageStaging 'scripts\scan-area-cdp.ps1') -Force

    if (-not $SkipRuntime) {
        Copy-Tree -SourcePath (Join-Path $runtimeStagingRoot 'runtime') -DestinationPath (Join-Path $packageStaging 'runtime') -Label 'runtime' -ForbiddenFileSuffixes $privateOnlySuffixes
        Copy-Item -LiteralPath $runtimeManifest -Destination (Join-Path $packageStaging 'runtime-manifest.json') -Force
        Copy-Tree -SourcePath (Join-Path $runtimeStagingRoot 'licenses') -DestinationPath (Join-Path $packageStaging 'licenses') -Label 'licenses' -ForbiddenFileSuffixes $privateOnlySuffixes
    } else {
        Copy-Tree -SourcePath (Join-Path $PSScriptRoot 'licenses') -DestinationPath (Join-Path $packageStaging 'licenses') -Label 'licenses' -ForbiddenFileSuffixes $privateOnlySuffixes
        Write-Warning 'Pacote montado sem runtime: é fixture de contrato, nunca um artefato de release.'
    }

    # ------------------------------------------------------------- manifest
    # Inventory the product bytes exactly as staged, so the ZIP can prove which
    # build it contains. The embedded runtime and licences stay under
    # runtime-manifest.json, and this manifest is not a source itself.
    $productPaths = New-Object System.Collections.Generic.List[string]
    foreach ($productRoot in @('app', 'extension')) {
        $productRootPath = Join-Path $packageStaging $productRoot
        if (-not (Test-Path -LiteralPath $productRootPath -PathType Container)) { continue }
        foreach ($productFile in @(Get-ChildItem -LiteralPath $productRootPath -Recurse -Force -File)) {
            $productRelative = $productFile.FullName.Substring($packageStaging.TrimEnd('\').Length).TrimStart('\')
            $productPaths.Add($productRelative.Replace('\', '/'))
        }
    }
    foreach ($productSingle in @('START.cmd', 'README.md', 'LEIA-ME-OUTRO-PC.txt', 'scripts/scan-area-cdp.ps1')) {
        if (Test-Path -LiteralPath (Join-Path $packageStaging $productSingle) -PathType Leaf) {
            $productPaths.Add($productSingle)
        }
    }
    if ($SkipRuntime) {
        # Without the embedded runtime there is no runtime contract, so the
        # licences are product source like anything else and must be declared;
        # with the runtime present they stay under runtime-manifest.json.
        $licenceRoot = Join-Path $packageStaging 'licenses'
        if (Test-Path -LiteralPath $licenceRoot -PathType Container) {
            foreach ($licenceFile in @(Get-ChildItem -LiteralPath $licenceRoot -Recurse -Force -File)) {
                $licenceRelative = $licenceFile.FullName.Substring($packageStaging.TrimEnd('\').Length).TrimStart('\')
                $productPaths.Add($licenceRelative.Replace('\', '/'))
            }
        }
    }
    $orderedProductPaths = @($productPaths | Select-Object -Unique)
    [Array]::Sort($orderedProductPaths, [System.StringComparer]::Ordinal)
    $manifestFiles = @()
    foreach ($productRelative in $orderedProductPaths) {
        $stagedProduct = Join-Path $packageStaging $productRelative
        $stagedItem = Get-Item -LiteralPath $stagedProduct
        $manifestFiles += [pscustomobject]@{
            path = $productRelative
            size = [long]$stagedItem.Length
            sha256 = (Get-FileHash -LiteralPath $stagedProduct -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $manifestJson = ([pscustomobject]@{
        schema = 1
        build_id = $buildId
        source_dirty = [bool]$AllowDirtySource
        files = $manifestFiles
    } | ConvertTo-Json -Depth 6)
    [IO.File]::WriteAllText((Join-Path $packageStaging 'package-manifest.json'), $manifestJson, (New-Object System.Text.UTF8Encoding($false)))

    Assert-PackageStagingSafe -Root $packageStaging

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($packageStaging, $temporaryZip, [IO.Compression.CompressionLevel]::Optimal, $false)
    Move-Item -LiteralPath $temporaryZip -Destination $outputZip -Force
} catch {
    if (Test-Path -LiteralPath $temporaryZip) { Remove-Item -LiteralPath $temporaryZip -Force -ErrorAction SilentlyContinue }
    throw
} finally {
    if (-not $KeepStaging -and (Test-Path -LiteralPath $packageStaging)) {
        Remove-Item -LiteralPath $packageStaging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$verifyArguments = @{ ZipPath = $outputZip; SkipSmoke = $true; ExpectedBuildId = $buildId }
if ($SkipRuntime) { $verifyArguments['AllowMissingRuntime'] = $true }
$verification = & (Join-Path $PSScriptRoot 'verify-package.ps1') @verifyArguments

$zipItem = Get-Item -LiteralPath $outputZip
[pscustomobject]@{
    output = $outputZip
    build_id = $buildId
    bytes = [long]$zipItem.Length
    sha256 = (Get-FileHash -LiteralPath $outputZip -Algorithm SHA256).Hash.ToLowerInvariant()
    runtime = $runtimeState
    staging = $packageStaging
    staging_kept = [bool]$KeepStaging
    verification = ($verification | ConvertFrom-Json)
} | ConvertTo-Json -Depth 8
