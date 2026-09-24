$ErrorActionPreference = 'Stop'

$testRoot = $PSScriptRoot
$launcherPath = Join-Path $testRoot '..\Abrir-Chrome-QA.bat'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $testRoot '..\..\..'))
$chromeFixture = Join-Path $env:SystemRoot 'System32\notepad.exe'
$customUrl = 'https://qa.example.invalid/test?case=42'

if (-not (Test-Path -LiteralPath $chromeFixture -PathType Leaf)) {
    throw "Executável de teste indisponível: $chromeFixture"
}

$planJson = (& $launcherPath -PlanOnly -ChromePath $chromeFixture -Url $customUrl) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "O .bat encerrou com código $LASTEXITCODE." }
$plan = ConvertFrom-Json -InputObject $planJson
$defaultPlanJson = (& $launcherPath -PlanOnly -ChromePath $chromeFixture) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "O .bat encerrou com código $LASTEXITCODE ao usar a URL padrão." }
$defaultPlan = ConvertFrom-Json -InputObject $defaultPlanJson
$expectedProfile = Join-Path $repoRoot 'dados-locais\chrome-qa-profile'
$expectedExtension = Join-Path $testRoot '..\portable\extensao-complementar-ato'
$expectedExtension = [IO.Path]::GetFullPath($expectedExtension)

$checks = @(
    [pscustomobject]@{ Name = 'usa o perfil privado padrão do QA'; Passed = $plan.profilePath -eq $expectedProfile },
    [pscustomobject]@{ Name = 'inicia o Chrome com o perfil privado'; Passed = $plan.arguments -contains "--user-data-dir=$expectedProfile" },
    [pscustomobject]@{ Name = 'carrega a extensão do extrator'; Passed = $plan.extensionPath -eq $expectedExtension },
    [pscustomobject]@{ Name = 'expõe DevTools na porta CDP 9222'; Passed = $plan.arguments -contains '--remote-debugging-port=9222' },
    [pscustomobject]@{ Name = 'informa o endpoint CDP local'; Passed = $plan.devToolsUrl -eq 'http://127.0.0.1:9222' },
    [pscustomobject]@{ Name = 'mantém CDP restrito ao loopback'; Passed = $plan.arguments -contains '--remote-debugging-address=127.0.0.1' },
    [pscustomobject]@{ Name = 'abre o painel DevTools nas abas'; Passed = $plan.arguments -contains '--auto-open-devtools-for-tabs' },
    [pscustomobject]@{ Name = 'limita extensões à extensão em teste'; Passed = $plan.arguments -contains "--disable-extensions-except=$expectedExtension" },
    [pscustomobject]@{ Name = 'carrega a extensão local'; Passed = $plan.arguments -contains "--load-extension=$expectedExtension" },
    [pscustomobject]@{ Name = 'aceita uma URL de teste opcional'; Passed = $plan.arguments[-1] -eq $customUrl },
    [pscustomobject]@{ Name = 'usa about:blank quando não há URL'; Passed = $defaultPlan.arguments[-1] -eq 'about:blank' }
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
