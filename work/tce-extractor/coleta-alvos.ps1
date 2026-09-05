param(
    [string]$PendingManifest = (Join-Path $PSScriptRoot '..\tce-downloads\pending-urls.json'),
    [string]$Root = (Join-Path $PSScriptRoot '..\tce-downloads')
)

$pending = [IO.Path]::GetFullPath($PendingManifest)
$collectionRoot = [IO.Path]::GetFullPath($Root)

if (-not (Test-Path -LiteralPath $pending -PathType Leaf)) {
    throw "Manifesto temporário de URLs não encontrado: $pending"
}

& python (Join-Path $PSScriptRoot 'targeted_collection.py') `
    --manifest $pending `
    --output-dir (Join-Path $collectionRoot 'alvos-organizados') `
    --checkpoint (Join-Path $collectionRoot 'coleta-alvos-checkpoint.json') `
    --target-manifest (Join-Path $collectionRoot 'alvos-manifest.json')

if ($LASTEXITCODE -ne 0) {
    throw "A coleta seletiva falhou (código $LASTEXITCODE). O manifesto temporário foi preservado para retomada."
}

Remove-Item -LiteralPath $pending -Force

