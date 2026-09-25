[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$StagingRoot = 'staging-package',
    [string]$RuntimeStaging = 'staging-runtime',
    [switch]$SkipRuntime,
    [switch]$Force,
    [switch]$KeepStaging
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
    foreach ($required in @('app\main.py', 'extension\manifest.json', 'START.cmd', 'README.md')) {
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

$verifyArguments = @{ ZipPath = $outputZip; SkipSmoke = $true }
if ($SkipRuntime) { $verifyArguments['AllowMissingRuntime'] = $true }
$verification = & (Join-Path $PSScriptRoot 'verify-package.ps1') @verifyArguments

$zipItem = Get-Item -LiteralPath $outputZip
[pscustomobject]@{
    output = $outputZip
    bytes = [long]$zipItem.Length
    sha256 = (Get-FileHash -LiteralPath $outputZip -Algorithm SHA256).Hash.ToLowerInvariant()
    runtime = $runtimeState
    staging = $packageStaging
    staging_kept = [bool]$KeepStaging
    verification = ($verification | ConvertFrom-Json)
} | ConvertTo-Json -Depth 8
