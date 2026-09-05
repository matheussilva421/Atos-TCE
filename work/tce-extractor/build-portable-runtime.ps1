[CmdletBinding()]
param(
    [string]$StagingRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    throw 'Execute este construtor como arquivo .ps1; dot-source ou código inline não é aceito.'
}

$ProjectRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ([string]::IsNullOrWhiteSpace($StagingRoot)) {
    $StagingRoot = Join-Path $ProjectRoot 'staging-verified'
} elseif (-not [IO.Path]::IsPathRooted($StagingRoot)) {
    $StagingRoot = Join-Path $ProjectRoot $StagingRoot
}
$StagingRoot = [IO.Path]::GetFullPath($StagingRoot)

function Assert-ValidStagingRoot {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ProjectRoot
    )

    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $project = [IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
    if ($candidate.Equals($project, [StringComparison]::OrdinalIgnoreCase)) {
        throw "StagingRoot rejeitado: a raiz do projeto nunca é um destino de staging: $candidate"
    }

    $parent = [IO.Path]::GetDirectoryName($candidate)
    $leaf = [IO.Path]::GetFileName($candidate)
    $reservedDestinations = @('portable', 'acervo', '.superpowers', 'outputs', 'staging-final')
    if ($null -eq $parent -or
        -not $parent.Equals($project, [StringComparison]::OrdinalIgnoreCase) -or
        $reservedDestinations -contains $leaf.ToLowerInvariant() -or
        $leaf -notmatch '^staging-[^\\/:]+$') {
        throw "StagingRoot rejeitado: use um basename reservado staging-* diretamente sob ProjectRoot; destino recusado: $candidate"
    }
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        throw "StagingRoot rejeitado: o destino existente não é uma pasta: $candidate"
    }
    return $candidate
}

# This validation intentionally runs before every cleanup, download reuse, or
# move.  Only a direct child named staging-* can ever be published.
$StagingRoot = Assert-ValidStagingRoot -Path $StagingRoot -ProjectRoot $ProjectRoot

function Assert-BuilderRemovalTarget {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string[]]$TemporaryRoots
    )

    $candidate = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    foreach ($temporaryRoot in $TemporaryRoots) {
        $root = [IO.Path]::GetFullPath($temporaryRoot).TrimEnd('\')
        if ($candidate.Equals($root, [StringComparison]::OrdinalIgnoreCase) -or
            $candidate.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
            return $candidate
        }
    }
    throw "Remoção bloqueada: somente roots temporários do builder podem ser removidos; destino publicado preservado: $candidate"
}

function Remove-BuilderPath {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string[]]$TemporaryRoots
    )

    $targetPath = Assert-BuilderRemovalTarget -Path $Path -TemporaryRoots $TemporaryRoots
    if (Test-Path -LiteralPath $targetPath) {
        Remove-Item -LiteralPath $targetPath -Recurse -Force
    }
}

$buildId = [guid]::NewGuid().ToString('N')
$stagingRootBuild = "$StagingRoot.build-$buildId"
$BuildRoot = $stagingRootBuild
$BackupRoot = "$StagingRoot.backup-$buildId"
$BuilderTemporaryRoots = @($BuildRoot, $BackupRoot)
Assert-BuilderRemovalTarget -Path $BuildRoot -TemporaryRoots $BuilderTemporaryRoots | Out-Null
Assert-BuilderRemovalTarget -Path $BackupRoot -TemporaryRoots $BuilderTemporaryRoots | Out-Null
if (Test-Path -LiteralPath $BuildRoot) {
    throw "Build temporário já existe; abortando para não remover trabalho alheio: $BuildRoot"
}
if (Test-Path -LiteralPath $BackupRoot) {
    throw "Backup temporário já existe; abortando para não remover trabalho alheio: $BackupRoot"
}

# Published-shape references retained as contracts for callers and tests. All
# real materialization below uses BuildRoot until Publish-Staging completes.
# $pythonRoot = Join-Path $StagingRoot 'runtime\python'
# $tesseractRoot = Join-Path $StagingRoot 'runtime\tesseract'

