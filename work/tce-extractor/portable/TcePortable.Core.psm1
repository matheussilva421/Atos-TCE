Set-StrictMode -Version 2.0

$script:TceDownloadMaxDownloads = 2

function ConvertTo-TceComparableText {
    param([AllowNull()][string]$Text)
    if ($null -eq $Text) { return '' }
    $normalized = $Text.Normalize([Text.NormalizationForm]::FormD)
    $builder = New-Object Text.StringBuilder
    foreach ($character in $normalized.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($character) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($character)
        }
    }
    return $builder.ToString().ToLowerInvariant()
}

function ConvertTo-TceSafeName {
    param([Parameter(Mandatory)][string]$Name)
    $normalized = $Name.Normalize([Text.NormalizationForm]::FormD)
    $builder = New-Object Text.StringBuilder
    foreach ($character in $normalized.ToCharArray()) {
        if ([Globalization.CharUnicodeInfo]::GetUnicodeCategory($character) -ne [Globalization.UnicodeCategory]::NonSpacingMark) {
            [void]$builder.Append($character)
        }
    }
    $plain = $builder.ToString()
    $extension = [IO.Path]::GetExtension($plain)
    $stem = if ($extension) { $plain.Substring(0, $plain.Length - $extension.Length) } else { $plain }
    $safe = ($stem -replace '[^A-Za-z0-9_-]+', '-' -replace '-+', '-').Trim(' ', '.', '-')
    $safeExtension = $extension -replace '[^A-Za-z0-9.]', ''
    $safe += $safeExtension
    if ([string]::IsNullOrWhiteSpace($safe)) { return 'arquivo' }
    if ($safe.Length -gt 140) { $safe = $safe.Substring(0, 140).TrimEnd('.', '-') }
    return $safe
}

function ConvertTo-TceSafeText {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) { return '' }
    $safe = [string]$Value
    $safe = $safe -replace '(?i)\b[a-z][a-z0-9+.-]{1,31}://[^\s"''<>]+', '[URL REMOVIDA]'
    $safe = $safe -replace '(?i)\b(?:authorization|cookie|token|credential|credencial|session|senha|password)\b\s*(?:(?:[:=]\s*)|(?:\s+))(?:bearer|basic)?\s*[^,\s;|]+', '[CREDENCIAL REMOVIDA]'
    $safe = $safe -replace '(?i)\b(?:url|authorization|cookie|token|credential|credencial|session|senha|password)\b', '[DADO SENSIVEL REMOVIDO]'
    return $safe
}

function Get-TceObjectPropertyValue {
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory)][string]$Name,
        [AllowNull()][object]$Default = $null
    )
    if ($null -eq $InputObject) { return $Default }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}

function Get-TceLiveDevToolsPort {
    param(
        [Parameter(Mandatory)][string]$ProfileRoot,
        [scriptblock]$PortProbe = {
            param([int]$Port)
            try {
                $targets = @(Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/list" -UseBasicParsing -TimeoutSec 3)
                return @($targets | Where-Object { $_.type -eq 'page' }).Count -gt 0
            } catch {
                return $false
            }
        }
    )
    $portFile = Join-Path $ProfileRoot 'DevToolsActivePort'
    if (-not (Test-Path -LiteralPath $portFile -PathType Leaf)) { return $null }
    try {
        $firstLine = Get-Content -LiteralPath $portFile -Encoding UTF8 -TotalCount 1
        $port = 0
        if (-not [int]::TryParse([string]$firstLine, [ref]$port)) { return $null }
        if ($port -lt 1 -or $port -gt 65535) { return $null }
        if ([bool](& $PortProbe $port)) { return $port }
    } catch { }
    return $null
}

function Search-TceProcesses {
    param(
        [Parameter(Mandatory)][object[]]$Processes,
        [Parameter(Mandatory)][string]$Term
    )
    $needle = ConvertTo-TceComparableText $Term
    return @($Processes | Where-Object {
        (ConvertTo-TceComparableText (($_.label, $_.key) -join ' ')).Contains($needle)
    })
}

function Resolve-TceSelection {
    param(
        [Parameter(Mandatory)][string]$InputText,
        [Parameter(Mandatory)][object[]]$Processes,
        [string[]]$KnownProcessKeys = @()
    )
    $text = $InputText.Trim().ToLowerInvariant()
    if ($text -eq 'todos') { return @($Processes) }
    if ($text -eq 'novos') {
        $knownCanonicalKeys = @{}
        foreach ($knownKey in @($KnownProcessKeys)) {
            if ([string]::IsNullOrWhiteSpace([string]$knownKey)) { continue }
            $canonicalKnownKey = ConvertTo-TceCanonicalProcessKey -Process ([pscustomobject]@{ key = [string]$knownKey }) -Context 'KnownProcessKeys'
            $knownCanonicalKeys[$canonicalKnownKey] = $true
        }
        return @($Processes | Where-Object {
            $canonicalProcessKey = ConvertTo-TceCanonicalProcessKey -Process $_ -Context 'processo selecionável'
            -not $knownCanonicalKeys.ContainsKey($canonicalProcessKey)
        })
    }

    $indexes = New-Object 'System.Collections.Generic.SortedSet[int]'
    foreach ($part in ($text -split ',')) {
        $token = $part.Trim()
        if ($token -match '^(\d+)\s*-\s*(\d+)$') {
            $start = [int]$Matches[1]
            $end = [int]$Matches[2]
            if ($start -gt $end) { throw "Intervalo inválido: $token" }
            foreach ($number in $start..$end) { [void]$indexes.Add($number) }
        } elseif ($token -match '^\d+$') {
            [void]$indexes.Add([int]$token)
        } elseif ($token) {
            throw "Seleção inválida: $token"
        }
    }
    foreach ($index in $indexes) {
        if ($index -lt 1 -or $index -gt $Processes.Count) {
            throw "Número fora da lista: $index"
        }
    }
    return @($indexes | ForEach-Object { $Processes[$_ - 1] })
}

function Write-TceJsonAtomic {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)]$Value
    )
    $directory = Split-Path -Parent $Path
    if ($directory) { [IO.Directory]::CreateDirectory($directory) | Out-Null }
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
    try {
        $json = ConvertTo-Json -InputObject $Value -Depth 30
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
}

