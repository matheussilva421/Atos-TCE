param(
    [Parameter(Mandatory = $true)]
    [string]$Incoming,
    [string]$Root = (Join-Path (Split-Path -Parent $PSScriptRoot) 'tce-downloads')
)

$ErrorActionPreference = 'Stop'
$organized = Join-Path $Root 'pdfs-organizados'
$manifest = Join-Path $Root 'manifest.json'
$processList = Join-Path $PSScriptRoot 'processos-61.json'

python (Join-Path $PSScriptRoot 'organize_pdfs.py') `
    --incoming $Incoming `
    --organized $organized `
    --manifest $manifest `
    --process-list $processList

if ($LASTEXITCODE -ne 0) {
    throw "A organização dos PDFs falhou (código $LASTEXITCODE)."
}

Write-Host "Manifesto: $manifest"
Write-Host "PDFs organizados: $organized"
