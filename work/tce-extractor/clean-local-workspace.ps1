[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [switch]$Apply,
    [switch]$PurgeQuarantine
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

function ConvertTo-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'path must not be empty' }
    return [IO.Path]::GetFullPath($Path)
}

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Base,
        [switch]$AllowEqual
    )

    $candidateFull = ConvertTo-FullPath $Candidate
    $baseFull = (ConvertTo-FullPath $Base).TrimEnd('\', '/')
    if ($AllowEqual -and $candidateFull.Equals($baseFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $candidateFull.StartsWith(($baseFull + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)
}

function Test-IsReparsePoint {
    param([Parameter(Mandatory = $true)][IO.FileSystemInfo]$Item)
    return (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Assert-NoReparsePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    $cursor = Get-Item -LiteralPath $Path -Force
    while ($null -ne $cursor) {
        if (Test-IsReparsePoint $cursor) { throw "reparse point is not allowed: $($cursor.FullName)" }
        if ($cursor.FullName.Equals($RootPath, [StringComparison]::OrdinalIgnoreCase)) { return }
        $parent = Split-Path -Parent $cursor.FullName
        if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-PathWithinRoot -Candidate $parent -Base $RootPath -AllowEqual)) {
            throw "path escapes root: $Path"
        }
        $cursor = Get-Item -LiteralPath $parent -Force
    }
    throw "path does not reach root: $Path"
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = $null
    $hasher = $null
    try {
        $share = ([IO.FileShare]::Read -bor [IO.FileShare]::Delete)
        $stream = New-Object IO.FileStream($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share, 1048576, [IO.FileOptions]::SequentialScan)
        $hasher = [Security.Cryptography.SHA256]::Create()
        return ([BitConverter]::ToString($hasher.ComputeHash($stream)) -replace '-', '').ToLowerInvariant()
    } finally {
        if ($null -ne $hasher) { $hasher.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Write-NewUtf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Content
    )

    $stream = $null
    $writer = $null
    try {
        $stream = New-Object IO.FileStream($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $writer = New-Object IO.StreamWriter($stream, (New-Object Text.UTF8Encoding($false)))
        $writer.Write($Content)
        $writer.Flush()
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        elseif ($null -ne $stream) { $stream.Dispose() }
    }
}

function Assert-SafeRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath)) {
        throw "entry path must be relative: $RelativePath"
    }
    if ($RelativePath.IndexOfAny([char[]]'*?[]') -ge 0) { throw "wildcards are not allowed: $RelativePath" }
    $parts = @($RelativePath -split '[\\/]')
    if ($parts.Count -eq 0 -or @($parts | Where-Object { $_ -eq '..' -or $_ -eq '.' -or [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        throw "path traversal is not allowed: $RelativePath"
    }
    $lower = @($parts | ForEach-Object { $_.ToLowerInvariant() })
    # tce-acervo* protects ancestor directories; entries are files validated below.
    $ancestors = @($lower | Select-Object -First ($lower.Count - 1))
    if ($lower -contains '.git' -or
        @($lower | Where-Object { $_ -like '.codex*' -or $_ -like '.chrome-work*' -or $_ -eq 'profile' -or $_ -like 'profile-*' }).Count -gt 0 -or
        @($lower | Where-Object { $_ -eq 'dados-locais' -or $_ -eq 'acervo-tce' -or $_ -eq 'backups-acervo' }).Count -gt 0 -or
        @($ancestors | Where-Object { $_ -like 'tce-acervo*' }).Count -gt 0) {
        throw "protected path is not allowed: $RelativePath"
    }
    $normalized = ($parts -join '\').ToLowerInvariant()
    if ($normalized -eq 'tmp' -or $normalized -eq 'tmp\fase0' -or $normalized.StartsWith('tmp\fase0\') -or
        $normalized -eq 'tmp\fase0-recovery' -or $normalized.StartsWith('tmp\fase0-recovery\') -or
        $normalized -eq 'tmp\quarantine' -or $normalized.StartsWith('tmp\quarantine\')) {
        throw "reserved path is not allowed: $RelativePath"
    }
}

function Get-ManifestDocument {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    $manifestFull = ConvertTo-FullPath $Path
    if (-not (Test-PathWithinRoot -Candidate $manifestFull -Base $RootPath)) { throw 'ManifestPath must stay inside root' }
    if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) { throw "manifest file does not exist: $manifestFull" }
    Assert-NoReparsePath -Path $manifestFull -RootPath $RootPath
    $utf8 = New-Object Text.UTF8Encoding($false, $true)
    $document = [IO.File]::ReadAllText($manifestFull, $utf8) | ConvertFrom-Json
    return [pscustomobject]@{ FullPath = $manifestFull; Document = $document }
}

function Assert-SafeQuarantineBase {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    $base = ConvertTo-FullPath (Join-Path $RootPath 'tmp\quarantine')
    if (-not (Test-PathWithinRoot -Candidate $base -Base $RootPath)) { throw 'quarantine base escapes root' }
    if (Test-Path -LiteralPath $base) {
        if (-not (Test-Path -LiteralPath $base -PathType Container)) { throw 'quarantine base is not a directory' }
        Assert-NoReparsePath -Path $base -RootPath $RootPath
    } else {
        $parent = Split-Path -Parent $base
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            $parent = $RootPath
        }
        Assert-NoReparsePath -Path $parent -RootPath $RootPath
    }
    return $base
}

$projectRoot = ConvertTo-FullPath (Join-Path $PSScriptRoot '..\..')
$rootFull = ConvertTo-FullPath $Root
if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) { throw "root directory does not exist: $rootFull" }
if (-not (Test-PathWithinRoot -Candidate $rootFull -Base $projectRoot -AllowEqual)) { throw 'root must stay inside project' }
Assert-NoReparsePath -Path $rootFull -RootPath $projectRoot
$quarantineBase = Assert-SafeQuarantineBase -RootPath $rootFull

if ($PurgeQuarantine) {
    if ($Apply) { throw 'Apply and PurgeQuarantine are mutually exclusive' }
    $receiptResult = Get-ManifestDocument -Path $ManifestPath -RootPath $rootFull
    $receipt = $receiptResult.Document
    if ([int]$receipt.schema_version -ne 1 -or [string]$receipt.root -ne $rootFull) { throw 'invalid receipt root or schema' }
    $quarantineRoot = ConvertTo-FullPath ([string]$receipt.quarantine_root)
    if (-not (Test-PathWithinRoot -Candidate $quarantineRoot -Base $quarantineBase) -or $quarantineRoot.IndexOfAny([char[]]'*?[]') -ge 0) {
        throw 'receipt quarantine root is not an explicit child of tmp\quarantine'
    }
    if (-not (Test-Path -LiteralPath $quarantineRoot -PathType Container)) { throw 'receipted quarantine does not exist' }
    Assert-NoReparsePath -Path $quarantineRoot -RootPath $rootFull
    $items = @($receipt.items)
    foreach ($item in $items) {
        $destination = ConvertTo-FullPath ([string]$item.destination)
        if (-not (Test-PathWithinRoot -Candidate $destination -Base $quarantineRoot)) { throw 'receipt destination escapes quarantine' }
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "receipted item is absent: $destination" }
        Assert-NoReparsePath -Path $destination -RootPath $rootFull
        if ((Get-FileSha256 $destination) -ne ([string]$item.sha256).ToLowerInvariant()) { throw "receipted hash mismatch: $destination" }
    }
    Remove-Item -LiteralPath $quarantineRoot -Recurse -Force
    [pscustomobject]@{ mode = 'purge'; purged_items = $items.Count; quarantine_root = $quarantineRoot } | ConvertTo-Json -Compress
    exit 0
}

$manifestResult = Get-ManifestDocument -Path $ManifestPath -RootPath $rootFull
$manifest = $manifestResult.Document
$manifestSchema = [int]$manifest.schema_version
$manifestRoot = [string]$manifest.root
if ($manifestSchema -ne 1 -or -not $manifestRoot.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw "invalid cleanup manifest root or schema: schema=$manifestSchema manifest_root=$manifestRoot expected_root=$rootFull"
}
$entries = @($manifest.entries)
if ($entries.Count -eq 0) { throw 'cleanup manifest has no entries' }

$seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$validated = New-Object System.Collections.Generic.List[object]
foreach ($entry in $entries) {
    $relative = [string]$entry.path
    Assert-SafeRelativePath $relative
    if (-not $seen.Add(($relative -replace '/', '\'))) { throw "duplicate cleanup path: $relative" }
    if ([string]$entry.kind -ne 'file') { throw "only file entries are accepted: $relative" }
    if ([string]$entry.decision -ne 'quarantine' -or $entry.approved -ne $true) { throw "entry is not explicitly approved: $relative" }
    $expectedHash = ([string]$entry.sha256).ToLowerInvariant()
    if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "invalid sha256: $relative" }
    $source = ConvertTo-FullPath (Join-Path $rootFull $relative)
    if (-not (Test-PathWithinRoot -Candidate $source -Base $rootFull)) { throw "entry escapes root: $relative" }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "approved target is absent: $relative" }
    Assert-NoReparsePath -Path $source -RootPath $rootFull
    if ($source.Equals($manifestResult.FullPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'manifest cannot approve itself' }
    $file = Get-Item -LiteralPath $source -Force
    if ([int64]$entry.bytes -ne [int64]$file.Length) { throw "byte count mismatch: $relative" }
    $actualHash = Get-FileSha256 $source
    if ($actualHash -ne $expectedHash) { throw "hash mismatch: $relative" }
    $validated.Add([pscustomobject]@{
        RelativePath = ($relative -replace '/', '\')
        Source = $source
        Bytes = [int64]$file.Length
        Sha256 = $actualHash
    })
}

$totalBytes = [int64](($validated | Measure-Object Bytes -Sum).Sum)
if (-not $Apply) {
    [pscustomobject]@{ mode = 'whatif'; approved_items = $validated.Count; approved_bytes = $totalBytes } | ConvertTo-Json -Compress
    exit 0
}

if (-not (Test-Path -LiteralPath $quarantineBase -PathType Container)) {
    New-Item -ItemType Directory -Path $quarantineBase -Force | Out-Null
}
Assert-NoReparsePath -Path $quarantineBase -RootPath $rootFull
$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
$quarantineRoot = Join-Path $quarantineBase $stamp
New-Item -ItemType Directory -Path $quarantineRoot | Out-Null
$moved = New-Object System.Collections.Generic.List[object]
$createdAt = [DateTime]::UtcNow.ToString('o')
foreach ($item in @($validated | Sort-Object RelativePath)) {
    $destination = ConvertTo-FullPath (Join-Path $quarantineRoot $item.RelativePath)
    if (-not (Test-PathWithinRoot -Candidate $destination -Base $quarantineRoot)) { throw "destination escapes quarantine: $($item.RelativePath)" }
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Move-Item -LiteralPath $item.Source -Destination $destination
    if ((Get-FileSha256 $destination) -ne $item.Sha256) { throw "post-move hash mismatch: $($item.RelativePath)" }
    $moved.Add([ordered]@{
        origin = $item.Source
        destination = $destination
        sha256 = $item.Sha256
        bytes = $item.Bytes
        timestamp = [DateTime]::UtcNow.ToString('o')
        result = 'moved'
    })
}
$receiptPath = Join-Path $quarantineRoot 'receipt.json'
$receipt = [ordered]@{
    schema_version = 1
    root = $rootFull
    quarantine_root = $quarantineRoot
    created_at = $createdAt
    items = $moved.ToArray()
}
Write-NewUtf8File -Path $receiptPath -Content ($receipt | ConvertTo-Json -Depth 10)
[pscustomobject]@{ mode = 'apply'; approved_items = $moved.Count; approved_bytes = $totalBytes; receipt = $receiptPath; quarantine_root = $quarantineRoot } | ConvertTo-Json -Compress