function Add-TceFailure {
    param(
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [Parameter(Mandatory)][string]$ProcessKey,
        [Parameter(Mandatory)][string]$Message
    )
    $path = Join-Path $ArchiveRoot 'falhas.json'
    $records = New-Object System.Collections.ArrayList
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        try {
            $parsed = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($record in @($parsed)) {
                $legacyValue = Get-TceObjectPropertyValue -InputObject $record -Name 'value'
                if ($null -ne $legacyValue -and $null -ne (Get-TceObjectPropertyValue -InputObject $record -Name 'Count')) {
                    foreach ($legacyRecord in @($legacyValue)) { [void]$records.Add($legacyRecord) }
                } else {
                    [void]$records.Add($record)
                }
            }
        } catch {
            throw "Arquivo de falhas inválido em ${path}: $($_.Exception.Message)"
        }
    }
    [void]$records.Add([pscustomobject]@{
        process = ConvertTo-TceSafeText $ProcessKey
        at = [DateTime]::UtcNow.ToString('o')
        error = ConvertTo-TceSafeText $Message
    })
    Write-TceJsonAtomic -Path $path -Value ([object[]]$records.ToArray())
}

function Get-TceCheckpoint {
    param([Parameter(Mandatory)][string]$ArchiveRoot)
    $path = Join-Path $ArchiveRoot 'checkpoint.json'
    if (Test-Path -LiteralPath $path) {
        try { return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json }
        catch { throw "Checkpoint inválido em ${path}: $($_.Exception.Message)" }
    }
    return [pscustomobject]@{ version = 1; updated_at = $null; processes = @(); documents = @() }
}

function ConvertTo-TceCanonicalProcessKey {
    param(
        [Parameter(Mandatory)][object]$Process,
        [string]$Context = 'processo'
    )
    $rawKey = Get-TceObjectPropertyValue -InputObject $Process -Name 'key' -Default ''
    if ([string]::IsNullOrWhiteSpace([string]$rawKey)) {
        $number = Get-TceObjectPropertyValue -InputObject $Process -Name 'number' -Default ''
        if ([string]::IsNullOrWhiteSpace([string]$number)) {
            $number = Get-TceObjectPropertyValue -InputObject $Process -Name 'numero' -Default ''
        }
        $year = Get-TceObjectPropertyValue -InputObject $Process -Name 'year' -Default ''
        if ([string]::IsNullOrWhiteSpace([string]$year)) {
            $year = Get-TceObjectPropertyValue -InputObject $Process -Name 'ano' -Default ''
        }
        if ([string]::IsNullOrWhiteSpace([string]$number) -or [string]::IsNullOrWhiteSpace([string]$year)) {
            throw "${Context}: chave canônica numero/ano ausente."
        }
        $rawKey = "$number/$year"
    }
    $match = [regex]::Match([string]$rawKey, '^\s*(\d+)\s*/\s*(\d{4})\s*$')
    if (-not $match.Success) { throw "${Context}: chave canônica inválida: $rawKey" }
    return '{0}/{1}' -f $match.Groups[1].Value, $match.Groups[2].Value
}

function Assert-TceCheckpointStructure {
    param(
        [Parameter(Mandatory)][object]$Checkpoint,
        [Parameter(Mandatory)][string]$Context
    )
    if ($null -eq $Checkpoint) { throw "${Context}: checkpoint vazio." }
    $processesProperty = $Checkpoint.PSObject.Properties['processes']
    $documentsProperty = $Checkpoint.PSObject.Properties['documents']
    if ($null -eq $processesProperty -or $null -eq $documentsProperty) {
        throw "${Context}: checkpoint deve conter processes e documents."
    }
    foreach ($record in @($processesProperty.Value)) {
        if ($null -eq $record -or $record -is [string]) { throw "${Context}: registro de processo inválido." }
        [void](ConvertTo-TceCanonicalProcessKey -Process $record -Context $Context)
        $status = Get-TceObjectPropertyValue -InputObject $record -Name 'status' -Default $null
        if ($null -eq $status -or [string]::IsNullOrWhiteSpace([string]$status)) {
            throw "${Context}: registro de processo sem status."
        }
    }
    foreach ($record in @($documentsProperty.Value)) {
        if ($null -eq $record -or $record -is [string]) { throw "${Context}: registro de documento inválido." }
    }
    return $Checkpoint
}

