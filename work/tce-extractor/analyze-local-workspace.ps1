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

function ConvertFrom-GitStatusOutput {
    param([AllowEmptyString()][string]$Output)

    $states = @{}
    if ($null -eq $Output) { return $states }

    foreach ($record in ($Output -split [char]0)) {
        if ([string]::IsNullOrWhiteSpace($record)) { continue }
        $recordType = $record.Substring(0, 1)
        $separatorCount = switch ($recordType) {
            '1' { 8 }
            '2' { 9 }
            'u' { 11 }
            '?' { 1 }
            '!' { 1 }
            default { -1 }
        }
        if ($separatorCount -lt 0) { continue }

        $seenSeparators = 0
        $pathStart = -1
        for ($index = 0; $index -lt $record.Length; $index++) {
            if ($record[$index] -eq ' ') {
                $seenSeparators++
                if ($seenSeparators -eq $separatorCount) {
                    $pathStart = $index + 1
                    break
                }
            }
        }
        if ($pathStart -lt 0 -or $pathStart -ge $record.Length) { continue }

        $path = $record.Substring($pathStart) -replace '\\', '/'
        $path = $path -replace '^(?:\./)+', ''
        if ([string]::IsNullOrWhiteSpace($path)) { continue }

        $state = switch ($recordType) {
            { $_ -in @('1', '2', 'u') } { 'modified' }
            '?' { 'untracked' }
            '!' { 'ignored' }
        }
        $states[$path.ToLowerInvariant()] = $state
    }
    return $states
}

function Get-GitStatusSnapshot {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    try {
        $gitArguments = @(
            '-c', ('safe.directory=' + $RepoRoot),
            '-C', $RepoRoot,
            'status', '--porcelain=v2', '-z', '--untracked-files=all', '--ignored=matching'
        )
        $gitOutput = @(& git @gitArguments 2>$null)
        $gitExitCode = $LASTEXITCODE
        if ($gitExitCode -ne 0) { throw "git status retornou código $gitExitCode" }

        $gitText = [string]::Join(([char]0).ToString(), [string[]]$gitOutput)
        return [pscustomobject]@{
            Source = 'queried'
            States = (ConvertFrom-GitStatusOutput $gitText)
        }
    } catch {
        return [pscustomobject]@{
            Source = 'unavailable'
            States = @{}
        }
    }
}

function Resolve-GitState {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Snapshot,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    if ($Snapshot.Source -ne 'queried') { return 'unknown' }
    $key = (($RelativePath -replace '\\', '/') -replace '^(?:\./)+', '').ToLowerInvariant()
    if ($Snapshot.States.ContainsKey($key)) { return $Snapshot.States[$key] }
    return 'clean_tracked'
}

function Get-ShortErrorMessage {
    param([Parameter(Mandatory = $true)][object]$ErrorRecord)

    $message = ([string]$ErrorRecord.Exception.Message -replace '\s+', ' ').Trim()
    if ($message.Length -gt 160) { return $message.Substring(0, 160) }
    return $message
}

