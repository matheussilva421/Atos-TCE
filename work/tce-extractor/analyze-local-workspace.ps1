[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Root,

    [Parameter(Mandatory = $true)]
    [string]$ManifestPath
)

$ErrorActionPreference = 'Stop'

function ConvertTo-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'caminho vazio não é permitido'
    }

    try {
        return [IO.Path]::GetFullPath($Path)
    } catch {
        throw "caminho inválido: $Path"
    }
}

function Test-PathWithinRoot {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Base
    )

    $candidateFull = ConvertTo-FullPath $Candidate
    $baseFull = ConvertTo-FullPath $Base
    $baseWithSeparator = $baseFull.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    return $candidateFull.Equals($baseFull, [StringComparison]::OrdinalIgnoreCase) -or
        $candidateFull.StartsWith($baseWithSeparator, [StringComparison]::OrdinalIgnoreCase)
}

function Get-ResolvedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $current = ConvertTo-FullPath $Path
    $seen = @{}
    for ($depth = 0; $depth -lt 32; $depth++) {
        $key = $current.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { throw "ciclo de reparse point: $Path" }
        $seen[$key] = $true
        $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
        if (-not (Test-IsReparsePoint $item)) { return (ConvertTo-FullPath $item.FullName) }
        $target = @($item.Target) | Select-Object -First 1
        if ($null -eq $target -or [string]::IsNullOrWhiteSpace([string]$target)) {
            throw "alvo de reparse point não resolvível: $Path"
        }
        $targetPath = [string]$target
        if (-not [IO.Path]::IsPathRooted($targetPath)) {
            $targetPath = Join-Path (Split-Path -Parent $current) $targetPath
        }
        $current = ConvertTo-FullPath $targetPath
    }
    throw "cadeia de reparse point excede o limite: $Path"
}