function ConvertFrom-TceCheckpointText {
    param(
        [Parameter(Mandatory)][string]$Text,
        [Parameter(Mandatory)][string]$Context
    )
    try { $checkpoint = $Text | ConvertFrom-Json }
    catch { throw "${Context}: JSON inválido: $($_.Exception.Message)" }
    return Assert-TceCheckpointStructure -Checkpoint $checkpoint -Context $Context
}

function Get-TceCheckpointFromSource {
    param([Parameter(Mandatory)][string]$Source)
    if ([string]::IsNullOrWhiteSpace($Source)) { throw 'BaseConcluidos inválida: informe um caminho.' }
    $sourceItem = Get-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
    if ($null -eq $sourceItem) { throw "BaseConcluidos inexistente: $Source" }

    if ($sourceItem.PSIsContainer) {
        $checkpointPath = Join-Path $sourceItem.FullName 'checkpoint.json'
        if (-not (Test-Path -LiteralPath $checkpointPath -PathType Leaf)) {
            throw "BaseConcluidos inválida: diretório sem checkpoint.json: $Source"
        }
        try { $text = [IO.File]::ReadAllText($checkpointPath, (New-Object Text.UTF8Encoding($false))) }
        catch { throw "BaseConcluidos inválida em ${checkpointPath}: $($_.Exception.Message)" }
        return ConvertFrom-TceCheckpointText -Text $text -Context "BaseConcluidos em $checkpointPath"
    }

    if ($sourceItem.Extension -ieq '.zip') {
        try {
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $archive = [IO.Compression.ZipFile]::OpenRead($sourceItem.FullName)
            try {
                $entries = @($archive.Entries | Where-Object { ($_.FullName -replace '\\', '/').TrimStart('/') -ieq 'acervo-tce/checkpoint.json' })
                if ($entries.Count -ne 1) { throw 'entrada acervo-tce/checkpoint.json ausente ou ambígua.' }
                $reader = New-Object IO.StreamReader($entries[0].Open(), [Text.Encoding]::UTF8, $true)
                try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
            } finally { $archive.Dispose() }
        } catch { throw "BaseConcluidos inválida em $Source (ZIP): $($_.Exception.Message)" }
        return ConvertFrom-TceCheckpointText -Text $text -Context "BaseConcluidos em $Source"
    }

    if ($sourceItem.Name -ine 'checkpoint.json') {
        throw "BaseConcluidos inválida: o arquivo deve ser checkpoint.json ou ZIP privado: $Source"
    }
    try { $text = [IO.File]::ReadAllText($sourceItem.FullName, (New-Object Text.UTF8Encoding($false))) }
    catch { throw "BaseConcluidos inválida em $Source`: $($_.Exception.Message)" }
    return ConvertFrom-TceCheckpointText -Text $text -Context "BaseConcluidos em $Source"
}

function Get-TceCompletedProcessKeys {
    param(
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [AllowEmptyString()][string]$BaseConcluidos = '',
        [switch]$BaselineAllComplete
    )
    if ($BaselineAllComplete -and [string]::IsNullOrWhiteSpace($BaseConcluidos)) {
        throw 'BaselineAllComplete exige BaseConcluidos explícita.'
    }
    $destination = Get-TceCheckpoint -ArchiveRoot $ArchiveRoot
    $destination = Assert-TceCheckpointStructure -Checkpoint $destination -Context "Checkpoint do destino $ArchiveRoot"
    $baseline = $null
    if (-not [string]::IsNullOrWhiteSpace($BaseConcluidos)) {
        $baseline = Get-TceCheckpointFromSource -Source $BaseConcluidos
    }

    $keys = New-Object System.Collections.ArrayList
    $seen = @{}
    foreach ($record in @($destination.processes)) {
        $status = Get-TceObjectPropertyValue -InputObject $record -Name 'status' -Default ''
        if ([string]$status -ine 'complete') { continue }
        $key = ConvertTo-TceCanonicalProcessKey -Process $record -Context 'checkpoint do destino'
        if (-not $seen.ContainsKey($key)) {
            $seen[$key] = $true
            [void]$keys.Add($key)
        }
    }
    if ($null -ne $baseline) {
        foreach ($record in @($baseline.processes)) {
            $status = Get-TceObjectPropertyValue -InputObject $record -Name 'status' -Default ''
            if (-not $BaselineAllComplete -and [string]$status -ine 'complete') { continue }
            $key = ConvertTo-TceCanonicalProcessKey -Process $record -Context 'BaseConcluidos'
            if (-not $seen.ContainsKey($key)) {
                $seen[$key] = $true
                [void]$keys.Add($key)
            }
        }
    }
    return @($keys.ToArray())
}