$manifestPath = Join-Path $ProjectRoot 'portable\runtime-manifest.json'
$licenseReadmePath = Join-Path $ProjectRoot 'portable\licenses\README.md'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Manifesto ausente: $manifestPath" }
if (-not (Test-Path -LiteralPath $licenseReadmePath -PathType Leaf)) { throw "README de licenças ausente: $licenseReadmePath" }

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$expectedVersions = @{
    python = '3.14.4'
    pymupdf = '1.28.2'
    tesseract = '5.4.0.20240606'
    sevenzip = '26.02'
}
$requiredTraineddata = @('por.traineddata', 'eng.traineddata', 'osd.traineddata')
foreach ($component in $expectedVersions.Keys) {
    if ([string]$manifest.$component.version -ne $expectedVersions[$component]) {
        throw "Versão não fixada para ${component}: $($manifest.$component.version)"
    }
    $hash = [string]$manifest.$component.sha256
    if ($hash -notmatch '^[0-9a-fA-F]{64}$') {
        throw "SHA-256 fixo ausente ou inválido para ${component}."
    }
    if ([string]::IsNullOrWhiteSpace([string]$manifest.$component.source)) {
        throw "Fonte HTTPS ausente para ${component}."
    }
    if (-not ([uri][string]$manifest.$component.source).Scheme.Equals('https', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Fonte não HTTPS para ${component}: $($manifest.$component.source)"
    }
}
if ([string]$manifest.sevenzip.artifact -ne '7z2602-extra.7z' -or
    [string]$manifest.sevenzip.standalone_artifact -ne '7zr.exe' -or
    [string]$manifest.sevenzip.standalone_sha256 -ne '56b8cc9f4971cef253644fafe54063ed7fdca551d4dee0f8c6baa81b855acd72' -or
    [string]$manifest.sevenzip.full_artifact -ne '7z2602-x64.exe' -or
    [string]$manifest.sevenzip.full_sha256 -ne '6745fa76dc2ea031596d8678f6f6b99c3c1b435b4164a63485adbbc7b8d82ef0') {
    throw 'Identidade do SevenZip 26.02 não está fixada no manifesto.'
}

function Get-FileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-FixedHash {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Expected,
        [Parameter(Mandatory)][string]$Label
    )
    $actual = Get-FileSha256 -Path $Path
    if ($actual -ne $Expected.ToLowerInvariant()) {
        throw "SHA-256 divergente para ${Label}: esperado $Expected, observado $actual"
    }
    return $actual
}

function Convert-TesseractOutputToLines {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Output
    )
    $text = ($Output | ForEach-Object { [string]$_ }) -join "`n"
    return @(
        $text -split '\r?\n' |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    )
}

function Invoke-FixedDownload {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string]$ExpectedHash,
        [Parameter(Mandatory)][string]$Label
    )
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
    try {
        Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
    } catch {
        $webRequestError = $_.Exception.Message
        if (Test-Path -LiteralPath $Destination) {
            Remove-BuilderPath -Path $Destination -TemporaryRoots $BuilderTemporaryRoots
        }
        $fallbackPython = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $fallbackPython) {
            throw "Invoke-WebRequest falhou para ${Label} ($webRequestError) e não há Python para o fallback de transporte."
        }
        Write-Warning "Invoke-WebRequest falhou para ${Label}; usando urllib somente como transporte: $webRequestError"
        & $fallbackPython.Source -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" $Uri $Destination
        if ($LASTEXITCODE -ne 0) { throw "Download de ${Label} falhou via Invoke-WebRequest e urllib (IWR: $webRequestError)." }
    }
    Assert-FixedHash -Path $Destination -Expected $ExpectedHash -Label $Label
}

function Copy-VerifiedOrDownload {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string]$ExpectedHash,
        [Parameter(Mandatory)][string]$Label,
        [Parameter()][string]$ExistingPath
    )
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Destination)) | Out-Null
    if (-not [string]::IsNullOrWhiteSpace($ExistingPath) -and
        (Test-Path -LiteralPath $ExistingPath -PathType Leaf)) {
        try {
            Assert-FixedHash -Path $ExistingPath -Expected $ExpectedHash -Label "$Label reutilizado"
            Copy-Item -LiteralPath $ExistingPath -Destination $Destination -Force
            Assert-FixedHash -Path $Destination -Expected $ExpectedHash -Label $Label
            Write-Host "Reutilizado download verificado: $Label"
            return
        } catch {
            if (Test-Path -LiteralPath $Destination -PathType Leaf) {
                Remove-BuilderPath -Path $Destination -TemporaryRoots $BuilderTemporaryRoots
            }
            Write-Warning "Download local de $Label não passou no hash; será obtido novamente: $($_.Exception.Message)"
        }
    }
    Invoke-FixedDownload -Uri $Uri -Destination $Destination -ExpectedHash $ExpectedHash -Label $Label
}

