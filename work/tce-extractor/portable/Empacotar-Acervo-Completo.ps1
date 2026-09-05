param(
    [Parameter(Mandatory = $true)]
    [string]$Destino,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$portableRoot = $PSScriptRoot
$python = Join-Path $portableRoot 'runtime\python\python.exe'
$packager = Join-Path $portableRoot 'app\package_complete_archive.py'
$archiveRoot = Join-Path $portableRoot 'acervo-tce'
$extensionData = Join-Path $archiveRoot 'dados-complementar-ato.json'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python portátil não encontrado: $python"
}
if (-not (Test-Path -LiteralPath $packager -PathType Leaf)) {
    throw "Empacotador não encontrado: $packager"
}
if (-not (Test-Path -LiteralPath $archiveRoot -PathType Container)) {
    throw "Acervo local não encontrado: $archiveRoot"
}
if (-not (Test-Path -LiteralPath $extensionData -PathType Leaf)) {
    throw "Dados da extensão não encontrados no acervo privado: $extensionData"
}

$arguments = @(
    $packager,
    '--source', $portableRoot,
    '--output', $Destino
)
if ($Force) {
    $arguments += '--force'
}
$arguments += '--distribution', 'private'

& $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "A criação do ZIP falhou (código $LASTEXITCODE)."
}
