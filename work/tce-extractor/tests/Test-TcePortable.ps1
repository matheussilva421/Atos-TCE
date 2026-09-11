$ErrorActionPreference = 'Stop'

$testDirectory = if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) { (Get-Location).Path } else { $PSScriptRoot }
$modulePath = [IO.Path]::GetFullPath((Join-Path $testDirectory '..\portable\TcePortable.Core.psm1'))
Import-Module $modulePath -Force

$script:passed = 0
$script:failed = 0

function Assert-Equal {
    param($Actual, $Expected, [string]$Name)
    if (($Actual | ConvertTo-Json -Compress -Depth 20) -ne ($Expected | ConvertTo-Json -Compress -Depth 20)) {
        $script:failed++
        Write-Host "FALHOU: $Name`n  esperado: $($Expected | ConvertTo-Json -Compress)`n  recebido: $($Actual | ConvertTo-Json -Compress)" -ForegroundColor Red
    } else {
        $script:passed++
        Write-Host "PASSOU: $Name" -ForegroundColor Green
    }
}

function Assert-True {
    param([bool]$Condition, [string]$Name)
    Assert-Equal $Condition $true $Name
}

$collectorScriptPath = Join-Path $testDirectory '..\portable\Coletar-Processos-TCE.ps1'
$collectorText = Get-Content -LiteralPath $collectorScriptPath -Raw -Encoding UTF8
Assert-True ($collectorText -match "ValidateSet\('progressivo','completo'\).*ModoPreparacao") 'coletor oferece modo progressivo ou completo'
Assert-True ($collectorText -match 'MaxDownloads') 'coletor expõe limite de downloads'
Assert-True ($collectorText -match 'Sync-TceProcessManifest[\s\S]*MaxDownloads') 'coletor encaminha limite ao coordenador'
Assert-True ($collectorText -match 'DownloaderContext') 'coletor separa contexto efêmero do worker de download'
Assert-True ($collectorText -match '\$result\.auth_required' -and $collectorText -match '\$result\.suspended') 'coletor interrompe coleta quando a sessão exige autenticação ou suspensão'
Assert-True ($collectorText -match 'pedir login|login necessário|autenticação necessária|Faça login' -and $collectorText -match 'break') 'coletor informa autenticação e não continua silenciosamente'
Assert-True ($collectorText -match '\$collectionSuspended\s*=\s*\$false' -and $collectorText -match 'ModoPreparacao.*-and\s*-not\s*\$collectionSuspended') 'coletor não analisa processos após suspensão de autenticação'
Assert-True ($collectorText -match 'incremental_pipeline\.py') 'coletor referencia preparação incremental por processo'
Assert-True ($collectorText -match 'ModoPreparacao.*progressivo|progressivo.*ModoPreparacao') 'coletor usa o modo de preparação para decidir a publicação'
Assert-True ($collectorText -match 'collector\.json') 'coletor publica marcador de execução para bloquear transferência concorrente'

