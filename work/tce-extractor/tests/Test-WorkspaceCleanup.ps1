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

function Invoke-AnalyzerResult {
    param(
        [string]$AnalyzerPath,
        [string]$Root,
        [string]$ManifestPath
    )

    $output = @(& $AnalyzerPath -Root $Root -ManifestPath $ManifestPath)
    return ([string]::Join([Environment]::NewLine, [string[]]$output)).Trim()
}

function Import-AnalyzerFunction {
    param(
        [string]$AnalyzerPath,
        [string]$Name
    )

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($AnalyzerPath, [ref]$tokens, [ref]$parseErrors)
    $functionAst = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $Name
    }, $true)) | Select-Object -First 1
    if ($null -eq $functionAst) {
        throw "função do analisador não encontrada: $Name"
    }
    Invoke-Expression ("function global:$Name " + $functionAst.Body.Extent.Text)
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
$preexistingManifestPath = Join-Path $fixtureRoot 'preexisting.json'
$symlinkManifestPath = Join-Path $fixtureRoot 'manifest-leaf-link.json'
$symlinkManifestTarget = Join-Path $outsideRoot 'manifest-leaf-target.json'
$symlinkManifestDirectoryTarget = Join-Path $outsideRoot 'manifest-leaf-target-directory'
$aclManifestPath = Join-Path $fixtureRoot 'acl-result.json'
$aclDirectory = Join-Path $fixtureRoot 'acl-denied'
$aclApplied = $false

New-Item -ItemType Directory -Path $fixtureRoot, $outsideTarget -Force | Out-Null

