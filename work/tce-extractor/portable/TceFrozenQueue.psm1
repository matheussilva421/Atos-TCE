Set-StrictMode -Version Latest

function Get-TceFrozenQueueProperty {
    param(
        [AllowNull()][object]$InputObject,
        [Parameter(Mandatory)][string]$Name
    )
    if ($null -eq $InputObject) { return $null }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function ConvertTo-TceFrozenQueueKey {
    param(
        [Parameter(Mandatory)][object]$Item,
        [Parameter(Mandatory)][string]$Context
    )
    $raw = [string](Get-TceFrozenQueueProperty -InputObject $Item -Name 'process_key')
    $match = [regex]::Match($raw, '^\s*(\d+)\s*/\s*(\d{4})\s*$')
    if (-not $match.Success) { throw "${Context}: process_key inválido." }
    return '{0}/{1}' -f $match.Groups[1].Value, $match.Groups[2].Value
}

function Get-TceFrozenQueueSha256 {
    param([Parameter(Mandatory)][string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Read-TceFrozenQueue {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [AllowNull()][Nullable[int]]$LotNumber = $null
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Fila congelada inexistente: $Path"
    }
    try {
        $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        throw "Fila congelada inválida: $Path"
    }
    if ($null -eq $value -or [int](Get-TceFrozenQueueProperty $value 'schema_version') -notin @(1, 2)) {
        throw 'schema_version da fila congelada incompatível.'
    }

    $analysisId = [string](Get-TceFrozenQueueProperty $value 'analysis_id')
    $datasetSha = [string](Get-TceFrozenQueueProperty $value 'dataset_sha256')
    $canonicalJson = [string](Get-TceFrozenQueueProperty $value 'canonical_json')
    if ($analysisId -notmatch '^analysis-[0-9a-f]{24}$' -or $datasetSha -notmatch '^[0-9a-f]{64}$' -or [string]::IsNullOrWhiteSpace($canonicalJson)) {
        throw 'Identidade/hash ausente ou inválida na fila congelada.'
    }
    $actualSha = Get-TceFrozenQueueSha256 -Text $canonicalJson
    if ($actualSha -cne $datasetSha -or $analysisId -cne ('analysis-' + $actualSha.Substring(0, 24))) {
        throw 'Hash ou identidade da fila congelada não confere.'
    }

    $spec = Get-TceFrozenQueueProperty $value 'spec'
    if ($null -eq $spec) { throw 'spec ausente na fila congelada.' }
    $sourceScope = [string](Get-TceFrozenQueueProperty $spec 'source_scope')
    if ($sourceScope -notin @('sector_finalistic', 'my_processes')) { throw 'source_scope inválido na fila congelada.' }
    if ([string](Get-TceFrozenQueueProperty $spec 'acquisition_source') -cne 'econtas') { throw 'acquisition_source da fila deve ser econtas.' }

    $queue = @(Get-TceFrozenQueueProperty $value 'queue')
    if ($null -eq (Get-TceFrozenQueueProperty $value 'queue')) { throw 'queue ausente na fila congelada.' }
    $seen = @{}
    $normalizedQueue = New-Object System.Collections.ArrayList
    foreach ($item in $queue) {
        $key = ConvertTo-TceFrozenQueueKey -Item $item -Context 'queue'
        if ($seen.ContainsKey($key)) { throw "chave duplicada na fila congelada: $key" }
        $seen[$key] = $true
        [void]$normalizedQueue.Add([pscustomobject]@{ process_key = $key; source = $item })
    }

    $lotsValue = Get-TceFrozenQueueProperty $value 'lots'
    $lots = @()
    if ($null -ne $lotsValue) {
        $lots = @($lotsValue)
        $flattened = New-Object System.Collections.ArrayList
        for ($index = 0; $index -lt $lots.Count; $index++) {
            $lot = $lots[$index]
            $number = [int](Get-TceFrozenQueueProperty $lot 'lot_number')
            if ($number -ne ($index + 1) -or [string](Get-TceFrozenQueueProperty $lot 'lot_id') -cne "lot-$number") {
                throw 'Lotes da fila congelada não são sequenciais.'
            }
            foreach ($item in @((Get-TceFrozenQueueProperty $lot 'items'))) {
                $key = ConvertTo-TceFrozenQueueKey -Item $item -Context "lots[$index].items"
                [void]$flattened.Add($key)
            }
        }
        $queueKeys = @($normalizedQueue | ForEach-Object process_key)
        if ((ConvertTo-Json $flattened -Compress) -cne (ConvertTo-Json $queueKeys -Compress)) {
            throw 'Lotes não preservam a ordem da fila congelada.'
        }
    }

    if ($null -ne $LotNumber) {
        if ([int]$LotNumber -lt 1) { throw 'NumeroLote deve ser positivo.' }
        if (-not $lots.Count) { throw 'NumeroLote solicitado, mas a análise não possui lotes.' }
        $chosen = @($lots | Where-Object { [int](Get-TceFrozenQueueProperty $_ 'lot_number') -eq [int]$LotNumber })
        if ($chosen.Count -ne 1) { throw "Lote inexistente: $([int]$LotNumber)" }
        $items = @((Get-TceFrozenQueueProperty $chosen[0] 'items'))
    } else {
        $items = @($normalizedQueue)
    }
    if (-not $items.Count) { throw 'A fila congelada não contém processos elegíveis.' }

    $normalizedItems = New-Object System.Collections.ArrayList
    foreach ($item in $items) {
        [void]$normalizedItems.Add([pscustomobject]@{
            process_key = ConvertTo-TceFrozenQueueKey -Item $item -Context 'lote'
            source = $item
        })
    }
    return [pscustomobject]@{
        analysis_id = $analysisId
        dataset_sha256 = $datasetSha
        source_scope = $sourceScope
        marker = Get-TceFrozenQueueProperty $spec 'marker'
        lot_number = if ($null -ne $LotNumber) { [int]$LotNumber } else { $null }
        queue_size = $normalizedQueue.Count
        items = @($normalizedItems)
    }
}

Export-ModuleMember -Function Read-TceFrozenQueue
