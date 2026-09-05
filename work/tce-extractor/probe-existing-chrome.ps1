[CmdletBinding()]
param(
    [string]$Processo = '103439/2023',
    [string]$ChromeUserData = "$env:LOCALAPPDATA\Google\Chrome\User Data"
)

$ErrorActionPreference = 'Stop'
$portFile = Join-Path $ChromeUserData 'DevToolsActivePort'
if (-not (Test-Path -LiteralPath $portFile -PathType Leaf)) {
    throw "Chrome aberto não expõe DevToolsActivePort: $portFile"
}
$lines = @(Get-Content -LiteralPath $portFile -Encoding UTF8)
if ($lines.Count -lt 2) { throw 'DevToolsActivePort incompleto.' }
$socket = New-Object Net.WebSockets.ClientWebSocket
$connectTimeout = New-Object Threading.CancellationTokenSource ([TimeSpan]::FromSeconds(10))
$socket.ConnectAsync([Uri]("ws://127.0.0.1:{0}{1}" -f $lines[0], $lines[1]), $connectTimeout.Token).GetAwaiter().GetResult()
$connectTimeout.Dispose()
$script:sequence = 0

function Send-CdpCommand {
    param([string]$Method, [hashtable]$Params = @{}, [string]$SessionId = '')
    $script:sequence++
    $request = @{ id = $script:sequence; method = $Method; params = $Params }
    if ($SessionId) { $request.sessionId = $SessionId }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($request | ConvertTo-Json -Compress -Depth 30))
    $segment = New-Object 'ArraySegment[byte]' -ArgumentList @(,$bytes)
    [void]$socket.SendAsync($segment, [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult()
    while ($true) {
        $stream = New-Object IO.MemoryStream
        do {
            $buffer = New-Object byte[] 1048576
            $receive = New-Object 'ArraySegment[byte]' -ArgumentList @(,$buffer)
            $receiveTimeout = New-Object Threading.CancellationTokenSource ([TimeSpan]::FromSeconds(10))
            try {
                $result = $socket.ReceiveAsync($receive, $receiveTimeout.Token).GetAwaiter().GetResult()
            } finally {
                $receiveTimeout.Dispose()
            }
            if ($result.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) { throw 'Chrome encerrou a conexão CDP.' }
            $stream.Write($buffer, 0, $result.Count)
        } while (-not $result.EndOfMessage)
        $message = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
        $stream.Dispose()
        if ($message.id -eq $script:sequence) {
            if ($message.error) { throw "CDP $Method falhou: $($message.error.message)" }
            return $message.result
        }
    }
}

try {
    $targets = Send-CdpCommand -Method 'Target.getTargets'
    $target = @($targets.targetInfos | Where-Object { $_.type -eq 'page' -and $_.url -match 'processos\.tce\.rn\.gov\.br' } | Select-Object -First 1)
    if (-not $target) { throw 'Aba do e-Contas não encontrada no Chrome exposto por CDP.' }
    $attached = Send-CdpCommand -Method 'Target.attachToTarget' -Params @{ targetId = $target[0].targetId; flatten = $true }
    $sessionId = [string]$attached.sessionId
    $sessionExpression = "(()=>{try{const u=JSON.parse(localStorage.getItem('currentUser')||'null');return {authenticated:!!(u&&u.token),sector:(u&&u.setorSelecionado&&u.setorSelecionado.codigoSetor)||''}}catch(_){return {authenticated:false,sector:''}}})()"
    $session = Send-CdpCommand -Method 'Runtime.evaluate' -SessionId $sessionId -Params @{ expression = $sessionExpression; returnByValue = $true }
    $safeSession = $session.result.value
    if (-not $safeSession.authenticated) { throw 'Sessão do e-Contas não está autenticada.' }

    if ($Processo -notmatch '^\s*(\d{5,8})\s*/\s*(20\d{2})\s*$') { throw 'Processo deve usar número/ano.' }
    $driver = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'portable\TcePortal.Driver.js') -Raw -Encoding UTF8
    $payload = @{ operation = 'manifest'; number = $Matches[1]; year = [int]$Matches[2] } | ConvertTo-Json -Compress
    $expression = "Promise.resolve(($driver)($payload)).then(m=>({process:m.process.key,events:m.events.length,documents:m.events.reduce((n,e)=>n+e.documents.length,0),postEventDocuments:m.events.filter(e=>Number(e.event)>1).reduce((n,e)=>n+e.documents.length,0)}))"
    $manifest = Send-CdpCommand -Method 'Runtime.evaluate' -SessionId $sessionId -Params @{ expression = $expression; awaitPromise = $true; returnByValue = $true }
    [pscustomobject]@{
        authenticated = [bool]$safeSession.authenticated
        sector = [string]$safeSession.sector
        process = [string]$manifest.result.value.process
        events = [int]$manifest.result.value.events
        documents = [int]$manifest.result.value.documents
        post_event_documents = [int]$manifest.result.value.postEventDocuments
    } | ConvertTo-Json -Compress
} finally {
    $socket.Dispose()
}
