<#
.SYNOPSIS
Leitura SÓ LEITURA da Área Restrita autenticada através de CDP.

.DESCRIPTION
Fallback de compatibilidade do marco M2. Reaproveita o padrão de conexão CDP já
comprovado em work/tce-extractor/probe-existing-chrome.ps1 e executa o MESMO
scanner da extensão (extension/lib/area-snapshot.js), de modo que o snapshot
tenha exatamente o mesmo esquema do caminho principal.

Este script NÃO abre "Complementar Ato", NÃO seleciona interessado, NÃO escreve
campo algum e NÃO clica em controle de conclusão. A única navegação permitida é
a paginação da lista, feita com o controle localizado pelo próprio scanner.

Saída: um único objeto JSON no stdout. Diagnóstico vai para stderr.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$ChromeUserData = "$env:LOCALAPPDATA\Google\Chrome\User Data",
    [string]$PortalPattern = 'novaarearestrita\.tce\.rn\.gov\.br',
    [int]$MaxPages = 50,
    [int]$NavigationWaitMs = 1200,
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

function Write-Diagnostic { param([string]$Message) [Console]::Error.WriteLine($Message) }

$scannerPath = Join-Path (Join-Path $RepoRoot 'extension\lib') 'area-snapshot.js'
if (-not (Test-Path -LiteralPath $scannerPath -PathType Leaf)) {
    throw "scanner da extensão não encontrado: $scannerPath"
}
$scannerSource = Get-Content -LiteralPath $scannerPath -Raw -Encoding UTF8
$scannerLiteral = $scannerSource | ConvertTo-Json -Compress

$portFile = Join-Path $ChromeUserData 'DevToolsActivePort'
if (-not (Test-Path -LiteralPath $portFile -PathType Leaf)) {
    throw "o Chrome não expõe DevToolsActivePort em $portFile (abra o Chrome com depuração remota)"
}
$portLines = @(Get-Content -LiteralPath $portFile -Encoding UTF8)
if ($portLines.Count -lt 2) { throw 'DevToolsActivePort incompleto.' }

$socket = New-Object Net.WebSockets.ClientWebSocket
$connectTimeout = New-Object Threading.CancellationTokenSource ([TimeSpan]::FromSeconds($TimeoutSeconds))
try {
    $socket.ConnectAsync(
        [Uri]('ws://127.0.0.1:{0}{1}' -f $portLines[0], $portLines[1]),
        $connectTimeout.Token
    ).GetAwaiter().GetResult()
} finally {
    $connectTimeout.Dispose()
}

