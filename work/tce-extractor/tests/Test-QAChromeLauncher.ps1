$ErrorActionPreference = 'Stop'

$testRoot = $PSScriptRoot
$launcherPath = Join-Path $testRoot '..\Abrir-Chrome-QA.bat'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $testRoot '..\..\..'))
$customUrl = 'https://qa.example.invalid/test?case=42'
$planJson = (& $launcherPath -PlanOnly -Url $customUrl) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "O .bat encerrou com código $LASTEXITCODE." }
$plan = ConvertFrom-Json -InputObject $planJson
$launcherScript = Join-Path $testRoot '..\Abrir-Chrome-QA.ps1'
$portalLabPlan = ConvertFrom-Json -InputObject ((& $launcherScript -PlanOnly) -join "`n")
if ($LASTEXITCODE -ne 0) { throw "O launcher PowerShell encerrou com código $LASTEXITCODE." }
$defaultPlanJson = (& $launcherPath -PlanOnly) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "O .bat encerrou com código $LASTEXITCODE ao usar a URL padrão." }
$defaultPlan = ConvertFrom-Json -InputObject $defaultPlanJson
$expectedProfile = Join-Path $env:LOCALAPPDATA 'Atos-TCE\Chrome-QA-Playwright'
$expectedExtension = [IO.Path]::GetFullPath((Join-Path $repoRoot 'extension'))
$runnerPath = Join-Path $repoRoot 'scripts\portal-lab\launch-qa-chromium.mjs'
$runnerSource = Get-Content -Raw -LiteralPath $runnerPath

$checks = @(
    [pscustomobject]@{ Name = 'usa Chromium gerenciado pelo Playwright'; Passed = $plan.browserEngine -eq 'playwright-chromium' },
    [pscustomobject]@{ Name = 'carrega a extensão-fonte da Mesa'; Passed = $plan.extensionRoot -eq $expectedExtension },
    [pscustomobject]@{ Name = 'usa perfil novo fora do repositório'; Passed = $plan.profileRoot -eq $expectedProfile -and -not $plan.profileRoot.StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase) },
    [pscustomobject]@{ Name = 'expõe CDP local na porta 9222'; Passed = $plan.devToolsUrl -eq 'http://127.0.0.1:9222' },
    [pscustomobject]@{ Name = 'passa a URL ao runner'; Passed = $plan.url -eq $customUrl },
    [pscustomobject]@{ Name = 'usa about:blank por padrão'; Passed = $defaultPlan.url -eq 'about:blank' },
    [pscustomobject]@{ Name = 'runner usa contexto persistente e Chromium'; Passed = $runnerSource.Contains('launchPersistentContext') -and $runnerSource.Contains('channel: "chromium"') },
    [pscustomobject]@{ Name = 'runner permite a extensão unpacked'; Passed = $runnerSource.Contains('ignoreDefaultArgs: ["--disable-extensions"]') -and $runnerSource.Contains('--load-extension=') -and $runnerSource.Contains('--disable-extensions-except=') },
    [pscustomobject]@{ Name = 'runner verifica a extensão pela service worker'; Passed = $runnerSource.Contains('chrome.runtime.getManifest()') },
    [pscustomobject]@{ Name = 'runner expõe CDP apenas no loopback'; Passed = $runnerSource.Contains('--remote-debugging-address=127.0.0.1') -and $runnerSource.Contains('--remote-debugging-port=') },
    [pscustomobject]@{ Name = 'launcher não depende dos flags removidos do Chrome estável'; Passed = $plan.browserEngine -ne 'google-chrome-stable' }
)

foreach ($check in $checks) {
    if (-not $check.Passed) {
        Write-Host "FALHOU: $($check.Name)" -ForegroundColor Red
    } else {
        Write-Host "PASSOU: $($check.Name)" -ForegroundColor Green
    }
}

$failed = @($checks | Where-Object { -not $_.Passed }).Count
Write-Host ("Resultado: {0} aprovadas; {1} falharam." -f ($checks.Count - $failed), $failed)
if ($failed -gt 0) { exit 1 }
