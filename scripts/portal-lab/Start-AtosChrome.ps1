[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 9222,

    [string] $ProfileRoot,

    [string] $ExtensionRoot,

    [string] $Url = 'about:blank',

    [string] $NodePath,

    [string] $PlaywrightEntry,

    [string] $BrowserCachePath,

    [switch] $PlanOnly
)

$ErrorActionPreference = 'Stop'

function Get-FullPath([string] $Path) {
    return [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path))
}

function Find-NodePlaywright {
    $nodeCandidates = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($NodePath)) { $nodeCandidates.Add($NodePath) }
    if (-not [string]::IsNullOrWhiteSpace($env:ATOS_TCE_NODE_EXE)) { $nodeCandidates.Add($env:ATOS_TCE_NODE_EXE) }
    $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($nodeCommand) { $nodeCandidates.Add($nodeCommand.Source) }
    if (-not [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
        $runtimeCache = Join-Path $env:USERPROFILE '.cache\codex-runtimes'
        if (Test-Path -LiteralPath $runtimeCache -PathType Container) {
            Get-ChildItem -LiteralPath $runtimeCache -Directory -ErrorAction SilentlyContinue | ForEach-Object {
                $nodeCandidates.Add((Join-Path $_.FullName 'dependencies\node\bin\node.exe'))
            }
        }
    }

    $explicitEntry = if ($PlaywrightEntry) { $PlaywrightEntry } else { $env:ATOS_TCE_PLAYWRIGHT_ENTRY }
    foreach ($candidate in ($nodeCandidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $fullNode = Get-FullPath $candidate
        $nodeDirectory = Split-Path -Parent $fullNode
        $nodeRoot = if ((Split-Path -Leaf $nodeDirectory) -ieq 'bin') {
            Split-Path -Parent $nodeDirectory
        } else {
            $nodeDirectory
        }
        $entryCandidates = @()
        if (-not [string]::IsNullOrWhiteSpace($explicitEntry)) { $entryCandidates += $explicitEntry }
        $entryCandidates += (Join-Path $nodeRoot 'node_modules\playwright\index.mjs')
        $entryCandidates += (Join-Path $nodeRoot 'node_modules\playwright\index.js')
        foreach ($entry in $entryCandidates) {
            if (Test-Path -LiteralPath $entry -PathType Leaf) {
                return [pscustomobject]@{
                    NodePath = $fullNode
                    PlaywrightEntry = (Get-FullPath $entry)
                }
            }
        }
    }
    return $null
}

$repositoryRoot = Get-FullPath (Join-Path $PSScriptRoot '..\..')
if ([string]::IsNullOrWhiteSpace($ProfileRoot)) {
    $ProfileRoot = Join-Path $env:LOCALAPPDATA 'Atos-TCE\Chrome-QA-Playwright'
}
if ([string]::IsNullOrWhiteSpace($ExtensionRoot)) {
    $ExtensionRoot = Join-Path $repositoryRoot 'extension'
}
$profileFullPath = Get-FullPath $ProfileRoot
$extensionFullPath = Get-FullPath $ExtensionRoot
$runnerPath = Get-FullPath (Join-Path $PSScriptRoot 'launch-qa-chromium.mjs')
$repositoryPrefix = $repositoryRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($profileFullPath.Equals($repositoryRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $profileFullPath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'ProfileRoot must be outside the repository so browser data cannot enter the package.'
}
if (-not (Test-Path -LiteralPath (Join-Path $extensionFullPath 'manifest.json') -PathType Leaf)) {
    throw "Unpacked extension manifest was not found under: $extensionFullPath"
}
if (-not (Test-Path -LiteralPath $runnerPath -PathType Leaf)) {
    throw "QA Chromium runner was not found: $runnerPath"
}

$dependencies = Find-NodePlaywright
if (-not $dependencies) {
    $dependencies = [pscustomobject]@{
        NodePath = $NodePath
        PlaywrightEntry = $(if ($PlaywrightEntry) { Get-FullPath $PlaywrightEntry } else { $env:ATOS_TCE_PLAYWRIGHT_ENTRY })
    }
}
if ([string]::IsNullOrWhiteSpace($BrowserCachePath)) {
    $BrowserCachePath = if ($env:PLAYWRIGHT_BROWSERS_PATH) {
        $env:PLAYWRIGHT_BROWSERS_PATH
    } else {
        Join-Path $env:LOCALAPPDATA 'ms-playwright'
    }
}
$browserCacheFullPath = Get-FullPath $BrowserCachePath
$launchArguments = @(
    '--extension-root', $extensionFullPath,
    '--profile-root', $profileFullPath,
    '--port', [string]$Port,
    '--url', $Url,
    '--playwright-entry', [string]$dependencies.PlaywrightEntry
)

$launchPlan = [ordered]@{
    browserEngine = 'playwright-chromium'
    nodePath = $dependencies.NodePath
    playwrightEntry = $dependencies.PlaywrightEntry
    runnerPath = $runnerPath
    extensionRoot = $extensionFullPath
    profileRoot = $profileFullPath
    browserCachePath = $browserCacheFullPath
    port = $Port
    devToolsUrl = "http://127.0.0.1:$Port"
    url = $Url
    arguments = $launchArguments
}

if ($PlanOnly) {
    $launchPlan | ConvertTo-Json -Compress -Depth 4
    return
}
if ([string]::IsNullOrWhiteSpace($dependencies.NodePath) -or
    -not (Test-Path -LiteralPath $dependencies.NodePath -PathType Leaf)) {
    throw 'Node.js was not found. Set ATOS_TCE_NODE_EXE or pass -NodePath.'
}
if ([string]::IsNullOrWhiteSpace($dependencies.PlaywrightEntry) -or
    -not (Test-Path -LiteralPath $dependencies.PlaywrightEntry -PathType Leaf)) {
    throw 'Playwright was not found. Set ATOS_TCE_PLAYWRIGHT_ENTRY or pass -PlaywrightEntry.'
}
if (-not (Test-Path -LiteralPath $browserCacheFullPath -PathType Container)) {
    throw "Playwright browser cache is missing: $browserCacheFullPath"
}

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
try {
    $listener.Start()
} catch {
    throw "Loopback port $Port is already in use. Existing processes were not changed."
} finally {
    $listener.Stop()
}

if (-not (Test-Path -LiteralPath $profileFullPath -PathType Container)) {
    New-Item -ItemType Directory -Path $profileFullPath -Force | Out-Null
}

$oldBrowserCachePath = $env:PLAYWRIGHT_BROWSERS_PATH
try {
    $env:PLAYWRIGHT_BROWSERS_PATH = $browserCacheFullPath
    & $dependencies.NodePath $runnerPath @launchArguments
    if ($LASTEXITCODE -ne 0) {
        throw "QA Chromium runner exited with code $LASTEXITCODE."
    }
} finally {
    $env:PLAYWRIGHT_BROWSERS_PATH = $oldBrowserCachePath
}