function Get-TceSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Invoke-TceDownloadBatch {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Jobs,
        [ValidateRange(1,2)][int]$MaxDownloads = 2,
        [Parameter(Mandatory)][scriptblock]$Downloader,
        [AllowNull()][object]$DownloaderContext = $null
    )
    if (-not $Jobs.Count) { return @() }

    $worker = {
        param($downloadSource, $document, $destination, $context)
        function Get-WorkerHttpStatus {
            param([AllowNull()][object]$Exception)
            if ($null -eq $Exception) { return $null }
            try {
                $response = $Exception.Response
                if ($null -ne $response) {
                    $statusProperty = $response.PSObject.Properties['StatusCode']
                    if ($null -ne $statusProperty) {
                        try { return [int]$statusProperty.Value } catch { }
                    }
                }
            } catch { }
            $message = [string]$Exception.Message
            $match = [regex]::Match($message, '(?i)(?:HTTP\s*|\()(?<status>\d{3})\b')
            if ($match.Success) { return [int]$match.Groups['status'].Value }
            return $null
        }

        function Get-WorkerRetryAfterSeconds {
            param([AllowNull()][object]$Exception)
            if ($null -eq $Exception) { return $null }
            $rawValue = $null
            try {
                $response = $Exception.Response
                if ($null -ne $response) {
                    $headersProperty = $response.PSObject.Properties['Headers']
                    if ($null -ne $headersProperty -and $null -ne $headersProperty.Value) {
                        $rawValue = [string]$headersProperty.Value['Retry-After']
                    }
                }
            } catch { }
            if ([string]::IsNullOrWhiteSpace($rawValue)) {
                try {
                    if ($null -ne $Exception.Data -and $Exception.Data.Contains('Retry-After')) {
                        $rawValue = [string]$Exception.Data['Retry-After']
                    }
                } catch { }
            }
            if ([string]::IsNullOrWhiteSpace($rawValue)) { return $null }
            $rawValue = $rawValue.Trim()
            $deltaSeconds = 0
            if ([int]::TryParse($rawValue, [Globalization.NumberStyles]::Integer, [Globalization.CultureInfo]::InvariantCulture, [ref]$deltaSeconds)) {
                if ($deltaSeconds -lt 0) { return 0 }
                return $deltaSeconds
            }
            $retryDate = [DateTimeOffset]::MinValue
            if ([DateTimeOffset]::TryParse($rawValue, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AllowWhiteSpaces, [ref]$retryDate)) {
                return [Math]::Max(0, [int][Math]::Ceiling(($retryDate - [DateTimeOffset]::UtcNow).TotalSeconds))
            }
            return $null
        }

        function ConvertTo-WorkerSafeText {
            param([AllowNull()][object]$Value)
            if ($null -eq $Value) { return '' }
            $safe = [string]$Value
            $safe = $safe -replace '(?i)\b[a-z][a-z0-9+.-]{1,31}://[^\s"''<>]+', '[URL REMOVIDA]'
            $safe = $safe -replace '(?i)\b(?:authorization|cookie|token|credential|credencial|session|senha|password)\b\s*(?:(?:[:=]\s*)|(?:\s+))(?:bearer|basic)?\s*[^,\s;|]+', '[CREDENCIAL REMOVIDA]'
            $safe = $safe -replace '(?i)\b(?:url|authorization|cookie|token|credential|credencial|session|senha|password)\b', '[DADO SENSIVEL REMOVIDO]'
            return $safe
        }

        $downloadScript = if ($downloadSource -is [scriptblock]) {
            $downloadSource
        } else {
            [scriptblock]::Create([string]$downloadSource)
        }
        $attempt = 0
        $rateLimited = $false
        $lastRetryAfterSeconds = $null
        while ($attempt -lt 3) {
            $attempt++
            try {
                if ([IO.File]::Exists([string]$destination)) {
                    Remove-Item -LiteralPath $destination -Force -ErrorAction SilentlyContinue
                }
                & $downloadScript $document $destination $context | Out-Null
                if (-not [IO.File]::Exists([string]$destination)) {
                    throw "Downloader não criou $destination"
                }
                return [pscustomobject]@{
                    success = $true; status = 'complete'; error = $null; attempts = $attempt; retry_count = $attempt - 1
                    retry_after_seconds = $lastRetryAfterSeconds; http_status = $null; auth_required = $false
                    suspended = $false; rate_limited = $rateLimited; reduce_concurrency = $rateLimited
                }
            } catch {
                $exception = $_.Exception
                $httpStatus = Get-WorkerHttpStatus -Exception $exception
                $retryAfterSeconds = Get-WorkerRetryAfterSeconds -Exception $exception
                if ($null -ne $retryAfterSeconds) { $lastRetryAfterSeconds = $retryAfterSeconds }
                $safeError = ConvertTo-WorkerSafeText $exception.Message
                try {
                    if ([IO.File]::Exists([string]$destination)) {
                        Remove-Item -LiteralPath $destination -Force -ErrorAction SilentlyContinue
                    }
                } catch { }

                if ($httpStatus -eq 429) {
                    $rateLimited = $true
                    if ($attempt -lt 3) {
                        $waitSeconds = if ($null -ne $retryAfterSeconds) { [int]$retryAfterSeconds } else { 0 }
                        if ($waitSeconds -gt 0) { Start-Sleep -Seconds $waitSeconds }
                        continue
                    }
                    return [pscustomobject]@{
                        success = $false; status = 'rate_limited'; error = $safeError; attempts = $attempt; retry_count = $attempt - 1
                        retry_after_seconds = $lastRetryAfterSeconds; http_status = $httpStatus; auth_required = $false
                        suspended = $false; rate_limited = $true; reduce_concurrency = $true
                    }
                }
                if ($httpStatus -eq 401) {
                    return [pscustomobject]@{
                        success = $false; status = 'auth_required'; error = $safeError; attempts = $attempt; retry_count = $attempt - 1
                        retry_after_seconds = $lastRetryAfterSeconds; http_status = $httpStatus; auth_required = $true
                        suspended = $false; rate_limited = $rateLimited; reduce_concurrency = $rateLimited
                    }
                }
                if ($httpStatus -eq 403) {
                    return [pscustomobject]@{
                        success = $false; status = 'suspended'; error = $safeError; attempts = $attempt; retry_count = $attempt - 1
                        retry_after_seconds = $lastRetryAfterSeconds; http_status = $httpStatus; auth_required = $false
                        suspended = $true; rate_limited = $rateLimited; reduce_concurrency = $rateLimited
                    }
                }
                return [pscustomobject]@{
                    success = $false; status = 'failed'; error = $safeError; attempts = $attempt; retry_count = $attempt - 1
                    retry_after_seconds = $lastRetryAfterSeconds; http_status = $httpStatus; auth_required = $false
                    suspended = $false; rate_limited = $rateLimited; reduce_concurrency = $rateLimited
                }
            }
        }
        return [pscustomobject]@{
            success = $false; status = 'failed'; error = 'Downloader não retornou resultado.'; attempts = $attempt
            retry_count = [Math]::Max(0, $attempt - 1); retry_after_seconds = $lastRetryAfterSeconds; http_status = $null
            auth_required = $false; suspended = $false; rate_limited = $rateLimited; reduce_concurrency = $rateLimited
        }
    }

    $effectiveMaxDownloads = [Math]::Min($MaxDownloads, [int]$script:TceDownloadMaxDownloads)
    $wrapResult = {
        param($job, $workerOutput, $effectiveLimit)
        $workerResult = @($workerOutput) | Where-Object {
            $_ -and $_.PSObject.Properties['success']
        } | Select-Object -Last 1
        if ($workerResult) {
            return [pscustomobject]@{
                job = $job; success = [bool]$workerResult.success; status = [string]$workerResult.status; error = [string]$workerResult.error
                attempts = [int]$workerResult.attempts; retry_count = [int]$workerResult.retry_count
                retry_after_seconds = $workerResult.retry_after_seconds; http_status = $workerResult.http_status
                auth_required = [bool]$workerResult.auth_required; suspended = [bool]$workerResult.suspended
                rate_limited = [bool]$workerResult.rate_limited; reduce_concurrency = [bool]$workerResult.reduce_concurrency
                effective_max_downloads = $effectiveLimit
            }
        }
        return [pscustomobject]@{
            job = $job; success = $false; status = 'failed'; error = 'Worker de download não retornou resultado.'
            attempts = 0; retry_count = 0; retry_after_seconds = $null; http_status = $null
            auth_required = $false; suspended = $false; rate_limited = $false; reduce_concurrency = $false
            effective_max_downloads = $effectiveLimit
        }
    }

    $isolatedWorker = $null -ne $DownloaderContext
    if ($effectiveMaxDownloads -eq 1 -or -not $isolatedWorker) {
        $serialResults = New-Object System.Collections.ArrayList
        foreach ($job in $Jobs) {
            $workerOutput = @(& $worker $Downloader $job.document $job.temporary $DownloaderContext)
            [void]$serialResults.Add((& $wrapResult $job $workerOutput $effectiveMaxDownloads))
        }
        if (@($serialResults | Where-Object { $_.reduce_concurrency }).Count -gt 0) {
            $script:TceDownloadMaxDownloads = 1
        }
        return @($serialResults.ToArray())
    }

    $pool = [RunspaceFactory]::CreateRunspacePool(1, $effectiveMaxDownloads)
    $pool.Open()
    $pending = New-Object System.Collections.ArrayList
    $results = New-Object System.Collections.ArrayList
    try {
        foreach ($job in $Jobs) {
            $powershell = [PowerShell]::Create()
            $powershell.RunspacePool = $pool
            [void]$powershell.AddScript($worker).
                AddArgument($Downloader.ToString()).
                AddArgument($job.document).
                AddArgument($job.temporary).
                AddArgument($DownloaderContext)
            $handle = $powershell.BeginInvoke()
            [void]$pending.Add([pscustomobject]@{
                job = $job
                powershell = $powershell
                handle = $handle
            })
        }

        foreach ($item in $pending) {
            try {
                $workerOutput = @($item.powershell.EndInvoke($item.handle))
                $workerResult = $workerOutput | Where-Object {
                    $_ -and $_.PSObject.Properties['success']
                } | Select-Object -Last 1
                if ($workerResult) {
                    [void]$results.Add((& $wrapResult $item.job @($workerResult) $effectiveMaxDownloads))
                } else {
                    [void]$results.Add((& $wrapResult $item.job @() $effectiveMaxDownloads))
                }
            } catch {
                [void]$results.Add([pscustomobject]@{
                    job = $item.job; success = $false; status = 'failed'; error = (ConvertTo-TceSafeText $_.Exception.Message)
                    attempts = 0; retry_count = 0; retry_after_seconds = $null; http_status = $null
                    auth_required = $false; suspended = $false; rate_limited = $false; reduce_concurrency = $false
                    effective_max_downloads = $effectiveMaxDownloads
                })
            } finally {
                $item.powershell.Dispose()
            }
        }
    } finally {
        $pool.Close()
        $pool.Dispose()
    }
    if (@($results | Where-Object { $_.reduce_concurrency }).Count -gt 0) {
        $script:TceDownloadMaxDownloads = 1
    }
    return @($results.ToArray())
}