function Expand-VerifiedWheel {
    param(
        [Parameter(Mandatory)][string]$HostPython,
        [Parameter(Mandatory)][string]$WheelPath,
        [Parameter(Mandatory)][string]$Destination
    )
    $zipExtractScript = @'
import sys
import zipfile
from pathlib import Path

wheel_path = Path(sys.argv[1])
destination = Path(sys.argv[2])
destination.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(wheel_path) as wheel:
    wheel.extractall(destination)
'@
    & $HostPython -c $zipExtractScript $WheelPath $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "Extração direta da wheel PyMuPDF falhou com código $LASTEXITCODE"
    }
}

function Copy-RequiredLicenseFiles {
    param(
        [Parameter(Mandatory)][string]$SourceRoot,
        [Parameter(Mandatory)][string]$DestinationRoot,
        [Parameter(Mandatory)][string]$Label
    )
    [IO.Directory]::CreateDirectory($DestinationRoot) | Out-Null
    $licenseFiles = @(Get-ChildItem -LiteralPath $SourceRoot -Recurse -File | Where-Object {
        $_.Name -match '^(?i)(license|licence|copying|notice|authors)(\.|$)'
    })
    if ($licenseFiles.Count -eq 0) {
        throw "Nenhum arquivo de licença/proveniência encontrado para $Label em $SourceRoot"
    }
    foreach ($file in $licenseFiles) {
        $relative = $file.FullName.Substring($SourceRoot.TrimEnd('\').Length).TrimStart('\')
        $destination = Join-Path $DestinationRoot $relative
        [IO.Directory]::CreateDirectory((Split-Path -Parent $destination)) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
    return $licenseFiles.Count
}

function Add-ManifestFile {
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][System.Collections.ArrayList]$Entries,
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$RelativePath,
        [Parameter(Mandatory)][string]$Component
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Arquivo gerado ausente: $Path" }
    [void]$Entries.Add([ordered]@{
        path = $RelativePath.Replace('\', '/')
        component = $Component
        size = (Get-Item -LiteralPath $Path).Length
        sha256 = Get-FileSha256 -Path $Path
    })
}

function Assert-ManifestFiles {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Entries
    )
    $missing = New-Object System.Collections.ArrayList
    $divergent = New-Object System.Collections.ArrayList
    foreach ($entry in $Entries) {
        $relative = ([string]$entry.path).Replace('/', '\')
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            [void]$missing.Add($entry.path)
            continue
        }
        try {
            $item = Get-Item -LiteralPath $path -ErrorAction Stop
            $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
        } catch {
            [void]$missing.Add("$($entry.path) [$($_.Exception.Message)]")
            continue
        }
        if ($item.Length -ne [long]$entry.size -or $actual -ne ([string]$entry.sha256).ToLowerInvariant()) {
            [void]$divergent.Add($entry.path)
        }
    }
    if ($missing.Count -gt 0 -or $divergent.Count -gt 0) {
        $missingPreview = ($missing | Select-Object -First 3) -join ', '
        $divergentPreview = ($divergent | Select-Object -First 3) -join ', '
        throw "Validação do runtime-manifest falhou: ausentes=$($missing.Count) ($missingPreview); divergentes=$($divergent.Count) ($divergentPreview)"
    }
    return [pscustomobject]@{ total = $Entries.Count; missing = $missing.Count; divergent = $divergent.Count }
}

function Publish-Staging {
    param(
        [Parameter(Mandatory)][string]$BuildRoot,
        [Parameter(Mandatory)][string]$StagingRoot,
        [Parameter(Mandatory)][string]$BackupRoot,
        [Parameter(Mandatory)][string[]]$TemporaryRoots
    )

    Assert-BuilderRemovalTarget -Path $BackupRoot -TemporaryRoots $TemporaryRoots | Out-Null
    if (-not (Test-Path -LiteralPath $BuildRoot -PathType Container)) {
        throw "Build temporário ausente antes da publicação: $BuildRoot"
    }
    $hadPublishedDestination = Test-Path -LiteralPath $StagingRoot
    $publishedMovedToBackup = $false
    $buildMovedToPublished = $false
    try {
        if ($hadPublishedDestination) {
            if (Test-Path -LiteralPath $BackupRoot) {
                throw "Backup temporário inesperadamente existente: $BackupRoot"
            }
            Move-Item -LiteralPath $StagingRoot -Destination $BackupRoot
            $publishedMovedToBackup = $true
        }
        Move-Item -LiteralPath $BuildRoot -Destination $StagingRoot
        $buildMovedToPublished = $true
        if ($publishedMovedToBackup) {
            Remove-BuilderPath -Path $BackupRoot -TemporaryRoots $TemporaryRoots
        }
    } catch {
        $publishError = $_
        $rollbackError = $null
        try {
            if ($buildMovedToPublished -and
                (Test-Path -LiteralPath $StagingRoot) -and
                -not (Test-Path -LiteralPath $BuildRoot)) {
                Move-Item -LiteralPath $StagingRoot -Destination $BuildRoot
            }
            if ($publishedMovedToBackup -and
                (Test-Path -LiteralPath $BackupRoot) -and
                -not (Test-Path -LiteralPath $StagingRoot)) {
                Move-Item -LiteralPath $BackupRoot -Destination $StagingRoot
            }
        } catch {
            $rollbackError = $_.Exception.Message
        }
        if ($null -ne $rollbackError) {
            throw "Publicação falhou e rollback falhou: $($publishError.Exception.Message); rollback: $rollbackError"
        }
        throw "Publicação falhou; rollback concluído: $($publishError.Exception.Message)"
    }
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# All downloads, extraction, gates and manifest generation stay in this
# transaction-local directory. The published destination is untouched until
# Publish-Staging after every gate passes.
$downloadRoot = Join-Path $BuildRoot 'downloads'
[IO.Directory]::CreateDirectory($downloadRoot) | Out-Null

$pythonRoot = Join-Path $BuildRoot 'runtime\python'
$tesseractRoot = Join-Path $BuildRoot 'runtime\tesseract'
$sitePackages = Join-Path $pythonRoot 'Lib\site-packages'
$tessdataRoot = Join-Path $tesseractRoot 'tessdata'
$licensesRoot = Join-Path $BuildRoot 'licenses'
$extractRoot = Join-Path $BuildRoot 'extract'
$toolsRoot = Join-Path $BuildRoot 'tools'
[IO.Directory]::CreateDirectory($pythonRoot) | Out-Null
[IO.Directory]::CreateDirectory($tesseractRoot) | Out-Null
[IO.Directory]::CreateDirectory($sitePackages) | Out-Null
[IO.Directory]::CreateDirectory($tessdataRoot) | Out-Null
[IO.Directory]::CreateDirectory($licensesRoot) | Out-Null
[IO.Directory]::CreateDirectory($extractRoot) | Out-Null
[IO.Directory]::CreateDirectory($toolsRoot) | Out-Null
Copy-Item -LiteralPath $licenseReadmePath -Destination (Join-Path $licensesRoot 'README.md') -Force

$pythonZip = Join-Path $downloadRoot 'python-3.14.4-embeddable-amd64.zip'
$previousDownloadRoot = Join-Path (Join-Path $ProjectRoot 'staging-final') 'downloads'
$previousVerifiedDownloadRoot = Join-Path (Join-Path $ProjectRoot 'staging-verified') 'downloads'
$previousPythonZip = Join-Path $previousDownloadRoot 'python-3.14.4-embeddable-amd64.zip'
if (-not (Test-Path -LiteralPath $previousPythonZip -PathType Leaf)) {
    $previousPythonZip = Join-Path $previousVerifiedDownloadRoot 'python-3.14.4-embeddable-amd64.zip'
}
Copy-VerifiedOrDownload -Uri $manifest.python.source -Destination $pythonZip -ExpectedHash $manifest.python.sha256 -Label 'Python embed 3.14.4' -ExistingPath $previousPythonZip
Expand-Archive -LiteralPath $pythonZip -DestinationPath $pythonRoot -Force

$pythonPth = Join-Path $pythonRoot 'python314._pth'
if (-not (Test-Path -LiteralPath $pythonPth -PathType Leaf)) { throw "python314._pth ausente após extração: $pythonPth" }
$pthLines = @([IO.File]::ReadAllLines($pythonPth) | Where-Object { $_.Trim() -ne 'import site' })
if (-not ($pthLines -contains 'Lib/site-packages')) { $pthLines += 'Lib/site-packages' }
if ($pthLines | Where-Object { $_.Trim() -eq 'import site' }) {
    throw "python314._pth não pode habilitar import site: $pythonPth"
}
[IO.File]::WriteAllLines($pythonPth, $pthLines, (New-Object Text.UTF8Encoding($false)))

$hostPython = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $hostPython) { throw 'Python do construtor não encontrado; ele é necessário somente durante a construção para download e extração da wheel.' }
$wheelDestination = Join-Path $downloadRoot 'pymupdf'
[IO.Directory]::CreateDirectory($wheelDestination) | Out-Null
$wheelArtifact = [string]$manifest.pymupdf.artifact
$previousWheel = Join-Path (Join-Path $previousDownloadRoot 'pymupdf') $wheelArtifact
if (-not (Test-Path -LiteralPath $previousWheel -PathType Leaf)) {
    $previousWheel = Join-Path (Join-Path $previousVerifiedDownloadRoot 'pymupdf') $wheelArtifact
}
if (Test-Path -LiteralPath $previousWheel -PathType Leaf) {
    Copy-VerifiedOrDownload -Uri $manifest.pymupdf.source -Destination (Join-Path $wheelDestination $wheelArtifact) -ExpectedHash $manifest.pymupdf.sha256 -Label 'PyMuPDF 1.28.2 wheel' -ExistingPath $previousWheel
} else {
    & $hostPython.Source -m pip download --no-deps --only-binary=:all: --platform win_amd64 --python-version 3.14 --implementation cp --abi abi3 --dest $wheelDestination "PyMuPDF==$($manifest.pymupdf.version)"
    if ($LASTEXITCODE -ne 0) { throw "pip download do PyMuPDF falhou com código $LASTEXITCODE" }
}
$wheels = @(Get-ChildItem -LiteralPath $wheelDestination -File -Filter '*.whl' | Where-Object {
    $_.Name -ieq $wheelArtifact
})
if ($wheels.Count -ne 1) { throw "Wheel PyMuPDF amd64 esperada não encontrada de forma única em $wheelDestination" }
$wheel = $wheels[0]
Assert-FixedHash -Path $wheel.FullName -Expected $manifest.pymupdf.sha256 -Label 'PyMuPDF 1.28.2 wheel'
Expand-VerifiedWheel -HostPython $hostPython.Source -WheelPath $wheel.FullName -Destination $sitePackages

$tesseractInstaller = Join-Path $downloadRoot 'tesseract-ocr-w64-setup-5.4.0.20240606.exe'
$previousTesseractInstaller = Join-Path $previousDownloadRoot 'tesseract-ocr-w64-setup-5.4.0.20240606.exe'
if (-not (Test-Path -LiteralPath $previousTesseractInstaller -PathType Leaf)) {
    $previousTesseractInstaller = Join-Path $previousVerifiedDownloadRoot 'tesseract-ocr-w64-setup-5.4.0.20240606.exe'
}
Copy-VerifiedOrDownload -Uri $manifest.tesseract.source -Destination $tesseractInstaller -ExpectedHash $manifest.tesseract.sha256 -Label 'Tesseract NSIS installer 5.4.0.20240606' -ExistingPath $previousTesseractInstaller

$sevenZipDownloadRoot = Join-Path $downloadRoot 'sevenzip'
$sevenZipExtraArchive = Join-Path $sevenZipDownloadRoot ([string]$manifest.sevenzip.artifact)
$sevenZipStandalone = Join-Path $sevenZipDownloadRoot ([string]$manifest.sevenzip.standalone_artifact)
$sevenZipFullInstaller = Join-Path $sevenZipDownloadRoot ([string]$manifest.sevenzip.full_artifact)
$previousSevenZipRoot = Join-Path $previousDownloadRoot 'sevenzip'
$previousVerifiedSevenZipRoot = Join-Path $previousVerifiedDownloadRoot 'sevenzip'
$previousSevenZipExtra = Join-Path $previousSevenZipRoot ([string]$manifest.sevenzip.artifact)
$previousVerifiedSevenZipExtra = Join-Path $previousVerifiedSevenZipRoot ([string]$manifest.sevenzip.artifact)
$previousSevenZipStandalone = Join-Path $previousSevenZipRoot ([string]$manifest.sevenzip.standalone_artifact)
$previousVerifiedSevenZipStandalone = Join-Path $previousVerifiedSevenZipRoot ([string]$manifest.sevenzip.standalone_artifact)
$previousSevenZipFull = Join-Path $previousSevenZipRoot ([string]$manifest.sevenzip.full_artifact)
$previousVerifiedSevenZipFull = Join-Path $previousVerifiedSevenZipRoot ([string]$manifest.sevenzip.full_artifact)
if (-not (Test-Path -LiteralPath $previousSevenZipExtra -PathType Leaf)) { $previousSevenZipExtra = $previousVerifiedSevenZipExtra }
if (-not (Test-Path -LiteralPath $previousSevenZipStandalone -PathType Leaf)) { $previousSevenZipStandalone = $previousVerifiedSevenZipStandalone }
if (-not (Test-Path -LiteralPath $previousSevenZipFull -PathType Leaf)) { $previousSevenZipFull = $previousVerifiedSevenZipFull }
Copy-VerifiedOrDownload -Uri $manifest.sevenzip.source -Destination $sevenZipExtraArchive -ExpectedHash $manifest.sevenzip.sha256 -Label '7-Zip Extra 26.02' -ExistingPath $previousSevenZipExtra
Copy-VerifiedOrDownload -Uri $manifest.sevenzip.standalone_source -Destination $sevenZipStandalone -ExpectedHash $manifest.sevenzip.standalone_sha256 -Label '7zr.exe 26.02' -ExistingPath $previousSevenZipStandalone
Copy-VerifiedOrDownload -Uri $manifest.sevenzip.full_source -Destination $sevenZipFullInstaller -ExpectedHash $manifest.sevenzip.full_sha256 -Label '7-Zip x64 26.02 archive' -ExistingPath $previousSevenZipFull

$sevenZipExtractRoot = Join-Path $extractRoot 'sevenzip-extra'
[IO.Directory]::CreateDirectory($sevenZipExtractRoot) | Out-Null
$sevenZipStandaloneOutput = @(& $sevenZipStandalone x $sevenZipExtraArchive "-o$sevenZipExtractRoot" '-y' 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Extração do pacote 7z2602-extra.7z com 7zr.exe falhou: $($sevenZipStandaloneOutput -join "`n")"
}
$sevenZipFullOutput = @(& $sevenZipStandalone x $sevenZipFullInstaller "-o$sevenZipExtractRoot" '-y' 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Extração do arquivo 7z2602-x64.exe com 7zr.exe falhou: $($sevenZipFullOutput -join "`n")"
}
$sevenZipExecutables = @(Get-ChildItem -LiteralPath $sevenZipExtractRoot -Recurse -File -Filter '7z.exe')
if ($sevenZipExecutables.Count -eq 0) {
    # 7-Zip Extra 26.02 names the x64 console binary 7za.exe. Materialize
    # that extracted binary under the builder's temporary 7z.exe tool name.
    $sevenZipExecutables = @(Get-ChildItem -LiteralPath $sevenZipExtractRoot -Recurse -File -Filter '7za.exe' | Where-Object {
        $_.FullName -match '(?i)[\\/]x64[\\/]'
    })
}
if ($sevenZipExecutables.Count -ne 1) { throw "7z.exe extraído não encontrado de forma única em $sevenZipExtractRoot" }
$sevenZipExe = $sevenZipExecutables[0].FullName

$tesseractExtractRoot = Join-Path $extractRoot 'tesseract-nsis'
[IO.Directory]::CreateDirectory($tesseractExtractRoot) | Out-Null
$nsisOutput = @(& $sevenZipExe x $tesseractInstaller "-o$tesseractExtractRoot" '-y' 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Extração do instalador NSIS Tesseract com 7z.exe falhou: $($nsisOutput -join "`n")"
}

# Copy only from the verified NSIS extraction tree. The installer is never
# executed and no local/system Tesseract tree is accepted as a source.
$extractedTesseractCandidates = @(Get-ChildItem -LiteralPath $tesseractExtractRoot -Recurse -File -Filter 'tesseract.exe' | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'tessdata') -PathType Container
})
if ($extractedTesseractCandidates.Count -ne 1) {
    throw "Árvore Tesseract extraída não contém uma instalação única com tessdata: $tesseractExtractRoot"
}
$extractedTesseractExe = $extractedTesseractCandidates[0].FullName
$extractedTesseractRoot = $extractedTesseractCandidates[0].Directory.FullName
$extractedTessdata = Join-Path $extractedTesseractRoot 'tessdata'
$extractedVersionOutput = @(& $extractedTesseractExe --version 2>&1) -join "`n"
if ($extractedVersionOutput -notmatch [regex]::Escape("tesseract v$($manifest.tesseract.version)")) {
    throw "Versão do Tesseract extraído não corresponde ao manifesto: $extractedVersionOutput"
}
# The verified UB Mannheim NSIS package ships eng/osd by default. Fetch the
# fixed Portuguese model into the same temporary extraction tree, then copy
# every shipped runtime file only from that tree.
$portugueseModel = $manifest.tesseract.language_data.por
Copy-VerifiedOrDownload -Uri $portugueseModel.source -Destination (Join-Path $extractedTessdata 'por.traineddata') -ExpectedHash $portugueseModel.sha256 -Label 'Tesseract por.traineddata' -ExistingPath ''
Copy-Item -LiteralPath $extractedTesseractExe -Destination (Join-Path $tesseractRoot 'tesseract.exe') -Force
$extractedDlls = @(Get-ChildItem -LiteralPath $extractedTesseractRoot -File -Filter '*.dll')
if ($extractedDlls.Count -eq 0) { throw "Nenhuma DLL nativa encontrada na árvore Tesseract extraída: $extractedTesseractRoot" }
foreach ($dll in $extractedDlls) {
    Copy-Item -LiteralPath $dll.FullName -Destination (Join-Path $tesseractRoot $dll.Name) -Force
}
foreach ($traineddataName in $requiredTraineddata) {
    $extractedLanguage = Join-Path $extractedTessdata $traineddataName
    if (-not (Test-Path -LiteralPath $extractedLanguage -PathType Leaf)) { throw "Idioma Tesseract ausente na árvore extraída: $extractedLanguage" }
    Copy-Item -LiteralPath $extractedLanguage -Destination (Join-Path $tessdataRoot $traineddataName) -Force
}

