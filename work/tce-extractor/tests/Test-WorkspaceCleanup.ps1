$ErrorActionPreference = 'Stop'

$script:passed = 0
$script:failed = 0

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)

    $actualJson = $Actual | ConvertTo-Json -Compress -Depth 20
    $expectedJson = $Expected | ConvertTo-Json -Compress -Depth 20
    if ($actualJson -ne $expectedJson) {
        $script:failed++
        Write-Host "FALHOU: $Name`n  esperado: $expectedJson`n  recebido: $actualJson" -ForegroundColor Red
    } else {
        $script:passed++
        Write-Host "PASSOU: $Name" -ForegroundColor Green
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Name)
    Assert-Equal $Condition $true $Name
}

function Assert-Throws {
    param([scriptblock]$ScriptBlock, [string]$Name)

    $threw = $false
    try {
        & $ScriptBlock
    } catch {
        $threw = $true
    }
    Assert-True $threw $Name
}

function Invoke-Analyzer {
    param(
        [string]$AnalyzerPath,
        [string]$Root,
        [string]$ManifestPath
    )

    & $AnalyzerPath -Root $Root -ManifestPath $ManifestPath | Out-Null
}

function New-TestFile {
    param([string]$Path, [string]$Content)

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    [IO.File]::WriteAllText($Path, $Content, (New-Object Text.UTF8Encoding($false)))
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$analyzerPath = Join-Path $PSScriptRoot '..\analyze-local-workspace.ps1'
$fixtureRoot = Join-Path $projectRoot ('tmp\workspace-cleanup-test-' + [guid]::NewGuid().ToString('N'))
$outsideRoot = Join-Path ([IO.Path]::GetTempPath()) ('workspace-cleanup-outside-' + [guid]::NewGuid().ToString('N'))
$outsideTarget = Join-Path $outsideRoot 'outside-target'
$manifestPath = Join-Path $fixtureRoot 'manifest.json'
$rejectionManifestPath = Join-Path $fixtureRoot 'rejection.json'
$outsideManifestPath = Join-Path $outsideRoot 'manifest.json'

New-Item -ItemType Directory -Path $fixtureRoot, $outsideTarget -Force | Out-Null

try {
    New-TestFile (Join-Path $fixtureRoot 'src\tracked.ps1') "Write-Output 'source fixture'`n"
    New-TestFile (Join-Path $fixtureRoot 'references.txt') "Referenced path: src\tracked.ps1`nPROFILE-SECRET-DO-NOT-REPORT`n"

    $zipBytes = [Text.Encoding]::UTF8.GetBytes('ZIP-SECRET-BYTES-ARE-HASHED-BUT-NOT-REPORTED')
    [IO.File]::WriteAllBytes((Join-Path $fixtureRoot 'duplicate-a.zip'), $zipBytes)
    [IO.File]::WriteAllBytes((Join-Path $fixtureRoot 'duplicate-b.zip'), $zipBytes)

    New-TestFile (Join-Path $fixtureRoot 'staging\prepared.tmp') 'staging fixture'
    New-TestFile (Join-Path $fixtureRoot 'cache\derived.cache') 'cache fixture'
    New-TestFile (Join-Path $fixtureRoot 'profile\session.json') '{"token":"PROFILE-SECRET"}'
    New-TestFile (Join-Path $fixtureRoot 'profile\nested\hidden.txt') 'PROFILE-NESTED-SECRET'
    New-TestFile (Join-Path $fixtureRoot '.codex-private\state.json') '{"cookie":"PRIVATE-SECRET"}'
    New-TestFile (Join-Path $fixtureRoot '.git\config') 'PRIVATE-GIT-METADATA'
    New-TestFile (Join-Path $fixtureRoot 'unknown.bin') 'UNKNOWN-SECRET'
    New-TestFile (Join-Path $outsideTarget 'outside.txt') 'OUTSIDE-SECRET'

    $junctionTarget = Join-Path $fixtureRoot 'junction-target'
    $junctionPath = Join-Path $fixtureRoot 'junction-inside'
    New-Item -ItemType Directory -Path $junctionTarget -Force | Out-Null
    New-TestFile (Join-Path $junctionTarget 'should-not-be-enumerated.txt') 'junction child'

    $junctionOutput = @(& cmd.exe /c mklink /J $junctionPath $junctionTarget 2>&1)
    $junctionCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $junctionPath -PathType Container)
    if (-not $junctionCreated) {
        $junctionOutput = @(& cmd.exe /c mklink /D $junctionPath $junctionTarget 2>&1)
        $junctionCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $junctionPath -PathType Container)
    }
    Assert-True $junctionCreated 'fixture cria symlink ou junction'

    $analyzerAvailable = Test-Path -LiteralPath $analyzerPath -PathType Leaf
    if (-not $analyzerAvailable) {
        Assert-True $false 'analisador read-only existe antes dos testes de comportamento'
        Write-Host "`nResultado: $script:passed passaram; $script:failed falharam. RED esperado: analyzer-local-workspace.ps1 ausente." -ForegroundColor Yellow
        exit 1
    }

    Invoke-Analyzer $analyzerPath $fixtureRoot $manifestPath
    Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) 'analisador produz manifesto no caminho solicitado'

    $manifestText = [IO.File]::ReadAllText($manifestPath)
    $parsedManifest = $manifestText | ConvertFrom-Json
    $entries = if ($parsedManifest -is [array]) { @($parsedManifest | ForEach-Object { $_ }) } else { @($parsedManifest) }
    $fieldNames = @('path', 'resolved_path', 'kind', 'bytes', 'sha256', 'git_state', 'referenced_by', 'classification', 'reason', 'recommended_action')
    $expectedFields = ($fieldNames | Sort-Object) -join '|'
    foreach ($entry in $entries) {
        $actualFields = @($entry.PSObject.Properties.Name | Sort-Object) -join '|'
        Assert-Equal $actualFields $expectedFields ('schema fechado para ' + $entry.path)
        Assert-True ($entry.path -notmatch '(^|[\\/])\.\.?([\\/]|$)') ('path relativo seguro para ' + $entry.path)
        Assert-True ([IO.Path]::IsPathRooted([string]$entry.resolved_path)) ('resolved_path absoluto para ' + $entry.path)
        Assert-True ([string]$entry.recommended_action -ne 'delete') ('nenhuma ação delete automática para ' + $entry.path)
    }

    $source = $entries | Where-Object { $_.path -eq 'src\tracked.ps1' } | Select-Object -First 1
    Assert-True ($null -ne $source) 'fonte fixture é enumerada'
    Assert-Equal ([string]$source.classification) 'source' 'fonte recebe classificação source'
    Assert-True (@($source.referenced_by) -contains 'references.txt:1') 'referência registra somente arquivo e linha'
    Assert-True ($manifestText -notmatch 'PROFILE-SECRET|ZIP-SECRET|PRIVATE-SECRET|UNKNOWN-SECRET|OUTSIDE-SECRET') 'manifesto não expõe conteúdo sensível'

    $duplicateEntries = @($entries | Where-Object { $_.path -in @('duplicate-a.zip', 'duplicate-b.zip') })
    Assert-Equal $duplicateEntries.Count 2 'ZIP duplicado mantém os dois itens no inventário'
    Assert-Equal (@($duplicateEntries | Select-Object -ExpandProperty sha256 -Unique).Count) 1 'ZIP duplicado tem o mesmo SHA-256'
    Assert-True (@($duplicateEntries | Where-Object { $_.classification -eq 'byte_identical_duplicate' }).Count -eq 2) 'ZIP duplicado recebe classificação byte_identical_duplicate'
    Assert-True (@($duplicateEntries | Where-Object { $_.recommended_action -eq 'quarantine' }).Count -eq 1) 'uma cópia duplicada é candidata a quarentena'

    foreach ($relative in @('staging\prepared.tmp', 'cache\derived.cache')) {
        $entry = $entries | Where-Object { $_.path -eq $relative } | Select-Object -First 1
        Assert-Equal ([string]$entry.classification) 'reproducible_cache_or_staging' ($relative + ' é cache/staging reproduzível')
        Assert-Equal ([string]$entry.recommended_action) 'quarantine' ($relative + ' recomenda quarentena')
    }

    foreach ($relative in @('profile\session.json', '.codex-private\state.json', '.git\config', 'unknown.bin')) {
        $entry = $entries | Where-Object { $_.path -eq $relative } | Select-Object -First 1
        Assert-True ($null -ne $entry) ($relative + ' é enumerado')
        Assert-True ([string]$entry.recommended_action -ne 'delete') ($relative + ' nunca recomenda delete')
    }

    $profileEntry = $entries | Where-Object { $_.path -eq 'profile\session.json' } | Select-Object -First 1
    $codexEntry = $entries | Where-Object { $_.path -eq '.codex-private\state.json' } | Select-Object -First 1
    $gitEntry = $entries | Where-Object { $_.path -eq '.git\config' } | Select-Object -First 1
    $unknownEntry = $entries | Where-Object { $_.path -eq 'unknown.bin' } | Select-Object -First 1
    Assert-Equal ([string]$profileEntry.classification) 'active_profile_or_session' 'perfil recebe classificação protegida'
    Assert-Equal ([string]$codexEntry.classification) 'private_operational_data' '.codex recebe classificação privada'
    Assert-Equal ([string]$gitEntry.classification) 'private_operational_data' '.git recebe classificação privada'
    Assert-Equal ([string]$unknownEntry.classification) 'unknown_artifact' 'desconhecido recebe classificação unknown_artifact'
    Assert-Equal ([string]$profileEntry.recommended_action) 'preserve' 'perfil recomenda preservação'
    Assert-Equal (@($entries | Where-Object { $_.path -like 'profile\nested\*' }).Count) 0 'conteúdo de perfil protegido não é enumerado'
    Assert-True ($null -eq $profileEntry.sha256) 'perfil protegido não tem hash de conteúdo'
    Assert-Equal ([string]$codexEntry.recommended_action) 'preserve' '.codex recomenda preservação'
    Assert-Equal ([string]$gitEntry.recommended_action) 'preserve' '.git recomenda preservação'
    Assert-True ($null -eq $gitEntry.sha256) '.git protegido não tem hash de conteúdo'
    Assert-Equal ([string]$unknownEntry.recommended_action) 'investigate' 'desconhecido recomenda investigação'

    $reparseEntry = $entries | Where-Object { $_.path -eq 'junction-inside' } | Select-Object -First 1
    Assert-Equal ([string]$reparseEntry.kind) 'reparse_point' 'junction é registrada como reparse_point'
    Assert-Equal ([int64]$reparseEntry.bytes) 0 'reparse_point não calcula bytes de descendentes'
    Assert-Equal (@($entries | Where-Object { $_.path -like 'junction-inside\*' }).Count) 0 'reparse_point não é seguido'
    Assert-True ([string]$reparseEntry.resolved_path -match 'junction-target') 'resolved_path da junction aponta para o alvo interno'

    $snapshotFiles = @(Get-ChildItem -LiteralPath $fixtureRoot -File -Force -Recurse | Where-Object { $_.FullName -ne $manifestPath } | ForEach-Object {
        [pscustomobject]@{ Path = $_.FullName.Substring($fixtureRoot.Length + 1); Hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    foreach ($snapshot in $snapshotFiles) {
        $current = Get-FileHash -LiteralPath (Join-Path $fixtureRoot $snapshot.Path) -Algorithm SHA256
        Assert-Equal $current.Hash $snapshot.Hash ('analisador não altera ' + $snapshot.Path)
    }

    Assert-Throws { Invoke-Analyzer $analyzerPath '' $manifestPath } 'raiz vazia é recusada'
    Assert-Throws { Invoke-Analyzer $analyzerPath $outsideRoot $outsideManifestPath } 'raiz fora do projeto é recusada'
    Assert-Throws { Invoke-Analyzer $analyzerPath $fixtureRoot $outsideManifestPath } 'manifesto fora da raiz é recusado'

    $outsideJunction = Join-Path $fixtureRoot 'junction-outside'
    $outsideJunctionOutput = @(& cmd.exe /c mklink /J $outsideJunction $outsideTarget 2>&1)
    $outsideJunctionCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $outsideJunction -PathType Container)
    if (-not $outsideJunctionCreated) {
        $outsideJunctionOutput = @(& cmd.exe /c mklink /D $outsideJunction $outsideTarget 2>&1)
        $outsideJunctionCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $outsideJunction -PathType Container)
    }
    Assert-True $outsideJunctionCreated 'fixture cria reparse point para caso externo'
    Assert-Throws { Invoke-Analyzer $analyzerPath $fixtureRoot $rejectionManifestPath } 'caminho resolvido fora da raiz é recusado'
} finally {
    if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    if (Test-Path -LiteralPath $outsideRoot) { Remove-Item -LiteralPath $outsideRoot -Recurse -Force }
}

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
