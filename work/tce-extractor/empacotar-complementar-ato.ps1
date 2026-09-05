param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$manifest = Join-Path $workspaceRoot 'outputs\pdfs-alvo-manifest.json'
$checkpoint = Join-Path $workspaceRoot 'outputs\extracao-checkpoint.json'
$sourceDoc = Join-Path $workspaceRoot 'outputs\doc.md'
$sourceSummary = Join-Path $workspaceRoot 'outputs\coleta-pdfs-resumo.md'
$sourceHandoff = Join-Path $workspaceRoot 'outputs\2026-09-02-tce-extrator-handoff.md'
$generator = Join-Path $PSScriptRoot 'html_generator.py'
$portableReadme = Join-Path $PSScriptRoot 'README-PORTATIL.md'
$outputZip = Join-Path $workspaceRoot 'outputs\tce-complementar-ato-portatil.zip'
$staging = Join-Path $workspaceRoot ("work\pacote-tce-" + [guid]::NewGuid().ToString('N'))
$temporaryZip = Join-Path $workspaceRoot ("outputs\.tce-complementar-ato-portatil-" + [guid]::NewGuid().ToString('N') + '.tmp.zip')

try {
    foreach ($required in @($manifest, $checkpoint, $sourceDoc, $sourceSummary, $sourceHandoff, $generator, $portableReadme)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Arquivo obrigatório não existe: $required"
        }
    }
    if ((Test-Path -LiteralPath $outputZip) -and -not $Force) {
        throw "O ZIP de destino já existe; remova-o ou escolha outro nome: $outputZip"
    }

    New-Item -ItemType Directory -Path $staging | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging 'pdfs') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging 'referencia') | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $staging 'codigo') | Out-Null

    $portableHtml = Join-Path $staging 'complementar-ato.html'
    & python $generator `
        --manifest $manifest `
        --checkpoint $checkpoint `
        --output $portableHtml `
        --pdf-link-root 'pdfs'
    if ($LASTEXITCODE -ne 0) {
        throw "A geração do HTML portátil falhou (código $LASTEXITCODE)."
    }

    $manifestData = Get-Content -LiteralPath $manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $pdfCount = 0
    foreach ($entry in @($manifestData.processes)) {
        $process = [string]$entry.process
        $folderName = $process -replace '/', '-'
        $destinationFolder = Join-Path $staging ("pdfs\$folderName")
        New-Item -ItemType Directory -Force -Path $destinationFolder | Out-Null
        foreach ($document in @($entry.documents)) {
            $source = [string]$document.pdf_path
            if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
                throw "PDF do manifesto não existe: $source"
            }
            $destination = Join-Path $destinationFolder ([IO.Path]::GetFileName($source))
            Copy-Item -LiteralPath $source -Destination $destination -Force
            $pdfCount++
        }
    }

    Copy-Item -LiteralPath $portableReadme -Destination (Join-Path $staging 'README-USO.md')
    Copy-Item -LiteralPath $sourceDoc -Destination (Join-Path $staging 'referencia\doc.md')
    Copy-Item -LiteralPath $checkpoint -Destination (Join-Path $staging 'referencia\extracao-checkpoint.json')
    Copy-Item -LiteralPath $sourceSummary -Destination (Join-Path $staging 'referencia\coleta-pdfs-resumo.md')
    Copy-Item -LiteralPath $sourceHandoff -Destination (Join-Path $staging 'referencia\handoff.md')
    Copy-Item -LiteralPath $generator -Destination (Join-Path $staging 'codigo\html_generator.py')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination (Join-Path $staging 'codigo\README-extrator.md')

    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $temporaryZip -CompressionLevel Optimal
    Move-Item -LiteralPath $temporaryZip -Destination $outputZip -Force
    $zipInfo = Get-Item -LiteralPath $outputZip
    [pscustomobject]@{
        zip = $zipInfo.FullName
        bytes = $zipInfo.Length
        processes = @($manifestData.processes).Count
        pdfs = $pdfCount
    } | ConvertTo-Json -Compress
}
finally {
    if ($staging -and (Test-Path -LiteralPath $staging)) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
    if ($temporaryZip -and (Test-Path -LiteralPath $temporaryZip)) {
        Remove-Item -LiteralPath $temporaryZip -Force
    }
}