function Get-PathClassification {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $parts = @($RelativePath -split '\\')
    $lowerParts = @($parts | ForEach-Object { $_.ToLowerInvariant() })
    $leaf = $parts[-1]
    $extension = [IO.Path]::GetExtension($leaf).ToLowerInvariant()

    if ($lowerParts -contains '.git' -or ($lowerParts | Where-Object { $_ -like '.codex*' }).Count -gt 0 -or
        ($lowerParts | Where-Object { $_ -in @('dados-locais', 'acervo-tce', 'backups-acervo') -or $_ -like 'tce-acervo-*' -or $_ -like 'acervo-tce*' }).Count -gt 0) {
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

function Get-ReferenceMap {
    param(
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][object[]]$Items
    )

    $rgCommand = @(Get-Command rg -All -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($rgCommand.Count -eq 0) { return @{} }
    $rgPath = [string]$rgCommand[0].Source

    $literalToPath = @{}
    foreach ($item in @($Items | Where-Object { $_.Kind -eq 'file' -and $_.Classification -in @('source', 'versioned_documentation') })) {
        foreach ($literal in @($item.Path, ($item.Path -replace '\\', '/'))) {
            if (-not [string]::IsNullOrWhiteSpace($literal)) { $literalToPath[$literal] = $item.Path }
        }
    }
    if ($literalToPath.Count -eq 0) { return @{} }

    $patterns = @($literalToPath.Keys | Sort-Object)
    $patternInput = ($patterns -join [Environment]::NewLine)
    $rgArguments = @(
        '-n', '--fixed-strings', '--no-heading', '--color', 'never',
        '--glob', '!*.pdf', '--glob', '!*.zip', '--glob', '!*.7z', '--glob', '!*.tar', '--glob', '!*.gz',
        '--glob', '!profile/**', '--glob', '!.chrome-work*/**', '--glob', '!.git/**', '--glob', '!.codex*/**',
        '--glob', '!**/dados-locais/**', '--glob', '!**/acervo-tce/**', '--glob', '!**/backups-acervo/**',
        '--glob', '!**/tce-acervo*/**', '--glob', '!**/TCE-Acervo*/**',
        '--file', '-', '--', $RootPath
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @($patternInput | & $rgPath @rgArguments 2>&1)
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $referenceMap = @{}
    foreach ($line in $output) {
        $text = [string]$line
        if ($text -notmatch '^(.*?):(\d+):(.*)$') { continue }
        try {
            $hitPath = ConvertTo-FullPath $matches[1]
            if (-not (Test-PathWithinRoot -Candidate $hitPath -Base $RootPath)) { continue }
            $hitRelative = Get-RelativePath -Path $hitPath -Base $RootPath
            $location = ($hitRelative + ':' + $matches[2])
            $content = $matches[3]
            foreach ($literal in $patterns) {
                if ($content.IndexOf($literal, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                    $targetPath = $literalToPath[$literal]
                    if (-not $referenceMap.ContainsKey($targetPath)) { $referenceMap[$targetPath] = New-Object System.Collections.Generic.List[string] }
                    if (-not $referenceMap[$targetPath].Contains($location)) { [void]$referenceMap[$targetPath].Add($location) }
                }
            }
        } catch {
            continue
        }
    }
    return $referenceMap
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
$manifestExisting = Get-Item -LiteralPath $manifestFull -Force -ErrorAction SilentlyContinue
if ($null -ne $manifestExisting) {
    throw "destino do manifesto já existe e não será sobrescrito: $manifestFull"
}

$queue = New-Object System.Collections.Generic.Queue[IO.DirectoryInfo]
$protectedDirectories = New-Object System.Collections.Generic.HashSet[string]
$queue.Enqueue((Get-Item -LiteralPath $rootFull -Force))
$items = New-Object System.Collections.Generic.List[object]
$warnings = New-Object System.Collections.Generic.List[string]
$skippedDirectories = 0
$gitSnapshot = Get-GitStatusSnapshot -RepoRoot $projectRoot

while ($queue.Count -gt 0) {
    $directory = $queue.Dequeue()
    $protectedParent = $protectedDirectories.Contains($directory.FullName)
    try {
        $children = @(Get-ChildItem -LiteralPath $directory.FullName -Force -ErrorAction Stop)
    } catch {
        $relativeDirectory = Get-RelativePath -Path $directory.FullName -Base $rootFull
        $reason = Get-ShortErrorMessage $_
        [void]$warnings.Add("diretório ignorado: $relativeDirectory ($reason)")
        $skippedDirectories++
        continue
    }

    foreach ($item in $children) {
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
        $isProtected = $classification.Classification -in @('private_operational_data', 'active_profile_or_session')
        if (-not $item.PSIsContainer -and -not $isReparse) {
            try {
                $itemLength = [int64]$item.Length
                $isLargeOpaque = ([IO.Path]::GetExtension($item.Name).ToLowerInvariant() -in @('.pdf', '.zip', '.7z', '.tar', '.gz')) -and ($itemLength -gt 16777216)
                if (-not $isProtected -and -not $isLargeOpaque) {
                    $bytes = $itemLength
                    $sha256 = Get-FileSha256 $itemFull
                } else {
                    $bytes = $itemLength
                }
            } catch {
                $sha256 = $null
                $reason = Get-ShortErrorMessage $_
                [void]$warnings.Add("arquivo sem leitura/hash: $relative ($reason)")
            }
        }

        $items.Add([pscustomobject]@{
            Path = $relative
            ResolvedPath = $resolvedItem
            Kind = $kind
            Bytes = $bytes
            Sha256 = $sha256
            GitState = (Resolve-GitState -Snapshot $gitSnapshot -RelativePath (Get-RelativePath -Path $itemFull -Base $projectRoot))
            ReferencedBy = @()
            Classification = $classification.Classification
            Reason = $classification.Reason
            RecommendedAction = $classification.Action
        })

        if ($item.PSIsContainer -and -not $isReparse) {
            if ($isProtected) { [void]$protectedDirectories.Add($itemFull) }
            if (-not $protectedParent) {
                $queue.Enqueue([IO.DirectoryInfo]$item)
            }
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

 $referenceMap = Get-ReferenceMap -RootPath $rootFull -Items $itemArray
foreach ($entry in $itemArray) {
    if ($referenceMap.ContainsKey($entry.Path)) {
        $entry.ReferencedBy = @($referenceMap[$entry.Path] | Sort-Object)
    } else {
        $entry.ReferencedBy = @()
    }
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
$manifestStream = $null
try {
    $manifestEncoding = New-Object Text.UTF8Encoding($false)
    $manifestBytes = $manifestEncoding.GetBytes($json)
    $manifestStream = New-Object IO.FileStream(
        $manifestFull,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    $manifestStream.Write($manifestBytes, 0, $manifestBytes.Length)
    $manifestStream.Flush()
} catch {
    throw "não foi possível criar o manifesto '$manifestFull' sem sobrescrever: $($_.Exception.Message)"
} finally {
    if ($null -ne $manifestStream) { $manifestStream.Dispose() }
}
$summary = [pscustomobject]@{
    entries = $itemArray.Count
    manifest = 'written'
    skipped_directories = $skippedDirectories
    warnings = $warnings.Count
    git_state_source = $gitSnapshot.Source
}
Write-Output (ConvertTo-Json -InputObject $summary -Compress)
