# Test-DocumentationTracking.ps1
# Windows PowerShell 5.1-compatible documentation tracking checks.
# The checks are repository-facing: they verify canonical paths,
# reconciliation of the two hybrid-plan sources, and README safety language.

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

function Test-GitIgnored {
    param([string]$RepoRoot, [string]$RelativePath)

    # -C ancora a consulta na raiz do repositorio: sem ele o git resolve
    # $RelativePath contra o diretorio de trabalho herdado e um caminho como
    # README.md passa a significar work/tce-extractor/README.md quando o
    # verificador executa este teste a partir de work/tce-extractor.
    & git -C $RepoRoot check-ignore -q -- $RelativePath 2>$null
    $gitExitCode = $LASTEXITCODE
    if ($gitExitCode -ne 0) {
        $gitArguments = @('-C', $RepoRoot, '-c', "safe.directory=$RepoRoot", 'check-ignore', '-q', '--', $RelativePath)
        & git @gitArguments 2>$null
        $gitExitCode = $LASTEXITCODE
    }
    return ($gitExitCode -eq 0)
}

$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$readmePath = Join-Path $projectRoot 'README.md'
$sourcePlan = 'docs/superpowers/plans/2026-09-10-fluxo-hibrido-lotes.md'
$sourceSpec = 'docs/notes/2026-09-10-fluxo-hibrido-lotes-spec.md'
$canonicalPlan = 'docs/notes/2026-09-10-fluxo-hibrido-lotes.md'

$canonicalDocuments = @(
    'README.md',
    'docs/notes/2026-09-08-fundamentacao-automatico-plano-fases.md',
    'docs/notes/2026-09-10-plano-consolidacao-main-e-conclusao.md',
    'docs/notes/2026-09-10-consolidacao-main-e-conclusao-spec.md',
    'docs/notes/2026-09-10-consolidacao-main-e-conclusao-handoff.md',
    $sourceSpec,
    $canonicalPlan
)

foreach ($relativePath in $canonicalDocuments) {
    $absolutePath = Join-Path $projectRoot $relativePath
    Assert-True (Test-Path -LiteralPath $absolutePath -PathType Leaf) "documento canonico existe: $relativePath"
    if (Test-Path -LiteralPath $absolutePath -PathType Leaf) {
        Assert-True (-not (Test-GitIgnored $projectRoot $relativePath)) "documento canonico nao e ignorado: $relativePath"
    }
}

$sourcePlanPath = Join-Path $projectRoot $sourcePlan
$canonicalPlanPath = Join-Path $projectRoot $canonicalPlan
$sourceSpecPath = Join-Path $projectRoot $sourceSpec
$hasSourcePlan = Test-Path -LiteralPath $sourcePlanPath -PathType Leaf
$hasCanonicalPlan = Test-Path -LiteralPath $canonicalPlanPath -PathType Leaf
$sourcePlanIgnored = Test-GitIgnored $projectRoot $sourcePlan
$reconciliationRegistered = $false

if ($hasCanonicalPlan) {
    $canonicalText = [IO.File]::ReadAllText($canonicalPlanPath)
    $reconciliationRegistered =
        # Keep the matcher ASCII-safe for a UTF-8 script without a BOM under
        # Windows PowerShell 5.1; the full heading remains Portuguese in docs.
        ($canonicalText -match '(?im)^##\s+Registro de reconcilia') -and
        ($canonicalText -match [regex]::Escape($sourcePlan)) -and
        ($canonicalText -match [regex]::Escape($sourceSpec))
}

Assert-True (-not ($hasSourcePlan -and $hasCanonicalPlan) -or $reconciliationRegistered) 'planos hibridos divergentes/redundantes tem reconciliacao registrada'
Assert-True (-not $sourcePlanIgnored -or ($hasCanonicalPlan -and $reconciliationRegistered)) 'plano hibrido ignorado so permanece como fonte superseded apos reconciliacao'

$readmeText = if (Test-Path -LiteralPath $readmePath -PathType Leaf) {
    [IO.File]::ReadAllText($readmePath)
} else {
    ''
}

Assert-True ($readmeText -match '(?is)acervo\s+privado.{0,240}227\s+processos') 'README distingue acervo privado de 227 processos'
Assert-True ($readmeText -match '(?is)runtime.{0,80}fase11k') 'README identifica o runtime fase11k'
Assert-True ($readmeText -match '(?is)envio\s+autom\u00E1tico.{0,240}real_send_enabled\s*=\s*false') 'README declara envio automatico desabilitado por padrao'
Assert-True ($readmeText -match '(?is)INICIAR\.cmd\s+envio-real') 'README declara o comando explicito de envio real'

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
