[CmdletBinding()]
param(
    [string]$Destino = 'acervo-tce',
    [ValidateSet('Auto','Chrome','Edge')][string]$Navegador = 'Auto',
    [string]$Selecao = '',
    [string]$FilaCongelada = '',
    [ValidateRange(0,1000)][int]$NumeroLote = 0,
    [string]$BaseConcluidos = '',
    [switch]$BaselineAllComplete,
    [switch]$SomenteDiagnostico,
    [switch]$ManterNavegadorAberto,
    [switch]$NaoInterativo,
    [switch]$ServiceChild,
    [ValidateSet('sector_finalistic','my_processes')][string]$EscopoPortal = 'sector_finalistic',
    [ValidateSet('progressivo','completo')][string]$ModoPreparacao = 'progressivo',
    [ValidateRange(1,2)][int]$MaxDownloads = 2,
    [string]$Python = '',
    [string]$Tesseract = '',
    [string]$Tessdata = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$scriptRoot = if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if ($Destino -eq 'acervo-tce') { $Destino = Join-Path $scriptRoot $Destino }
Import-Module (Join-Path $scriptRoot 'TcePortable.Core.psm1') -Force
Import-Module (Join-Path $scriptRoot 'TceFrozenQueue.psm1') -Force

$script:CdpSequence = 0
$script:CdpSocket = $null
$script:AreaCdpSocket = $null
$script:BrowserProcess = $null
$portalUrl = if ($EscopoPortal -eq 'sector_finalistic') {
    'https://processos.tce.rn.gov.br/#/dashboard/processos-no-setor/no-setor?ProcessosFinalisticosNoSetor=true&setor=CBP'
} else {
    'https://processos.tce.rn.gov.br/#/dashboard/meus/meus-processos?ProcessosFinalisticosNoSetor=true&setor=CBP'
}

function Find-ChromiumBrowser {
    $candidates = @()
    if ($Navegador -in @('Auto','Chrome')) {
        if (${env:ProgramFiles}) { $candidates += Join-Path ${env:ProgramFiles} 'Google\Chrome\Application\chrome.exe' }
        if (${env:ProgramFiles(x86)}) { $candidates += Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe' }
        if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe' }
    }
    if ($Navegador -in @('Auto','Edge')) {
        if (${env:ProgramFiles(x86)}) { $candidates += Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe' }
        if (${env:ProgramFiles}) { $candidates += Join-Path ${env:ProgramFiles} 'Microsoft\Edge\Application\msedge.exe' }
        if ($env:LOCALAPPDATA) { $candidates += Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe' }
    }
    $found = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $found) { throw 'Chrome ou Edge não encontrado. Instale um deles ou use -Navegador Chrome/Edge.' }
    return $found
}

function Start-TceBrowser {
    $browserExe = Find-ChromiumBrowser
    $attachedPort = Get-TceExistingPortalDevToolsPort
    if ($attachedPort) {
        Write-Host "Reutilizando navegador TCE/RN já aberto na porta DevTools $attachedPort." -ForegroundColor Green
        return $attachedPort
    }
    $profile = Join-Path $scriptRoot 'dados-locais\perfil-navegador'
    [IO.Directory]::CreateDirectory($profile) | Out-Null
    $existingPort = Get-TceLiveDevToolsPort -ProfileRoot $profile
    if ($existingPort) {
        Write-Host "Reutilizando navegador autenticado já aberto." -ForegroundColor Green
        return $existingPort
    }
    $portFile = Join-Path $profile 'DevToolsActivePort'
    if (Test-Path -LiteralPath $portFile) { Remove-Item -LiteralPath $portFile -Force }
    $arguments = @(
        "--user-data-dir=`"$profile`"",
        '--remote-debugging-port=0',
        '--no-first-run',
        '--no-default-browser-check',
        '--new-window',
        $portalUrl
    )
    $script:BrowserProcess = Start-Process -FilePath $browserExe -ArgumentList $arguments -PassThru
    $limit = [DateTime]::UtcNow.AddSeconds(30)
    while (-not (Test-Path -LiteralPath $portFile)) {
        if ([DateTime]::UtcNow -gt $limit) { throw 'O navegador não abriu a porta de automação em 30 segundos.' }
        Start-Sleep -Milliseconds 200
    }
    $lines = Get-Content -LiteralPath $portFile
    return [int]$lines[0]
}

function Connect-TceCdpTarget {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$UrlPattern
    )
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/json/list" -UseBasicParsing
    $target = $targets | Where-Object { $_.type -eq 'page' -and $_.url -match $UrlPattern } | Select-Object -First 1
    if (-not $target) { throw "Nenhuma aba controlável correspondeu a $UrlPattern." }
    $socket = New-Object Net.WebSockets.ClientWebSocket
    [void]($socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult())
    return $socket
}

function Connect-TceCdp {
    param([Parameter(Mandatory)][int]$Port)
    $script:CdpSocket = Connect-TceCdpTarget -Port $Port -UrlPattern 'processos\.tce\.rn\.gov\.br'
}

function Send-TceCdpSocket {
    param(
        [Parameter(Mandatory)][object]$Socket,
        [Parameter(Mandatory)][string]$Method,
        [hashtable]$Params = @{}
    )
    $script:CdpSequence++
    $id = $script:CdpSequence
    $request = @{ id = $id; method = $Method; params = $Params } | ConvertTo-Json -Compress -Depth 30
    $bytes = [Text.Encoding]::UTF8.GetBytes($request)
    $segment = New-Object 'ArraySegment[byte]' -ArgumentList @(,$bytes)
    [void]($Socket.SendAsync($segment, [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult())

    while ($true) {
        $stream = New-Object IO.MemoryStream
        do {
            $buffer = New-Object byte[] 1048576
            $receiveSegment = New-Object 'ArraySegment[byte]' -ArgumentList @(,$buffer)
            $result = $Socket.ReceiveAsync($receiveSegment, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            if ($result.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) { throw 'O navegador encerrou a conexão.' }
            $stream.Write($buffer, 0, $result.Count)
        } while (-not $result.EndOfMessage)
        $message = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
        $stream.Dispose()
        if ($message.id -eq $id) {
            if ($message.error) { throw "CDP $Method falhou: $($message.error.message)" }
            return $message.result
        }
    }
}

function Send-TceCdp {
    param([Parameter(Mandatory)][string]$Method, [hashtable]$Params = @{})
    return Send-TceCdpSocket -Socket $script:CdpSocket -Method $Method -Params $Params
}

function Invoke-TceJavaScript {
    param([Parameter(Mandatory)][hashtable]$Payload)
    $driver = Get-Content -LiteralPath (Join-Path $scriptRoot 'TcePortal.Driver.js') -Raw -Encoding UTF8
    $payloadJson = $Payload | ConvertTo-Json -Compress -Depth 20
    $expression = "($driver)($payloadJson)"
    $result = Send-TceCdp -Method 'Runtime.evaluate' -Params @{ expression = $expression; awaitPromise = $true; returnByValue = $true }
    if ($result.exceptionDetails) {
        $description = $result.exceptionDetails.exception.description
        if (-not $description) { $description = $result.exceptionDetails.text }
        throw "Erro na página do TCE: $description"
    }
    return $result.result.value
}

function Invoke-TceBrowserDownload {
    param(
        [Parameter(Mandatory)]$Document,
        [Parameter(Mandatory)][string]$Destination,
        [AllowNull()][object]$Context = $null
    )
    $documentId = [string](Get-TceObjectPropertyValue -InputObject $Document -Name 'id' -Default 'sem-id')
    $documentUrl = [string](Get-TceObjectPropertyValue -InputObject $Document -Name 'url' -Default '')
    if (-not $documentUrl) { throw "Documento $documentId não possui endereço de download." }
    $absoluteUri = [Uri]::new([Uri]'https://processos.tce.rn.gov.br/', $documentUrl)
    $socket = $script:CdpSocket
    if ($absoluteUri.Host -eq 'novaarearestrita.tce.rn.gov.br') {
        if (-not $script:AreaCdpSocket) {
            $script:AreaCdpSocket = Connect-TceCdpTarget -Port $port -UrlPattern 'novaarearestrita\.tce\.rn\.gov\.br'
        }
        $socket = $script:AreaCdpSocket
    }
    $urlJson = $absoluteUri.AbsoluteUri | ConvertTo-Json -Compress
    $expression = @"
(async()=>{
  const response = await fetch($urlJson, { credentials: 'include' });
  if (!response.ok) return { ok: false, status: response.status };
  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, Math.min(offset + 0x8000, bytes.length)));
  }
  return { ok: true, status: response.status, base64: btoa(binary) };
})()
"@
    $result = Send-TceCdpSocket -Socket $socket -Method 'Runtime.evaluate' -Params @{ expression = $expression; awaitPromise = $true; returnByValue = $true }
    if ($result.exceptionDetails) {
        $description = $result.exceptionDetails.exception.description
        if (-not $description) { $description = $result.exceptionDetails.text }
        throw "Download no contexto autenticado do Chrome falhou: $description"
    }
    $value = $result.result.value
    if (-not $value.ok) { throw "Download no contexto autenticado do Chrome retornou HTTP $($value.status)." }
    if ([string]::IsNullOrWhiteSpace([string]$value.base64)) { throw 'O arquivo baixado pelo Chrome veio vazio.' }
    [IO.File]::WriteAllBytes($Destination, [Convert]::FromBase64String([string]$value.base64))
    if (-not [IO.File]::Exists($Destination) -or (Get-Item -LiteralPath $Destination).Length -eq 0) {
        throw 'O arquivo baixado pelo Chrome veio vazio.'
    }
}

function Wait-TcePage {
    param([int]$Seconds = 30)
    $limit = [DateTime]::UtcNow.AddSeconds($Seconds)
    do {
        try {
            $state = Send-TceCdp -Method 'Runtime.evaluate' -Params @{ expression = 'document.readyState'; returnByValue = $true }
            if ($state.result.value -in @('interactive','complete')) { return }
        } catch { }
        Start-Sleep -Milliseconds 300
    } while ([DateTime]::UtcNow -lt $limit)
    throw 'A página do TCE não terminou de carregar.'
}

function Show-ProcessList {
    param([object[]]$Processes)
    Write-Host ''
    for ($index = 0; $index -lt $Processes.Count; $index++) {
        Write-Host ('{0,3}. {1}' -f ($index + 1), $Processes[$index].label)
    }
    Write-Host ''
    Write-Host 'Comandos: 1,4,8-12 | todos | novos | buscar NOME/PROCESSO' -ForegroundColor Cyan
}

function Invoke-TceDownload {
    param($Document, [string]$Destination, [string]$Token)
    $documentId = [string](Get-TceObjectPropertyValue -InputObject $Document -Name 'id' -Default 'sem-id')
    $documentUrl = [string](Get-TceObjectPropertyValue -InputObject $Document -Name 'url' -Default '')
    if (-not $documentUrl) { throw "Documento $documentId não possui endereço de download." }
    $uri = [Uri]::new([Uri]'https://processos.tce.rn.gov.br/', $documentUrl)
    $headers = @{ 'User-Agent' = 'TCE-Processos-Portatil/1.0' }
    $requiresAuth = [bool](Get-TceObjectPropertyValue -InputObject $Document -Name 'requires_auth' -Default $false)
    if ($requiresAuth -or $uri.Host -eq 'processos.tce.rn.gov.br') {
        if (-not $Token) { throw 'Sessão sem token para baixar um arquivo autenticado.' }
        $headers.Authorization = $Token
    }
    Invoke-WebRequest -Uri $uri.AbsoluteUri -Headers $headers -OutFile $Destination -UseBasicParsing -TimeoutSec 120
    if ((Get-Item -LiteralPath $Destination).Length -eq 0) { throw 'O arquivo baixado veio vazio.' }
}

function Write-SafeFailure {
    param([string]$ProcessKey, [string]$Message)
    Add-TceFailure -ArchiveRoot $Destino -ProcessKey $ProcessKey -Message $Message
}

$script:CollectorLeaseStream = $null
$script:CollectorLeasePath = $null
$script:CollectorMarkerPath = $null
$script:CollectorLeaseToken = $null

function Test-TceProcessAlive {
    param([Parameter(Mandatory)][int]$ProcessId)
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        return -not $process.HasExited
    } catch {
        return $false
    }
}

function Remove-TceStaleLeaseFiles {
    param(
        [Parameter(Mandatory)][string]$LockPath,
        [Parameter(Mandatory)][string]$MarkerPath
    )
    if (Test-Path -LiteralPath $MarkerPath -PathType Leaf) {
        try {
            $marker = Get-Content -LiteralPath $MarkerPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($marker.pid -and (Test-TceProcessAlive -ProcessId ([int]$marker.pid))) {
                throw 'Coleta já está em execução; aguarde ou encerre-a antes de tentar novamente.'
            }
            Remove-Item -LiteralPath $MarkerPath -Force -ErrorAction SilentlyContinue
        } catch {
            if ($_.Exception.Message -match 'já está em execução') { throw }
            throw 'Marcador de coleta inválido; transferência/coleta recusada até revisão manual.'
        }
    }
    if (Test-Path -LiteralPath $LockPath -PathType Leaf) {
        try {
            $lock = Get-Content -LiteralPath $LockPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if (-not $lock.pid -or (Test-TceProcessAlive -ProcessId ([int]$lock.pid))) {
                throw 'Outra operação portátil está em execução; aguarde ou encerre-a antes de tentar novamente.'
            }
            Remove-Item -LiteralPath $LockPath -Force -ErrorAction SilentlyContinue
        } catch {
            if ($_.Exception.Message -match 'está em execução') { throw }
            throw 'Lock de operação inválido; transferência/coleta recusada até revisão manual.'
        }
    }
}

function Start-TceCollectorLease {
    $bridgeRoot = Join-Path $scriptRoot 'dados-locais\bridge'
    [IO.Directory]::CreateDirectory($bridgeRoot) | Out-Null
    $transferRequestPath = Join-Path $bridgeRoot 'transfer-request.json'
    if (Test-TceTransferPauseRequested) {
        throw 'Transferência portátil em andamento; nova coleta foi pausada até a conclusão.'
    }
    $lockName = if ($ServiceChild) { '.collector.lock' } else { '.operation.lock' }
    $lockPath = Join-Path $bridgeRoot $lockName
    $markerPath = Join-Path $bridgeRoot 'collector.json'
    $token = [guid]::NewGuid().ToString('N')
    Remove-TceStaleLeaseFiles -LockPath $lockPath -MarkerPath $markerPath
    try {
        $stream = New-Object IO.FileStream($lockPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    } catch [IO.IOException] {
        throw 'Outra operação portátil está fechando ou transferindo o pacote; tente novamente depois.'
    }
    try {
        $metadata = [ordered]@{
            schema_version = 1
            kind = 'collector'
            pid = [int]$PID
            started_at = [DateTime]::UtcNow.ToString('o')
            token = $token
        }
        $bytes = [Text.Encoding]::UTF8.GetBytes((($metadata | ConvertTo-Json -Compress) + "`n"))
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        Write-TceJsonAtomic -Path $markerPath -Value $metadata
    } catch {
        $stream.Dispose()
        if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
            try {
                $currentLock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([string]$currentLock.token -eq $token) { Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
            } catch { }
        }
        throw
    }
    $script:CollectorLeaseStream = $stream
    $script:CollectorLeasePath = $lockPath
    $script:CollectorMarkerPath = $markerPath
    $script:CollectorLeaseToken = $token
}

function Test-TceTransferPauseRequested {
    $requestPath = Join-Path $scriptRoot 'dados-locais\bridge\transfer-request.json'
    if (-not (Test-Path -LiteralPath $requestPath -PathType Leaf)) { return $false }
    try {
        $request = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $request.pid -or (Test-TceProcessAlive -ProcessId ([int]$request.pid))) { return $true }
        Remove-Item -LiteralPath $requestPath -Force -ErrorAction SilentlyContinue
        return $false
    } catch {
        throw 'Solicitação de transferência inválida; coleta recusada até revisão manual.'
    }
}

function Stop-TceCollectorLease {
    $stream = $script:CollectorLeaseStream
    $lockPath = $script:CollectorLeasePath
    $markerPath = $script:CollectorMarkerPath
    $token = $script:CollectorLeaseToken
    $script:CollectorLeaseStream = $null
    $script:CollectorLeasePath = $null
    $script:CollectorMarkerPath = $null
    $script:CollectorLeaseToken = $null
    if ($null -eq $stream) { return }
    try {
        if (Test-Path -LiteralPath $markerPath -PathType Leaf) {
            try {
                $current = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([string]$current.token -eq $token) { Remove-Item -LiteralPath $markerPath -Force -ErrorAction SilentlyContinue }
            } catch { }
        }
    } finally {
        $stream.Dispose()
        if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
            try {
                $currentLock = Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ([string]$currentLock.token -eq $token) { Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue }
            } catch { }
        }
    }
}

function Invoke-TceIncrementalPreparation {
    param([Parameter(Mandatory)][string]$ProcessKey)
    if ([string]::IsNullOrWhiteSpace($Python) -or [string]::IsNullOrWhiteSpace($Tesseract) -or [string]::IsNullOrWhiteSpace($Tessdata)) {
        Write-Warning "Preparação incremental indisponível para ${ProcessKey}: runtime não informado; a coleta continuará e a análise poderá ser executada pelo menu."
        return
    }
    $pipelinePath = Join-Path $scriptRoot 'app\incremental_pipeline.py'
    if (-not (Test-Path -LiteralPath $pipelinePath -PathType Leaf)) { throw "Pipeline incremental ausente: $pipelinePath" }
    & $Python -B -s $pipelinePath --archive-root $Destino --process-key $ProcessKey --tesseract $Tesseract --tessdata $Tessdata
    if ($LASTEXITCODE -ne 0) { throw "Preparação incremental falhou para $ProcessKey (código $LASTEXITCODE)." }
}

try {
    Write-Host 'TCE/RN - coletor portátil de todos os eventos' -ForegroundColor Cyan
    Write-Host "Destino: $Destino"
    $knownKeys = @(Get-TceCompletedProcessKeys -ArchiveRoot $Destino -BaseConcluidos $BaseConcluidos -BaselineAllComplete:$BaselineAllComplete)
    $port = Start-TceBrowser
    Connect-TceCdp -Port $port
    Wait-TcePage

    if ($SomenteDiagnostico) {
        $diagnosticSession = Invoke-TceJavaScript -Payload @{ operation = 'session' }
        Write-Host "Diagnóstico aprovado. Navegador e conexão local funcionando. Sessão autenticada: $($diagnosticSession.authenticated)." -ForegroundColor Green
        return
    }

    if ($NaoInterativo) {
        Write-Host 'Modo não interativo: validando a sessão já aberta.' -ForegroundColor Yellow
    } else {
        Write-Host ''
        Write-Host 'Faça login na janela aberta e deixe a página “Meus Processos” visível.' -ForegroundColor Yellow
        [void](Read-Host 'Depois pressione ENTER aqui')
    }

    $session = Invoke-TceJavaScript -Payload @{ operation = 'session' }
    if (-not $session.authenticated) { throw 'Login não detectado. Entre no e-Contas e execute novamente.' }
    Write-Host "Sessão confirmada. Escopo e-Contas: $EscopoPortal. Setor: $($session.sector)" -ForegroundColor Green

    if (-not [string]::IsNullOrWhiteSpace($FilaCongelada) -and -not [string]::IsNullOrWhiteSpace($Selecao)) {
        throw 'Use FilaCongelada ou Selecao, não os dois ao mesmo tempo.'
    }
    $frozen = $null
    if (-not [string]::IsNullOrWhiteSpace($FilaCongelada)) {
        $requestedLot = if ($NumeroLote -gt 0) { [Nullable[int]]$NumeroLote } else { $null }
        $frozen = Read-TceFrozenQueue -Path $FilaCongelada -LotNumber $requestedLot
    }

    [void](Send-TceCdp -Method 'Page.navigate' -Params @{ url = $portalUrl })
    Wait-TcePage
    Start-Sleep -Seconds 2
    $targetKeys = if ($frozen) { @($frozen.items | ForEach-Object process_key) } else { @() }
    $targetMarker = if ($frozen) { $frozen.marker } else { $null }
    $allProcesses = @(Invoke-TceJavaScript -Payload @{ operation = 'enumerateProcesses'; targetKeys = $targetKeys; marker = $targetMarker })
    if (-not $allProcesses.Count) { throw 'Nenhum processo foi encontrado na lista atual.' }

    if ($frozen) {
        $byKey = @{}
        foreach ($process in $allProcesses) {
            $key = ConvertTo-TceCanonicalProcessKey -Process $process -Context 'lista atual do e-Contas'
            if ($byKey.ContainsKey($key)) { throw "Processo duplicado na lista atual do e-Contas: $key" }
            $byKey[$key] = $process
        }
        $selectedList = New-Object System.Collections.ArrayList
        $missing = New-Object System.Collections.ArrayList
        foreach ($queued in @($frozen.items)) {
            if ($byKey.ContainsKey($queued.process_key)) {
                [void]$selectedList.Add($byKey[$queued.process_key])
            } else {
                [void]$missing.Add($queued.process_key)
            }
        }
        if ($missing.Count) {
            throw "Fila congelada não encontrada integralmente no e-Contas; nenhum download iniciado. Ausentes: $([string]::Join(', ', @($missing)))"
        }
        $selected = @($selectedList)
        Write-Host "Fila congelada validada: $($selected.Count) processo(s)$(if ($frozen.lot_number) { ", lote $($frozen.lot_number)" }). Ordem preservada; substituições recusadas." -ForegroundColor Green
    } else {
        $view = $allProcesses
        Show-ProcessList -Processes $view
        $answer = $Selecao
        while ($true) {
            if (-not $answer) { $answer = Read-Host 'Selecione os processos' }
            if ($answer -match '^\s*buscar\s+(.+)$') {
                $view = @(Search-TceProcesses -Term $Matches[1] -Processes $allProcesses)
                Show-ProcessList -Processes $view
                $answer = ''
                continue
            }
            $selected = @(Resolve-TceSelection -InputText $answer -Processes $view -KnownProcessKeys $knownKeys)
            break
        }
    }
    if (-not $selected.Count) { Write-Host 'Nenhum processo selecionado.'; exit 0 }

    Start-TceCollectorLease
    Write-Host "`n$($selected.Count) processo(s) selecionado(s). Iniciando sincronização..." -ForegroundColor Cyan
    $totals = @{ downloaded = 0; skipped = 0; deduplicated = 0; failed = 0 }
    $collectionSuspended = $false
    for ($index = 0; $index -lt $selected.Count; $index++) {
        if (Test-TceTransferPauseRequested) {
            Write-Warning 'Transferência solicitada; novas operações foram pausadas e a coleta será drenada.'
            $collectionSuspended = $true
            break
        }
        $item = $selected[$index]
        Write-Host "[$($index + 1)/$($selected.Count)] $($item.key)" -ForegroundColor Cyan
        try {
            $manifest = Invoke-TceJavaScript -Payload @{ operation = 'manifest'; number = [string]$item.number; year = [int]$item.year }
            $badDocuments = @($manifest.events | ForEach-Object documents | Where-Object { -not (Get-TceObjectPropertyValue -InputObject $_ -Name 'url' -Default '') })
            foreach ($bad in $badDocuments) {
                $badTitle = Get-TceObjectPropertyValue -InputObject $bad -Name 'title' -Default 'Documento indisponível'
                $badError = Get-TceObjectPropertyValue -InputObject $bad -Name 'error' -Default 'Sem endereço de download.'
                Write-Warning (ConvertTo-TceSafeText "$($item.key): $badTitle - $badError")
            }
            $downloader = {
                param($document, $destination, $context)
                Invoke-TceBrowserDownload -Document $document -Destination $destination -Context $context
            }
            $result = Sync-TceProcessManifest -Manifest $manifest -ArchiveRoot $Destino -MaxDownloads 1 -Downloader $downloader -DownloaderContext $null
            $totals.downloaded += $result.downloaded
            $totals.skipped += $result.skipped
            $totals.deduplicated += $result.deduplicated
            if ($result.rate_limited) {
                Write-Warning "$($item.key): servidor limitou a taxa; próximas chamadas usarão um download por vez."
            }
            if ($result.auth_required -or $result.suspended) {
                $totals.failed++
                $authMessage = if ($result.auth_required) {
                    'Sessão expirada ou não autorizada. Faça login novamente antes de retomar a coleta.'
                } else {
                    'Acesso suspenso pelo servidor. Aguarde a liberação antes de retomar a coleta.'
                }
                Write-Warning "$($item.key): $authMessage"
                Write-SafeFailure -ProcessKey $item.key -Message $authMessage
                $collectionSuspended = $true
                break
            }
            Write-Host "  baixados: $($result.downloaded); já existentes: $($result.skipped); duplicados: $($result.deduplicated)" -ForegroundColor Green
            if ($ModoPreparacao -eq 'progressivo') {
                Invoke-TceIncrementalPreparation -ProcessKey $item.key
            }
            if (Test-TceTransferPauseRequested) {
                Write-Warning 'Transferência solicitada; fila drenada após o processo atual.'
                $collectionSuspended = $true
                break
            }
        } catch {
            $totals.failed++
            Write-Warning (ConvertTo-TceSafeText "$($item.key): $($_.Exception.Message)")
            Write-SafeFailure -ProcessKey $item.key -Message $_.Exception.Message
        }
    }

    if ($ModoPreparacao -eq 'completo' -and -not $collectionSuspended) {
        foreach ($item in $selected) {
            if (Test-TceTransferPauseRequested) {
                Write-Warning 'Transferência solicitada; preparação completa foi pausada.'
                $collectionSuspended = $true
                break
            }
            try {
                Invoke-TceIncrementalPreparation -ProcessKey $item.key
            } catch {
                Write-Warning (ConvertTo-TceSafeText "$($item.key): $($_.Exception.Message)")
                Write-SafeFailure -ProcessKey $item.key -Message $_.Exception.Message
            }
        }
    }

    Write-Host "`nConcluído ($ModoPreparacao). Baixados: $($totals.downloaded); reutilizados: $($totals.skipped); deduplicados: $($totals.deduplicated); processos com falha: $($totals.failed)." -ForegroundColor Green
    Write-Host "Acervo: $Destino"
} finally {
    Stop-TceCollectorLease
    if ($script:CdpSocket) { $script:CdpSocket.Dispose() }
    if ($script:AreaCdpSocket) { $script:AreaCdpSocket.Dispose() }
    if (-not $ManterNavegadorAberto -and $script:BrowserProcess -and -not $script:BrowserProcess.HasExited) {
        $script:BrowserProcess.CloseMainWindow() | Out-Null
    }
}
