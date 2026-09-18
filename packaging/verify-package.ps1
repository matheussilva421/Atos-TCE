[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ZipPath,
    [switch]$AllowMissingRuntime,
    [switch]$SkipSmoke,
    [string]$ExtractRoot,
    [int]$HealthTimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$RepositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

# The standard portable ZIP carries the application, the extension, the fixed
# runtime and the licences. It never carries private archive data, browser
# profiles, tokens or build scratch.
$forbiddenPrefixes = @(
    'data/',
    'acervo-tce/',
    'dados-locais/',
    'profile/',
    'outputs/',
    'versions/',
    'work/',
    'logs/'
)
$forbiddenSuffixes = @(
    '.pdf',
    '.db',
    '.sqlite',
    '.sqlite3',
    '.db-wal',
    '.db-shm',
    '.har',
    '.trace',
    '.part',
    '.tmp',
    '.pyc',
    '.pyo',
    '.log'
)
$requiredEntries = @(
    'app/main.py',
    'app/core/store.py',
    'extension/manifest.json',
    'START.cmd',
    'README.md'
)
$runtimeRequiredEntries = @(
    'runtime-manifest.json',
    'runtime/python/python.exe',
    'licenses/README.md'
)

function Get-NormalizedEntryName {
    param([Parameter(Mandatory)][string]$Name)
    return ($Name.Replace('\', '/').TrimStart('/'))
}

function Get-EntrySha256 {
    param(
        [Parameter(Mandatory)][System.IO.Compression.ZipArchiveEntry]$Entry
    )
    $stream = $Entry.Open()
    try {
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $hash = $algorithm.ComputeHash($stream)
        } finally {
            $algorithm.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    return ([BitConverter]::ToString($hash)).Replace('-', '').ToLowerInvariant()
}

function Stop-SmokeProcess {
    param([Parameter(Mandatory)][System.Diagnostics.Process]$Process)
    try {
        if (-not $Process.HasExited) {
            # START.cmd starts cmd.exe, which starts the packaged interpreter:
            # only the whole tree can be stopped, or the service outlives the test.
            $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
            & $taskkill /PID $Process.Id /T /F 2>&1 | Out-Null
        }
        $Process.WaitForExit(15000) | Out-Null
    } catch {
        Write-Warning "Falha ao encerrar o processo do smoke: $($_.Exception.Message)"
    }
}

function Get-FreeLoopbackPort {
    # The packaged service prints its port to a buffered stdout when the smoke
    # redirects it, so the verifier chooses the port and probes health instead.
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    try {
        return ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    } finally {
        $listener.Stop()
    }
}

function Get-LogTail {
    param([Parameter(Mandatory)][string]$Path)
    if (Test-Path -LiteralPath $Path -PathType Leaf) {
        $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
        if (-not [string]::IsNullOrWhiteSpace($content)) { return $content.Trim() }
    }
    return ''
}

function Invoke-PackageSmoke {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][string]$DestinationRoot,
        [Parameter(Mandatory)][int]$TimeoutSeconds
    )

    if (Test-Path -LiteralPath $DestinationRoot) {
        throw "Extração de smoke já existe; remova ou escolha outro caminho: $DestinationRoot"
    }
    [IO.Directory]::CreateDirectory($DestinationRoot) | Out-Null
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $DestinationRoot -Force

    $launcher = Join-Path $DestinationRoot 'START.cmd'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "Pacote extraído sem START.cmd: $DestinationRoot"
    }
    $extensionManifest = Join-Path $DestinationRoot 'extension\manifest.json'
    if (-not (Test-Path -LiteralPath $extensionManifest -PathType Leaf)) {
        throw "Pacote extraído sem extension/manifest.json: $DestinationRoot"
    }
    $extensionIdentity = Get-Content -LiteralPath $extensionManifest -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$extensionIdentity.manifest_version -ne 3) {
        throw "Extensão empacotada não é Manifest V3: $extensionManifest"
    }

    $dataRoot = Join-Path $DestinationRoot 'smoke-data'
    $stdoutLog = Join-Path $DestinationRoot 'smoke-stdout.log'
    $stderrLog = Join-Path $DestinationRoot 'smoke-stderr.log'
    $port = Get-FreeLoopbackPort
    $arguments = @(
        '--data-root', ('"' + $dataRoot + '"'),
        '--port', [string]$port,
        '--no-browser'
    )
    $process = Start-Process -FilePath $launcher -ArgumentList $arguments -WorkingDirectory $DestinationRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $health = $null
    try {
        while ((Get-Date) -lt $deadline) {
            if ($process.HasExited) {
                $tail = (Get-LogTail -Path $stderrLog) + (Get-LogTail -Path $stdoutLog)
                throw "Serviço empacotado encerrou antes de responder na porta $port (exit $($process.ExitCode)): $tail"
            }
            try {
                $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/v1/health" -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) {
                    $health = $response.Content | ConvertFrom-Json
                    break
                }
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
        if ($null -eq $health) {
            $tail = (Get-LogTail -Path $stderrLog) + (Get-LogTail -Path $stdoutLog)
            throw "Serviço empacotado não respondeu /api/v1/health em $TimeoutSeconds s na porta ${port}: $tail"
        }

        $database = Join-Path $dataRoot 'atos-tce.db'
        if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
            throw "Smoke não criou o banco em raiz de dados isolada: $database"
        }
    } finally {
        Stop-SmokeProcess -Process $process
    }

    return [pscustomobject]@{
        extract_root = $DestinationRoot
        port = $port
        database = $database
        health = $health
        extension_version = [string]$extensionIdentity.version
    }
}