$pythonLicenseCount = Copy-RequiredLicenseFiles -SourceRoot $pythonRoot -DestinationRoot (Join-Path $licensesRoot 'Python') -Label 'Python'
$pymupdfDistInfo = @(Get-ChildItem -LiteralPath $sitePackages -Directory -Filter '*pymupdf*.dist-info')
if ($pymupdfDistInfo.Count -ne 1) { throw "Metadados .dist-info do PyMuPDF não encontrados de forma única." }
$pymupdfLicenseCount = Copy-RequiredLicenseFiles -SourceRoot $pymupdfDistInfo[0].FullName -DestinationRoot (Join-Path $licensesRoot 'PyMuPDF') -Label 'PyMuPDF'
$tesseractLicenseCount = Copy-RequiredLicenseFiles -SourceRoot $extractedTesseractRoot -DestinationRoot (Join-Path $licensesRoot 'Tesseract') -Label 'Tesseract extraído'

$pythonExe = Join-Path $pythonRoot 'python.exe'
$tesseractExe = Join-Path $tesseractRoot 'tesseract.exe'
$oldPath = $env:Path
try {
    $env:Path = "$env:SystemRoot\System32;$env:SystemRoot"
    $pythonProbe = @(& $pythonExe -B -s -c "import os, pathlib, sys; assert sys.version_info[:3] == (3, 14, 4), sys.version; import pymupdf; module = pathlib.Path(pymupdf.__file__).resolve(); root = pathlib.Path(sys.argv[1]).resolve(); assert str(module).lower().startswith(str(root).lower() + os.sep), (module, root); assert pymupdf.__version__ == '1.28.2', pymupdf.__version__; print(pymupdf.__version__); print('pymupdf_file=' + str(module)); print(sys.executable)" $BuildRoot 2>&1) -join "`n"
    if ($LASTEXITCODE -ne 0 -or $pythonProbe -notmatch '(?m)^1\.28\.2$') {
        throw "Validação PyMuPDF/Python isolada falhou no build temporário: $pythonProbe"
    }
    $tesseractOutput = @(& $tesseractExe --tessdata-dir $tessdataRoot --list-langs 2>&1)
    $tesseractProbe = ($tesseractOutput | ForEach-Object { [string]$_ }) -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Validação Tesseract falhou em PATH restrito: $tesseractProbe" }
    $tesseractLanguages = @(Convert-TesseractOutputToLines -Output $tesseractOutput)
    foreach ($language in @('por', 'eng', 'osd')) {
        if ($tesseractLanguages -notcontains $language) { throw "Idioma $language não apareceu em --list-langs: $tesseractProbe" }
    }
} finally {
    $env:Path = $oldPath
}