function Sync-TceProcessManifest {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$ArchiveRoot,
        [ValidateRange(1,2)][int]$MaxDownloads = 2,
        [Parameter(Mandatory)][scriptblock]$Downloader,
        [AllowNull()][object]$DownloaderContext = $null
    )
    [IO.Directory]::CreateDirectory($ArchiveRoot) | Out-Null
    $checkpoint = Get-TceCheckpoint -ArchiveRoot $ArchiveRoot
    $documentRecords = New-Object System.Collections.ArrayList
    foreach ($record in @($checkpoint.documents)) { [void]$documentRecords.Add($record) }
    $processRecords = New-Object System.Collections.ArrayList
    foreach ($record in @($checkpoint.processes)) { [void]$processRecords.Add($record) }

    $existingByKey = @{}
    $existingByHash = @{}
    foreach ($record in $documentRecords) {
        $existingByKey[[string]$record.key] = $record
        if ($record.sha256 -and $record.path) { $existingByHash[[string]$record.sha256] = [string]$record.path }
    }

    $process = $Manifest.process
    $processKey = [string]$process.key
    $safeProcessFolderName = ConvertTo-TceSafeName ($processKey -replace '/', '-')
    $legacyProcessFolder = Join-Path $ArchiveRoot $safeProcessFolderName
    $newProcessRoot = Join-Path $ArchiveRoot 'processos'
    $newProcessFolder = Join-Path $newProcessRoot $safeProcessFolderName
    $processFolder = if (Test-Path -LiteralPath $legacyProcessFolder -PathType Container) {
        $legacyProcessFolder
    } else {
        $newProcessFolder
    }
    [IO.Directory]::CreateDirectory($processFolder) | Out-Null
    $downloaded = 0
    $skipped = 0
    $deduplicated = 0
    $hadErrors = $false
    $authRequired = $false
    $suspended = $false
    $rateLimited = $false
    $reduceConcurrency = [int]$script:TceDownloadMaxDownloads -lt 2
    $retryCount = 0
    $retryAfterSeconds = $null
    $httpStatuses = New-Object System.Collections.ArrayList
    $initialMaxDownloads = [Math]::Min($MaxDownloads, [int]$script:TceDownloadMaxDownloads)
    $safeEvents = New-Object System.Collections.ArrayList

    foreach ($event in @($Manifest.events | Sort-Object event, event_id)) {
        $eventNumber = [int]$event.event
        $eventId = [string]$event.event_id
        $eventFolderName = 'evento-{0:D4}-{1}' -f $eventNumber, (ConvertTo-TceSafeName $eventId)
        $eventFolder = Join-Path $processFolder $eventFolderName
        [IO.Directory]::CreateDirectory($eventFolder) | Out-Null
        $safeDocumentByOrdinal = @{}
        $downloadJobs = New-Object System.Collections.ArrayList
        $ordinal = 0

        foreach ($document in @($event.documents)) {
            $ordinal++
            $documentKey = "$processKey|$eventId|$($document.id)"
            $documentUrl = Get-TceObjectPropertyValue -InputObject $document -Name 'url' -Default ''
            if (-not $documentUrl) {
                $hadErrors = $true
                $safeError = ConvertTo-TceSafeText (Get-TceObjectPropertyValue -InputObject $document -Name 'error' -Default 'Documento indisponível.')
                $errorRecord = [pscustomobject]@{
                    key = $documentKey
                    id = [string](Get-TceObjectPropertyValue -InputObject $document -Name 'id' -Default "documento-$ordinal")
                    title = ConvertTo-TceSafeText (Get-TceObjectPropertyValue -InputObject $document -Name 'title' -Default "documento-$ordinal")
                    extension = [string](Get-TceObjectPropertyValue -InputObject $document -Name 'extension' -Default '.pdf')
                    remote_signature = ConvertTo-TceSafeText (Get-TceObjectPropertyValue -InputObject $document -Name 'remote_signature' -Default '')
                    sha256 = $null
                    path = $null
                    duplicate_of = $null
                    status = 'error'
                    error = $safeError
                }
                $safeDocumentByOrdinal[$ordinal] = $errorRecord
                continue
            }
            $safeRemoteSignature = ConvertTo-TceSafeText (Get-TceObjectPropertyValue -InputObject $document -Name 'remote_signature' -Default '')
            $known = $existingByKey[$documentKey]
            if ($known -and $known.remote_signature -eq $safeRemoteSignature -and $known.path -and (Test-Path -LiteralPath (Join-Path $ArchiveRoot $known.path))) {
                $skipped++
                $safeDocumentByOrdinal[$ordinal] = $known
                continue
            }

            $extension = [string](Get-TceObjectPropertyValue -InputObject $document -Name 'extension' -Default '.pdf')
            if (-not $extension.StartsWith('.')) { $extension = '.' + $extension }
            $rawTitle = Get-TceObjectPropertyValue -InputObject $document -Name 'title' -Default ''
            $title = if ($rawTitle) { ConvertTo-TceSafeText $rawTitle } else { "documento-$ordinal" }
            if ([string]::IsNullOrWhiteSpace($title)) { $title = "documento-$ordinal" }
            if ([IO.Path]::GetExtension($title).Equals($extension, [StringComparison]::OrdinalIgnoreCase)) {
                $title = [IO.Path]::GetFileNameWithoutExtension($title)
            }
            $fileName = 'documento-{0:D3}-{1}{2}' -f $ordinal, (ConvertTo-TceSafeName $title), $extension.ToLowerInvariant()
            $destination = Join-Path $eventFolder $fileName
            $relativePath = $destination.Substring($ArchiveRoot.TrimEnd('\').Length).TrimStart('\')
            $temporary = $destination + '.' + [guid]::NewGuid().ToString('N') + '.part'
            [void]$downloadJobs.Add([pscustomobject]@{
                ordinal = $ordinal
                document = $document
                document_key = $documentKey
                known = $known
                safe_remote_signature = $safeRemoteSignature
                extension = $extension
                title = $title
                destination = $destination
                relative_path = $relativePath
                temporary = $temporary
            })
        }

        $downloadResults = @(Invoke-TceDownloadBatch -Jobs @($downloadJobs.ToArray()) -MaxDownloads $MaxDownloads -Downloader $Downloader -DownloaderContext $DownloaderContext)
        foreach ($downloadResult in $downloadResults) {
            $job = $downloadResult.job
            $authRequired = $authRequired -or [bool]$downloadResult.auth_required
            $suspended = $suspended -or [bool]$downloadResult.suspended
            $rateLimited = $rateLimited -or [bool]$downloadResult.rate_limited
            $reduceConcurrency = $reduceConcurrency -or [bool]$downloadResult.reduce_concurrency
            $retryCount += [int]$downloadResult.retry_count
            if ($null -ne $downloadResult.retry_after_seconds) {
                if ($null -eq $retryAfterSeconds -or [int]$downloadResult.retry_after_seconds -gt $retryAfterSeconds) {
                    $retryAfterSeconds = [int]$downloadResult.retry_after_seconds
                }
            }
            if ($null -ne $downloadResult.http_status -and -not $httpStatuses.Contains([int]$downloadResult.http_status)) {
                [void]$httpStatuses.Add([int]$downloadResult.http_status)
            }
            if (-not $downloadResult.success) {
                $hadErrors = $true
                $safeDocumentByOrdinal[$job.ordinal] = [pscustomobject]@{
                    key = $job.document_key
                    id = [string](Get-TceObjectPropertyValue -InputObject $job.document -Name 'id' -Default "documento-$($job.ordinal)")
                    title = $job.title
                    extension = $job.extension
                    remote_signature = $job.safe_remote_signature
                    sha256 = $null
                    path = $null
                    duplicate_of = $null
                    status = 'error'
                    error = ConvertTo-TceSafeText ([string]$downloadResult.error)
                }
                if (Test-Path -LiteralPath $job.temporary) { Remove-Item -LiteralPath $job.temporary -Force }
                continue
            }

            try {
                if (-not (Test-Path -LiteralPath $job.temporary)) { throw "Downloader não criou $($job.temporary)" }
                $hash = Get-TceSha256 -Path $job.temporary
                $duplicateOf = $null
                $previousVersions = New-Object System.Collections.ArrayList
                if ($job.known -and $job.known.previous_versions) {
                    foreach ($version in @($job.known.previous_versions)) { [void]$previousVersions.Add($version) }
                }
                if ($existingByHash.ContainsKey($hash) -and (Test-Path -LiteralPath (Join-Path $ArchiveRoot $existingByHash[$hash]))) {
                    $duplicateOf = $existingByHash[$hash]
                    Remove-Item -LiteralPath $job.temporary -Force
                    $deduplicated++
                    $storedPath = $duplicateOf
                } else {
                    if (Test-Path -LiteralPath $job.destination) {
                        $oldHash = Get-TceSha256 -Path $job.destination
                        $oldExtension = [IO.Path]::GetExtension($job.destination)
                        $oldStem = [IO.Path]::GetFileNameWithoutExtension($job.destination)
                        $versionName = "$oldStem--versao-$($oldHash.Substring(0, 8))$oldExtension"
                        $versionPath = Join-Path (Split-Path -Parent $job.destination) $versionName
                        if (-not (Test-Path -LiteralPath $versionPath)) {
                            Move-Item -LiteralPath $job.destination -Destination $versionPath
                        }
                        $versionRelative = $versionPath.Substring($ArchiveRoot.TrimEnd('\').Length).TrimStart('\')
                        $existingByHash[$oldHash] = $versionRelative
                        [void]$previousVersions.Add([pscustomobject]@{ sha256 = $oldHash; path = $versionRelative })
                    }
                    Move-Item -LiteralPath $job.temporary -Destination $job.destination -Force
                    $storedPath = $job.relative_path
                    $existingByHash[$hash] = $storedPath
                }
                $downloaded++
                $safeRecord = [pscustomobject]@{
                    key = $job.document_key
                    id = [string]$job.document.id
                    title = $job.title
                    extension = $job.extension.ToLowerInvariant()
                    remote_signature = $job.safe_remote_signature
                    sha256 = $hash
                    path = $storedPath
                    duplicate_of = $duplicateOf
                    previous_versions = @($previousVersions)
                    status = 'complete'
                }
                if ($job.known) { [void]$documentRecords.Remove($job.known) }
                [void]$documentRecords.Add($safeRecord)
                $existingByKey[$job.document_key] = $safeRecord
                $safeDocumentByOrdinal[$job.ordinal] = $safeRecord
            } finally {
                if (Test-Path -LiteralPath $job.temporary) { Remove-Item -LiteralPath $job.temporary -Force }
            }
        }

        $safeDocuments = New-Object System.Collections.ArrayList
        foreach ($documentOrdinal in @($safeDocumentByOrdinal.Keys | Sort-Object { [int]$_ })) {
            [void]$safeDocuments.Add($safeDocumentByOrdinal[$documentOrdinal])
        }

        $safeEvent = [pscustomobject]@{
            event = $eventNumber
            event_id = $eventId
            date = [string]$event.date
            title = ConvertTo-TceSafeText (Get-TceObjectPropertyValue -InputObject $event -Name 'title' -Default '')
            active = [bool]$event.active
            documents = @($safeDocuments)
        }
        Write-TceJsonAtomic -Path (Join-Path $eventFolder 'evento.json') -Value $safeEvent
        [void]$safeEvents.Add($safeEvent)
        if ($authRequired -or $suspended) { break }
    }

    $safeProcess = [pscustomobject]@{
        key = $processKey
        id = [string]$process.id
        number = [string]$process.number
        year = [int]$process.year
        status = if ($hadErrors) { 'partial' } else { 'complete' }
        synced_at = [DateTime]::UtcNow.ToString('o')
        events = @($safeEvents)
    }
    Write-TceJsonAtomic -Path (Join-Path $processFolder 'processo.json') -Value $safeProcess

    foreach ($record in @($processRecords | Where-Object { $_.key -eq $processKey })) { [void]$processRecords.Remove($record) }
    [void]$processRecords.Add([pscustomobject]@{ key = $processKey; id = [string]$process.id; status = $safeProcess.status; synced_at = $safeProcess.synced_at })
    $safeCheckpoint = [pscustomobject]@{
        version = 1
        updated_at = [DateTime]::UtcNow.ToString('o')
        processes = @($processRecords)
        documents = @($documentRecords)
    }
    Write-TceJsonAtomic -Path (Join-Path $ArchiveRoot 'checkpoint.json') -Value $safeCheckpoint
    $controlStatus = if ($suspended) { 'suspended' } elseif ($authRequired) { 'auth_required' } elseif ($rateLimited -and $hadErrors) { 'rate_limited' } elseif ($hadErrors) { 'partial' } else { 'complete' }
    $httpStatusValue = if ($httpStatuses.Count -eq 1) { $httpStatuses[0] } else { @($httpStatuses.ToArray()) }
    return [pscustomobject]@{
        process = $processKey
        downloaded = $downloaded
        skipped = $skipped
        deduplicated = $deduplicated
        status = $controlStatus
        auth_required = $authRequired
        suspended = $suspended
        rate_limited = $rateLimited
        reduce_concurrency = $reduceConcurrency
        retry_count = $retryCount
        retry_after_seconds = $retryAfterSeconds
        http_statuses = $httpStatusValue
        max_downloads = $initialMaxDownloads
        recommended_max_downloads = [int]$script:TceDownloadMaxDownloads
    }
}

Export-ModuleMember -Function ConvertTo-TceSafeName, ConvertTo-TceSafeText, Get-TceObjectPropertyValue, Get-TceLiveDevToolsPort, Search-TceProcesses, Resolve-TceSelection, Write-TceJsonAtomic, Add-TceFailure, Get-TceCheckpoint, Get-TceCheckpointFromSource, Get-TceCompletedProcessKeys, ConvertTo-TceCanonicalProcessKey, Get-TceSha256, Sync-TceProcessManifest