try {
    New-TestFile (Join-Path $fixtureRoot 'src\tracked.ps1') "Write-Output 'source fixture'`n"
    New-TestFile (Join-Path $fixtureRoot 'references.txt') "Referenced path: src\tracked.ps1`nPROFILE-SECRET-DO-NOT-REPORT`n"
    New-TestFile (Join-Path $fixtureRoot 'dados-locais\reference-leak.txt') "Private hit: src\tracked.ps1`n"
    New-TestFile (Join-Path $fixtureRoot 'acervo-tce\reference-leak.txt') "Private hit: src\tracked.ps1`n"

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

    $parserLoaded = $false
    try {
        Import-AnalyzerFunction $analyzerPath 'ConvertFrom-GitStatusOutput'
        Import-AnalyzerFunction $analyzerPath 'Get-GitStatusSnapshot'
        Import-AnalyzerFunction $analyzerPath 'Resolve-GitState'
        $parserLoaded = $true
    } catch {
        Assert-True $false ('funções de git do analisador são testáveis: ' + $_.Exception.Message)
    }
    if ($parserLoaded) {
        $syntheticGitStatus = @(
            "1 .M N... 100644 100644 100644 1111111 1111111 SRC/Mixed-Modified.PS1`0",
            "2 R. N... 100644 100644 100644 2222222 2222222 R100 renamed-new.ps1`0renamed-old.ps1`0",
            "u UU N... 100644 100644 100644 100644 3333333 3333333 3333333 3333333 unmerged.ps1`0",
            "? new file.ps1`0",
            "! ignored.cache`0"
        ) -join ''
        $syntheticStates = ConvertFrom-GitStatusOutput $syntheticGitStatus
        $queriedSynthetic = [pscustomobject]@{ Source = 'queried'; States = $syntheticStates }
        Assert-Equal ([string]$syntheticStates['src/mixed-modified.ps1']) 'modified' 'git parser mapeia registro 1 como modified'
        Assert-Equal ([string]$syntheticStates['renamed-new.ps1']) 'modified' 'git parser mapeia registro 2 como modified'
        Assert-Equal ([string]$syntheticStates['unmerged.ps1']) 'modified' 'git parser mapeia registro u como modified'
        Assert-Equal ([string]$syntheticStates['new file.ps1']) 'untracked' 'git parser mapeia registro ? como untracked'
        Assert-Equal ([string]$syntheticStates['ignored.cache']) 'ignored' 'git parser mapeia registro ! como ignored'
        Assert-Equal ([string](Resolve-GitState -Snapshot $queriedSynthetic -RelativePath 'SRC\clean-tracked.ps1')) 'clean_tracked' 'git estado ausente é clean_tracked'

        $unavailableSynthetic = Get-GitStatusSnapshot -RepoRoot $outsideRoot
        Assert-Equal ([string]$unavailableSynthetic.Source) 'unavailable' 'git consulta indisponível fica unavailable'
        Assert-Equal ([string](Resolve-GitState -Snapshot $unavailableSynthetic -RelativePath 'src\unknown.ps1')) 'unknown' 'git consulta indisponível fica unknown'
    }

    $initialAnalyzerResult = Invoke-AnalyzerResult $analyzerPath $fixtureRoot $manifestPath
    $initialSummary = $initialAnalyzerResult | ConvertFrom-Json
    Assert-True (Test-Path -LiteralPath $manifestPath -PathType Leaf) 'analisador produz manifesto no caminho solicitado'
    Assert-Equal ([string]$initialSummary.git_state_source) 'queried' 'resumo registra origem queried do git_state'
    Assert-True ([int]$initialSummary.skipped_directories -ge 0) 'resumo registra skipped_directories'
    Assert-True ([int]$initialSummary.warnings -ge 0) 'resumo registra warnings'

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
    Assert-True (-not (@($source.referenced_by) -match 'dados-locais|acervo-tce')) 'referências em diretórios privados são excluídas'
    Assert-True ([string]$source.git_state -in @('clean_tracked', 'modified', 'untracked', 'ignored', 'unknown')) 'fonte recebe git_state real'
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

    $preexistingContent = 'PREEXISTING-MANIFEST-MUST-REMAIN-INTACT'
    New-TestFile $preexistingManifestPath $preexistingContent
    $preexistingError = $null
    try {
        Invoke-Analyzer $analyzerPath $fixtureRoot $preexistingManifestPath
    } catch {
        $preexistingError = [string]$_.Exception.Message
    }
    Assert-True ($null -ne $preexistingError -and $preexistingError.Contains($preexistingManifestPath)) 'manifesto preexistente é recusado com caminho na mensagem'
    Assert-Equal ([IO.File]::ReadAllText($preexistingManifestPath)) $preexistingContent 'manifesto preexistente permanece intacto'

    New-TestFile $symlinkManifestTarget 'SYMLINK-MANIFEST-TARGET-MUST-REMAIN-INTACT'
    New-TestFile (Join-Path $symlinkManifestDirectoryTarget 'sentinel.txt') 'SYMLINK-DIRECTORY-TARGET-MUST-REMAIN-INTACT'
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $symlinkOutput = @(& cmd.exe /c mklink $symlinkManifestPath $symlinkManifestTarget 2>&1)
    $symlinkExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    $symlinkKind = 'file symlink'
    $symlinkCreated = ($symlinkExitCode -eq 0) -and (Test-Path -LiteralPath $symlinkManifestPath)
    if (-not $symlinkCreated) {
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $symlinkOutput = @(& cmd.exe /c mklink /J $symlinkManifestPath $symlinkManifestDirectoryTarget 2>&1)
        $symlinkExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorActionPreference
        $symlinkKind = 'directory junction fallback'
        $symlinkCreated = ($symlinkExitCode -eq 0) -and (Test-Path -LiteralPath $symlinkManifestPath)
    }
    Assert-True $symlinkCreated ('fixture cria ' + $symlinkKind + ' de leaf do manifesto para fora')
    if ($symlinkCreated) {
        $symlinkError = $null
        try {
            Invoke-Analyzer $analyzerPath $fixtureRoot $symlinkManifestPath
        } catch {
            $symlinkError = [string]$_.Exception.Message
        }
        Assert-True ($null -ne $symlinkError -and $symlinkError.Contains($symlinkManifestPath) -and $symlinkError -match 'já existe|destino') 'leaf reparse do manifesto é recusado com caminho na mensagem'
        if ($symlinkKind -eq 'file symlink') {
            Assert-Equal ([IO.File]::ReadAllText($symlinkManifestTarget)) 'SYMLINK-MANIFEST-TARGET-MUST-REMAIN-INTACT' 'symlink externo não recebe escrita'
        } else {
            Assert-Equal ([IO.File]::ReadAllText((Join-Path $symlinkManifestDirectoryTarget 'sentinel.txt'))) 'SYMLINK-DIRECTORY-TARGET-MUST-REMAIN-INTACT' 'junction externa não recebe escrita'
        }
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        if ($symlinkKind -eq 'file symlink') {
            @(& cmd.exe /c del $symlinkManifestPath 2>&1) | Out-Null
        } else {
            @(& cmd.exe /c rmdir $symlinkManifestPath 2>&1) | Out-Null
        }
        $ErrorActionPreference = $previousErrorActionPreference
    }

    New-TestFile (Join-Path $aclDirectory 'blocked.txt') 'ACL-BLOCKED-FILE'
    try {
        $currentUserSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        $denyRule = '*{0}:(OI)(CI)(F)' -f $currentUserSid
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        @(& icacls.exe $aclDirectory /deny $denyRule 2>&1) | Out-Null
        $aclExitCode = $LASTEXITCODE
        $ErrorActionPreference = $previousErrorActionPreference
        $aclApplied = ($aclExitCode -eq 0)
        Assert-True $aclApplied 'fixture aplica ACL de negação no diretório'
        if ($aclApplied) {
            $aclResult = $null
            $aclError = $null
            try {
                $aclResult = Invoke-AnalyzerResult $analyzerPath $fixtureRoot $aclManifestPath
            } catch {
                $aclError = [string]$_.Exception.Message
            }
            Assert-True (Test-Path -LiteralPath $aclManifestPath -PathType Leaf) 'analisador grava manifesto apesar de diretório não listável'
            if ($null -ne $aclResult) {
                $aclSummary = $aclResult | ConvertFrom-Json
                Assert-True ([int]$aclSummary.skipped_directories -ge 1) 'diretório não listável é contabilizado em skipped_directories'
                Assert-True ([int]$aclSummary.warnings -ge 1) 'falha de enumeração é contabilizada em warnings'
            } else {
                Assert-True $false ('diretório não listável não aborta o analisador: ' + $aclError)
            }
        }
    } finally {
        if (Test-Path -LiteralPath $aclDirectory) {
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            @(& icacls.exe $aclDirectory /reset 2>&1) | Out-Null
            $aclResetExitCode = $LASTEXITCODE
            $ErrorActionPreference = $previousErrorActionPreference
            if ($aclResetExitCode -eq 0) {
                Remove-Item -LiteralPath $aclDirectory -Recurse -Force
            }
        }
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
