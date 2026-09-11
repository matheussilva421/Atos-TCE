[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [switch]$Apply,
    [switch]$Resume,
    [switch]$PurgeQuarantine,
    [switch]$WhatIf,
    # Seam explícito de teste: permite apenas fixtures dentro do TEMP do SO.
    [switch]$TestTemporaryRoot,
    # Seam explícito de teste: simula uma mudança entre as checagens e o movimento.
    [ValidateSet('before-final-move-collision-file', 'before-final-move-collision-directory', 'post-move-hash-mismatch', 'abort-after-first-move')]
    [string]$TestHook,
    # Seam explícito de teste: substitui a enumeração real de processos vivos.
    [string[]]$TestRunningProcesses,
    # Seam explícito de teste: fornece nome e user_data_dir por processo.
    [object[]]$TestBrowserProcesses,
    # Seam explícito de teste: força a enumeração real a falhar.
    [switch]$TestDenyProcessEnumeration
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$testProcessOverrideCount = 0
if ($null -ne $TestRunningProcesses) { $testProcessOverrideCount = @($TestRunningProcesses).Count }
$testBrowserOverrideCount = 0
if ($null -ne $TestBrowserProcesses) { $testBrowserOverrideCount = @($TestBrowserProcesses).Count }
if ($testProcessOverrideCount -gt 0 -and -not $TestTemporaryRoot) { throw 'TestRunningProcesses requires TestTemporaryRoot' }
if ($testBrowserOverrideCount -gt 0 -and -not $TestTemporaryRoot) { throw 'TestBrowserProcesses requires TestTemporaryRoot' }
if ($TestDenyProcessEnumeration -and -not $TestTemporaryRoot) { throw 'TestDenyProcessEnumeration requires TestTemporaryRoot' }
if ($WhatIf) {
    $Apply = $false
    $Resume = $false
    $PurgeQuarantine = $false
}
if ($Apply -and $PurgeQuarantine) { throw 'Apply and PurgeQuarantine are mutually exclusive' }
if ($Resume -and $PurgeQuarantine) { throw 'Resume and PurgeQuarantine are mutually exclusive' }
if ($Apply -and $Resume) { throw 'Apply and Resume are mutually exclusive' }

# Risco residual: a origem é pinada por handle; o handle não impede alterações
# feitas por processos que já tenham aberto o arquivo com compartilhamento de
# escrita, e o movimento continua sujeito às garantias do filesystem.
# A operação pressupõe workspace quiescente; um mutex nomeado derivado da raiz
# bloqueia execuções concorrentes do próprio cleaner e um journal durável permite
# retomar (-Resume) após interrupção abrupta.
# Ordem: validar raiz/manifesto -> validar paths lexicais -> resolver e validar
# paths existentes -> conferir bytes/hash -> (Apply) revalidar pais/destino/hash
# imediatamente antes do movimento -> mover -> conferir hash pós-movimento ->
# registrar no journal -> gravar recibo. Purge valida recibo e quarentena antes
# de remover arquivos.

function ConvertTo-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'path must not be empty' }
    return [IO.Path]::GetFullPath($Path)
}

function Get-NormalizedRootPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = ConvertTo-FullPath $Path
    if ($full.Length -gt 3) { $full = $full.TrimEnd([char[]]@('\', '/')) }
    return $full
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

    $normalizedRoot = Get-NormalizedRootPath $RootPath
    $cursor = Get-Item -LiteralPath $Path -Force
    while ($null -ne $cursor) {
        if (Test-IsReparsePoint $cursor) { throw "reparse point is not allowed: $($cursor.FullName)" }
        if ($cursor.FullName.Equals($normalizedRoot, [StringComparison]::OrdinalIgnoreCase)) { return }
        $parent = Split-Path -Parent $cursor.FullName
        if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-PathWithinRoot -Candidate $parent -Base $normalizedRoot -AllowEqual)) {
            throw "path escapes root: $Path"
        }
        $cursor = Get-Item -LiteralPath $parent -Force
    }
    throw "path does not reach root: $Path"
}

function Assert-NoReparseTreePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    $root = Get-Item -LiteralPath $Path -Force
    $pending = New-Object 'Collections.Generic.Queue[System.IO.FileSystemInfo]'
    $pending.Enqueue($root)
    while ($pending.Count -gt 0) {
        $current = $pending.Dequeue()
        if (Test-IsReparsePoint $current) {
            throw "reparse point is not allowed in quarantine: $($current.FullName)"
        }
        if (-not (Test-PathWithinRoot -Candidate $current.FullName -Base $RootPath -AllowEqual)) {
            throw "path escapes root during reparse preflight: $($current.FullName)"
        }
        if ($current.PSIsContainer) {
            try {
                foreach ($child in @(Get-ChildItem -LiteralPath $current.FullName -Force -ErrorAction Stop)) {
                    $pending.Enqueue($child)
                }
            } catch {
                throw "reparse preflight enumeration failed: $($current.FullName)"
            }
        }
    }
}