# Build-only downloads, archive tools, and extraction trees must not leak into
# the published runtime. Their deletion is still confined to BuildRoot.
Remove-BuilderPath -Path $downloadRoot -TemporaryRoots $BuilderTemporaryRoots
Remove-BuilderPath -Path $extractRoot -TemporaryRoots $BuilderTemporaryRoots
Remove-BuilderPath -Path $toolsRoot -TemporaryRoots $BuilderTemporaryRoots

$includedFiles = New-Object System.Collections.ArrayList
Get-ChildItem -LiteralPath (Join-Path $BuildRoot 'runtime') -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($BuildRoot.TrimEnd('\').Length).TrimStart('\')
    $component = if ($relative -like 'runtime\python\*') { 'python' } elseif ($relative -like 'runtime\tesseract\*') { 'tesseract' } else { 'runtime' }
    Add-ManifestFile -Entries $includedFiles -Path $_.FullName -RelativePath $relative -Component $component
}
Get-ChildItem -LiteralPath $licensesRoot -Recurse -File | ForEach-Object {
    $relative = $_.FullName.Substring($BuildRoot.TrimEnd('\').Length).TrimStart('\')
    Add-ManifestFile -Entries $includedFiles -Path $_.FullName -RelativePath $relative -Component 'licenses'
}

$manifestOutput = [ordered]@{}
foreach ($property in $manifest.PSObject.Properties) { $manifestOutput[$property.Name] = $property.Value }
$manifestOutput['build'] = [ordered]@{
    built_at_utc = [DateTime]::UtcNow.ToString('o')
    tesseract_source_kind = 'verified-nsis-extraction'
    tesseract_source_version = $manifest.tesseract.version
    tesseract_source_path_recorded = $false
    sevenzip_source_kind = 'verified-extra-archive-and-standalone'
    license_file_counts = [ordered]@{ python = $pythonLicenseCount; pymupdf = $pymupdfLicenseCount; tesseract = $tesseractLicenseCount }
    included_files = @($includedFiles)
}
$manifestOutputPath = Join-Path $BuildRoot 'runtime-manifest.json'
$manifestJson = $manifestOutput | ConvertTo-Json -Depth 20
[IO.File]::WriteAllText($manifestOutputPath, $manifestJson + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
$manifestValidation = Assert-ManifestFiles -Root $BuildRoot -Entries @($manifestOutput.build.included_files)

Publish-Staging -BuildRoot $BuildRoot -StagingRoot $StagingRoot -BackupRoot $BackupRoot -TemporaryRoots $BuilderTemporaryRoots

[pscustomobject]@{
    staging = $StagingRoot
    python = $pythonProbe
    tesseract_languages = $tesseractProbe
    runtime_files = @($includedFiles).Count
    manifest_validation = $manifestValidation
    licenses = [ordered]@{ python = $pythonLicenseCount; pymupdf = $pymupdfLicenseCount; tesseract = $tesseractLicenseCount }
    manifest = (Join-Path $StagingRoot 'runtime-manifest.json')
} | ConvertTo-Json -Depth 10