$zipFullPath = (Resolve-Path -LiteralPath $ZipPath -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $zipFullPath -PathType Leaf)) {
    throw "Pacote ausente: $zipFullPath"
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($zipFullPath)
$smokeRoot = $null
$smokeResult = $null
try {
    $entries = @{}
    $forbidden = New-Object System.Collections.ArrayList
    foreach ($entry in $archive.Entries) {
        $name = Get-NormalizedEntryName -Name $entry.FullName
        if ([string]::IsNullOrWhiteSpace($name)) { continue }
        if (-not $entries.ContainsKey($name)) {
            $entries[$name] = $entry
        }
        $lower = $name.ToLowerInvariant()
        foreach ($prefix in $forbiddenPrefixes) {
            if ($lower.StartsWith($prefix)) {
                [void]$forbidden.Add("prefixo proibido ${prefix}: $name")
            }
        }
        foreach ($suffix in $forbiddenSuffixes) {
            if ($lower.EndsWith($suffix)) {
                [void]$forbidden.Add("extensão proibida ${suffix}: $name")
            }
        }
        if ($lower -match '(^|/)__pycache__(/|$)') {
            [void]$forbidden.Add("bytecode compilado no pacote: $name")
        }
    }
    if ($forbidden.Count -gt 0) {
        throw ("Allowlist do pacote violada: `n  " + (($forbidden | Select-Object -First 10) -join "`n  "))
    }

    $missing = @($requiredEntries | Where-Object { -not $entries.ContainsKey($_) })
    if ($missing.Count -gt 0) {
        throw "Pacote sem arquivos obrigatórios: $($missing -join ', ')"
    }

    $launcherEntry = $entries['START.cmd']
    $launcherStream = $launcherEntry.Open()
    try {
        $reader = New-Object IO.StreamReader($launcherStream)
        try { $launcherText = $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally {
        $launcherStream.Dispose()
    }
    if ($launcherText -notmatch 'app\.main') {
        throw 'START.cmd empacotado não inicia app.main'
    }

    $runtimeIncluded = $entries.ContainsKey('runtime-manifest.json')
    $runtimeEntryCount = 0
    if ($runtimeIncluded) {
        $missingRuntime = @($runtimeRequiredEntries | Where-Object { -not $entries.ContainsKey($_) })
        if ($missingRuntime.Count -gt 0) {
            throw "Pacote com runtime-manifest.json mas sem arquivos obrigatórios do runtime: $($missingRuntime -join ', ')"
        }
        $runtimeManifestEntry = $entries['runtime-manifest.json']
        $manifestStream = $runtimeManifestEntry.Open()
        try {
            $manifestReader = New-Object IO.StreamReader($manifestStream)
            try { $runtimeManifestText = $manifestReader.ReadToEnd() } finally { $manifestReader.Dispose() }
        } finally {
            $manifestStream.Dispose()
        }
        $runtimeManifest = $runtimeManifestText | ConvertFrom-Json
        $declared = @($runtimeManifest.build.included_files)
        if ($declared.Count -eq 0) {
            throw 'runtime-manifest.json empacotado não declara build.included_files'
        }
        $declaredPaths = @{}
        foreach ($item in $declared) {
            $declaredPath = Get-NormalizedEntryName -Name ([string]$item.path)
            if ($declaredPaths.ContainsKey($declaredPath)) { continue }
            $declaredPaths[$declaredPath] = $true
            if (-not $entries.ContainsKey($declaredPath)) {
                throw "Arquivo declarado no runtime-manifest.json está ausente do pacote: $declaredPath"
            }
            $declaredEntry = $entries[$declaredPath]
            if ([long]$item.size -ne [long]$declaredEntry.Length) {
                throw "Tamanho divergente no pacote para ${declaredPath}: manifesto $($item.size), pacote $($declaredEntry.Length)"
            }
            $actualHash = Get-EntrySha256 -Entry $declaredEntry
            if ($actualHash -ne ([string]$item.sha256).ToLowerInvariant()) {
                throw "SHA-256 divergente no pacote para ${declaredPath}: manifesto $($item.sha256), pacote $actualHash"
            }
        }
        foreach ($name in $entries.Keys) {
            $lower = $name.ToLowerInvariant()
            if (-not ($lower.StartsWith('runtime/') -or $lower.StartsWith('licenses/'))) { continue }
            if ($lower -eq 'runtime-manifest.json') { continue }
            if (-not $declaredPaths.ContainsKey($name)) {
                throw "Arquivo de runtime/licença não declarado no runtime-manifest.json: $name"
            }
        }
        $runtimeEntryCount = $declaredPaths.Count
    } elseif (-not $AllowMissingRuntime) {
        throw 'Pacote sem runtime: runtime-manifest.json ausente (use -AllowMissingRuntime somente para fixtures de contrato)'
    }

    if (-not $SkipSmoke) {
        if ([string]::IsNullOrWhiteSpace($ExtractRoot)) {
            $smokeRoot = Join-Path $RepositoryRoot ('tmp\package-test-' + [guid]::NewGuid().ToString('N'))
        } else {
            $smokeRoot = [IO.Path]::GetFullPath($ExtractRoot)
        }
    }
} finally {
    $archive.Dispose()
}

if (-not $SkipSmoke) {
    try {
        $smokeResult = Invoke-PackageSmoke -ArchivePath $zipFullPath -DestinationRoot $smokeRoot -TimeoutSeconds $HealthTimeoutSeconds
    } catch {
        Write-Host "Smoke falhou; extração preservada em $smokeRoot"
        throw
    }
    try {
        Remove-Item -LiteralPath $smokeRoot -Recurse -Force -ErrorAction Stop
    } catch {
        throw "Smoke passou, mas a extração não pôde ser removida ($smokeRoot): $($_.Exception.Message)"
    }
}

$summary = [pscustomobject]@{
    zip = $zipFullPath
    entries = $entries.Count
    runtime_included = $runtimeIncluded
    runtime_files = $runtimeEntryCount
    smoke = if ($null -eq $smokeResult) { $null } else { $smokeResult }
}
$summary | ConvertTo-Json -Depth 8