function Get-FileSha256FromStream {
    param([Parameter(Mandatory = $true)][IO.Stream]$Stream)

    $hasher = $null
    try {
        $Stream.Position = 0
        $hasher = [Security.Cryptography.SHA256]::Create()
        return ([BitConverter]::ToString($hasher.ComputeHash($Stream)) -replace '-', '').ToLowerInvariant()
    } finally {
        if ($null -ne $hasher) { $hasher.Dispose() }
    }
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = $null
    try {
        $share = ([IO.FileShare]::Read -bor [IO.FileShare]::Delete)
        $stream = New-Object IO.FileStream($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share, 1048576, [IO.FileOptions]::SequentialScan)
        return Get-FileSha256FromStream -Stream $stream
    } finally {
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
    foreach ($part in $parts) {
        if ($part.IndexOf('~', [StringComparison]::Ordinal) -ge 0) {
            throw "short-name aliases are not allowed: $RelativePath"
        }
        if ($part -match '[\.\s]$') {
            throw "trailing dot or space is not allowed: $RelativePath"
        }
        if ($part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$') {
            throw "reserved Windows device name is not allowed: $RelativePath"
        }
    }
    $lower = @($parts | ForEach-Object { $_.ToLowerInvariant() })
    # tce-acervo* protects ancestor directories; entries are files validated below.
    $ancestors = @($lower | Select-Object -First ($lower.Count - 1))
    if ($lower -contains '.git' -or
        @($lower | Where-Object { $_ -like '.codex*' -or $_ -like '.chrome-work*' -or $_ -like 'profile*' }).Count -gt 0 -or
        @($lower | Where-Object { $_ -eq 'dados-locais' -or $_ -eq 'acervo-tce' -or $_ -eq 'backups-acervo' }).Count -gt 0 -or
        @($ancestors | Where-Object { $_ -like 'tce-acervo*' }).Count -gt 0) {
        throw "protected path is not allowed: $RelativePath"
    }
    $normalized = ($parts -join '\').ToLowerInvariant()
    if ($normalized -eq 'tmp' -or $normalized -like 'tmp\fase0*' -or
        $normalized -eq 'tmp\quarantine' -or $normalized.StartsWith('tmp\quarantine\')) {
        throw "reserved path is not allowed: $RelativePath"
    }
}

function Assert-SafeResolvedPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    $resolved = Get-Item -LiteralPath $Path -Force
    $resolvedFull = ConvertTo-FullPath $resolved.FullName
    if (-not (Test-PathWithinRoot -Candidate $resolvedFull -Base $RootPath -AllowEqual)) {
        throw "resolved path escapes root: $Path"
    }
    $relative = $resolvedFull.Substring((ConvertTo-FullPath $RootPath).TrimEnd('\', '/').Length).TrimStart('\', '/')
    if ([string]::IsNullOrWhiteSpace($relative)) { return $resolvedFull }
    Assert-SafeRelativePath $relative
    return $resolvedFull
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Base
    )

    $pathFull = ConvertTo-FullPath $Path
    $baseFull = (ConvertTo-FullPath $Base).TrimEnd('\', '/')
    if (-not (Test-PathWithinRoot -Candidate $pathFull -Base $baseFull)) {
        throw "path escapes base: $Path"
    }
    return ($pathFull.Substring($baseFull.Length).TrimStart('\', '/') -replace '/', '\')
}

function Invoke-TestHook {
    param(
        [Parameter(Mandatory = $true)][string]$Hook,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if ([string]::IsNullOrWhiteSpace($Hook)) { return }
    if ($Hook -eq 'before-final-move-collision-file') {
        New-Item -ItemType File -Path $Destination -Force | Out-Null
    } elseif ($Hook -eq 'before-final-move-collision-directory') {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    } elseif ($Hook -eq 'post-move-hash-mismatch') {
        # O handle pinado mantém somente Read+Delete; o seam troca a entrada
        # removendo-a (Delete compartilhado) e criando um novo arquivo.
        Remove-Item -LiteralPath $Destination -Force
        [IO.File]::WriteAllText($Destination, 'TEST-HOOK-POST-MOVE-MISMATCH', (New-Object Text.UTF8Encoding($false)))
    }
}

function Get-CleanupLockName {
    param([Parameter(Mandatory = $true)][string]$RootPath)

    if ([string]::IsNullOrWhiteSpace($RootPath)) { throw 'lock root must not be empty' }
    $full = [IO.Path]::GetFullPath($RootPath)
    if ($full.Length -gt 3) { $full = $full.TrimEnd([char[]]@('\', '/')) }
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = ([BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($full.ToLowerInvariant()))) -replace '-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
    }
    return ('Global\tce-cleanup-' + $digest.Substring(0, 24))
}

function Get-CleanupLock {
    param([Parameter(Mandatory = $true)][string]$LockName)

    $mutex = New-Object System.Threading.Mutex($false, $LockName)
    $acquired = $false
    try {
        $acquired = $mutex.WaitOne(0)
    } catch [System.Threading.AbandonedMutexException] {
        # Dono anterior morreu sem liberar: o mutex foi entregue a este processo.
        $acquired = $true
    } catch {
        $mutex.Dispose()
        throw
    }
    if (-not $acquired) {
        $mutex.Dispose()
        throw 'another cleanup operation is already running for this root'
    }
    return $mutex
}

function Release-CleanupLock {
    param([Parameter(Mandatory = $true)][object]$Mutex)

    try { $Mutex.ReleaseMutex() } catch { }
    try { $Mutex.Dispose() } catch { }
}

function Get-CleanupProcessNames {
    param(
        [string[]]$OverrideNames,
        [switch]$DenyEnumeration
    )

    $names = New-Object System.Collections.Generic.List[string]
    if ($null -ne $OverrideNames) {
        foreach ($name in @($OverrideNames)) {
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            $normalized = ([string]$name).Trim().ToLowerInvariant()
            if ($normalized.EndsWith('.exe', [StringComparison]::Ordinal)) { $normalized = $normalized.Substring(0, $normalized.Length - 4) }
            $names.Add($normalized)
        }
        return ([string[]]$names.ToArray())
    }
    if ($DenyEnumeration) { throw 'browser process enumeration failed: synthetic enumeration denial' }
    try {
        foreach ($process in @(Get-Process -ErrorAction Stop)) {
            $processName = ''
            try { $processName = [string]$process.Name } catch { throw }
            if (-not [string]::IsNullOrWhiteSpace($processName)) { $names.Add($processName.Trim().ToLowerInvariant()) }
        }
    } catch {
        throw ('browser process enumeration failed: ' + $_.Exception.Message)
    }
    return ([string[]]$names.ToArray())
}

function Normalize-BrowserProcessName {
    param([string]$Name)

    if ([string]::IsNullOrWhiteSpace($Name)) { return '' }
    $normalized = $Name.Trim().ToLowerInvariant()
    if ($normalized.EndsWith('.exe', [StringComparison]::Ordinal)) {
        $normalized = $normalized.Substring(0, $normalized.Length - 4)
    }
    return $normalized
}

function Normalize-BrowserUserDataDirectory {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    try {
        $full = [IO.Path]::GetFullPath($Path.Trim())
        if ($full.Length -gt 3) { $full = $full.TrimEnd([char[]]@('\', '/')) }
        return $full
    } catch {
        return $null
    }
}

function Get-BrowserProcesses {
    param(
        [object[]]$OverrideProcesses,
        [string[]]$OverrideNames,
        [switch]$DenyEnumeration
    )

    $browserBaseNames = @('chrome', 'msedge', 'firefox', 'brave', 'opera', 'vivaldi', 'chromium', 'iexplore', 'thorium', 'arc')
    $processes = New-Object System.Collections.Generic.List[object]
    if ($null -ne $OverrideProcesses -and @($OverrideProcesses).Count -gt 0) {
        foreach ($process in @($OverrideProcesses)) {
            $nameProperty = @($process.PSObject.Properties | Where-Object { $_.Name -ieq 'name' } | Select-Object -First 1)
            if ($nameProperty.Count -eq 0) { continue }
            $name = Normalize-BrowserProcessName ([string]$nameProperty[0].Value)
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            $userDataProperty = @($process.PSObject.Properties | Where-Object { $_.Name -ieq 'user_data_dir' -or $_.Name -ieq 'UserDataDir' } | Select-Object -First 1)
            $userDataDir = $null
            if ($userDataProperty.Count -gt 0) { $userDataDir = Normalize-BrowserUserDataDirectory ([string]$userDataProperty[0].Value) }
            $processes.Add([pscustomobject]@{ name = $name; user_data_dir = $userDataDir })
        }
        return ([object[]]$processes.ToArray())
    }

    if ($null -ne $OverrideNames -and @($OverrideNames).Count -gt 0) {
        foreach ($nameValue in @(Get-CleanupProcessNames -OverrideNames $OverrideNames)) {
            $name = Normalize-BrowserProcessName $nameValue
            if ([string]::IsNullOrWhiteSpace($name)) { continue }
            $processes.Add([pscustomobject]@{ name = $name; user_data_dir = $null })
        }
        return ([object[]]$processes.ToArray())
    }

    $runningNames = @(Get-CleanupProcessNames -DenyEnumeration:$DenyEnumeration)
    $knownRunningNames = @($runningNames | ForEach-Object { Normalize-BrowserProcessName $_ } | Where-Object { $browserBaseNames -contains $_ } | Sort-Object -Unique)
    if ($knownRunningNames.Count -eq 0) { return ([object[]]$processes.ToArray()) }
    try {
        $runningProcesses = @(Get-Process -Name $knownRunningNames -ErrorAction Stop)
    } catch {
        throw ('browser process enumeration failed: ' + $_.Exception.Message)
    }
    foreach ($process in $runningProcesses) {
        $name = Normalize-BrowserProcessName ([string]$process.Name)
        if ($browserBaseNames -notcontains $name) { continue }
        $userDataDir = $null
        # CIM é apenas evidência suplementar; falha de acesso não autoriza
        # assumir posse e será tratada pela sonda de exclusividade por item.
        try {
            $cimProcess = @(Get-CimInstance -ClassName Win32_Process -Filter ('ProcessId = {0}' -f $process.Id) -ErrorAction Stop | Select-Object -First 1)
            $commandLine = ''
            if ($cimProcess.Count -gt 0) { $commandLine = [string]$cimProcess[0].CommandLine }
            $match = [regex]::Match($commandLine, '(?i)--user-data-dir(?:=|\s+)(?:"([^"]+)"|''([^'']+)''|([^\s]+))')
            if ($match.Success) {
                $candidate = $match.Groups[1].Value
                if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = $match.Groups[2].Value }
                if ([string]::IsNullOrWhiteSpace($candidate)) { $candidate = $match.Groups[3].Value }
                $userDataDir = Normalize-BrowserUserDataDirectory $candidate
            }
        } catch {
            $userDataDir = $null
        }
        $processes.Add([pscustomobject]@{ name = $name; user_data_dir = $userDataDir })
    }
    return ([object[]]$processes.ToArray())
}

function Test-IsBrowserAreaRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    $browserBaseNames = @('chrome', 'msedge', 'firefox', 'brave', 'opera', 'vivaldi', 'chromium', 'iexplore', 'thorium', 'arc')
    foreach ($segment in @(([string]$RelativePath -replace '/', '\') -split '\\')) {
        if ([string]::IsNullOrWhiteSpace($segment)) { continue }
        $token = ([string]@($segment -split '[-_.]')[0]).ToLowerInvariant()
        if ($browserBaseNames -contains $token) { return $true }
    }
    return $false
}

function Test-PathCoveredBy {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Directory
    )

    $candidateFull = ConvertTo-FullPath $Candidate
    $directoryFull = Normalize-BrowserUserDataDirectory $Directory
    if ([string]::IsNullOrWhiteSpace($directoryFull)) { return $false }
    if ($candidateFull.Equals($directoryFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $candidateFull.StartsWith(($directoryFull + [IO.Path]::DirectorySeparatorChar), [StringComparison]::OrdinalIgnoreCase)
}

function Test-CleanupPathExclusive {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $stream = $null
        try {
            $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
            return $true
        } catch {
            return $false
        } finally {
            if ($null -ne $stream) { $stream.Dispose() }
        }
    }
    if (Test-Path -LiteralPath $Path -PathType Container) {
        try {
            foreach ($file in @(Get-ChildItem -LiteralPath $Path -File -Force -Recurse -ErrorAction Stop)) {
                $stream = $null
                try {
                    $stream = [IO.File]::Open($file.FullName, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
                } catch {
                    return $false
                } finally {
                    if ($null -ne $stream) { $stream.Dispose() }
                }
            }
            return $true
        } catch {
            return $false
        }
    }
    return $false
}

function Get-BrowserProfileBlockers {
    param(
        [Parameter(Mandatory = $true)][object[]]$Items,
        [Parameter(Mandatory = $true)][string]$RootPath,
        [object[]]$BrowserProcesses = @()
    )

    $browserBaseNames = @('chrome', 'msedge', 'firefox', 'brave', 'opera', 'vivaldi', 'chromium', 'iexplore', 'thorium', 'arc')
    $blockers = New-Object System.Collections.Generic.List[object]
    foreach ($item in @($Items)) {
        $relative = [string]$item.RelativePath
        if (-not (Test-IsBrowserAreaRelativePath -RelativePath $relative)) { continue }
        $owner = @($BrowserProcesses | Where-Object {
            -not [string]::IsNullOrWhiteSpace([string]$_.user_data_dir) -and
            (Test-PathCoveredBy -Candidate ([string]$item.Source) -Directory ([string]$_.user_data_dir))
        } | Select-Object -First 1)
        if ($owner.Count -gt 0) {
            $blockers.Add([pscustomobject]@{ RelativePath = $relative; Process = [string]$owner[0].name })
            continue
        }
        if (-not (Test-CleanupPathExclusive -Path ([string]$item.Source))) {
            $processName = [string](@($BrowserProcesses | Select-Object -First 1 | ForEach-Object { $_.name }))
            if ([string]::IsNullOrWhiteSpace($processName)) { $processName = 'browser profile lock' }
            $blockers.Add([pscustomobject]@{ RelativePath = $relative; Process = $processName })
        }
    }
    return ([object[]]$blockers.ToArray())
}

function Add-JournalRecord {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Record
    )

    $line = ConvertTo-Json -InputObject $Record -Compress -Depth 8
    $stream = $null
    $writer = $null
    try {
        $stream = New-Object IO.FileStream($Path, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::Read)
        $writer = New-Object IO.StreamWriter($stream, (New-Object Text.UTF8Encoding($false)))
        $writer.WriteLine($line)
        $writer.Flush()
        $stream.Flush($true)
    } finally {
        if ($null -ne $writer) { $writer.Dispose() }
        elseif ($null -ne $stream) { $stream.Dispose() }
    }
}

function Read-JournalRecords {
    param([Parameter(Mandatory = $true)][string]$Path)

    $records = New-Object System.Collections.Generic.List[object]
    foreach ($line in @(Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $records.Add(($line | ConvertFrom-Json))
        } catch {
            throw "journal line is not valid JSON: $Path"
        }
    }
    return ([object[]]$records.ToArray())
}

function Assert-JournalStructure {
    param(
        [Parameter(Mandatory = $true)][string]$JournalPath,
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][object]$ExpectedDestinations,
        [Parameter(Mandatory = $true)][string]$QuarantineRoot
    )

    if (-not (Test-Path -LiteralPath $JournalPath -PathType Leaf)) { return }
    Assert-NoReparsePath -Path $JournalPath -RootPath $RootPath
    $records = @(Read-JournalRecords -Path $JournalPath)
    if ($records.Count -eq 0) { throw 'journal is empty' }
    $headerSeen = $false
    foreach ($record in $records) {
        $properties = @($record.PSObject.Properties.Name)
        $recordType = ''
        if ($properties -contains 'type') { $recordType = [string]$record.type }
        if ($recordType -eq 'header') {
            if (-not $headerSeen) {
                $headerSeen = $true
                if ($properties -contains 'quarantine_root' -and -not [string]::IsNullOrWhiteSpace([string]$record.quarantine_root)) {
                    if (-not (ConvertTo-FullPath ([string]$record.quarantine_root)).Equals($QuarantineRoot, [StringComparison]::OrdinalIgnoreCase)) {
                        throw 'journal quarantine root does not match receipt'
                    }
                }
            }
            continue
        }
        if (-not $headerSeen) { throw 'journal item precedes header' }
        if ($properties -notcontains 'destination') { throw 'journal item has no destination' }
        $destination = ConvertTo-FullPath ([string]$record.destination)
        if (-not $ExpectedDestinations.Contains($destination)) { throw 'receipt has no item for journal destination' }
    }
}

function Find-ResumableQuarantine {
    param(
        [Parameter(Mandatory = $true)][string]$QuarantineBase,
        [Parameter(Mandatory = $true)][string]$RootPath
    )

    if (-not (Test-Path -LiteralPath $QuarantineBase -PathType Container)) { return '' }
    foreach ($candidate in @(Get-ChildItem -LiteralPath $QuarantineBase -Directory -Force | Sort-Object Name -Descending)) {
        Assert-NoReparsePath -Path $candidate.FullName -RootPath $RootPath
        if (Test-Path -LiteralPath (Join-Path $candidate.FullName 'journal.ndjson') -PathType Leaf) { return $candidate.FullName }
    }
    return ''
}

function Get-ApprovedCleanupItems {
    param(
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][object[]]$Entries,
        [Parameter(Mandatory = $true)][bool]$RequireSource,
        [switch]$AllowSourceInUse
    )

    $seen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $items = New-Object System.Collections.Generic.List[object]
    foreach ($entry in $Entries) {
        $relative = [string]$entry.path
        Assert-SafeRelativePath $relative
        $relativeNormalized = ($relative -replace '/', '\')
        if (-not $seen.Add($relativeNormalized)) { throw "duplicate cleanup path: $relative" }
        if ([string]$entry.kind -ne 'file') { throw "only file entries are accepted: $relative" }
        if ([string]$entry.decision -ne 'quarantine' -or $entry.approved -ne $true) { throw "entry is not explicitly approved: $relative" }
        $expectedHash = ([string]$entry.sha256).ToLowerInvariant()
        if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "invalid sha256: $relative" }
        $source = ConvertTo-FullPath (Join-Path $RootPath $relative)
        if (-not (Test-PathWithinRoot -Candidate $source -Base $RootPath)) { throw "entry escapes root: $relative" }
        if ($source.Equals($ManifestPath, [StringComparison]::OrdinalIgnoreCase)) { throw 'manifest cannot approve itself' }

        $bytes = [int64]$entry.bytes
        $hash = $expectedHash
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            [void](Assert-SafeResolvedPath -Path $source -RootPath $RootPath)
            Assert-NoReparsePath -Path $source -RootPath $RootPath
            $file = Get-Item -LiteralPath $source -Force
            if ([int64]$entry.bytes -ne [int64]$file.Length) { throw "byte count mismatch: $relative" }
            try {
                $actualHash = Get-FileSha256 $source
            } catch {
                $sourceException = $_.Exception
                $isSourceInUse = $false
                while ($null -ne $sourceException) {
                    if ($sourceException -is [IO.IOException]) { $isSourceInUse = $true; break }
                    $sourceException = $sourceException.InnerException
                }
                if ($isSourceInUse -and $AllowSourceInUse -and (Test-IsBrowserAreaRelativePath -RelativePath $relative)) {
                    $items.Add([pscustomobject]@{
                        RelativePath = $relativeNormalized
                        Source = $source
                        Bytes = $bytes
                        Sha256 = $hash
                    })
                    continue
                }
                if ($isSourceInUse) { throw "source file is in use: $relative" }
                throw
            }
            if ($actualHash -ne $expectedHash) { throw "hash mismatch: $relative" }
            $bytes = [int64]$file.Length
            $hash = $actualHash
        } elseif ($RequireSource) {
            throw "approved target is absent: $relative"
        }
        $items.Add([pscustomobject]@{
            RelativePath = $relativeNormalized
            Source = $source
            Bytes = $bytes
            Sha256 = $hash
        })
    }
    return ([object[]]$items.ToArray())
}

function Write-Receipt {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][string]$QuarantineRoot,
        [Parameter(Mandatory = $true)][string]$CreatedAt,
        [Parameter(Mandatory = $true)][object[]]$Items
    )

    $receipt = [ordered]@{
        schema_version = 1
        root = $RootPath
        quarantine_root = $QuarantineRoot
        created_at = $CreatedAt
        items = @($Items)
    }
    $directory = Split-Path -Parent $Path
    $temporaryPath = Join-Path $directory ('receipt.json.' + [guid]::NewGuid().ToString('N') + '.tmp')
    $backupPath = $null
    try {
        Write-NewUtf8File -Path $temporaryPath -Content ($receipt | ConvertTo-Json -Depth 10)
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try {
                [IO.File]::Replace($temporaryPath, $Path, $null)
            } catch {
                # O overload com backup nulo pode ser rejeitado pelo binder do
                # PS 5.1/.NET atual; o backup efêmero mantém a publicação
                # atômica e é removido no finally. Se o primeiro overload falhar
                # por outro motivo, o segundo também falhará sem mover o temp.
                $backupPath = Join-Path $directory ('receipt.json.' + [guid]::NewGuid().ToString('N') + '.bak')
                [IO.File]::Replace($temporaryPath, $Path, $backupPath)
            }
        } else {
            [IO.File]::Move($temporaryPath, $Path)
        }
    } catch {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            try { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue } catch { }
        }
        if ($null -ne $backupPath -and (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
            try { Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue } catch { }
        }
        throw
    } finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            try { Remove-Item -LiteralPath $temporaryPath -Force -ErrorAction SilentlyContinue } catch { }
        }
        if ($null -ne $backupPath -and (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
            try { Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue } catch { }
        }
    }
}

function Assert-ReceiptStructure {
    param(
        [Parameter(Mandatory = $true)][string]$ReceiptPath,
        [Parameter(Mandatory = $true)][object]$Receipt,
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)][string]$QuarantineBase
    )

    if ([int]$Receipt.schema_version -ne 1 -or -not ([string]$Receipt.root).Equals($RootPath, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'invalid receipt root or schema'
    }
    $quarantineRoot = ConvertTo-FullPath ([string]$Receipt.quarantine_root)
    $receiptFull = ConvertTo-FullPath $ReceiptPath
    $expectedReceipt = ConvertTo-FullPath (Join-Path $quarantineRoot 'receipt.json')
    if (-not $receiptFull.Equals($expectedReceipt, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'receipt path must be quarantine\receipt.json'
    }
    $quarantineParent = (Split-Path -Parent $quarantineRoot).TrimEnd('\', '/')
    $expectedQuarantineParent = (ConvertTo-FullPath $QuarantineBase).TrimEnd('\', '/')
    if (-not (Test-PathWithinRoot -Candidate $quarantineRoot -Base $QuarantineBase) -or
        -not $quarantineParent.Equals($expectedQuarantineParent, [StringComparison]::OrdinalIgnoreCase) -or
        $quarantineRoot.IndexOfAny([char[]]'*?[]') -ge 0) {
        throw 'receipt quarantine root is not an explicit child of tmp\quarantine'
    }
    if (-not (Test-Path -LiteralPath $quarantineRoot -PathType Container)) { throw 'receipted quarantine does not exist' }
    Assert-NoReparsePath -Path $quarantineRoot -RootPath $RootPath
    Assert-NoReparseTreePath -Path $quarantineRoot -RootPath $RootPath
    if (-not (Test-Path -LiteralPath $receiptFull -PathType Leaf)) { throw 'receipt file does not exist' }

    $items = @($Receipt.items)
    if ($items.Count -eq 0) { throw 'receipt has no items' }
    $seenDestinations = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $expectedDestinations = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($item in $items) {
        if ([string]$item.result -ne 'moved') { throw 'receipt item result must be moved' }
        $origin = ConvertTo-FullPath ([string]$item.origin)
        if (-not (Test-PathWithinRoot -Candidate $origin -Base $RootPath)) { throw 'receipt origin escapes root' }
        $relativeOrigin = Get-RelativePath -Path $origin -Base $RootPath
        Assert-SafeRelativePath $relativeOrigin
        $destination = ConvertTo-FullPath ([string]$item.destination)
        $expectedDestination = ConvertTo-FullPath (Join-Path $quarantineRoot $relativeOrigin)
        if (-not $destination.Equals($expectedDestination, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'receipt destination does not match quarantine and origin'
        }
        if (-not $seenDestinations.Add($destination)) { throw 'duplicate receipt destination' }
        [void]$expectedDestinations.Add($destination)
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) { throw "receipted item is absent: $destination" }
        Assert-NoReparsePath -Path $destination -RootPath $RootPath
        $destinationInfo = Get-Item -LiteralPath $destination -Force
        if ([int64]$item.bytes -ne [int64]$destinationInfo.Length) { throw "receipt byte count mismatch: $destination" }
        $expectedHash = ([string]$item.sha256).ToLowerInvariant()
        if ($expectedHash -notmatch '^[0-9a-f]{64}$') { throw "invalid receipt sha256: $destination" }
        if ((Get-FileSha256 $destination) -ne $expectedHash) { throw "receipted hash mismatch: $destination" }
    }

    $journalFull = ConvertTo-FullPath (Join-Path $quarantineRoot 'journal.ndjson')
    Assert-JournalStructure -JournalPath $journalFull -RootPath $RootPath -ExpectedDestinations $expectedDestinations -QuarantineRoot $quarantineRoot

    $filesInQuarantine = @(Get-ChildItem -LiteralPath $quarantineRoot -File -Force -Recurse)
    foreach ($file in @($filesInQuarantine)) {
        Assert-NoReparsePath -Path $file.FullName -RootPath $RootPath
        if ($file.FullName.Equals($receiptFull, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if ($file.FullName.Equals($journalFull, [StringComparison]::OrdinalIgnoreCase)) { continue }
        if (-not $expectedDestinations.Contains((ConvertTo-FullPath $file.FullName))) {
            throw "unlisted file exists in quarantine: $($file.FullName)"
        }
    }
    return [pscustomobject]@{ QuarantineRoot = $quarantineRoot; ReceiptPath = $receiptFull; Items = $items }
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
$rootFull = Get-NormalizedRootPath $Root
if (-not (Test-Path -LiteralPath $rootFull -PathType Container)) { throw "root directory does not exist: $rootFull" }
$rootBoundary = $projectRoot
if ($TestTemporaryRoot) {
    $tempBoundary = ConvertTo-FullPath ([IO.Path]::GetTempPath())
    if (-not (Test-PathWithinRoot -Candidate $rootFull -Base $tempBoundary -AllowEqual)) {
        throw 'TestTemporaryRoot requires root inside the OS temp directory'
    }
    $rootBoundary = $rootFull
} elseif (-not (Test-PathWithinRoot -Candidate $rootFull -Base $projectRoot -AllowEqual)) {
    throw 'root must stay inside project'
}
if (-not $TestTemporaryRoot -and -not [string]::IsNullOrWhiteSpace($TestHook)) {
    throw 'TestHook requires TestTemporaryRoot'
}
Assert-NoReparsePath -Path $rootFull -RootPath $rootBoundary
$quarantineBase = Assert-SafeQuarantineBase -RootPath $rootFull

$cleanupLock = $null
try {
    if ($Apply -or $Resume -or $PurgeQuarantine) {
        $cleanupLock = Get-CleanupLock -LockName (Get-CleanupLockName -RootPath $rootFull)
    }

    if ($PurgeQuarantine) {
        $receiptResult = Get-ManifestDocument -Path $ManifestPath -RootPath $rootFull
        $receipt = $receiptResult.Document
        $structure = Assert-ReceiptStructure -ReceiptPath $receiptResult.FullPath -Receipt $receipt -RootPath $rootFull -QuarantineBase $quarantineBase
        foreach ($item in @($structure.Items)) {
            Remove-Item -LiteralPath ([string]$item.destination) -Force
        }
        Remove-Item -LiteralPath $structure.ReceiptPath -Force
        $journalFull = ConvertTo-FullPath (Join-Path $structure.QuarantineRoot 'journal.ndjson')
        if (Test-Path -LiteralPath $journalFull -PathType Leaf) { Remove-Item -LiteralPath $journalFull -Force }
        $directories = @(Get-ChildItem -LiteralPath $structure.QuarantineRoot -Directory -Force -Recurse | Sort-Object { $_.FullName.Length } -Descending)
        foreach ($directory in $directories) {
            Remove-Item -LiteralPath $directory.FullName -Force
        }
        Remove-Item -LiteralPath $structure.QuarantineRoot -Force
        [pscustomobject]@{ mode = 'purge'; purged_items = $structure.Items.Count; quarantine_root = $structure.QuarantineRoot } | ConvertTo-Json -Compress
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

    $items = @(Get-ApprovedCleanupItems -RootPath $rootFull -ManifestPath $manifestResult.FullPath -Entries $entries -RequireSource (-not $Resume) -AllowSourceInUse:($Apply -or $Resume))
    $totalBytes = [int64](($items | Measure-Object Bytes -Sum).Sum)

    if (-not $Apply -and -not $Resume) {
        [pscustomobject]@{ mode = 'whatif'; approved_items = $items.Count; approved_bytes = $totalBytes } | ConvertTo-Json -Compress
        exit 0
    }

    $browserProcesses = @(Get-BrowserProcesses -OverrideProcesses $TestBrowserProcesses -OverrideNames $TestRunningProcesses -DenyEnumeration:$TestDenyProcessEnumeration)
    $blockers = @(Get-BrowserProfileBlockers -Items $items -RootPath $rootFull -BrowserProcesses $browserProcesses)
    if ($blockers.Count -gt 0) {
        throw ("running browser process blocks cleanup of browser profile: {0} (process {1})" -f $blockers[0].RelativePath, $blockers[0].Process)
    }

    if ($Resume) {
        $resumeQuarantine = [string](Find-ResumableQuarantine -QuarantineBase $quarantineBase -RootPath $rootFull)
        if ([string]::IsNullOrWhiteSpace($resumeQuarantine)) { throw 'no resumable quarantine' }
        $quarantineRoot = $resumeQuarantine
        $journalPath = Join-Path $quarantineRoot 'journal.ndjson'
        $receiptPath = Join-Path $quarantineRoot 'receipt.json'
        if (Test-Path -LiteralPath $receiptPath -PathType Leaf) {
            try {
                # Resume idempotente: a quarentena já foi concluída por um
                # resume anterior, desde que o recibo esteja íntegro.
                $completedResult = Get-ManifestDocument -Path $receiptPath -RootPath $rootFull
                $completedStructure = Assert-ReceiptStructure -ReceiptPath $completedResult.FullPath -Receipt $completedResult.Document -RootPath $rootFull -QuarantineBase $quarantineBase
                [pscustomobject]@{
                    mode = 'resume'
                    recovered_items = $completedStructure.Items.Count
                    moved_items = 0
                    receipt = $receiptPath
                    quarantine_root = $quarantineRoot
                } | ConvertTo-Json -Compress
                exit 0
            } catch {
                Write-Warning ('receipt.json is invalid or incomplete; falling back to journal.ndjson: ' + $_.Exception.Message)
            }
        }
        $resumeRecords = @(Read-JournalRecords -Path $journalPath)
        if ($resumeRecords.Count -eq 0 -or [string]$resumeRecords[0].type -ne 'header') { throw 'resumable journal has no header' }
        $resumeHeaderProperties = @($resumeRecords[0].PSObject.Properties.Name)
        if ($resumeHeaderProperties -contains 'root' -and -not ([string]$resumeRecords[0].root).Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'resume journal root does not match requested root'
        }

        $recovered = New-Object System.Collections.Generic.List[object]
        $movedNow = New-Object System.Collections.Generic.List[object]
        foreach ($item in @($items | Sort-Object RelativePath)) {
            $destination = ConvertTo-FullPath (Join-Path $quarantineRoot $item.RelativePath)
            if (-not (Test-PathWithinRoot -Candidate $destination -Base $quarantineRoot)) { throw "destination escapes quarantine: $($item.RelativePath)" }
            if (Test-Path -LiteralPath $destination -PathType Leaf) {
                Assert-NoReparsePath -Path $destination -RootPath $rootFull
                $destinationInfo = Get-Item -LiteralPath $destination -Force
                if ((Get-FileSha256 $destination) -ne $item.Sha256) { throw "resume destination hash mismatch: $($item.RelativePath)" }
                $recovered.Add([ordered]@{
                    origin = $item.Source
                    destination = $destination
                    sha256 = $item.Sha256
                    bytes = [int64]$destinationInfo.Length
                    timestamp = [DateTime]::UtcNow.ToString('o')
                    result = 'moved'
                })
                continue
            }
            if (-not (Test-Path -LiteralPath $item.Source -PathType Leaf)) { throw "resume destination is missing: $($item.RelativePath)" }
            $parent = Split-Path -Parent $destination
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
                New-Item -ItemType Directory -Path $parent -Force | Out-Null
            }
            if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw "destination parent is not a directory: $parent" }
            Assert-NoReparsePath -Path $parent -RootPath $rootFull
            if (Test-Path -LiteralPath $destination) { throw "destination already exists: $destination" }
            [void](Assert-SafeResolvedPath -Path $item.Source -RootPath $rootFull)
            Assert-NoReparsePath -Path $item.Source -RootPath $rootFull
            $sourceStream = $null
            try {
                try {
                    $sourceStream = [IO.File]::Open($item.Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::Read -bor [IO.FileShare]::Delete))
                } catch {
                    throw "source file is in use: $($item.RelativePath)"
                }
                if ([int64]$sourceStream.Length -ne $item.Bytes) { throw "source byte count changed before move: $($item.RelativePath)" }
                $pinnedHash = Get-FileSha256FromStream -Stream $sourceStream
                if ($pinnedHash -ne $item.Sha256) { throw "source hash changed before move: $($item.RelativePath)" }
                Add-JournalRecord -Path $journalPath -Record ([ordered]@{
                    type = 'item'
                    result = 'planned'
                    origin = $item.Source
                    destination = $destination
                    sha256 = $pinnedHash
                    bytes = $item.Bytes
                    timestamp = [DateTime]::UtcNow.ToString('o')
                })
                Move-Item -LiteralPath $item.Source -Destination $destination
                $postMoveHash = Get-FileSha256 $destination
                if ($postMoveHash -ne $pinnedHash) { throw "post-move hash mismatch: $($item.RelativePath)" }
                Add-JournalRecord -Path $journalPath -Record ([ordered]@{
                    type = 'item'
                    result = 'moved'
                    origin = $item.Source
                    destination = $destination
                    sha256 = $pinnedHash
                    bytes = $item.Bytes
                    timestamp = [DateTime]::UtcNow.ToString('o')
                })
                $movedNow.Add([ordered]@{
                    origin = $item.Source
                    destination = $destination
                    sha256 = $pinnedHash
                    bytes = $item.Bytes
                    timestamp = [DateTime]::UtcNow.ToString('o')
                    result = 'moved'
                })
            } finally {
                if ($null -ne $sourceStream) { $sourceStream.Dispose() }
            }
        }
        $receiptItems = @(@($recovered.ToArray()) + @($movedNow.ToArray()))
        Write-Receipt -Path $receiptPath -RootPath $rootFull -QuarantineRoot $quarantineRoot -CreatedAt ([DateTime]::UtcNow.ToString('o')) -Items $receiptItems
        [pscustomobject]@{
            mode = 'resume'
            recovered_items = $recovered.Count
            moved_items = $movedNow.Count
            receipt = $receiptPath
            quarantine_root = $quarantineRoot
        } | ConvertTo-Json -Compress
        exit 0
    }

    if (-not (Test-Path -LiteralPath $quarantineBase -PathType Container)) {
        New-Item -ItemType Directory -Path $quarantineBase -Force | Out-Null
    }
    Assert-NoReparsePath -Path $quarantineBase -RootPath $rootFull
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss-fff')
    $quarantineRoot = Join-Path $quarantineBase $stamp
    New-Item -ItemType Directory -Path $quarantineRoot | Out-Null
    $journalPath = Join-Path $quarantineRoot 'journal.ndjson'
    $createdAt = [DateTime]::UtcNow.ToString('o')
    $receiptPath = Join-Path $quarantineRoot 'receipt.json'
    $sortedItems = @($items | Sort-Object RelativePath)
    Add-JournalRecord -Path $journalPath -Record ([ordered]@{
        type = 'header'
        schema_version = 1
        root = $rootFull
        quarantine_root = $quarantineRoot
        created_at = $createdAt
    })
    foreach ($item in $sortedItems) {
        if ($item.RelativePath.Equals('receipt.json', [StringComparison]::OrdinalIgnoreCase)) { throw 'entry would collide with quarantine receipt' }
        if ($item.RelativePath.Equals('journal.ndjson', [StringComparison]::OrdinalIgnoreCase)) { throw 'entry would collide with quarantine journal' }
        Add-JournalRecord -Path $journalPath -Record ([ordered]@{
            type = 'item'
            result = 'planned'
            origin = $item.Source
            destination = (ConvertTo-FullPath (Join-Path $quarantineRoot $item.RelativePath))
            sha256 = $item.Sha256
            bytes = $item.Bytes
            timestamp = [DateTime]::UtcNow.ToString('o')
        })
    }

    $moved = New-Object System.Collections.Generic.List[object]
    $moveCount = 0
    foreach ($item in $sortedItems) {
        $destination = ConvertTo-FullPath (Join-Path $quarantineRoot $item.RelativePath)
        if (-not (Test-PathWithinRoot -Candidate $destination -Base $quarantineRoot)) { throw "destination escapes quarantine: $($item.RelativePath)" }
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) { throw "destination parent is not a directory: $parent" }

        # Última janela de contenção: o seam cria uma colisão antes das checagens finais.
        if (-not [string]::IsNullOrWhiteSpace($TestHook) -and $TestHook.StartsWith('before-final-move-collision-', [StringComparison]::Ordinal)) {
            Invoke-TestHook -Hook $TestHook -Destination $destination
        }
        Assert-NoReparsePath -Path $parent -RootPath $rootFull
        if (Test-Path -LiteralPath $destination) { throw "destination already exists: $destination" }
        [void](Assert-SafeResolvedPath -Path $item.Source -RootPath $rootFull)
        Assert-NoReparsePath -Path $item.Source -RootPath $rootFull
        $sourceStream = $null
        try {
            try {
                $sourceStream = [IO.File]::Open($item.Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::Read -bor [IO.FileShare]::Delete))
            } catch {
                throw "source file is in use: $($item.RelativePath)"
            }
            if ([int64]$sourceStream.Length -ne $item.Bytes) { throw "source byte count changed before move: $($item.RelativePath)" }
            $pinnedHash = Get-FileSha256FromStream -Stream $sourceStream
            if ($pinnedHash -ne $item.Sha256) { throw "source hash changed before move: $($item.RelativePath)" }

            Move-Item -LiteralPath $item.Source -Destination $destination
            if ($TestHook -eq 'post-move-hash-mismatch') {
                Invoke-TestHook -Hook $TestHook -Destination $destination
            }
            $postMoveHash = Get-FileSha256 $destination
            if ($postMoveHash -ne $pinnedHash) {
                $unconfirmed = [ordered]@{
                    origin = $item.Source
                    destination = $destination
                    sha256 = $pinnedHash
                    bytes = $item.Bytes
                    timestamp = [DateTime]::UtcNow.ToString('o')
                    result = 'unconfirmed'
                }
                $rollbackError = $null
                try {
                    $sourceParent = Split-Path -Parent $item.Source
                    Assert-NoReparsePath -Path $sourceParent -RootPath $rootFull
                    if (Test-Path -LiteralPath $item.Source) { throw "rollback source already exists: $($item.Source)" }
                    Move-Item -LiteralPath $destination -Destination $item.Source
                } catch {
                    $rollbackError = [string]$_.Exception.Message
                }
                $moved.Add($unconfirmed)
                Write-Receipt -Path $receiptPath -RootPath $rootFull -QuarantineRoot $quarantineRoot -CreatedAt $createdAt -Items $moved.ToArray()
                if ($null -ne $rollbackError) {
                    throw "post-move hash mismatch: $($item.RelativePath); rollback failed: $rollbackError"
                }
                throw "post-move hash mismatch: $($item.RelativePath)"
            }
        } finally {
            if ($null -ne $sourceStream) { $sourceStream.Dispose() }
        }
        $moveCount++
        Add-JournalRecord -Path $journalPath -Record ([ordered]@{
            type = 'item'
            result = 'moved'
            origin = $item.Source
            destination = $destination
            sha256 = $item.Sha256
            bytes = $item.Bytes
            timestamp = [DateTime]::UtcNow.ToString('o')
        })
        $moved.Add([ordered]@{
            origin = $item.Source
            destination = $destination
            sha256 = $item.Sha256
            bytes = $item.Bytes
            timestamp = [DateTime]::UtcNow.ToString('o')
            result = 'moved'
        })
        if ($TestHook -eq 'abort-after-first-move' -and $moveCount -eq 1) { exit 70 }
    }
    Write-Receipt -Path $receiptPath -RootPath $rootFull -QuarantineRoot $quarantineRoot -CreatedAt $createdAt -Items $moved.ToArray()
    [pscustomobject]@{ mode = 'apply'; approved_items = $moved.Count; approved_bytes = $totalBytes; receipt = $receiptPath; quarantine_root = $quarantineRoot } | ConvertTo-Json -Compress
    exit 0
} finally {
    if ($null -ne $cleanupLock) { Release-CleanupLock -Mutex $cleanupLock }
}
