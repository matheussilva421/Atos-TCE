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

function Assert-ThrowsContaining {
    param([scriptblock]$ScriptBlock, [string]$ExpectedText, [string]$Name)

    $message = $null
    try {
        & $ScriptBlock
    } catch {
        $message = [string]$_.Exception.Message
    }
    Assert-True ($null -ne $message -and $message.Contains($ExpectedText)) ($Name + ' (mensagem: ' + $message + ')')
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

function Import-CleanerFunction {
    param(
        [string]$CleanerPath,
        [string]$Name
    )

    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($CleanerPath, [ref]$tokens, [ref]$parseErrors)
    $functionAst = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $Name
    }, $true)) | Select-Object -First 1
    if ($null -eq $functionAst) {
        throw "função do cleaner não encontrada: $Name"
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
$cleanerPath = Join-Path $PSScriptRoot '..\clean-local-workspace.ps1'
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

    $cleanerAvailable = Test-Path -LiteralPath $cleanerPath -PathType Leaf
    Assert-True $cleanerAvailable 'cleaner script exists'
    if ($cleanerAvailable) {
        $cleanerHeader = Get-Content -LiteralPath $cleanerPath -Raw
        Assert-True ($cleanerHeader.Contains('Risco residual: a origem é pinada por handle') -and
            $cleanerHeader.IndexOf('Ordem: validar raiz/manifesto') -ge 0) 'cleaner header declares residual risk and check order'
        # Os fixtures do cleaner ficam no TEMP do SO, fora do workspace.
        $cleanerRoot = Join-Path $outsideRoot 'cleaner-cases'
        New-Item -ItemType Directory -Path $cleanerRoot -Force | Out-Null
        $hardeningRoot = Join-Path $outsideRoot 'hardening-cases'
        New-Item -ItemType Directory -Path $hardeningRoot -Force | Out-Null

        function Write-CleanupManifest {
            param([string]$Path, [string]$Root, [object[]]$Entries)
            $payload = [ordered]@{
                schema_version = 1
                root = [IO.Path]::GetFullPath($Root)
                entries = @($Entries)
            }
            [IO.File]::WriteAllText($Path, ($payload | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        }

        function New-CleanupEntry {
            param([string]$Path, [string]$Hash, [long]$Bytes, [bool]$Approved = $true)
            return [ordered]@{
                path = $Path
                kind = 'file'
                bytes = $Bytes
                sha256 = $Hash
                decision = 'quarantine'
                approved = $Approved
            }
        }

        function Invoke-CleanerJson {
            param(
                [string]$Root,
                [string]$Manifest,
                [switch]$Apply,
                [switch]$Resume,
                [switch]$PurgeQuarantine,
                [switch]$WhatIf,
                [switch]$TestTemporaryRoot,
                [string]$TestHook,
                [string[]]$TestRunningProcesses,
                [object[]]$TestBrowserProcesses,
                [switch]$TestDenyProcessEnumeration
            )
            $arguments = @{ Root = $Root; ManifestPath = $Manifest }
            if ($Apply) { $arguments.Apply = $true }
            if ($Resume) { $arguments.Resume = $true }
            if ($PurgeQuarantine) { $arguments.PurgeQuarantine = $true }
            if ($WhatIf) { $arguments.WhatIf = $true }
            if ($TestTemporaryRoot) { $arguments.TestTemporaryRoot = $true }
            if (-not [string]::IsNullOrWhiteSpace($TestHook)) { $arguments.TestHook = $TestHook }
            if ($null -ne $TestRunningProcesses -and $TestRunningProcesses.Count -gt 0) { $arguments.TestRunningProcesses = $TestRunningProcesses }
            if ($null -ne $TestBrowserProcesses -and @($TestBrowserProcesses).Count -gt 0) { $arguments.TestBrowserProcesses = @($TestBrowserProcesses) }
            if ($TestDenyProcessEnumeration) { $arguments.TestDenyProcessEnumeration = $true }
            $output = @(& $cleanerPath @arguments)
            return ([string]::Join([Environment]::NewLine, [string[]]$output)).Trim() | ConvertFrom-Json
        }

        function New-ManualReceiptFixture {
            param(
                [string]$Name,
                [string]$RelativePath,
                [string]$Content
            )

            $quarantineRoot = Join-Path $cleanerRoot ('tmp\quarantine\' + $Name)
            $destination = Join-Path $quarantineRoot $RelativePath
            New-TestFile $destination $Content
            $destinationInfo = Get-Item -LiteralPath $destination -Force
            $hash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant()
            $origin = [IO.Path]::GetFullPath((Join-Path $cleanerRoot $RelativePath))
            $item = [ordered]@{
                origin = $origin
                destination = [IO.Path]::GetFullPath($destination)
                sha256 = $hash
                bytes = [int64]$destinationInfo.Length
                timestamp = [DateTime]::UtcNow.ToString('o')
                result = 'moved'
            }
            $receiptPath = Join-Path $quarantineRoot 'receipt.json'
            $receipt = [ordered]@{
                schema_version = 1
                root = [IO.Path]::GetFullPath($cleanerRoot)
                quarantine_root = [IO.Path]::GetFullPath($quarantineRoot)
                created_at = [DateTime]::UtcNow.ToString('o')
                items = @($item)
            }
            [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
            return [pscustomobject]@{
                QuarantineRoot = $quarantineRoot
                Destination = $destination
                ReceiptPath = $receiptPath
                Receipt = $receipt
                Item = $item
            }
        }

        # RED: estes contratos devem falhar enquanto o hardening ainda não existir.
        $savedCleanerRoot = $cleanerRoot
        $cleanerRoot = $hardeningRoot
        $cleanerTokens = $null
        $cleanerParseErrors = $null
        $cleanerAst = [System.Management.Automation.Language.Parser]::ParseFile($cleanerPath, [ref]$cleanerTokens, [ref]$cleanerParseErrors)
        $safePathAst = @($cleanerAst.FindAll({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Assert-SafeRelativePath'
        }, $true)) | Select-Object -First 1
        Invoke-Expression ('function global:Assert-SafeRelativePath ' + $safePathAst.Body.Extent.Text)

        $tildeFile = Join-Path $cleanerRoot 'guard-tilde~1.txt'
        New-TestFile $tildeFile 'GUARD-TILDE'
        $tildeHash = (Get-FileHash -LiteralPath $tildeFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $tildeManifest = Join-Path $cleanerRoot 'guard-tilde-manifest.json'
        Write-CleanupManifest $tildeManifest $cleanerRoot @(
            (New-CleanupEntry 'guard-tilde~1.txt' $tildeHash ([IO.FileInfo]$tildeFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $tildeManifest -TestTemporaryRoot | Out-Null } 'short-name aliases are not allowed' 'segmento com ~ é recusado'
        Assert-ThrowsContaining { Assert-SafeRelativePath 'guard-tilde~1.txt' } 'short-name aliases are not allowed' 'guard lexical recusa ~ diretamente'

        $trailingDotDirectory = Join-Path $cleanerRoot 'guard-trailing-dot'
        $trailingDotFile = Join-Path $trailingDotDirectory 'child.txt'
        New-TestFile $trailingDotFile 'GUARD-TRAILING-DOT'
        $trailingDotHash = (Get-FileHash -LiteralPath $trailingDotFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $trailingDotManifest = Join-Path $cleanerRoot 'guard-trailing-dot-manifest.json'
        Write-CleanupManifest $trailingDotManifest $cleanerRoot @(
            (New-CleanupEntry 'guard-trailing-dot.\child.txt' $trailingDotHash ([IO.FileInfo]$trailingDotFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $trailingDotManifest -TestTemporaryRoot | Out-Null } 'trailing dot or space' 'segmento terminado em ponto é recusado'
        Assert-ThrowsContaining { Assert-SafeRelativePath 'guard-trailing-space \child.txt' } 'trailing dot or space' 'segmento terminado em espaço é recusado'

        $reservedManifest = Join-Path $cleanerRoot 'guard-reserved-manifest.json'
        Write-CleanupManifest $reservedManifest $cleanerRoot @(
            (New-CleanupEntry 'CON\child.txt' ('3' * 64) 1)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $reservedManifest -TestTemporaryRoot | Out-Null } 'reserved Windows device name' 'nome reservado do Windows é recusado'
        foreach ($reservedName in @('CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM9', 'LPT1', 'LPT9')) {
            $reservedRelative = $reservedName + '\child.txt'
            Assert-ThrowsContaining { Assert-SafeRelativePath $reservedRelative } 'reserved Windows device name' ('nome reservado ' + $reservedName + ' é recusado')
        }

        $resolvedAliasFile = Join-Path $cleanerRoot '.git\resolved-alias-target.txt'
        New-TestFile $resolvedAliasFile 'RESOLVED-PROTECTED-ALIAS'
        Import-CleanerFunction $cleanerPath 'ConvertTo-FullPath'
        Import-CleanerFunction $cleanerPath 'Test-PathWithinRoot'
        Import-CleanerFunction $cleanerPath 'Assert-SafeResolvedPath'
        Assert-ThrowsContaining {
            Assert-SafeResolvedPath -Path (Join-Path $cleanerRoot '.git.\resolved-alias-target.txt') -RootPath $cleanerRoot
        } 'protected path is not allowed' 'alias resolvido para .git é recusado'

        $collisionFile = Join-Path $cleanerRoot 'collision-file.txt'
        New-TestFile $collisionFile 'COLLISION-SOURCE-MUST-REMAIN'
        $collisionHash = (Get-FileHash -LiteralPath $collisionFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $collisionManifest = Join-Path $cleanerRoot 'collision-file-manifest.json'
        Write-CleanupManifest $collisionManifest $cleanerRoot @(
            (New-CleanupEntry 'collision-file.txt' $collisionHash ([IO.FileInfo]$collisionFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $collisionManifest -Apply -TestTemporaryRoot -TestHook 'before-final-move-collision-file' | Out-Null } 'destination already exists' 'destino arquivo preexistente é recusado antes do movimento'
        Assert-Equal ([IO.File]::ReadAllText($collisionFile)) 'COLLISION-SOURCE-MUST-REMAIN' 'origem permanece intacta após colisão de arquivo'

        $collisionDirectoryFile = Join-Path $cleanerRoot 'collision-directory.txt'
        New-TestFile $collisionDirectoryFile 'COLLISION-DIRECTORY-SOURCE-MUST-REMAIN'
        $collisionDirectoryHash = (Get-FileHash -LiteralPath $collisionDirectoryFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $collisionDirectoryManifest = Join-Path $cleanerRoot 'collision-directory-manifest.json'
        Write-CleanupManifest $collisionDirectoryManifest $cleanerRoot @(
            (New-CleanupEntry 'collision-directory.txt' $collisionDirectoryHash ([IO.FileInfo]$collisionDirectoryFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $collisionDirectoryManifest -Apply -TestTemporaryRoot -TestHook 'before-final-move-collision-directory' | Out-Null } 'destination already exists' 'destino diretório preexistente é recusado antes do movimento'
        Assert-Equal ([IO.File]::ReadAllText($collisionDirectoryFile)) 'COLLISION-DIRECTORY-SOURCE-MUST-REMAIN' 'origem permanece intacta após colisão de diretório'

        $toctouRoot = Join-Path $outsideRoot 'toctou-mismatch'
        New-Item -ItemType Directory -Path $toctouRoot -Force | Out-Null
        $toctouFile = Join-Path $toctouRoot 'toctou.txt'
        New-TestFile $toctouFile 'TOCTOU-ORIGINAL'
        $toctouHash = (Get-FileHash -LiteralPath $toctouFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $toctouManifest = Join-Path $toctouRoot 'toctou-manifest.json'
        Write-CleanupManifest $toctouManifest $toctouRoot @(
            (New-CleanupEntry 'toctou.txt' $toctouHash ([IO.FileInfo]$toctouFile).Length)
        )
        $toctouError = $null
        try {
            Invoke-CleanerJson $toctouRoot $toctouManifest -Apply -TestTemporaryRoot -TestHook 'post-move-hash-mismatch' | Out-Null
        } catch {
            $toctouError = [string]$_.Exception.Message
        }
        Assert-True ($null -ne $toctouError -and $toctouError.Contains('post-move hash mismatch')) 'divergência pós-movimento é reportada como erro'
        $toctouReceipts = @(Get-ChildItem -LiteralPath (Join-Path $toctouRoot 'tmp\quarantine') -Filter 'receipt.json' -File -Force -Recurse -ErrorAction SilentlyContinue)
        Assert-Equal $toctouReceipts.Count 1 'divergência pós-movimento gera um recibo'
        if ($toctouReceipts.Count -eq 1) {
            $toctouReceipt = Get-Content -LiteralPath $toctouReceipts[0].FullName -Raw | ConvertFrom-Json
            Assert-Equal $toctouReceipt.items[0].result 'unconfirmed' 'divergência pós-movimento registra unconfirmed'
            Assert-True (Test-Path -LiteralPath $toctouFile -PathType Leaf) 'rollback tenta devolver o arquivo à origem'
            Assert-True (-not (Test-Path -LiteralPath $toctouReceipt.items[0].destination)) 'rollback remove o destino divergente'
        }

        $purgeWrongReceipt = New-ManualReceiptFixture 'forged-wrong-receipt' 'listed\file.txt' 'PURGE-FORGED'
        $wrongReceiptPath = Join-Path $cleanerRoot 'wrong-receipt-location.json'
        [IO.File]::WriteAllText($wrongReceiptPath, (Get-Content -LiteralPath $purgeWrongReceipt.ReceiptPath -Raw), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $wrongReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt path must be quarantine\receipt.json' 'purge exige receipt.json literal na quarentena'

        $purgeWrongResult = New-ManualReceiptFixture 'forged-wrong-result' 'listed\file.txt' 'PURGE-WRONG-RESULT'
        $purgeWrongResult.Receipt.items[0].result = 'planned'
        [IO.File]::WriteAllText($purgeWrongResult.ReceiptPath, ($purgeWrongResult.Receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeWrongResult.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt item result must be moved' 'purge recusa result diferente de moved'

        $purgeWrongBytes = New-ManualReceiptFixture 'forged-wrong-bytes' 'listed\file.txt' 'PURGE-WRONG-BYTES'
        $purgeWrongBytes.Receipt.items[0].bytes = [int64]$purgeWrongBytes.Receipt.items[0].bytes + 1
        [IO.File]::WriteAllText($purgeWrongBytes.ReceiptPath, ($purgeWrongBytes.Receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeWrongBytes.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt byte count mismatch' 'purge valida bytes reais do arquivo'

        $purgeOutsideOrigin = New-ManualReceiptFixture 'forged-outside-origin' 'listed\file.txt' 'PURGE-OUTSIDE-ORIGIN'
        $purgeOutsideOrigin.Receipt.items[0].origin = [IO.Path]::GetFullPath((Join-Path $outsideRoot 'outside-origin.txt'))
        [IO.File]::WriteAllText($purgeOutsideOrigin.ReceiptPath, ($purgeOutsideOrigin.Receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeOutsideOrigin.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt origin escapes root' 'purge recusa origin fora da raiz'

        $purgeWrongDestination = New-ManualReceiptFixture 'forged-wrong-destination' 'listed\file.txt' 'PURGE-WRONG-DESTINATION'
        $purgeWrongDestination.Receipt.items[0].destination = [IO.Path]::GetFullPath((Join-Path $purgeWrongDestination.QuarantineRoot 'other\file.txt'))
        [IO.File]::WriteAllText($purgeWrongDestination.ReceiptPath, ($purgeWrongDestination.Receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeWrongDestination.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt destination does not match quarantine and origin' 'purge valida destination derivado de quarantine e origin'

        $purgeDuplicate = New-ManualReceiptFixture 'forged-duplicate-destination' 'listed\file.txt' 'PURGE-DUPLICATE'
        $purgeDuplicate.Receipt.items = @($purgeDuplicate.Receipt.items[0], $purgeDuplicate.Receipt.items[0])
        [IO.File]::WriteAllText($purgeDuplicate.ReceiptPath, ($purgeDuplicate.Receipt | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding($false)))
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeDuplicate.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'duplicate receipt destination' 'purge recusa destinations duplicados'

        $purgeExtra = New-ManualReceiptFixture 'forged-extra-file' 'listed\file.txt' 'PURGE-EXTRA'
        New-TestFile (Join-Path $purgeExtra.QuarantineRoot 'unlisted-extra.txt') 'PURGE-UNLISTED-EXTRA'
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $purgeExtra.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'unlisted file exists in quarantine' 'purge recusa arquivo extra não listado'

        $cleanerRoot = $savedCleanerRoot

        $whatIfFile = Join-Path $cleanerRoot 'whatif.txt'
        New-TestFile $whatIfFile 'WHATIF-CONTENT'
        $whatIfHash = (Get-FileHash -LiteralPath $whatIfFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $whatIfManifest = Join-Path $cleanerRoot 'whatif-manifest.json'
        Write-CleanupManifest $whatIfManifest $cleanerRoot @(
            (New-CleanupEntry 'whatif.txt' $whatIfHash ([IO.FileInfo]$whatIfFile).Length)
        )
        $whatIfResult = Invoke-CleanerJson $cleanerRoot $whatIfManifest -TestTemporaryRoot
        Assert-Equal $whatIfResult.mode 'whatif' 'default mode is whatif'
        Assert-Equal ([int]$whatIfResult.approved_items) 1 'whatif counts approved items'
        Assert-True (Test-Path -LiteralPath $whatIfFile -PathType Leaf) 'whatif does not move source'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $cleanerRoot 'tmp\quarantine'))) 'whatif creates no quarantine'

        $hashFile = Join-Path $cleanerRoot 'hash-mismatch.txt'
        New-TestFile $hashFile 'CURRENT-CONTENT'
        $hashManifest = Join-Path $cleanerRoot 'hash-manifest.json'
        Write-CleanupManifest $hashManifest $cleanerRoot @(
            (New-CleanupEntry 'hash-mismatch.txt' ('0' * 64) ([IO.FileInfo]$hashFile).Length)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $hashManifest -TestTemporaryRoot | Out-Null } 'hash mismatch is rejected'

        $missingManifest = Join-Path $cleanerRoot 'missing-manifest.json'
        Write-CleanupManifest $missingManifest $cleanerRoot @(
            (New-CleanupEntry 'missing.txt' ('1' * 64) 1)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $missingManifest -TestTemporaryRoot | Out-Null } 'missing target is rejected'

        $traversalManifest = Join-Path $cleanerRoot 'traversal-manifest.json'
        Write-CleanupManifest $traversalManifest $cleanerRoot @(
            (New-CleanupEntry '..\outside.txt' ('2' * 64) 1)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $traversalManifest -TestTemporaryRoot | Out-Null } 'path traversal is rejected'

        $unapprovedFile = Join-Path $cleanerRoot 'unapproved.txt'
        New-TestFile $unapprovedFile 'UNAPPROVED'
        $unapprovedHash = (Get-FileHash -LiteralPath $unapprovedFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $unapprovedManifest = Join-Path $cleanerRoot 'unapproved-manifest.json'
        Write-CleanupManifest $unapprovedManifest $cleanerRoot @(
            (New-CleanupEntry 'unapproved.txt' $unapprovedHash ([IO.FileInfo]$unapprovedFile).Length $false)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $unapprovedManifest -TestTemporaryRoot | Out-Null } 'unapproved item is rejected'

        $profileFile = Join-Path $cleanerRoot 'profile\session.json'
        New-TestFile $profileFile 'PROFILE'
        $profileHash = (Get-FileHash -LiteralPath $profileFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $profileManifest = Join-Path $cleanerRoot 'profile-manifest.json'
        Write-CleanupManifest $profileManifest $cleanerRoot @(
            (New-CleanupEntry 'profile\session.json' $profileHash ([IO.FileInfo]$profileFile).Length)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $profileManifest -TestTemporaryRoot | Out-Null } 'active profile path is rejected'

        $protectedAcervoFile = Join-Path $cleanerRoot 'tce-acervo-backup\data.bin'
        New-TestFile $protectedAcervoFile 'PROTECTED-ACERVO'
        $protectedAcervoHash = (Get-FileHash -LiteralPath $protectedAcervoFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $protectedAcervoManifest = Join-Path $cleanerRoot 'protected-acervo-manifest.json'
        Write-CleanupManifest $protectedAcervoManifest $cleanerRoot @(
            (New-CleanupEntry 'tce-acervo-backup\data.bin' $protectedAcervoHash ([IO.FileInfo]$protectedAcervoFile).Length)
        )
        Assert-Throws { Invoke-CleanerJson $cleanerRoot $protectedAcervoManifest -TestTemporaryRoot | Out-Null } 'protected acervo directory is rejected'

        $rootZipName = 'TCE-Acervo-Atualizado-227-2026-09-05.zip'
        $rootZipFile = Join-Path $cleanerRoot $rootZipName
        New-TestFile $rootZipFile 'ROOT-ZIP-DUPLICATE'
        $rootZipHash = (Get-FileHash -LiteralPath $rootZipFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $rootZipManifest = Join-Path $cleanerRoot 'root-zip-manifest.json'
        Write-CleanupManifest $rootZipManifest $cleanerRoot @(
            (New-CleanupEntry $rootZipName $rootZipHash ([IO.FileInfo]$rootZipFile).Length)
        )
        $rootZipResult = Invoke-CleanerJson $cleanerRoot $rootZipManifest -TestTemporaryRoot
        Assert-Equal ([string]$rootZipResult.mode) 'whatif' 'root-level duplicate zip keeps whatif mode'
        Assert-Equal ([int]$rootZipResult.approved_items) 1 'approved root-level leaf file starting with tce-acervo is accepted'
        Assert-True (Test-Path -LiteralPath $rootZipFile -PathType Leaf) 'root-level duplicate zip is not moved in whatif'

        $reparseTarget = Join-Path $cleanerRoot 'reparse-target.txt'
        $reparsePath = Join-Path $cleanerRoot 'reparse-link.txt'
        New-TestFile $reparseTarget 'REPARSE'
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        @(& cmd.exe /c mklink $reparsePath $reparseTarget 2>&1) | Out-Null
        $reparseCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $reparsePath)
        $ErrorActionPreference = $previousErrorActionPreference
        $reparseRelative = 'reparse-link.txt'
        $reparseKind = 'file symlink'
        if (-not $reparseCreated) {
            $reparseDirectoryTarget = Join-Path $cleanerRoot 'reparse-directory-target'
            $reparseDirectory = Join-Path $cleanerRoot 'reparse-directory'
            New-TestFile (Join-Path $reparseDirectoryTarget 'child.txt') 'REPARSE'
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            @(& cmd.exe /c mklink /J $reparseDirectory $reparseDirectoryTarget 2>&1) | Out-Null
            $reparseCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $reparseDirectory -PathType Container)
            $ErrorActionPreference = $previousErrorActionPreference
            $reparsePath = $reparseDirectory
            $reparseTarget = Join-Path $reparseDirectoryTarget 'child.txt'
            $reparseRelative = 'reparse-directory\child.txt'
            $reparseKind = 'directory junction fallback'
        }
        Assert-True $reparseCreated ('cleanup fixture creates ' + $reparseKind)
        if ($reparseCreated) {
            $reparseHash = (Get-FileHash -LiteralPath $reparseTarget -Algorithm SHA256).Hash.ToLowerInvariant()
            $reparseManifest = Join-Path $cleanerRoot 'reparse-manifest.json'
            Write-CleanupManifest $reparseManifest $cleanerRoot @(
                (New-CleanupEntry $reparseRelative $reparseHash ([IO.FileInfo]$reparseTarget).Length)
            )
            Assert-Throws { Invoke-CleanerJson $cleanerRoot $reparseManifest -TestTemporaryRoot | Out-Null } 'reparse target is rejected'
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            if ($reparseKind -eq 'file symlink') {
                @(& cmd.exe /c del $reparsePath 2>&1) | Out-Null
            } else {
                @(& cmd.exe /c rmdir $reparsePath 2>&1) | Out-Null
            }
            $ErrorActionPreference = $previousErrorActionPreference
        }

        $outsideQuarantineRoot = Join-Path $outsideRoot 'outside-quarantine'
        New-Item -ItemType Directory -Path $outsideQuarantineRoot -Force | Out-Null
        $quarantineParent = Join-Path $cleanerRoot 'tmp'
        New-Item -ItemType Directory -Path $quarantineParent -Force | Out-Null
        $quarantineLink = Join-Path $quarantineParent 'quarantine'
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        @(& cmd.exe /c mklink /J $quarantineLink $outsideQuarantineRoot 2>&1) | Out-Null
        $quarantineLinkCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $quarantineLink -PathType Container)
        $ErrorActionPreference = $previousErrorActionPreference
        Assert-True $quarantineLinkCreated 'cleanup fixture creates external quarantine junction'
        if ($quarantineLinkCreated) {
            Assert-Throws { Invoke-CleanerJson $cleanerRoot $whatIfManifest -TestTemporaryRoot | Out-Null } 'quarantine destination outside root is rejected'
            $previousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            @(& cmd.exe /c rmdir $quarantineLink 2>&1) | Out-Null
            $ErrorActionPreference = $previousErrorActionPreference
        }

        $applyFile = Join-Path $cleanerRoot 'apply.txt'
        New-TestFile $applyFile 'APPLY-CONTENT'
        $applyHash = (Get-FileHash -LiteralPath $applyFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $applyManifest = Join-Path $cleanerRoot 'apply-manifest.json'
        Write-CleanupManifest $applyManifest $cleanerRoot @(
            (New-CleanupEntry 'apply.txt' $applyHash ([IO.FileInfo]$applyFile).Length)
        )
        $applyResult = Invoke-CleanerJson $cleanerRoot $applyManifest -Apply -TestTemporaryRoot
        Assert-Equal $applyResult.mode 'apply' 'apply mode is explicit'
        Assert-True (-not (Test-Path -LiteralPath $applyFile)) 'apply moves approved source'
        Assert-True (Test-Path -LiteralPath $applyResult.receipt -PathType Leaf) 'apply writes receipt'
        $receipt = Get-Content -LiteralPath $applyResult.receipt -Raw | ConvertFrom-Json
        Assert-Equal ([int]$receipt.items.Count) 1 'receipt records moved item'
        Assert-Equal $receipt.items[0].sha256 $applyHash 'receipt records approved hash'
        Assert-Equal $receipt.items[0].result 'moved' 'receipt records move result'
        Assert-Equal (Get-FileHash -LiteralPath $receipt.items[0].destination -Algorithm SHA256).Hash.ToLowerInvariant() $applyHash 'happy path confere hash pós-movimento no destino'

        Assert-Throws { Invoke-CleanerJson $cleanerRoot (Join-Path $cleanerRoot 'tmp') -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'purge refuses broad tmp target'
        $purgeResult = Invoke-CleanerJson $cleanerRoot $applyResult.receipt -PurgeQuarantine -TestTemporaryRoot
        Assert-Equal $purgeResult.mode 'purge' 'purge mode is explicit'
        Assert-True (-not (Test-Path -LiteralPath $receipt.quarantine_root)) 'purge removes only receipted quarantine'

        # Hardening pós-review-3 (Fase 0.8). RED: estes contratos são escritos
        # antes da implementação correspondente no cleaner.
        $trailingRootFile = Join-Path $cleanerRoot 'trailing-root.txt'
        New-TestFile $trailingRootFile 'TRAILING-ROOT-CONTENT'
        $trailingRootHash = (Get-FileHash -LiteralPath $trailingRootFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $trailingRootManifest = Join-Path $cleanerRoot 'trailing-root-manifest.json'
        Write-CleanupManifest $trailingRootManifest $cleanerRoot @(
            (New-CleanupEntry 'trailing-root.txt' $trailingRootHash ([IO.FileInfo]$trailingRootFile).Length)
        )
        $trailingRootResult = Invoke-CleanerJson ($cleanerRoot + '\') $trailingRootManifest -TestTemporaryRoot
        Assert-Equal ([string]$trailingRootResult.mode) 'whatif' 'raiz com separador final é normalizada'
        Assert-Equal ([int]$trailingRootResult.approved_items) 1 'raiz normalizada aprova os itens esperados'

        $chromeProfileFile = Join-Path $cleanerRoot 'work\chrome-qa-profile\cookies.txt'
        New-TestFile $chromeProfileFile 'CHROME-QA-COOKIE'
        $chromeProfileHash = (Get-FileHash -LiteralPath $chromeProfileFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $chromeProfileManifest = Join-Path $cleanerRoot 'chrome-profile-manifest.json'
        Write-CleanupManifest $chromeProfileManifest $cleanerRoot @(
            (New-CleanupEntry 'work\chrome-qa-profile\cookies.txt' $chromeProfileHash ([IO.FileInfo]$chromeProfileFile).Length)
        )
        $browserWhatIf = Invoke-CleanerJson $cleanerRoot $chromeProfileManifest -TestTemporaryRoot -TestRunningProcesses @('chrome')
        Assert-Equal ([string]$browserWhatIf.mode) 'whatif' 'whatif não bloqueia perfil de navegador'

        $browserOwner = [pscustomobject]@{
            Name = 'chrome'
            UserDataDir = [IO.Path]::GetFullPath((Join-Path $cleanerRoot 'work\chrome-qa-profile'))
        }
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $chromeProfileManifest -Apply -TestTemporaryRoot -TestBrowserProcesses @($browserOwner) | Out-Null } 'running browser process' 'apply recusa posse declarada do perfil de navegador'
        Assert-Equal ([IO.File]::ReadAllText($chromeProfileFile)) 'CHROME-QA-COOKIE' 'origem do perfil permanece intacta quando bloqueada'
        Assert-ThrowsContaining { & $cleanerPath -Root $fixtureRoot -ManifestPath $chromeProfileManifest -Apply -TestBrowserProcesses @($browserOwner) } 'requires TestTemporaryRoot' 'TestBrowserProcesses exige TestTemporaryRoot'

        $browserApply = $null
        try { $browserApply = Invoke-CleanerJson $cleanerRoot $chromeProfileManifest -Apply -TestTemporaryRoot -TestRunningProcesses @('chrome') } catch { }
        Assert-True ($null -ne $browserApply) 'perfil de navegador é permitido sem posse declarada quando arquivo está exclusivo'
        if ($null -ne $browserApply) {
            Assert-Equal ([string]$browserApply.mode) 'apply' 'perfil de navegador permitido reporta apply'
            Assert-True (-not (Test-Path -LiteralPath $chromeProfileFile)) 'perfil de navegador é movido sem posse declarada quando arquivo está exclusivo'
            $browserPurge = Invoke-CleanerJson $cleanerRoot $browserApply.receipt -PurgeQuarantine -TestTemporaryRoot
            Assert-Equal ([int]$browserPurge.purged_items) 1 'quarentena do perfil pode ser purgada'
        }
        Assert-ThrowsContaining { & $cleanerPath -Root $fixtureRoot -ManifestPath $chromeProfileManifest -Apply -TestRunningProcesses @('chrome') } 'requires TestTemporaryRoot' 'TestRunningProcesses exige TestTemporaryRoot'

        $explicitWhatIfRoot = Join-Path $outsideRoot 'explicit-whatif'
        New-Item -ItemType Directory -Path $explicitWhatIfRoot -Force | Out-Null
        $explicitWhatIfFile = Join-Path $explicitWhatIfRoot 'explicit-whatif.txt'
        New-TestFile $explicitWhatIfFile 'EXPLICIT-WHATIF-CONTENT'
        $explicitWhatIfHash = (Get-FileHash -LiteralPath $explicitWhatIfFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $explicitWhatIfManifest = Join-Path $explicitWhatIfRoot 'explicit-whatif-manifest.json'
        Write-CleanupManifest $explicitWhatIfManifest $explicitWhatIfRoot @(
            (New-CleanupEntry 'explicit-whatif.txt' $explicitWhatIfHash ([IO.FileInfo]$explicitWhatIfFile).Length)
        )
        $explicitWhatIf = $null
        try { $explicitWhatIf = Invoke-CleanerJson $explicitWhatIfRoot $explicitWhatIfManifest -WhatIf -TestTemporaryRoot } catch { }
        Assert-Equal ([string]$explicitWhatIf.mode) 'whatif' '-WhatIf explícito mantém modo whatif'
        $explicitApplyWhatIf = $null
        try { $explicitApplyWhatIf = Invoke-CleanerJson $explicitWhatIfRoot $explicitWhatIfManifest -Apply -WhatIf -TestTemporaryRoot } catch { }
        Assert-Equal ([string]$explicitApplyWhatIf.mode) 'whatif' '-Apply -WhatIf não entra em apply'
        Assert-True (Test-Path -LiteralPath $explicitWhatIfFile -PathType Leaf) '-Apply -WhatIf mantém a origem intacta'
        Assert-True (-not (Test-Path -LiteralPath (Join-Path $explicitWhatIfRoot 'tmp\quarantine'))) '-Apply -WhatIf não cria quarentena'

        $sourceLockRoot = Join-Path $outsideRoot 'source-lock'
        New-Item -ItemType Directory -Path $sourceLockRoot -Force | Out-Null
        $sourceLockFile = Join-Path $sourceLockRoot 'locked-source.txt'
        New-TestFile $sourceLockFile 'SOURCE-LOCK-MUST-REMAIN'
        $sourceLockHash = (Get-FileHash -LiteralPath $sourceLockFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $sourceLockManifest = Join-Path $sourceLockRoot 'source-lock-manifest.json'
        Write-CleanupManifest $sourceLockManifest $sourceLockRoot @(
            (New-CleanupEntry 'locked-source.txt' $sourceLockHash ([IO.FileInfo]$sourceLockFile).Length)
        )
        $sourceHolderScript = Join-Path $outsideRoot 'source-holder.ps1'
        New-TestFile $sourceHolderScript @'
param([string]$Path, [string]$ReadyPath)
$stream = $null
try {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
    [IO.File]::WriteAllText($ReadyPath, 'SOURCE-LOCK-ACQUIRED', [Text.Encoding]::ASCII)
    Start-Sleep -Seconds 120
} finally {
    if ($null -ne $stream) { $stream.Dispose() }
}
'@
        $sourceHolderReadyPath = Join-Path $outsideRoot 'source-holder.ready'
        $sourceHolderErrorPath = Join-Path $outsideRoot 'source-holder.err'
        if (Test-Path -LiteralPath $sourceHolderReadyPath) { Remove-Item -LiteralPath $sourceHolderReadyPath -Force }
        $sourceHolder = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $sourceHolderScript, '-Path', $sourceLockFile, '-ReadyPath', $sourceHolderReadyPath) -PassThru -WindowStyle Hidden -RedirectStandardError $sourceHolderErrorPath
        try {
            $sourceHolderReady = $false
            $sourceHolderDeadline = (Get-Date).AddSeconds(20)
            while (-not $sourceHolderReady -and (Get-Date) -lt $sourceHolderDeadline) {
                if (Test-Path -LiteralPath $sourceHolderReadyPath -PathType Leaf) {
                    $sourceHolderReady = ([IO.File]::ReadAllText($sourceHolderReadyPath)).Contains('SOURCE-LOCK-ACQUIRED')
                }
                if (-not $sourceHolderReady) { Start-Sleep -Milliseconds 200 }
            }
            Assert-True $sourceHolderReady 'processo auxiliar segura a origem com FileShare None'
            if ($sourceHolderReady) {
                Assert-ThrowsContaining { Invoke-CleanerJson $sourceLockRoot $sourceLockManifest -Apply -TestTemporaryRoot | Out-Null } 'source file is in use' 'apply recusa origem pinada que está em uso'
            }
        } finally {
            if ($null -ne $sourceHolder -and -not $sourceHolder.HasExited) {
                Stop-Process -Id $sourceHolder.Id -Force
                $sourceHolder.WaitForExit()
            }
        }
        Assert-Equal ([IO.File]::ReadAllText($sourceLockFile)) 'SOURCE-LOCK-MUST-REMAIN' 'origem permanece intacta quando o handle não pode ser aberto'

        $denyProfileFile = Join-Path $cleanerRoot 'work\chrome-deny-profile\cookies.txt'
        New-TestFile $denyProfileFile 'DENY-PROFILE-MUST-REMAIN'
        $denyProfileHash = (Get-FileHash -LiteralPath $denyProfileFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $denyProfileManifest = Join-Path $cleanerRoot 'chrome-deny-profile-manifest.json'
        Write-CleanupManifest $denyProfileManifest $cleanerRoot @(
            (New-CleanupEntry 'work\chrome-deny-profile\cookies.txt' $denyProfileHash ([IO.FileInfo]$denyProfileFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $denyProfileManifest -Apply -TestTemporaryRoot -TestDenyProcessEnumeration | Out-Null } 'browser process enumeration failed' 'falha de enumeração de navegador bloqueia fail-closed'
        Assert-Equal ([IO.File]::ReadAllText($denyProfileFile)) 'DENY-PROFILE-MUST-REMAIN' 'origem permanece intacta após falha de enumeração'
        Assert-ThrowsContaining { & $cleanerPath -Root $fixtureRoot -ManifestPath $denyProfileManifest -Apply -TestDenyProcessEnumeration } 'requires TestTemporaryRoot' 'TestDenyProcessEnumeration exige TestTemporaryRoot'

        $lockedProfileFile = Join-Path $cleanerRoot 'work\chrome-locked-profile\cookies.txt'
        New-TestFile $lockedProfileFile 'LOCKED-PROFILE-MUST-REMAIN'
        $lockedProfileHash = (Get-FileHash -LiteralPath $lockedProfileFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $lockedProfileManifest = Join-Path $cleanerRoot 'chrome-locked-profile-manifest.json'
        Write-CleanupManifest $lockedProfileManifest $cleanerRoot @(
            (New-CleanupEntry 'work\chrome-locked-profile\cookies.txt' $lockedProfileHash ([IO.FileInfo]$lockedProfileFile).Length)
        )
        $profileHolderReadyPath = Join-Path $outsideRoot 'profile-holder.ready'
        $profileHolderErrorPath = Join-Path $outsideRoot 'profile-holder.err'
        if (Test-Path -LiteralPath $profileHolderReadyPath) { Remove-Item -LiteralPath $profileHolderReadyPath -Force }
        $profileHolder = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $sourceHolderScript, '-Path', $lockedProfileFile, '-ReadyPath', $profileHolderReadyPath) -PassThru -WindowStyle Hidden -RedirectStandardError $profileHolderErrorPath
        try {
            $profileHolderReady = $false
            $profileHolderDeadline = (Get-Date).AddSeconds(20)
            while (-not $profileHolderReady -and (Get-Date) -lt $profileHolderDeadline) {
                if (Test-Path -LiteralPath $profileHolderReadyPath -PathType Leaf) {
                    $profileHolderReady = ([IO.File]::ReadAllText($profileHolderReadyPath)).Contains('SOURCE-LOCK-ACQUIRED')
                }
                if (-not $profileHolderReady) { Start-Sleep -Milliseconds 200 }
            }
            Assert-True $profileHolderReady 'processo auxiliar segura arquivo do perfil com FileShare None'
            if ($profileHolderReady) {
                Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $lockedProfileManifest -Apply -TestTemporaryRoot -TestRunningProcesses @('chrome') | Out-Null } 'running browser process' 'processo vivo sem posse bloqueia arquivo de perfil em uso'
            }
        } finally {
            if ($null -ne $profileHolder -and -not $profileHolder.HasExited) {
                Stop-Process -Id $profileHolder.Id -Force
                $profileHolder.WaitForExit()
            }
        }
        Assert-Equal ([IO.File]::ReadAllText($lockedProfileFile)) 'LOCKED-PROFILE-MUST-REMAIN' 'origem do perfil em uso permanece intacta'

        $fallbackFile = Join-Path $cleanerRoot 'receipt-fallback.txt'
        New-TestFile $fallbackFile 'RECEIPT-FALLBACK-CONTENT'
        $fallbackHash = (Get-FileHash -LiteralPath $fallbackFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $fallbackManifest = Join-Path $cleanerRoot 'receipt-fallback-manifest.json'
        Write-CleanupManifest $fallbackManifest $cleanerRoot @(
            (New-CleanupEntry 'receipt-fallback.txt' $fallbackHash ([IO.FileInfo]$fallbackFile).Length)
        )
        $fallbackApply = Invoke-CleanerJson $cleanerRoot $fallbackManifest -Apply -TestTemporaryRoot
        Assert-Equal ([string]$fallbackApply.mode) 'apply' 'apply cria fixture para fallback do recibo'
        [IO.File]::WriteAllText($fallbackApply.receipt, '{"schema_version":1,"items":[', (New-Object Text.UTF8Encoding($false)))
        $fallbackResume = $null
        try { $fallbackResume = Invoke-CleanerJson $cleanerRoot $fallbackManifest -Resume -TestTemporaryRoot } catch { }
        Assert-Equal ([string]$fallbackResume.mode) 'resume' 'resume usa journal quando recibo está truncado'
        if ($null -ne $fallbackResume) {
            Assert-Equal ([int]$fallbackResume.recovered_items) 1 'resume recupera item do journal com recibo truncado'
            Assert-Equal ([int]$fallbackResume.moved_items) 0 'resume não move novamente item já presente na quarentena'
            $fallbackReceipt = Get-Content -LiteralPath $fallbackResume.receipt -Raw | ConvertFrom-Json
            Assert-Equal ([int]$fallbackReceipt.items.Count) 1 'resume reescreve recibo válido com um item'
            Assert-Equal ([string]$fallbackReceipt.items[0].sha256) $fallbackHash 'recibo reescrito mantém hash do item'
            Assert-Equal (Get-FileHash -LiteralPath $fallbackReceipt.items[0].destination -Algorithm SHA256).Hash.ToLowerInvariant() $fallbackHash 'destino do recibo reescrito confere hash'
            $fallbackTemps = @(Get-ChildItem -LiteralPath $fallbackApply.quarantine_root -Filter 'receipt.json.*.tmp' -File -Force -ErrorAction SilentlyContinue)
            Assert-Equal $fallbackTemps.Count 0 'resume não deixa temporário de recibo'
            $fallbackPurge = Invoke-CleanerJson $cleanerRoot $fallbackResume.receipt -PurgeQuarantine -TestTemporaryRoot
            Assert-Equal ([int]$fallbackPurge.purged_items) 1 'purge limpa quarentena após fallback do journal'
        }

        $junctionPurge = New-ManualReceiptFixture 'junction-in-quarantine' 'listed\file.txt' 'PURGE-JUNCTION'
        $purgeJunctionTarget = Join-Path $outsideRoot 'purge-junction-target'
        New-TestFile (Join-Path $purgeJunctionTarget 'sentinel.txt') 'PURGE-JUNCTION-SENTINEL'
        $purgeJunctionPath = Join-Path $junctionPurge.QuarantineRoot 'external-junction'
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        @(& cmd.exe /c mklink /J $purgeJunctionPath $purgeJunctionTarget 2>&1) | Out-Null
        $purgeJunctionCreated = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $purgeJunctionPath -PathType Container)
        $ErrorActionPreference = $previousErrorActionPreference
        Assert-True $purgeJunctionCreated 'fixture cria junction externa dentro da quarentena'
        if ($purgeJunctionCreated) {
            Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $junctionPurge.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'reparse' 'purge recusa reparse point antes de remover'
            Assert-Equal ([IO.File]::ReadAllText((Join-Path $purgeJunctionTarget 'sentinel.txt'))) 'PURGE-JUNCTION-SENTINEL' 'purge não remove alvo externo da junction'
            Assert-True (Test-Path -LiteralPath $junctionPurge.ReceiptPath -PathType Leaf) 'purge preserva recibo quando encontra reparse'
        }

        $journalFile = Join-Path $cleanerRoot 'journal-case.txt'
        New-TestFile $journalFile 'JOURNAL-CASE-CONTENT'
        $journalHash = (Get-FileHash -LiteralPath $journalFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $journalManifest = Join-Path $cleanerRoot 'journal-case-manifest.json'
        Write-CleanupManifest $journalManifest $cleanerRoot @(
            (New-CleanupEntry 'journal-case.txt' $journalHash ([IO.FileInfo]$journalFile).Length)
        )
        $journalApply = Invoke-CleanerJson $cleanerRoot $journalManifest -Apply -TestTemporaryRoot
        Assert-Equal ([string]$journalApply.mode) 'apply' 'apply com journal conclui'
        $journalPath = Join-Path $journalApply.quarantine_root 'journal.ndjson'
        Assert-True (Test-Path -LiteralPath $journalPath -PathType Leaf) 'apply grava journal.ndjson na quarentena'
        if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
            $journalRecords = @(Get-Content -LiteralPath $journalPath | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_ | ConvertFrom-Json })
            Assert-True ($journalRecords.Count -ge 2) 'journal registra cabeçalho e plano do item'
            Assert-Equal ([string]$journalRecords[0].type) 'header' 'primeiro registro do journal é o cabeçalho'
            $journalItem = $journalRecords | Where-Object { [string]$_.type -ne 'header' } | Select-Object -First 1
            Assert-Equal ([string]$journalItem.sha256) $journalHash 'journal registra o hash aprovado'
            $journalExpectedDestination = [IO.Path]::GetFullPath((Join-Path $journalApply.quarantine_root 'journal-case.txt')).ToLowerInvariant()
            Assert-Equal ([string]$journalItem.destination).ToLowerInvariant() $journalExpectedDestination 'journal registra o destino na quarentena'
        }
        $journalPurge = Invoke-CleanerJson $cleanerRoot $journalApply.receipt -PurgeQuarantine -TestTemporaryRoot
        Assert-Equal ([string]$journalPurge.mode) 'purge' 'purge aceita quarentena com journal consistente'

        $abortFileA = Join-Path $cleanerRoot 'abort-a.txt'
        $abortFileB = Join-Path $cleanerRoot 'abort-b.txt'
        New-TestFile $abortFileA 'ABORT-A-CONTENT'
        New-TestFile $abortFileB 'ABORT-B-CONTENT'
        $abortHashA = (Get-FileHash -LiteralPath $abortFileA -Algorithm SHA256).Hash.ToLowerInvariant()
        $abortHashB = (Get-FileHash -LiteralPath $abortFileB -Algorithm SHA256).Hash.ToLowerInvariant()
        $abortManifest = Join-Path $cleanerRoot 'abort-manifest.json'
        Write-CleanupManifest $abortManifest $cleanerRoot @(
            (New-CleanupEntry 'abort-a.txt' $abortHashA ([IO.FileInfo]$abortFileA).Length),
            (New-CleanupEntry 'abort-b.txt' $abortHashB ([IO.FileInfo]$abortFileB).Length)
        )
        $abortExit = $null
        try {
            @(& $cleanerPath -Root $cleanerRoot -ManifestPath $abortManifest -Apply -TestTemporaryRoot -TestHook 'abort-after-first-move') | Out-Null
            $abortExit = $LASTEXITCODE
        } catch {
            $abortExit = -1
        }
        Assert-Equal $abortExit 70 'hook de aborto encerra o cleaner após o primeiro movimento'
        if ($abortExit -eq 70) {
            $abortQuarantines = @(Get-ChildItem -LiteralPath (Join-Path $cleanerRoot 'tmp\quarantine') -Directory -Force |
                Where-Object { $_.Name -match '^\d{8}-\d{6}-\d{3}$' } | Sort-Object Name -Descending)
            Assert-True ($abortQuarantines.Count -ge 1) 'aborto deixa quarentena parcial'
            $abortQuarantine = $abortQuarantines[0].FullName
            Assert-True (-not (Test-Path -LiteralPath (Join-Path $abortQuarantine 'receipt.json'))) 'aborto não grava recibo final'
            Assert-True (Test-Path -LiteralPath (Join-Path $abortQuarantine 'journal.ndjson') -PathType Leaf) 'aborto preserva o journal'
            $movedBeforeResume = @(Get-ChildItem -LiteralPath $abortQuarantine -File -Recurse -Force | Where-Object { $_.Name -ne 'journal.ndjson' })
            Assert-Equal $movedBeforeResume.Count 1 'aborto deixa exatamente um item na quarentena'
            Assert-True (Test-Path -LiteralPath $abortFileB -PathType Leaf) 'item não processado permanece na origem'
            $resumeResult = Invoke-CleanerJson $cleanerRoot $abortManifest -Resume -TestTemporaryRoot
            Assert-Equal ([string]$resumeResult.mode) 'resume' 'resume reporta modo próprio'
            Assert-Equal ([int]$resumeResult.recovered_items) 1 'resume recupera o item já movido'
            Assert-Equal ([int]$resumeResult.moved_items) 1 'resume move o item pendente'
            Assert-True (-not (Test-Path -LiteralPath $abortFileA) -and -not (Test-Path -LiteralPath $abortFileB)) 'resume conclui as origens'
            $resumeReceipt = Get-Content -LiteralPath $resumeResult.receipt -Raw | ConvertFrom-Json
            Assert-Equal ([int]$resumeReceipt.items.Count) 2 'recibo do resume cobre os dois itens'
            $resumeReceiptA = $resumeReceipt.items | Where-Object { [string]$_.origin -like '*abort-a.txt' } | Select-Object -First 1
            $resumeReceiptB = $resumeReceipt.items | Where-Object { [string]$_.origin -like '*abort-b.txt' } | Select-Object -First 1
            Assert-Equal ([string]$resumeReceiptA.sha256) $abortHashA 'recibo do resume mantém hash do item recuperado'
            Assert-Equal (Get-FileHash -LiteralPath $resumeReceiptA.destination -Algorithm SHA256).Hash.ToLowerInvariant() $abortHashA 'destino recuperado confere hash'
            Assert-Equal ([string]$resumeReceiptB.sha256) $abortHashB 'recibo do resume mantém hash do item pendente'
            Assert-Equal (Get-FileHash -LiteralPath $resumeReceiptB.destination -Algorithm SHA256).Hash.ToLowerInvariant() $abortHashB 'destino movido confere hash'
            $resumeAgain = Invoke-CleanerJson $cleanerRoot $abortManifest -Resume -TestTemporaryRoot
            Assert-Equal ([int]$resumeAgain.recovered_items) 2 'resume repetido recupera tudo'
            Assert-Equal ([int]$resumeAgain.moved_items) 0 'resume repetido não move nada'
            $resumePurge = Invoke-CleanerJson $cleanerRoot $resumeResult.receipt -PurgeQuarantine -TestTemporaryRoot
            Assert-Equal ([int]$resumePurge.purged_items) 2 'purge limpa a quarentena retomada'
        }

        $orphanRoot = Join-Path $outsideRoot 'orphan-cases'
        New-Item -ItemType Directory -Path $orphanRoot -Force | Out-Null
        $orphanFile = Join-Path $orphanRoot 'orphan.txt'
        New-TestFile $orphanFile 'ORPHAN-CONTENT'
        $orphanHash = (Get-FileHash -LiteralPath $orphanFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $orphanManifest = Join-Path $orphanRoot 'orphan-manifest.json'
        Write-CleanupManifest $orphanManifest $orphanRoot @(
            (New-CleanupEntry 'orphan.txt' $orphanHash ([IO.FileInfo]$orphanFile).Length)
        )
        Assert-ThrowsContaining { Invoke-CleanerJson $orphanRoot $orphanManifest -Resume -TestTemporaryRoot | Out-Null } 'no resumable quarantine' 'resume sem journal é recusado'
        Assert-ThrowsContaining { Invoke-CleanerJson $orphanRoot $orphanManifest -Apply -Resume -TestTemporaryRoot | Out-Null } 'mutually exclusive' 'Apply e Resume são mutuamente exclusivos'

        $missingDestinationRoot = Join-Path $outsideRoot 'missing-destination'
        New-Item -ItemType Directory -Path $missingDestinationRoot -Force | Out-Null
        $missingDestinationFile = Join-Path $missingDestinationRoot 'missing-destination.txt'
        New-TestFile $missingDestinationFile 'MISSING-DESTINATION-CONTENT'
        $missingDestinationHash = (Get-FileHash -LiteralPath $missingDestinationFile -Algorithm SHA256).Hash.ToLowerInvariant()
        $missingDestinationManifest = Join-Path $missingDestinationRoot 'missing-destination-manifest.json'
        Write-CleanupManifest $missingDestinationManifest $missingDestinationRoot @(
            (New-CleanupEntry 'missing-destination.txt' $missingDestinationHash ([IO.FileInfo]$missingDestinationFile).Length)
        )
        $missingDestinationExit = $null
        try {
            @(& $cleanerPath -Root $missingDestinationRoot -ManifestPath $missingDestinationManifest -Apply -TestTemporaryRoot -TestHook 'abort-after-first-move') | Out-Null
            $missingDestinationExit = $LASTEXITCODE
        } catch {
            $missingDestinationExit = -1
        }
        if ($missingDestinationExit -eq 70) {
            $missingDestinationQuarantine = @(Get-ChildItem -LiteralPath (Join-Path $missingDestinationRoot 'tmp\quarantine') -Directory -Force | Sort-Object Name -Descending)[0].FullName
            Remove-Item -LiteralPath (Join-Path $missingDestinationQuarantine 'missing-destination.txt') -Force
            Assert-ThrowsContaining { Invoke-CleanerJson $missingDestinationRoot $missingDestinationManifest -Resume -TestTemporaryRoot | Out-Null } 'resume destination is missing' 'resume falha quando o destino sumiu da quarentena'
        }

        $lockFunctionReady = $false
        $lockName = $null
        try {
            Import-CleanerFunction $cleanerPath 'Get-CleanupLockName'
            $lockName = [string](Get-CleanupLockName -RootPath $cleanerRoot)
            $lockFunctionReady = -not [string]::IsNullOrWhiteSpace($lockName)
        } catch {
            $lockFunctionReady = $false
        }
        Assert-True $lockFunctionReady 'cleaner expõe nome de lock estável derivado da raiz'
        if ($lockFunctionReady) {
            $lockSourceFile = Join-Path $cleanerRoot 'lock-case.txt'
            New-TestFile $lockSourceFile 'LOCK-CASE-CONTENT'
            $lockSourceHash = (Get-FileHash -LiteralPath $lockSourceFile -Algorithm SHA256).Hash.ToLowerInvariant()
            $lockManifest = Join-Path $cleanerRoot 'lock-case-manifest.json'
            Write-CleanupManifest $lockManifest $cleanerRoot @(
                (New-CleanupEntry 'lock-case.txt' $lockSourceHash ([IO.FileInfo]$lockSourceFile).Length)
            )
            $holderScript = Join-Path $outsideRoot 'lock-holder.ps1'
            New-TestFile $holderScript @'
param([string]$Name, [string]$ReadyPath)
$mutex = New-Object System.Threading.Mutex($false, $Name)
$acquired = $false
$deadline = (Get-Date).AddSeconds(30)
while (-not $acquired -and (Get-Date) -lt $deadline) {
    $acquired = $mutex.WaitOne(0)
    if (-not $acquired) { Start-Sleep -Milliseconds 50 }
}
if (-not $acquired) {
    Set-Content -LiteralPath $ReadyPath -Value 'HOLDER-FAILED' -Encoding ASCII
    exit 2
}
Set-Content -LiteralPath $ReadyPath -Value 'HOLDER-ACQUIRED' -Encoding ASCII
Start-Sleep -Seconds 120
[void]$mutex.ReleaseMutex()
'@
            $holderOutput = Join-Path $outsideRoot 'lock-holder.out'
            $holderError = Join-Path $outsideRoot 'lock-holder.err'
            if (Test-Path -LiteralPath $holderOutput -PathType Leaf) { Remove-Item -LiteralPath $holderOutput -Force }
            $holder = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $holderScript, '-Name', $lockName, '-ReadyPath', $holderOutput) -PassThru -WindowStyle Hidden -RedirectStandardError $holderError
            try {
                $holderReady = $false
                $holderDeadline = (Get-Date).AddSeconds(20)
                while (-not $holderReady -and (Get-Date) -lt $holderDeadline) {
                    if (Test-Path -LiteralPath $holderOutput -PathType Leaf) {
                        $holderText = ''
                        try {
                            $holderText = [IO.File]::ReadAllText($holderOutput)
                        } catch {
                            $holderText = ''
                        }
                        $holderReady = $holderText.Contains('HOLDER-ACQUIRED')
                    }
                    if (-not $holderReady) { Start-Sleep -Milliseconds 200 }
                }
                Assert-True $holderReady 'processo auxiliar segura o lock nomeado'
                if ($holderReady) {
                    Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $lockManifest -Apply -TestTemporaryRoot | Out-Null } 'another cleanup operation is already running' 'apply concorrente é recusado pelo lock'
                    Assert-Equal ([IO.File]::ReadAllText($lockSourceFile)) 'LOCK-CASE-CONTENT' 'origem permanece intacta sob lock'
                }
            } finally {
                if ($null -ne $holder -and -not $holder.HasExited) { Stop-Process -Id $holder.Id -Force }
            }
            $lockApply = Invoke-CleanerJson $cleanerRoot $lockManifest -Apply -TestTemporaryRoot
            Assert-Equal ([string]$lockApply.mode) 'apply' 'lock liberado permite apply'
            Assert-True (-not (Test-Path -LiteralPath $lockSourceFile)) 'apply pós-lock move a origem'
            $lockPurge = Invoke-CleanerJson $cleanerRoot $lockApply.receipt -PurgeQuarantine -TestTemporaryRoot
            Assert-Equal ([int]$lockPurge.purged_items) 1 'purge pós-lock limpa a quarentena'
        }

        $forgedJournal = New-ManualReceiptFixture 'forged-journal-unknown' 'listed\file.txt' 'FORGED-JOURNAL'
        $forgedJournalHeader = [ordered]@{
            type = 'header'
            schema_version = 1
            root = [IO.Path]::GetFullPath($cleanerRoot)
            quarantine_root = [IO.Path]::GetFullPath($forgedJournal.QuarantineRoot)
            created_at = [DateTime]::UtcNow.ToString('o')
        }
        $forgedJournalItem = [ordered]@{
            type = 'item'
            result = 'planned'
            origin = [IO.Path]::GetFullPath((Join-Path $cleanerRoot 'other\file.txt'))
            destination = [IO.Path]::GetFullPath((Join-Path $forgedJournal.QuarantineRoot 'other\file.txt'))
            sha256 = [string]$forgedJournal.Item.sha256
            bytes = [int64]$forgedJournal.Item.bytes
            timestamp = [DateTime]::UtcNow.ToString('o')
        }
        $forgedJournalText = (($forgedJournalHeader | ConvertTo-Json -Compress) + [Environment]::NewLine + ($forgedJournalItem | ConvertTo-Json -Compress) + [Environment]::NewLine)
        New-TestFile (Join-Path $forgedJournal.QuarantineRoot 'journal.ndjson') $forgedJournalText
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $forgedJournal.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'receipt has no item for journal destination' 'purge recusa journal com destino fora do recibo'

        $noHeaderJournal = New-ManualReceiptFixture 'forged-journal-no-header' 'listed\file.txt' 'FORGED-JOURNAL-NO-HEADER'
        $noHeaderItem = [ordered]@{
            type = 'item'
            result = 'planned'
            origin = [IO.Path]::GetFullPath((Join-Path $cleanerRoot 'listed\file.txt'))
            destination = [IO.Path]::GetFullPath($noHeaderJournal.Destination)
            sha256 = [string]$noHeaderJournal.Item.sha256
            bytes = [int64]$noHeaderJournal.Item.bytes
            timestamp = [DateTime]::UtcNow.ToString('o')
        }
        New-TestFile (Join-Path $noHeaderJournal.QuarantineRoot 'journal.ndjson') (($noHeaderItem | ConvertTo-Json -Compress) + [Environment]::NewLine)
        Assert-ThrowsContaining { Invoke-CleanerJson $cleanerRoot $noHeaderJournal.ReceiptPath -PurgeQuarantine -TestTemporaryRoot | Out-Null } 'journal item precedes header' 'purge recusa journal sem cabeçalho'
    }
} finally {
    if (Test-Path -LiteralPath $fixtureRoot) { Remove-Item -LiteralPath $fixtureRoot -Recurse -Force }
    if (Test-Path -LiteralPath $outsideRoot) { Remove-Item -LiteralPath $outsideRoot -Recurse -Force }
}

$expectedCases = 307
if ($script:passed -ne $expectedCases) {
    $script:failed++
    Write-Host "FALHOU: contagem fixa de casos (esperado=$expectedCases; recebido=$script:passed)" -ForegroundColor Red
    exit 1
}
Write-Host "PASSOU: contagem fixa de casos ($expectedCases)" -ForegroundColor Green

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