function Assert-Throws {
    param(
        [Parameter(Mandatory)][scriptblock]$Action,
        [Parameter(Mandatory)][string]$MessagePattern,
        [Parameter(Mandatory)][string]$Name
    )
    try {
        & $Action
        $script:failed++
        Write-Host "FALHOU: $Name (nenhuma exceção)" -ForegroundColor Red
    } catch {
        if ($_.Exception.Message -match $MessagePattern) {
            $script:passed++
            Write-Host "PASSOU: $Name" -ForegroundColor Green
        } else {
            $script:failed++
            Write-Host "FALHOU: $Name`n  mensagem recebida: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
}

if ($null -eq ('TceSyntheticWebResponse' -as [type])) {
    Add-Type -TypeDefinition @"
using System.Net;

public sealed class TceSyntheticWebResponse : WebResponse
{
    private readonly int statusCode;
    private readonly WebHeaderCollection headers;

    public TceSyntheticWebResponse(int statusCode, string retryAfter)
    {
        this.statusCode = statusCode;
        this.headers = new WebHeaderCollection();
        if (!string.IsNullOrEmpty(retryAfter)) this.headers["Retry-After"] = retryAfter;
    }

    public int StatusCode { get { return this.statusCode; } }
    public string StatusDescription { get { return "synthetic"; } }
    public override WebHeaderCollection Headers { get { return this.headers; } }
}
"@
}

function New-SyntheticHttpException {
    param(
        [Parameter(Mandatory)][int]$StatusCode,
        [AllowEmptyString()][string]$RetryAfter = '0'
    )
    $response = New-Object TceSyntheticWebResponse -ArgumentList $StatusCode, $RetryAfter
    return New-Object System.Net.WebException -ArgumentList @(
        "HTTP $StatusCode https://tce.invalid/download?token=synthetic-secret",
        $null,
        [Net.WebExceptionStatus]::ProtocolError,
        $response
    )
}

function New-RetryContractManifest {
    param([Parameter(Mandatory)][string]$ProcessKey)
    $parts = $ProcessKey -split '/'
    return [pscustomobject]@{
        process = [pscustomobject]@{ key = $ProcessKey; id = $parts[0]; number = $parts[0]; year = [int]$parts[1] }
        events = @(
            [pscustomobject]@{
                event = 1; event_id = "retry-$($parts[0])"; date = '2026-09-08T00:00:00'; title = 'Retry fixture'; active = $true
                documents = @(
                    [pscustomobject]@{ id = 'retry-document'; title = 'fixture'; extension = '.pdf'; url = 'memory://synthetic'; remote_signature = 'retry-v1' }
                )
            }
        )
    }
}

$processes = @(
    [pscustomobject]@{ key = '103439/2023'; label = '103439/2023 - Magnolia' },
    [pscustomobject]@{ key = '103442/2023'; label = '103442/2023 - Antonio' },
    [pscustomobject]@{ key = '103443/2023'; label = '103443/2023 - Carlos' },
    [pscustomobject]@{ key = '103454/2023'; label = '103454/2023 - Marco' },
    [pscustomobject]@{ key = '103456/2023'; label = '103456/2023 - Ana' }
)

Assert-Equal (Resolve-TceSelection -InputText '1,3-4' -Processes $processes | ForEach-Object key) @('103439/2023','103443/2023','103454/2023') 'seleciona itens e intervalos'
Assert-Equal (Resolve-TceSelection -InputText 'todos' -Processes $processes | ForEach-Object key) ($processes | ForEach-Object key) 'seleciona todos'
Assert-Equal (Resolve-TceSelection -InputText 'novos' -Processes $processes -KnownProcessKeys @('103439/2023','103443/2023') | ForEach-Object key) @('103442/2023','103454/2023','103456/2023') 'seleciona somente processos novos'
Assert-Equal (@(Resolve-TceSelection -InputText 'novos' -Processes $processes -KnownProcessKeys @('103439/2023','103443/2023','103443/2023') | ForEach-Object key)) @('103442/2023','103454/2023','103456/2023') 'seleciona novos sem depender de IDs fixos'
$canonicalProcesses = @([pscustomobject]@{ key = ' 103439 / 2023 '; number = '103439'; year = 2023; label = 'processo com chave espaçada' })
Assert-Equal (@(Resolve-TceSelection -InputText 'novos' -Processes $canonicalProcesses -KnownProcessKeys @('103439/2023') | ForEach-Object key)) @() 'novos compara somente a chave canônica numero/ano'
Assert-Equal (Search-TceProcesses -Term 'antonio' -Processes $processes | ForEach-Object key) @('103442/2023') 'busca sem diferenciar acentos ou caixa'
Assert-Equal (ConvertTo-TceSafeName 'Ofício: teste / revisão?.PDF') 'Oficio-teste-revisao.PDF' 'normaliza nome de arquivo'
Assert-Equal (Get-TceObjectPropertyValue -InputObject ([pscustomobject]@{ id = 'sem-url' }) -Name 'url' -Default '') '' 'propriedade opcional ausente usa valor padrão em modo estrito'

$browserProfileRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-browser-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $browserProfileRoot | Out-Null
try {
    [IO.File]::WriteAllLines((Join-Path $browserProfileRoot 'DevToolsActivePort'), @('49247','/devtools/browser/test'))
    Assert-Equal (Get-TceLiveDevToolsPort -ProfileRoot $browserProfileRoot -PortProbe { param($Port) return $Port -eq 49247 }) 49247 'reutiliza porta DevTools ativa do perfil portátil'
    Assert-Equal (Get-TceLiveDevToolsPort -ProfileRoot $browserProfileRoot -PortProbe { param($Port) return $false }) $null 'ignora porta DevTools obsoleta'
} finally {
    Remove-Item -LiteralPath $browserProfileRoot -Recurse -Force
}

$checkpointEncodingRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-encoding-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $checkpointEncodingRoot | Out-Null
try {
    $checkpointJson = '{"version":1,"updated_at":null,"processes":[{"key":"ação/2024"}],"documents":[]}'
    [IO.File]::WriteAllText((Join-Path $checkpointEncodingRoot 'checkpoint.json'), $checkpointJson, (New-Object Text.UTF8Encoding($false)))
    $readCheckpoint = Get-TceCheckpoint -ArchiveRoot $checkpointEncodingRoot
    Assert-Equal $readCheckpoint.processes[0].key 'ação/2024' 'le checkpoint UTF-8 sem BOM no Windows PowerShell 5.1'
} finally {
    Remove-Item -LiteralPath $checkpointEncodingRoot -Recurse -Force
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tempRoot | Out-Null
try {
    $payloads = @{
        'memory://main' = [Text.Encoding]::UTF8.GetBytes('%PDF-fixture-main')
        'memory://same' = [Text.Encoding]::UTF8.GetBytes('%PDF-fixture-main')
    }
    $manifest = [pscustomobject]@{
        process = [pscustomobject]@{ key = '103439/2023'; id = 582647; number = '103439'; year = 2023 }
        events = @(
            [pscustomobject]@{
                event = 1; event_id = 9001; date = '2023-04-28T12:02:10'; title = 'Documento https://tce.invalid/event token=event-title-secret'; active = $true
                documents = @(
                    [pscustomobject]@{ id = 'info-11'; title = 'Resolução https://tce.invalid/title token=title-secret'; extension = '.pdf'; url = 'memory://main'; remote_signature = 'Authorization: Bearer signature-secret' },
                    [pscustomobject]@{ id = 'annex-12'; title = 'Cópia.pdf'; extension = '.pdf'; url = 'memory://same'; remote_signature = 'v1' },
                    [pscustomobject]@{ id = 'info-13'; title = 'Arquivo indisponível'; extension = '.pdf'; error = 'HTTP 404 Authorization: Bearer error-secret cookie=cookie-secret token=token-secret credential=credential-secret'; remote_signature = 'erro-v1' }
                )
            },
            [pscustomobject]@{ event = 2; event_id = 9002; date = '2023-04-29T10:00:00'; title = 'Tramitação'; active = $true; documents = @() }
        )
    }
    $downloadCount = 0
    $downloader = {
        param($Document, $Destination)
        $script:downloadCount++
        [IO.File]::WriteAllBytes($Destination, $payloads[$Document.url])
    }

    $first = Sync-TceProcessManifest -Manifest $manifest -ArchiveRoot $tempRoot -Downloader $downloader
    Assert-Equal $first.downloaded 2 'primeira sincronizacao baixa os dois documentos'
    Assert-Equal $first.deduplicated 1 'conteudo repetido e deduplicado por SHA-256'
    Assert-True (Test-Path (Join-Path $tempRoot 'processos\103439-2023\processo.json')) 'grava processo novo no layout processos'
    Assert-True (Test-Path (Join-Path $tempRoot 'processos\103439-2023\evento-0002-9002\evento.json')) 'preserva evento sem arquivo'
    $eventMetadata = Get-Content (Join-Path $tempRoot 'processos\103439-2023\evento-0001-9001\evento.json') -Raw -Encoding UTF8
    Assert-True ($eventMetadata -match 'Arquivo indisponível' -and $eventMetadata -match 'error') 'preserva documento indisponivel como erro seguro'
    Assert-True (-not ($eventMetadata -match 'error-secret|cookie-secret|token-secret|credential-secret|title-secret|signature-secret|event-title-secret|tce.invalid/event|Authorization|cookie|token')) 'remove credenciais de erro, titulo, assinatura e evento'
    Assert-True (-not (Test-Path (Join-Path $tempRoot 'processos\103439-2023\evento-0001-9001\documento-002-Copia.pdf.pdf'))) 'nao duplica extensao no nome'

    $checkpointText = Get-Content (Join-Path $tempRoot 'checkpoint.json') -Raw
    Assert-True (-not ($checkpointText -match 'memory://|token|Authorization')) 'checkpoint nao grava URL nem credencial'

    $second = Sync-TceProcessManifest -Manifest $manifest -ArchiveRoot $tempRoot -Downloader $downloader
    Assert-Equal $second.downloaded 0 'retomada idempotente ignora documentos inalterados'
    Assert-Equal $script:downloadCount 2 'retomada nao chama downloader novamente'

    $payloads['memory://main'] = [Text.Encoding]::UTF8.GetBytes('%PDF-fixture-main-v2')
    $manifest.events[0].documents[0].remote_signature = 'v2'
    $third = Sync-TceProcessManifest -Manifest $manifest -ArchiveRoot $tempRoot -Downloader $downloader
    Assert-Equal $third.downloaded 1 'assinatura remota alterada baixa nova versao'
    Assert-True ((Get-ChildItem (Join-Path $tempRoot 'processos\103439-2023\evento-0001-9001') -File | Where-Object Name -match 'versao').Count -eq 1) 'mudanca preserva a versao local anterior'
} finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
}

$parallelRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-parallel-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $parallelRoot | Out-Null
try {
    $parallelManifest = [pscustomobject]@{
        process = [pscustomobject]@{ key = '103450/2023'; id = 582650; number = '103450'; year = 2023 }
        events = @(
            [pscustomobject]@{
                event = 2; event_id = 9010; date = '2023-05-01T10:00:00'; title = 'Documentos'; active = $true
                documents = @(
                    [pscustomobject]@{ id = 'parallel-1'; title = 'Um'; extension = '.pdf'; url = 'memory://parallel-1'; remote_signature = 'p1' },
                    [pscustomobject]@{ id = 'parallel-2'; title = 'Dois'; extension = '.pdf'; url = 'memory://parallel-2'; remote_signature = 'p2' },
                    [pscustomobject]@{ id = 'parallel-3'; title = 'Tres'; extension = '.pdf'; url = 'memory://parallel-3'; remote_signature = 'p3' },
                    [pscustomobject]@{ id = 'parallel-4'; title = 'Quatro'; extension = '.pdf'; url = 'memory://parallel-4'; remote_signature = 'p4' }
                )
            }
        )
    }
    $parallelMarkerRoot = Join-Path $parallelRoot 'markers'
    New-Item -ItemType Directory -Path $parallelMarkerRoot | Out-Null
    foreach ($document in $parallelManifest.events[0].documents) {
        Add-Member -InputObject $document -NotePropertyName marker_root -NotePropertyValue $parallelMarkerRoot
    }
    $parallelDownloader = {
        param($Document, $Destination)
        $marker = [IO.Path]::Combine([string]$Document.marker_root, [IO.Path]::GetFileName($Destination))
        function Get-ParallelSequence {
            param([Parameter(Mandatory)][string]$Root)
            $mutex = [Threading.Mutex]::new($false, 'TcePortableParallelSequence')
            try {
                [void]$mutex.WaitOne()
                $sequencePath = Join-Path $Root 'sequence.txt'
                $current = 0
                if ([IO.File]::Exists($sequencePath)) { $current = [int](Get-Content -LiteralPath $sequencePath -Raw) }
                $next = $current + 1
                [IO.File]::WriteAllText($sequencePath, $next.ToString())
                return $next
            } finally {
                $mutex.ReleaseMutex()
                $mutex.Dispose()
            }
        }
        [IO.File]::WriteAllText("$marker.start", (Get-ParallelSequence -Root $Document.marker_root).ToString())
        try {
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            while (@(Get-ChildItem -LiteralPath $Document.marker_root -Filter '*.start' -File).Count -lt 2) {
                if ([DateTime]::UtcNow -gt $deadline) { throw 'concorrência sintética não iniciou dois workers' }
                [Threading.Thread]::Sleep(20)
            }
            [Threading.Thread]::Sleep(180)
            [IO.File]::WriteAllText($Destination, "%PDF-$($Document.id)")
        } finally {
            [IO.File]::WriteAllText("$marker.end", (Get-ParallelSequence -Root $Document.marker_root).ToString())
        }
    }
    $parallelResult = Sync-TceProcessManifest -Manifest $parallelManifest -ArchiveRoot $parallelRoot -MaxDownloads 2 -Downloader $parallelDownloader -DownloaderContext @{}
    Assert-Equal $parallelResult.downloaded 4 'limite de downloads processa todos os documentos'
    $events = @()
    foreach ($marker in Get-ChildItem -LiteralPath $parallelMarkerRoot -File | Where-Object { $_.Name -match '\.(start|end)$' }) {
        $events += [pscustomobject]@{ kind = if ($marker.Name -match '\.start$') { 'start' } else { 'end' }; ticks = [int64](Get-Content -LiteralPath $marker.FullName -Raw) }
    }
    $active = 0
    $maximum = 0
    foreach ($event in @($events | Sort-Object ticks)) {
        if ($event.kind -eq 'start') { $active++; if ($active -gt $maximum) { $maximum = $active } } else { $active-- }
    }
    Assert-Equal $events.Count 8 'limite de downloads registra inicio e fim de cada documento'
    Assert-True ($maximum -gt 1 -and $maximum -le 2) 'limite de downloads mantem concorrencia efetiva de no maximo dois'
} finally {
    Remove-Item -LiteralPath $parallelRoot -Recurse -Force
}

$retryContractRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-retry-contract-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $retryContractRoot | Out-Null
try {
    $retryManifest = New-RetryContractManifest -ProcessKey '103491/2026'
    $rateLimitAttempts = 0
    $rateLimitDownloader = {
        param($Document, $Destination)
        $script:rateLimitAttempts++
        throw (New-SyntheticHttpException -StatusCode 429 -RetryAfter '0')
    }
    $rateLimitResult = Sync-TceProcessManifest -Manifest $retryManifest -ArchiveRoot (Join-Path $retryContractRoot 'rate-limit') -MaxDownloads 2 -Downloader $rateLimitDownloader
    Assert-Equal $script:rateLimitAttempts 3 'HTTP 429 encerra após no máximo três tentativas'
    Assert-Equal $rateLimitResult.status 'rate_limited' 'HTTP 429 propaga estado de limitação'
    Assert-True $rateLimitResult.rate_limited 'HTTP 429 marca limitação de taxa'
    Assert-True $rateLimitResult.reduce_concurrency 'HTTP 429 sinaliza redução de concorrência'
    Assert-Equal $rateLimitResult.recommended_max_downloads 1 'HTTP 429 recomenda MaxDownloads igual a um'
    Assert-Equal $rateLimitResult.retry_after_seconds 0 'HTTP 429 lê Retry-After da resposta'
    $rateLimitCheckpoint = Get-Content -LiteralPath (Join-Path $retryContractRoot 'rate-limit\checkpoint.json') -Raw -Encoding UTF8
    Assert-True (-not ($rateLimitCheckpoint -match 'synthetic-secret|Authorization|Bearer|token=')) 'HTTP 429 não persiste token na mensagem de erro'

    $laterResult = Sync-TceProcessManifest -Manifest (New-RetryContractManifest -ProcessKey '103492/2026') -ArchiveRoot (Join-Path $retryContractRoot 'later') -MaxDownloads 2 -Downloader {
        param($Document, $Destination)
        [IO.File]::WriteAllText($Destination, '%PDF-later')
    }
    Assert-Equal $laterResult.max_downloads 1 'chamada posterior ao HTTP 429 reduz MaxDownloads efetivo para um'

    $transientAttempts = 0
    $transientDownloader = {
        param($Document, $Destination)
        $script:transientAttempts++
        if ($script:transientAttempts -eq 1) { throw (New-SyntheticHttpException -StatusCode 429 -RetryAfter '0') }
        [IO.File]::WriteAllText($Destination, '%PDF-transient-success')
    }
    $transientResult = Sync-TceProcessManifest -Manifest (New-RetryContractManifest -ProcessKey '103493/2026') -ArchiveRoot (Join-Path $retryContractRoot 'transient-success') -MaxDownloads 2 -Downloader $transientDownloader
    Assert-Equal $script:transientAttempts 2 'HTTP 429 transitório tenta novamente uma vez antes do sucesso'
    Assert-Equal $transientResult.downloaded 1 'sucesso após HTTP 429 é persistido'
    Assert-Equal $transientResult.status 'complete' 'sucesso após HTTP 429 mantém estado completo'
    Assert-True $transientResult.reduce_concurrency 'sucesso após HTTP 429 mantém sinal para reduzir concorrência'

    foreach ($authCase in @(
        [pscustomobject]@{ statusCode = 401; expectedStatus = 'auth_required'; expectedAuth = $true; expectedSuspended = $false; name = 'HTTP 401 exige login' },
        [pscustomobject]@{ statusCode = 403; expectedStatus = 'suspended'; expectedAuth = $false; expectedSuspended = $true; name = 'HTTP 403 sinaliza suspensão' }
    )) {
        $authState = [pscustomobject]@{ attempts = 0; status_code = $authCase.statusCode }
        $authDownloader = {
            param($Document, $Destination)
            $authState.attempts++
            throw (New-SyntheticHttpException -StatusCode $authState.status_code -RetryAfter '0')
        }.GetNewClosure()
        $authProcessKey = if ($authCase.statusCode -eq 401) { '103494/2026' } else { '103495/2026' }
        $authResult = Sync-TceProcessManifest -Manifest (New-RetryContractManifest -ProcessKey $authProcessKey) -ArchiveRoot (Join-Path $retryContractRoot ("auth-$($authCase.statusCode)")) -MaxDownloads 2 -Downloader $authDownloader
        Assert-Equal $authState.attempts 1 "$($authCase.name) não faz retry"
        Assert-Equal $authResult.status $authCase.expectedStatus "$($authCase.name) propaga status ao coordenador"
        Assert-Equal $authResult.auth_required $authCase.expectedAuth "$($authCase.name) propaga auth_required"
        Assert-Equal $authResult.suspended $authCase.expectedSuspended "$($authCase.name) propaga suspended"
        Assert-True (-not ($authResult | ConvertTo-Json -Depth 20 | Select-String -Quiet 'synthetic-secret|Authorization|Bearer|token=')) "$($authCase.name) mantém token fora do resultado"
    }

    $authStopManifest = New-RetryContractManifest -ProcessKey '103497/2026'
    $authStopManifest.events = @($authStopManifest.events) + @(
        [pscustomobject]@{
            event = 2; event_id = 'retry-after-auth'; date = '2026-09-08T00:01:00'; title = 'Não baixar após autenticação'; active = $true
            documents = @([pscustomobject]@{ id = 'must-not-download'; title = 'não deve baixar'; extension = '.pdf'; url = 'memory://must-not-download'; remote_signature = 'never' })
        }
    )
    $authStopAttempts = 0
    $authStopDownloader = {
        param($Document, $Destination)
        $script:authStopAttempts++
        if ($Document.id -eq 'retry-document') { throw (New-SyntheticHttpException -StatusCode 401 -RetryAfter '0') }
        [IO.File]::WriteAllText($Destination, '%PDF-must-not-download')
    }
    $authStopResult = Sync-TceProcessManifest -Manifest $authStopManifest -ArchiveRoot (Join-Path $retryContractRoot 'auth-stop') -MaxDownloads 1 -Downloader $authStopDownloader
    Assert-Equal $script:authStopAttempts 1 '401 interrompe eventos posteriores do mesmo processo'
    Assert-Equal $authStopResult.status 'auth_required' '401 mantém estado de autenticação ao interromper o processo'

    $badRequestAttempts = 0
    $badRequestDownloader = {
        param($Document, $Destination)
        $script:badRequestAttempts++
        throw (New-SyntheticHttpException -StatusCode 400 -RetryAfter '0')
    }
    $badRequestResult = Sync-TceProcessManifest -Manifest (New-RetryContractManifest -ProcessKey '103496/2026') -ArchiveRoot (Join-Path $retryContractRoot 'bad-request') -MaxDownloads 2 -Downloader $badRequestDownloader
    Assert-Equal $script:badRequestAttempts 1 'HTTP 400 não faz retry'
    Assert-Equal $badRequestResult.http_statuses 400 'HTTP 400 propaga código HTTP'
    Assert-True (-not $badRequestResult.auth_required -and -not $badRequestResult.suspended) 'HTTP 400 não é tratado como autenticação ou suspensão'
} finally {
    if (Test-Path -LiteralPath $retryContractRoot) { Remove-Item -LiteralPath $retryContractRoot -Recurse -Force }
}

$legacyRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-legacy-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $legacyRoot '103439-2023') -Force | Out-Null
try {
    $legacy = Sync-TceProcessManifest -Manifest $manifest -ArchiveRoot $legacyRoot -Downloader $downloader
    Assert-True (Test-Path (Join-Path $legacyRoot '103439-2023\processo.json')) 'reutiliza processo existente no layout legado'
    Assert-True (-not (Test-Path (Join-Path $legacyRoot 'processos\103439-2023\processo.json'))) 'nao duplica processo legado no layout novo'
} finally {
    Remove-Item -LiteralPath $legacyRoot -Recurse -Force
}

$failureRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-failure-test-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $failureRoot | Out-Null
try {
    Add-TceFailure -ArchiveRoot $failureRoot -ProcessKey '103490/2023' -Message 'primeira falha token=segredo'
    Add-TceFailure -ArchiveRoot $failureRoot -ProcessKey '103605/2023' -Message 'segunda falha'
    Add-TceFailure -ArchiveRoot $failureRoot -ProcessKey '103542/2023' -Message 'terceira falha'
    $failureJson = Get-Content -LiteralPath (Join-Path $failureRoot 'falhas.json') -Raw -Encoding UTF8
    $failures = @($failureJson | ConvertFrom-Json | ForEach-Object { $_ })
    Assert-Equal $failures.Count 3 'falhas permanecem em lista plana após múltiplas gravações'
    Assert-Equal @($failures | ForEach-Object process) @('103490/2023','103605/2023','103542/2023') 'falhas preservam os processos na ordem'
    Assert-True (-not ((Get-Content -LiteralPath (Join-Path $failureRoot 'falhas.json') -Raw) -match 'segredo|"value"|"Count"')) 'falhas não persistem segredo nem wrapper de array'
} finally {
    Remove-Item -LiteralPath $failureRoot -Recurse -Force
}

$launcherText = Get-Content (Join-Path $PSScriptRoot '..\portable\Coletar-Processos-TCE.ps1') -Raw
$driverText = Get-Content (Join-Path $PSScriptRoot '..\portable\TcePortal.Driver.js') -Raw
Assert-True (-not ($launcherText -match '103439|582647')) 'launcher nao fixa numeros de processos antigos'
Assert-True ($launcherText -match '\[void\]\(\$socket\.ConnectAsync') 'conexão CDP não despeja objeto técnico no terminal'
Assert-True ($driverText -match '/api/Processo/.*?/eventos' -and $driverText -match '/api/informacao/') 'driver usa APIs de eventos e arquivos'

$baselineTestRoot = Join-Path ([IO.Path]::GetTempPath()) ("tce-portable-baseline-test-" + [guid]::NewGuid().ToString('N'))
$baselineDirectory = Join-Path $baselineTestRoot 'baseline-directory'
$baselineZipInput = Join-Path $baselineTestRoot 'zip-input'
$destinationCheckpointRoot = Join-Path $baselineTestRoot 'destination'
New-Item -ItemType Directory -Path $baselineDirectory -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $baselineZipInput 'acervo-tce') -Force | Out-Null
New-Item -ItemType Directory -Path $destinationCheckpointRoot -Force | Out-Null
try {
    $baseCheckpoint = [pscustomobject]@{
        version = 1
        processes = @(
            [pscustomobject]@{ key = '103443 / 2023'; number = '103443'; year = 2023; id = 'historical-id'; status = 'complete' },
            [pscustomobject]@{ key = '103456/2023'; number = '103456'; year = 2023; id = 'historical-partial-id'; status = 'partial' }
        )
        documents = @()
    }
    $destinationCheckpoint = [pscustomobject]@{
        version = 1
        processes = @(
            [pscustomobject]@{ key = '103439/2023'; number = '103439'; year = 2023; id = 'destination-id'; status = 'complete' },
            [pscustomobject]@{ key = '103454/2023'; number = '103454'; year = 2023; id = 'destination-partial-id'; status = 'partial' }
        )
        documents = @()
    }
    $baselineCheckpointPath = Join-Path $baselineTestRoot 'checkpoint.json'
    $baselineJson = $baseCheckpoint | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText($baselineCheckpointPath, $baselineJson, (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText((Join-Path $baselineDirectory 'checkpoint.json'), $baselineJson, (New-Object Text.UTF8Encoding($false)))
    [IO.File]::WriteAllText((Join-Path $baselineZipInput 'acervo-tce\checkpoint.json'), $baselineJson, (New-Object Text.UTF8Encoding($false)))
    $baselineZipPath = Join-Path $baselineTestRoot 'baseline.zip'
    Compress-Archive -Path (Join-Path $baselineZipInput 'acervo-tce') -DestinationPath $baselineZipPath
    $destinationJson = $destinationCheckpoint | ConvertTo-Json -Depth 20
    [IO.File]::WriteAllText((Join-Path $destinationCheckpointRoot 'checkpoint.json'), $destinationJson, (New-Object Text.UTF8Encoding($false)))

    $expectedCompleted = @('103439/2023', '103443/2023')
    $expectedWholeBaseline = @('103439/2023', '103443/2023', '103456/2023')
    foreach ($baselineSource in @($baselineCheckpointPath, $baselineDirectory, $baselineZipPath)) {
        Assert-Equal (Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $baselineSource) $expectedCompleted "une checkpoint de destino e BaseConcluidos: $([IO.Path]::GetFileName($baselineSource))"
        Assert-Equal (Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $baselineSource -BaselineAllComplete) $expectedWholeBaseline "trata todos os processos da base como concluídos somente com BaselineAllComplete: $([IO.Path]::GetFileName($baselineSource))"
    }
    $knownWithBaseline = @(Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $baselineCheckpointPath)
    Assert-Equal (Resolve-TceSelection -InputText 'novos' -Processes $processes -KnownProcessKeys $knownWithBaseline | ForEach-Object key) @('103442/2023','103454/2023','103456/2023') 'novos une somente processos completos do destino e da base histórica'
    $knownWithWholeBaseline = @(Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $baselineCheckpointPath -BaselineAllComplete)
    Assert-Equal (Resolve-TceSelection -InputText 'novos' -Processes $processes -KnownProcessKeys $knownWithWholeBaseline | ForEach-Object key) @('103442/2023','103454/2023') 'BaselineAllComplete inclui partial da base sem incluir partial do destino'

    $invalidBaselinePath = Join-Path $baselineTestRoot 'missing-baseline.json'
    Assert-Throws -Action { Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $invalidBaselinePath } -MessagePattern 'BaseConcluidos.*(inexistente|inválid)' -Name 'BaseConcluidos inexistente falha com mensagem clara'
    Assert-Throws -Action { Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaselineAllComplete } -MessagePattern 'BaselineAllComplete.*BaseConcluidos' -Name 'BaselineAllComplete exige BaseConcluidos explícita'
    $malformedBaselineDirectory = Join-Path $baselineTestRoot 'malformed-baseline'
    New-Item -ItemType Directory -Path $malformedBaselineDirectory -Force | Out-Null
    $malformedBaselinePath = Join-Path $malformedBaselineDirectory 'checkpoint.json'
    [IO.File]::WriteAllText($malformedBaselinePath, '{"processes":[]}', (New-Object Text.UTF8Encoding($false)))
    Assert-Throws -Action { Get-TceCompletedProcessKeys -ArchiveRoot $destinationCheckpointRoot -BaseConcluidos $malformedBaselineDirectory } -MessagePattern 'BaseConcluidos.*documents' -Name 'BaseConcluidos malformada falha sem tolerância silenciosa'

    $collectorPath = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $modulePath) 'Coletar-Processos-TCE.ps1'))
    $collectorText = Get-Content -LiteralPath $collectorPath -Raw -Encoding UTF8
    $validationOffset = $collectorText.IndexOf('$knownKeys = @(Get-TceCompletedProcessKeys')
    $browserOffset = $collectorText.IndexOf('$port = Start-TceBrowser')
    Assert-True ($collectorText -match '\[switch\]\$BaselineAllComplete') 'coletor expõe BaselineAllComplete explicitamente'
    Assert-True ($collectorText -match '-BaselineAllComplete:\$BaselineAllComplete') 'coletor encaminha BaselineAllComplete ao cálculo de novos'
    Assert-True ($validationOffset -ge 0) 'coletor valida BaseConcluidos antes da coleta'
    Assert-True ($browserOffset -gt $validationOffset) 'coletor só inicia navegador depois de validar a base'
} finally {
    if (Test-Path -LiteralPath $baselineTestRoot) { Remove-Item -LiteralPath $baselineTestRoot -Recurse -Force }
}

