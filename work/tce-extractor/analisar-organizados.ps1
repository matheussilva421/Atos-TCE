param(
    [string]$Root = (Join-Path (Split-Path -Parent $PSScriptRoot) 'tce-downloads')
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$manifest = Join-Path $workspaceRoot 'outputs\pdfs-alvo-manifest.json'
$output = Join-Path $workspaceRoot 'outputs\doc.md'
$checkpoint = Join-Path $workspaceRoot 'outputs\extracao-checkpoint.json'
$tesseract = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
$tessdata = Join-Path $workspaceRoot 'work\tessdata'

python (Join-Path $PSScriptRoot 'batch_runner.py') `
    --manifest $manifest `
    --output $output `
    --checkpoint $checkpoint `
    --tesseract $tesseract `
    --tessdata-dir $tessdata

if ($LASTEXITCODE -ne 0) {
    throw "A análise dos PDFs falhou (código $LASTEXITCODE)."
}