$script:sequence = 0
function Send-CdpCommand {
    param([string]$Method, [hashtable]$Params = @{}, [string]$SessionId = '')
    $script:sequence++
    $request = @{ id = $script:sequence; method = $Method; params = $Params }
    if ($SessionId) { $request.sessionId = $SessionId }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($request | ConvertTo-Json -Compress -Depth 30))
    $segment = New-Object 'ArraySegment[byte]' -ArgumentList @(, $bytes)
    [void]$socket.SendAsync(
        $segment, [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None
    ).GetAwaiter().GetResult()
    while ($true) {
        $stream = New-Object IO.MemoryStream
        do {
            $buffer = New-Object byte[] 1048576
            $receive = New-Object 'ArraySegment[byte]' -ArgumentList @(, $buffer)
            $receiveTimeout = New-Object Threading.CancellationTokenSource ([TimeSpan]::FromSeconds($TimeoutSeconds))
            try {
                $result = $socket.ReceiveAsync($receive, $receiveTimeout.Token).GetAwaiter().GetResult()
            } finally {
                $receiveTimeout.Dispose()
            }
            if ($result.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) { throw 'O Chrome encerrou a conexão CDP.' }
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

function Invoke-Evaluation {
    param([string]$SessionId, [string]$Expression)
    $attempts = 0
    while ($true) {
        $attempts++
        try {
            return Send-CdpCommand -Method 'Runtime.evaluate' -SessionId $SessionId -Params @{
                expression = $Expression
                returnByValue = $true
                awaitPromise = $true
            }
        } catch {
            # The portal may be mid-navigation between pages.
            if ($attempts -ge 4) { throw }
            Start-Sleep -Milliseconds 700
        }
    }
}

$collectTemplate = @'
(() => {
  const SCANNER = __SCANNER__;
  const found = [];
  const blocked = [];
  const visit = (win, depth, label) => {
    if (!win || depth > 8) return;
    let doc = null;
    try { doc = win.document; } catch (error) { blocked.push(label); return; }
    try {
      if (!(win.TCEAreaSnapshot && win.TCEAreaSnapshot.scan)) { win.eval(SCANNER); }
    } catch (error) { blocked.push(label); }
    try {
      const snapshot = win.TCEAreaSnapshot && win.TCEAreaSnapshot.scan(doc);
      if (snapshot && Array.isArray(snapshot.rows)) found.push(snapshot);
    } catch (error) { blocked.push(label); }
    let frames = null;
    try { frames = win.frames; } catch (error) { return; }
    for (let index = 0; index < (frames ? frames.length : 0); index += 1) {
      visit(frames[index], depth + 1, label + '/' + index);
    }
  };
  visit(window, 0, 'top');
  const ranked = found.slice().sort((left, right) => right.rows.length - left.rows.length);
  const best = ranked[0] || null;
  if (!best) {
    return JSON.stringify({ role: 'unknown', source_scope: null, marker: null, page: 1, total_pages: 1, rows: [], blocked_frames: blocked });
  }
  return JSON.stringify({
    role: best.role,
    source_scope: best.source_scope,
    marker: best.marker,
    page: best.page,
    total_pages: best.total_pages,
    rows: best.rows,
    blocked_frames: blocked,
  });
})()
'@

$nextTemplate = @'
(() => {
  const visit = (win, depth) => {
    if (!win || depth > 8) return false;
    try {
      const scanner = win.TCEAreaSnapshot;
      if (scanner && scanner.findNextPageControl) {
        const control = scanner.findNextPageControl(win.document);
        if (control) { control.click(); return true; }
      }
    } catch (error) { /* frame sem o portal */ }
    let frames = null;
    try { frames = win.frames; } catch (error) { return false; }
    for (let index = 0; index < (frames ? frames.length : 0); index += 1) {
      if (visit(frames[index], depth + 1)) return true;
    }
    return false;
  };
  return visit(window, 0);
})()
'@

$collectExpression = $collectTemplate.Replace('__SCANNER__', $scannerLiteral)

try {
    $targets = Send-CdpCommand -Method 'Target.getTargets'
    $target = @(
        $targets.targetInfos |
            Where-Object { $_.type -eq 'page' -and $_.url -match $PortalPattern } |
            Select-Object -First 1
    )
    if (-not $target) {
        throw 'Nenhuma aba da Área Restrita está aberta no Chrome exposto por CDP.'
    }
    $attached = Send-CdpCommand -Method 'Target.attachToTarget' -Params @{ targetId = $target[0].targetId; flatten = $true }
    $sessionId = [string]$attached.sessionId

    $snapshots = New-Object System.Collections.Generic.List[object]
    $blockedFrames = New-Object System.Collections.Generic.List[string]
    $pagesVisited = 0
    for ($page = 0; $page -lt $MaxPages; $page++) {
        $evaluated = Invoke-Evaluation -SessionId $sessionId -Expression $collectExpression
        $raw = [string]$evaluated.result.value
        if (-not $raw) { throw 'A leitura da página não devolveu snapshot.' }
        $snapshot = $raw | ConvertFrom-Json
        $snapshots.Add($snapshot)
        $pagesVisited++
        foreach ($frame in @($snapshot.blocked_frames)) {
            if ($frame -and -not $blockedFrames.Contains($frame)) { $blockedFrames.Add($frame) }
        }
        if ([int]$snapshot.total_pages -le [int]$snapshot.page) { break }
        $clicked = Invoke-Evaluation -SessionId $sessionId -Expression $nextTemplate
        if (-not $clicked.result.value) { break }
        Start-Sleep -Milliseconds $NavigationWaitMs
    }
} finally {
    if ($socket.State -eq [Net.WebSockets.WebSocketState]::Open) { $socket.Dispose() }
}

if ($snapshots.Count -eq 0) { throw 'Nenhuma página da Área Restrita pôde ser lida.' }

$seen = @{}
$rows = New-Object System.Collections.Generic.List[object]
foreach ($snapshot in $snapshots) {
    foreach ($row in @($snapshot.rows)) {
        $key = '{0}|{1}' -f $row.process_key, $row.interested_normalized
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        $rows.Add($row)
    }
}

$last = $snapshots[$snapshots.Count - 1]
$marker = $null
$sourceScope = $null
foreach ($snapshot in $snapshots) {
    if (-not $marker -and $snapshot.marker) { $marker = $snapshot.marker }
    if (-not $sourceScope -and $snapshot.source_scope) { $sourceScope = $snapshot.source_scope }
}

$payload = [ordered]@{
    role          = [string]$last.role
    source_scope  = $sourceScope
    marker        = $marker
    page          = $pagesVisited
    total_pages   = [int]$last.total_pages
    rows          = $rows.ToArray()
    origin        = 'cdp'
    pages_visited = $pagesVisited
    blocked_frames = $blockedFrames.ToArray()
}

Write-Diagnostic ('páginas lidas: {0}; linhas: {1}; frames bloqueados: {2}' -f $pagesVisited, $rows.Count, $blockedFrames.Count)
ConvertTo-Json -InputObject $payload -Depth 12 -Compress
