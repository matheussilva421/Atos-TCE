[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int] $Port = 9222,

    [ValidateRange(250, 30000)]
    [int] $TimeoutMs = 3000
)

$ErrorActionPreference = 'Stop'
$request = $null
$response = $null
$reader = $null

try {
    $endpoint = "http://127.0.0.1:$Port/json/version"
    $request = [System.Net.HttpWebRequest]::Create($endpoint)
    $request.Method = 'GET'
    $request.AllowAutoRedirect = $false
    $request.Proxy = $null
    $request.Timeout = $TimeoutMs
    $request.ReadWriteTimeout = $TimeoutMs
    $response = [System.Net.HttpWebResponse] $request.GetResponse()
    if ([int] $response.StatusCode -ne 200) {
        throw 'CDP version endpoint did not return HTTP 200.'
    }

    $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
    $body = $reader.ReadToEnd()
    try {
        $version = ConvertFrom-Json -InputObject $body -ErrorAction Stop
    }
    catch {
        throw 'CDP version response is invalid.'
    }

    $webSocketText = [string] $version.webSocketDebuggerUrl
    $webSocketUri = $null
    if (-not [Uri]::TryCreate($webSocketText, [UriKind]::Absolute, [ref] $webSocketUri) -or
        $webSocketUri.Scheme -ne 'ws') {
        throw 'CDP websocket endpoint is invalid.'
    }

    $loopbackHosts = @('127.0.0.1', 'localhost', '::1')
    if ($webSocketUri.Host -notin $loopbackHosts) {
        throw 'CDP websocket endpoint must use loopback.'
    }
    if ($webSocketUri.Port -ne $Port) {
        throw 'CDP websocket endpoint port does not match the requested port.'
    }

    "CDP_ENDPOINT_OK port=$Port host=127.0.0.1"
}
catch [System.Net.WebException] {
    $webResponse = $_.Exception.Response
    if ($webResponse -and $webResponse -is [System.Net.HttpWebResponse] -and
        [int] $webResponse.StatusCode -ne 200) {
        throw 'CDP version endpoint did not return HTTP 200.'
    }
    throw 'Unable to read the loopback CDP version endpoint.'
}
finally {
    if ($reader) { $reader.Dispose() }
    if ($response) { $response.Dispose() }
}