function Test-IsReparsePoint {
    param([Parameter(Mandatory = $true)][IO.FileSystemInfo]$Item)

    return (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Base
    )

    $relative = $Path.Substring($Base.TrimEnd('\', '/').Length).TrimStart('\', '/')
    return ($relative -replace '/', '\')
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = $null
    $hasher = $null
    try {
        $share = ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
        $stream = New-Object IO.FileStream(
            $Path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            $share,
            1048576,
            [IO.FileOptions]::SequentialScan
        )
        $hasher = [Security.Cryptography.SHA256]::Create()
        $digest = $hasher.ComputeHash($stream)
        return ([BitConverter]::ToString($digest) -replace '-', '').ToLowerInvariant()
    } finally {
        if ($null -ne $hasher) { $hasher.Dispose() }
        if ($null -ne $stream) { $stream.Dispose() }
    }
}

function Get-PathClassification {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $parts = @($RelativePath -split '\\')
    $lowerParts = @($parts | ForEach-Object { $_.ToLowerInvariant() })
    $leaf = $parts[-1]
    $extension = [IO.Path]::GetExtension($leaf).ToLowerInvariant()

    if ($lowerParts -contains '.git' -or ($lowerParts | Where-Object { $_ -like '.codex*' }).Count -gt 0 -or
        ($lowerParts | Where-Object { $_ -in @('dados-locais', 'acervo-tce', 'backups-acervo') }).Count -gt 0) {
        return [pscustomobject]@{ Classification = 'private_operational_data'; Reason = 'metadado privado ou operacional'; Action = 'preserve' }
    }

    if (($lowerParts | Where-Object { $_ -eq 'profile' -or $_ -like '.chrome-work*' -or $_ -like 'profile*' }).Count -gt 0) {
        return [pscustomobject]@{ Classification = 'active_profile_or_session'; Reason = 'perfil ou sessão ativa'; Action = 'preserve' }
    }

    if (($lowerParts | Where-Object { $_ -eq 'tmp' -or $_ -eq 'cache' -or $_ -eq 'staging' -or $_ -like 'staging*' -or $_ -like '.package-staging-*' }).Count -gt 0) {
        return [pscustomobject]@{ Classification = 'reproducible_cache_or_staging'; Reason = 'cache ou staging reproduzível'; Action = 'quarantine' }
    }

    if ($extension -in @('.ps1', '.psm1', '.py', '.js', '.mjs', '.ts', '.tsx', '.jsx', '.css', '.html', '.htm', '.cmd', '.bat')) {
        return [pscustomobject]@{ Classification = 'source'; Reason = 'fonte versionada ou executável do projeto'; Action = 'preserve' }
    }

    if ($extension -in @('.md', '.txt', '.rst')) {
        return [pscustomobject]@{ Classification = 'versioned_documentation'; Reason = 'documentação versionada'; Action = 'preserve' }
    }

    if ($extension -in @('.zip', '.7z', '.tar', '.gz')) {
        return [pscustomobject]@{ Classification = 'authorized_or_candidate_delivery'; Reason = 'entrega ou pacote que exige decisão explícita'; Action = 'preserve' }
    }

    return [pscustomobject]@{ Classification = 'unknown_artifact'; Reason = 'artefato sem classificação segura'; Action = 'investigate' }
}

function Get-ReferenceLocations {
    param(
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    $rgCommand = @(Get-Command rg -All -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rgCommand.Count -eq 0) { return @() }
    $rgPath = [string]$rgCommand[0].Source

    $patterns = @($RelativePath, ($RelativePath -replace '\\', '/')) | Select-Object -Unique
    $locations = New-Object System.Collections.Generic.List[string]
    foreach ($pattern in $patterns) {
        $output = @(& $rgPath -n --fixed-strings --no-heading --color never `
            --glob '!*.pdf' --glob '!*.zip' --glob '!*.7z' --glob '!*.tar' --glob '!*.gz' `
            --glob '!profile/**' --glob '!.chrome-work*/**' --glob '!.git/**' --glob '!.codex*/**' `
            -- $pattern $RootPath 2>$null)
        foreach ($line in $output) {
            $text = [string]$line
            if ($text -match '^(.*?):(\d+):') {
                try {
                    $hitPath = ConvertTo-FullPath $matches[1]
                    if (-not (Test-PathWithinRoot -Candidate $hitPath -Base $RootPath)) { continue }
                    $hitRelative = Get-RelativePath -Path $hitPath -Base $RootPath
                    $location = ($hitRelative + ':' + $matches[2])
                } catch {
                    continue
                }
                if (-not $locations.Contains($location)) { [void]$locations.Add($location) }
            }
        }
    }
    return @($locations | Sort-Object)
}

$projectRoot = ConvertTo-FullPath (Join-Path $PSScriptRoot '..\..')
$rootFull = ConvertTo-FullPath $Root
$manifestFull = ConvertTo-FullPath $ManifestPath

if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) {
    throw "raiz inexistente ou não é diretório: $rootFull"
}

$rootResolved = Get-ResolvedPath $rootFull
if (-not (Test-PathWithinRoot -Candidate $rootResolved -Base $projectRoot) -or
    -not $rootResolved.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'raiz deve ser um diretório físico dentro do projeto'
}

if (-not (Test-PathWithinRoot -Candidate $manifestFull -Base $rootFull)) {
    throw 'ManifestPath deve permanecer dentro da raiz analisada'
}

$manifestParent = Split-Path -Parent $manifestFull
if (-not (Test-Path -LiteralPath $manifestParent -PathType Container)) {
    throw "diretório do manifesto não existe: $manifestParent"
}
$manifestParentResolved = Get-ResolvedPath $manifestParent
if (-not (Test-PathWithinRoot -Candidate $manifestParentResolved -Base $rootFull)) {
    throw 'diretório resolvido do manifesto está fora da raiz'
}

$queue = New-Object System.Collections.Generic.Queue[IO.DirectoryInfo]
$queue.Enqueue((Get-Item -LiteralPath $rootFull -Force))
$items = New-Object System.Collections.Generic.List[object]

while ($queue.Count -gt 0) {
    $directory = $queue.Dequeue()
    foreach ($item in @(Get-ChildItem -LiteralPath $directory.FullName -Force -ErrorAction Stop)) {
        $itemFull = ConvertTo-FullPath $item.FullName
        if (-not (Test-PathWithinRoot -Candidate $itemFull -Base $rootFull)) {
            throw "item fora da raiz: $itemFull"
        }

        $relative = Get-RelativePath -Path $itemFull -Base $rootFull
        if ([string]::IsNullOrWhiteSpace($relative)) { continue }

        $classification = Get-PathClassification $relative
        $isReparse = Test-IsReparsePoint $item
        $resolvedItem = $itemFull
        if ($isReparse) {
            $resolvedItem = Get-ResolvedPath $itemFull
            if (-not (Test-PathWithinRoot -Candidate $resolvedItem -Base $rootFull)) {
                throw "reparse point resolve fora da raiz: $relative"
            }
        }

        $kind = if ($isReparse) { 'reparse_point' } elseif ($item.PSIsContainer) { 'directory' } else { 'file' }
        $bytes = [int64]0
        $sha256 = $null
        if (-not $item.PSIsContainer -and -not $isReparse) {
            $bytes = [int64]$item.Length
            $sha256 = Get-FileSha256 $itemFull
        }

        $items.Add([pscustomobject]@{
            Path = $relative
            ResolvedPath = $resolvedItem
            Kind = $kind
            Bytes = $bytes
            Sha256 = $sha256
            GitState = 'untracked_or_modified_snapshot'
            ReferencedBy = @()
            Classification = $classification.Classification
            Reason = $classification.Reason
            RecommendedAction = $classification.Action
        })

        if ($item.PSIsContainer -and -not $isReparse) {
            $queue.Enqueue((Get-Item -LiteralPath $itemFull -Force))
        }
    }
}

$itemArray = $items.ToArray()
$fileGroups = @($itemArray | Where-Object { $_.Kind -eq 'file' -and $_.Sha256 } | Group-Object Sha256 | Where-Object { $_.Count -gt 1 })
foreach ($group in $fileGroups) {
    $groupItems = @($group.Group | Sort-Object Path)
    for ($index = 0; $index -lt $groupItems.Count; $index++) {
        $entry = $groupItems[$index]
        $entry.Classification = 'byte_identical_duplicate'
        $entry.Reason = 'bytes idênticos; retenha uma cópia canônica'
        $entry.RecommendedAction = if ($index -eq 0) { 'preserve' } else { 'quarantine' }
    }
}

foreach ($entry in $itemArray) {
    $entry.ReferencedBy = @(Get-ReferenceLocations -RootPath $rootFull -RelativePath $entry.Path)
}

$manifestEntries = New-Object System.Collections.Generic.List[object]
foreach ($entry in $itemArray) {
    [void]$manifestEntries.Add([pscustomobject]@{
        path = $entry.Path
        resolved_path = $entry.ResolvedPath
        kind = $entry.Kind
        bytes = $entry.Bytes
        sha256 = $entry.Sha256
        git_state = $entry.GitState
        referenced_by = @($entry.ReferencedBy)
        classification = $entry.Classification
        reason = $entry.Reason
        recommended_action = $entry.RecommendedAction
    })
}
$json = ConvertTo-Json -InputObject $manifestEntries.ToArray() -Depth 10
[IO.File]::WriteAllText($manifestFull, $json, (New-Object Text.UTF8Encoding($false)))
$summary = [pscustomobject]@{ entries = $itemArray.Count; manifest = 'written' }
Write-Output (ConvertTo-Json -InputObject $summary -Compress)
