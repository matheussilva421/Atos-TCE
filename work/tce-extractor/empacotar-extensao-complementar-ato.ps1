[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$projectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$extensionRoot = Join-Path $projectRoot 'portable\extensao-complementar-ato'
$outputZip = [IO.Path]::GetFullPath($OutputPath)
$outputParent = Split-Path -Parent $outputZip
$runId = [guid]::NewGuid().ToString('N')
$stage = Join-Path $projectRoot ('.extension-staging-' + $runId)
$temporaryZip = Join-Path $outputParent ('.' + [IO.Path]::GetFileName($outputZip) + '.' + $runId + '.tmp.zip')

$EXTENSION_FILE_ALLOWLIST = @(
    'manifest.json',
    'background/service-worker.js',
    'content/form-detector.js',
    'lib/bridge-client.js',
    'lib/matcher.js',
    'lib/messages.js',
    'lib/normalizer.js',
    'lib/schema.js',
    'sidepanel/panel.css',
    'sidepanel/panel.html',
    'sidepanel/panel.js'
)

function Assert-NoReparsePoint {
    param([Parameter(Mandatory)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Reparse point não permitido: $Path"
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory)][string]$Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        return (($algorithm.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) -join '').ToUpperInvariant()
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

try {
    if (-not (Test-Path -LiteralPath $extensionRoot -PathType Container)) {
        throw "Pasta da extensão não encontrada: $extensionRoot"
    }
    if ((Test-Path -LiteralPath $outputZip -PathType Leaf) -and -not $Force) {
        throw "ZIP existente; use -Force para substituir explicitamente: $outputZip"
    }
    [IO.Directory]::CreateDirectory($outputParent) | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $stage 'extensao-complementar-ato') -Force | Out-Null

    foreach ($relative in $EXTENSION_FILE_ALLOWLIST) {
        $source = Join-Path $extensionRoot ($relative -replace '/', '\')
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Arquivo da extensão ausente: $source"
        }
        Assert-NoReparsePoint -Path $source
        $destination = Join-Path (Join-Path $stage 'extensao-complementar-ato') ($relative -replace '/', '\')
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $temporaryZip -CompressionLevel Optimal
    $archive = [IO.Compression.ZipFile]::OpenRead($temporaryZip)
    try {
        $actual = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') } | Sort-Object)
        $expected = @($EXTENSION_FILE_ALLOWLIST | ForEach-Object { 'extensao-complementar-ato/' + $_ } | Sort-Object)
        if (($actual -join "`n") -cne ($expected -join "`n")) {
            throw "ZIP da extensão contém arquivos inesperados ou ausentes"
        }
    }
    finally {
        $archive.Dispose()
    }

    Move-Item -LiteralPath $temporaryZip -Destination $outputZip -Force
    $hash = Get-Sha256 -Path $outputZip
    [pscustomobject]@{
        zip = $outputZip
        files = $EXTENSION_FILE_ALLOWLIST.Count
        sha256 = $hash
    } | ConvertTo-Json -Compress
}
finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    if (Test-Path -LiteralPath $temporaryZip) { Remove-Item -LiteralPath $temporaryZip -Force }
}
