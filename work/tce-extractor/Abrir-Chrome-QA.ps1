[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Url = 'about:blank',
    [string]$ChromePath = '',
    [switch]$PlanOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$extensionRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'portable\extensao-complementar-ato'))
$profileRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'dados-locais\chrome-qa-profile'))
$devToolsPort = 9222

if (-not (Test-Path -LiteralPath $extensionRoot -PathType Container)) {
    throw "Extensão de QA não encontrada: $extensionRoot"
}

if ([string]::IsNullOrWhiteSpace($ChromePath)) {
    $chromeCandidates = @(
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    )
    $ChromePath = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($ChromePath)) {
        $appPathKeys = @(
            'HKCU:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
            'HKLM:\Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe',
            'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'
        )
        foreach ($key in $appPathKeys) {
            if (-not (Test-Path -LiteralPath $key)) { continue }
            $candidate = (Get-Item -LiteralPath $key).GetValue('')
            if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
                $ChromePath = $candidate
                break
            }
        }
    }
}

if ([string]::IsNullOrWhiteSpace($ChromePath) -or -not (Test-Path -LiteralPath $ChromePath -PathType Leaf)) {
    throw 'Google Chrome não encontrado. Instale o Chrome ou informe -ChromePath com o caminho de chrome.exe.'
}

$launchArguments = @(
    "--user-data-dir=$profileRoot",
    "--remote-debugging-address=127.0.0.1",
    "--remote-debugging-port=$devToolsPort",
    "--disable-extensions-except=$extensionRoot",
    "--load-extension=$extensionRoot",
    '--auto-open-devtools-for-tabs',
    '--no-first-run',
    '--no-default-browser-check',
    '--new-window',
    $Url
)

$plan = [pscustomobject]@{
    chromePath = [IO.Path]::GetFullPath($ChromePath)
    profilePath = $profileRoot
    extensionPath = $extensionRoot
    devToolsUrl = "http://127.0.0.1:$devToolsPort"
    arguments = $launchArguments
}

if ($PlanOnly) {
    ConvertTo-Json -InputObject $plan -Compress -Depth 5
    return
}

$qaProcesses = @(
    Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and
            $_.CommandLine.IndexOf($profileRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
        }
)
$qaDebugProcesses = @(
    $qaProcesses | Where-Object {
        $_.CommandLine -match "--remote-debugging-port(?:=|\s+)$devToolsPort(?:\s|$)"
    }
)

$debugEndpoint = $null
try {
    $debugEndpoint = Invoke-RestMethod -Uri "$($plan.devToolsUrl)/json/version" -TimeoutSec 2
} catch {
    $debugEndpoint = $null
}

if ($qaProcesses.Count -gt 0) {
    if ($qaDebugProcesses.Count -gt 0 -and $debugEndpoint -and $debugEndpoint.webSocketDebuggerUrl) {
        Write-Host "Chrome QA já está aberto. DevTools remoto: $($plan.devToolsUrl)"
        return
    }
    throw 'O perfil Chrome QA já está aberto sem DevTools ativo. Feche as janelas desse perfil e execute o .bat novamente.'
}

$tcpProbe = New-Object System.Net.Sockets.TcpClient
$portInUse = $false
try {
    $connect = $tcpProbe.BeginConnect([Net.IPAddress]::Loopback, $devToolsPort, $null, $null)
    if ($connect.AsyncWaitHandle.WaitOne(500)) {
        try {
            $tcpProbe.EndConnect($connect)
            $portInUse = $true
        } catch {
            $portInUse = $false
        }
    }
    $connect.AsyncWaitHandle.Close()
} finally {
    $tcpProbe.Dispose()
}

if ($portInUse) {
    throw "A porta DevTools $devToolsPort já está ocupada por outro processo. Feche o processo ou libere a porta antes de abrir o Chrome QA."
}

$null = New-Item -ItemType Directory -Path $profileRoot -Force
$argumentLine = ($launchArguments | ForEach-Object {
    $argument = [string]$_
    if ($argument -match '[\s"]') { '"' + $argument.Replace('"', '\"') + '"' } else { $argument }
}) -join ' '

Start-Process -FilePath $plan.chromePath -ArgumentList $argumentLine -WorkingDirectory $repoRoot | Out-Null
Write-Host 'Chrome QA iniciado com a extensão local e o painel DevTools.'
Write-Host "Perfil isolado: $profileRoot"
Write-Host "CDP local: $($plan.devToolsUrl)"