$diagnosticPath = [IO.Path]::GetFullPath((Join-Path $testDirectory '..\portable\TESTAR-PACOTE.ps1'))
try { . $diagnosticPath } catch { $diagnosticLoadError = $_.Exception.Message }
Assert-True ($null -ne (Get-Command Get-TcePortableRuntimeLayout -ErrorAction SilentlyContinue)) 'diagnostico expõe verificação testável do runtime'
Assert-True ($null -ne (Get-Command Get-TcePortableDatasetStatus -ErrorAction SilentlyContinue)) 'diagnostico expõe verificação testável do JSON da extensão'
Assert-True ($null -ne (Get-Command Get-TcePortableExtensionManifestStatus -ErrorAction SilentlyContinue)) 'diagnostico expõe verificação do manifest da extensão'
Assert-True ($null -ne (Get-Command Get-TcePortableNodeStatus -ErrorAction SilentlyContinue)) 'diagnostico verifica que Node não é requisito'
$diagnosticText = Get-Content -LiteralPath $diagnosticPath -Raw -Encoding UTF8
$pythonDiagnosticInvocations = @([regex]::Matches($diagnosticText, '(?m)&\s+\$Runtime\.Python\b[^\r\n]*') | ForEach-Object Value)
Assert-Equal $pythonDiagnosticInvocations.Count 3 'diagnostico usa exatamente três invocações Python'
Assert-Equal @($pythonDiagnosticInvocations | Where-Object { $_ -match '&\s+\$Runtime\.Python\s+-B\s+-s(?:\s|$)' }).Count 3 'diagnostico passa -B -s em todas as invocações Python'
Assert-True ($diagnosticText -notmatch '(?m)&\s+\$Runtime\.Python\s+-s(?:\s|$)') 'diagnostico não chama Python sem -B'

