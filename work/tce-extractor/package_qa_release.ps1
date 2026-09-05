param([switch]$Build)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$projectRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$outputRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '..\..\outputs'))
$baseRoot = Join-Path $outputRoot 'TCE-Atos-Novos-43-COM-GUIA-2026-09-05'
$releaseRoot = Join-Path $outputRoot 'TCE-Atos-CORRIGIDO-QA-2026-09-05'
if (-not $Build) { Write-Output "Dry run. Source: $baseRoot; new release: $releaseRoot"; exit 0 }
if (Test-Path -LiteralPath $releaseRoot) { throw 'Release directory already exists; no overwrite permitted.' }
if (-not (Test-Path -LiteralPath (Join-Path $baseRoot 'acervo-tce\dados-complementar-ato.json'))) { throw 'Verified base archive missing.' }
[IO.Directory]::CreateDirectory($releaseRoot) | Out-Null
foreach ($item in Get-ChildItem -LiteralPath $baseRoot -Force) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Base contains reparse point.' }
    Copy-Item -LiteralPath $item.FullName -Destination $releaseRoot -Recurse
}
$portableRoot = Join-Path $projectRoot 'portable'
foreach ($name in @('INICIAR.cmd','GUIA-RAPIDO.html','GUIA-RAPIDO.md','README.md','Empacotar-Acervo-Completo.ps1','TESTAR-PACOTE.ps1')) {
    Copy-Item -LiteralPath (Join-Path $portableRoot $name) -Destination (Join-Path $releaseRoot $name) -Force
}
foreach ($name in @('menu.ps1','reset_archive.py')) {
    Copy-Item -LiteralPath (Join-Path $portableRoot ('app\' + $name)) -Destination (Join-Path $releaseRoot ('app\' + $name)) -Force
}
foreach ($name in @('html_generator.py','package_complete_archive.py')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $name) -Destination (Join-Path $releaseRoot ('app\' + $name)) -Force
}
foreach ($relative in @('manifest.json','content\form-detector.js','background\service-worker.js','lib\matcher.js')) {
    Copy-Item -LiteralPath (Join-Path $portableRoot ('extensao-complementar-ato\' + $relative)) -Destination (Join-Path $releaseRoot ('extensao-complementar-ato\' + $relative)) -Force
}
# Encoding-only normalization of generated Windows scripts; runtime stays byte-identical.
$utf8Bom = New-Object Text.UTF8Encoding($true)
foreach ($file in Get-ChildItem -LiteralPath $releaseRoot -Recurse -File) {
    if ($file.Extension -in @('.ps1','.psm1') -and -not $file.FullName.StartsWith((Join-Path $releaseRoot 'runtime') + '\')) {
        [IO.File]::WriteAllText($file.FullName, [IO.File]::ReadAllText($file.FullName), $utf8Bom)
    }
}
$python = Join-Path $releaseRoot 'runtime\python\python.exe'
$audit = Join-Path $releaseRoot 'app\package_audit.py'
& $python -B $audit $releaseRoot --distribution private
if ($LASTEXITCODE -ne 0) { throw 'Private release audit failed.' }
& (Join-Path $releaseRoot 'TESTAR-PACOTE.ps1') -PackageRoot $releaseRoot
if ($LASTEXITCODE -ne 0) { throw 'Offline release runtime validation failed.' }
& $python -B (Join-Path $releaseRoot 'app\package_complete_archive.py') --source $releaseRoot --output (Join-Path $outputRoot 'TCE-Atos-CORRIGIDO-QA-2026-09-05.zip') --distribution private
if ($LASTEXITCODE -ne 0) { throw 'ZIP creation failed.' }
Write-Output $releaseRoot
