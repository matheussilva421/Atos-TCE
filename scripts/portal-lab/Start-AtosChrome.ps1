[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 9222,

    [string] $ProfileRoot = (Join-Path $env:LOCALAPPDATA 'Atos-TCE\Chrome-Debug'),

    [string] $ChromePath
)

$ErrorActionPreference = 'Stop'

function Get-FullPath([string] $Path) {
    return [System.IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Path))
}

$repositoryRoot = Get-FullPath (Join-Path $PSScriptRoot '..\..')
$profileFullPath = Get-FullPath $ProfileRoot
$repositoryPrefix = $repositoryRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($profileFullPath.Equals($repositoryRoot, [StringComparison]::OrdinalIgnoreCase) -or
    $profileFullPath.StartsWith($repositoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'ProfileRoot must be outside the repository.'
}

if ([string]::IsNullOrWhiteSpace($ChromePath)) {
    $chromeCandidates = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $ChromePath = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}

if ([string]::IsNullOrWhiteSpace($ChromePath) -or -not (Test-Path -LiteralPath $ChromePath -PathType Leaf)) {
    throw 'Chrome executable was not found.'
}
$chromeFullPath = Get-FullPath $ChromePath

$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
try {
    $listener.Start()
}
catch {
    throw "Loopback port $Port is already in use or unavailable. Existing processes were not changed."
}
finally {
    if ($listener) { $listener.Stop() }
}

$arguments = @(
    '--remote-debugging-address=127.0.0.1',
    "--remote-debugging-port=$Port",
    "--user-data-dir=`"$profileFullPath`"",
    '--no-first-run',
    '--no-default-browser-check'
)

$launchPlan = [ordered]@{
    executable = $chromeFullPath
    port = $Port
    profileRoot = $profileFullPath
    arguments = $arguments
}

if ($WhatIfPreference) {
    $launchPlan | ConvertTo-Json -Compress -Depth 3
    return
}

if ($PSCmdlet.ShouldProcess("Chrome on 127.0.0.1:$Port", 'Start with an isolated profile')) {
    if (-not (Test-Path -LiteralPath $profileFullPath -PathType Container)) {
        New-Item -ItemType Directory -Path $profileFullPath -Force | Out-Null
    }
    $process = Start-Process -FilePath $chromeFullPath -ArgumentList $arguments -WindowStyle Normal -PassThru
    [pscustomobject]@{
        status = 'CHROME_STARTED'
        processId = $process.Id
        port = $Port
        profileRoot = $profileFullPath
    }
}