$emptyChecks = New-Object System.Collections.ArrayList
$emptyCheckException = $null
try {
    Add-TcePortableCheck -Checks $emptyChecks -Name 'fixture' -Passed $true -Message 'check inicial'
} catch {
    $emptyCheckException = $_.Exception
}
Assert-True ($null -eq $emptyCheckException) 'agregador aceita ArrayList inicialmente vazia'
Assert-Equal @($emptyChecks).Count 1 'agregador registra check após iniciar vazio'

$emptyMessageCheckException = $null
try {
    Add-TcePortableCheck -Checks $emptyChecks -Name 'fixture sem mensagem' -Passed $true -Message ''
} catch {
    $emptyMessageCheckException = $_.Exception
}
Assert-True ($null -eq $emptyMessageCheckException) 'agregador aceita mensagem vazia sem exceção de binding'
$emptyMessage = if ($null -eq $emptyMessageCheckException -and $emptyChecks.Count -gt 1) { [string]$emptyChecks[1].Message } else { '' }
Assert-True (-not [string]::IsNullOrWhiteSpace($emptyMessage)) 'check sem mensagem recebe texto legível'

$failedCheckFixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-portable-failed-check-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $failedCheckFixtureRoot -Force | Out-Null
try {
    $failedCheckResult = Invoke-TcePortablePackageCheck -PackageRoot $failedCheckFixtureRoot
    Assert-True (-not $failedCheckResult.Passed) 'qualquer check reprovado reprova o pacote'
    Assert-True (@($failedCheckResult.Checks).Count -gt 0) 'check reprovado não desaparece do resultado'
    Assert-True (@($failedCheckResult.Checks | Where-Object { -not $_.Passed }).Count -gt 0) 'resultado expõe ao menos um check reprovado'
} catch {
    Assert-True $false 'qualquer check reprovado retorna diagnóstico sem exceção não tratada'
} finally {
    if (Test-Path -LiteralPath $failedCheckFixtureRoot) { Remove-Item -LiteralPath $failedCheckFixtureRoot -Recurse -Force }
}

$directFixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-portable-direct-fixture-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directFixtureRoot -Force | Out-Null
$directScriptPath = Join-Path $directFixtureRoot 'TESTAR-PACOTE.ps1'
Copy-Item -LiteralPath $diagnosticPath -Destination $directScriptPath
try {
    $directProcessInfo = New-Object Diagnostics.ProcessStartInfo
    $directProcessInfo.FileName = 'powershell.exe'
    $directProcessInfo.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $directScriptPath + '"'
    $directProcessInfo.UseShellExecute = $false
    $directProcessInfo.CreateNoWindow = $true
    $directProcessInfo.RedirectStandardOutput = $true
    $directProcessInfo.RedirectStandardError = $true
    $directProcess = New-Object Diagnostics.Process
    $directProcess.StartInfo = $directProcessInfo
    [void]$directProcess.Start()
    $directStdout = $directProcess.StandardOutput.ReadToEnd()
    $directStderr = $directProcess.StandardError.ReadToEnd()
    $directProcess.WaitForExit()
    $directExitCode = $directProcess.ExitCode
    $directText = $directStdout + [Environment]::NewLine + $directStderr
    $directProcess.Dispose()
    Assert-True ($directExitCode -ne 0) 'execução direta retorna código não zero quando o pacote falha'
    Assert-True ($directText -match [regex]::Escape('Pacote: ' + $directFixtureRoot)) 'execução direta usa a pasta do próprio script como raiz'
    Assert-True ($directText -match 'Pacote reprovado') 'execução direta nunca imprime aprovação falsa'
    Assert-True ($directText -notmatch 'Pacote integro') 'execução direta não anuncia pacote íntegro após check reprovado'
    Assert-True ($directText -notmatch 'ParameterBindingValidationException') 'pacote sem runtime reprova sem exceção de binding não tratada'
} finally {
    if (Test-Path -LiteralPath $directFixtureRoot) { Remove-Item -LiteralPath $directFixtureRoot -Recurse -Force }
}

if ($null -ne (Get-Command Get-TcePortableRuntimeLayout -ErrorAction SilentlyContinue)) {
    $diagnosticFixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-portable-diagnostic-' + [guid]::NewGuid().ToString('N'))
    $fixtureRuntimeRoot = Join-Path $diagnosticFixtureRoot 'runtime'
    $fixtureTessdata = Join-Path $fixtureRuntimeRoot 'tesseract\tessdata'
    New-Item -ItemType Directory -Path (Join-Path $fixtureRuntimeRoot 'python'), $fixtureTessdata -Force | Out-Null
    foreach ($relative in @(
        'runtime\python\python.exe',
        'runtime\python\python314._pth',
        'runtime\tesseract\tesseract.exe',
        'runtime\tesseract\libtesseract-5.dll',
        'runtime\tesseract\libleptonica-6.dll',
        'runtime\tesseract\tessdata\por.traineddata',
        'runtime\tesseract\tessdata\eng.traineddata'
    )) {
        [IO.File]::WriteAllText((Join-Path $diagnosticFixtureRoot $relative), 'fixture')
    }
    try {
        $runtimeStatus = Get-TcePortableRuntimeLayout -PackageRoot $diagnosticFixtureRoot
        Assert-True (-not $runtimeStatus.IsComplete) 'runtime incompleto e identificado antes da execucao'
        Assert-Equal @($runtimeStatus.Missing | ForEach-Object { [IO.Path]::GetFileName($_) }) @('osd.traineddata') 'runtime informa idioma Tesseract ausente'

        [IO.File]::WriteAllText((Join-Path $diagnosticFixtureRoot 'runtime\tesseract\tessdata\osd.traineddata'), 'fixture')
        $completeRuntimeStatus = Get-TcePortableRuntimeLayout -PackageRoot $diagnosticFixtureRoot
        Assert-True $completeRuntimeStatus.IsComplete 'runtime completo e identificado'

        $datasetRoot = Join-Path $diagnosticFixtureRoot 'acervo-tce'
        New-Item -ItemType Directory -Path $datasetRoot -Force | Out-Null
        $validLogicalPayload = [ordered]@{ batch_id = 'fixture'; process_keys = @(); records = @(); schema_version = 1 }
        $validLogicalCanonical = ConvertTo-Json -InputObject $validLogicalPayload -Compress -Depth 20
        $validHashAlgorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $validHashBytes = $validHashAlgorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($validLogicalCanonical))
            $validLogicalSha = (([BitConverter]::ToString($validHashBytes)).Replace('-', '')).ToLowerInvariant()
        } finally {
            $validHashAlgorithm.Dispose()
        }
        $validDatasetObject = [ordered]@{
            schema_version = 1
            generated_at = 'fixture'
            batch = [ordered]@{
                id = 'fixture'
                logical_sha256 = $validLogicalSha
                process_count = 0
                record_count = 0
                process_keys = @()
            }
            records = @()
        }
        $validDataset = ConvertTo-Json -InputObject $validDatasetObject -Compress -Depth 20
        [IO.File]::WriteAllText((Join-Path $datasetRoot 'dados-complementar-ato.json'), $validDataset, (New-Object Text.UTF8Encoding($false)))
        $datasetStatus = Get-TcePortableDatasetStatus -ArchiveRoot $diagnosticFixtureRoot
        Assert-True $datasetStatus.IsValid 'JSON da extensao valido verifica hash e contagens'

        $invalidDataset = $validDataset -replace '"record_count":0', '"record_count":1'
        [IO.File]::WriteAllText((Join-Path $datasetRoot 'dados-complementar-ato.json'), $invalidDataset, (New-Object Text.UTF8Encoding($false)))
        $invalidDatasetStatus = Get-TcePortableDatasetStatus -ArchiveRoot $diagnosticFixtureRoot
        Assert-True (-not $invalidDatasetStatus.IsValid) 'JSON da extensao rejeita contagem divergente'
    } finally {
        if (Test-Path -LiteralPath $diagnosticFixtureRoot) { Remove-Item -LiteralPath $diagnosticFixtureRoot -Recurse -Force }
    }
}

if ($null -ne (Get-Command Get-TcePortableExtensionManifestStatus -ErrorAction SilentlyContinue)) {
    $extensionStatus = Get-TcePortableExtensionManifestStatus -PackageRoot (Split-Path -Parent $diagnosticPath)
    Assert-True $extensionStatus.IsValid 'manifest da extensão e arquivos declarados estão válidos'
    Assert-Equal $extensionStatus.Permissions @('storage', 'sidePanel', 'alarms', 'webNavigation') 'manifest usa somente permissões permitidas'
    Assert-Equal $extensionStatus.HostPermissions @('https://novaarearestrita.tce.rn.gov.br/*', 'http://127.0.0.1/*') 'manifest usa somente portal e bridge loopback'
}

if ($null -ne (Get-Command Get-TcePortableNodeStatus -ErrorAction SilentlyContinue)) {
    $nodeStatus = Get-TcePortableNodeStatus -PackageRoot (Split-Path -Parent $diagnosticPath)
    Assert-True $nodeStatus.IsValid 'pacote operacional não depende de Node'
}

Write-Host "`nResultado: $script:passed passaram; $script:failed falharam."
if ($script:failed -gt 0) { exit 1 }
