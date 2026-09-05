param(
    [string]$ManifestDirectory = (Join-Path $PSScriptRoot '..\tce-downloads\single-manifests'),
    [string]$CollectionRoot = (Join-Path $PSScriptRoot '..\tce-downloads'),
    [string]$OutputDirectory = '',
    [string]$StateDirectory = '',
    [ValidateRange(1, 6)]
    [int]$MaxParallel = 3
)

$manifestRoot = [IO.Path]::GetFullPath($ManifestDirectory)
$collectionRootPath = [IO.Path]::GetFullPath($CollectionRoot)
$scriptPath = Join-Path $PSScriptRoot 'targeted_collection.py'
$outputDirectoryPath = if ($OutputDirectory) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    Join-Path $collectionRootPath 'alvos-organizados'
}
$stateDirectoryPath = if ($StateDirectory) {
    [IO.Path]::GetFullPath($StateDirectory)
} else {
    Join-Path $collectionRootPath 'single-results'
}
$logDirectory = Join-Path $stateDirectoryPath 'logs'

if (-not (Test-Path -LiteralPath $manifestRoot -PathType Container)) {
    throw "Diretório de manifestos não encontrado: $manifestRoot"
}

New-Item -ItemType Directory -Force -Path $outputDirectoryPath, $stateDirectoryPath, $logDirectory | Out-Null
$queue = [Collections.Generic.Queue[IO.FileInfo]]::new()
Get-ChildItem -LiteralPath $manifestRoot -File -Filter '*.json' |
    Sort-Object Name |
    ForEach-Object { $queue.Enqueue($_) }

$running = @{}
$failures = [Collections.Generic.List[object]]::new()
$completed = 0
$total = $queue.Count

while ($queue.Count -gt 0 -or $running.Count -gt 0) {
    while ($queue.Count -gt 0 -and $running.Count -lt $MaxParallel) {
        $manifest = $queue.Dequeue()
        $stem = $manifest.BaseName
        $stdout = Join-Path $logDirectory "$stem.out.log"
        $stderr = Join-Path $logDirectory "$stem.err.log"
        $arguments = @(
            $scriptPath,
            '--manifest', $manifest.FullName,
            '--output-dir', $outputDirectoryPath,
            '--checkpoint', (Join-Path $stateDirectoryPath "$stem.checkpoint.json"),
            '--target-manifest', (Join-Path $stateDirectoryPath "$stem.targets.json")
        )
        $process = Start-Process -FilePath 'python' -ArgumentList $arguments `
            -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
            -WindowStyle Hidden -PassThru
        $running[$process.Id] = [pscustomobject]@{
            Process = $process
            Name = $stem
            Stdout = $stdout
            Stderr = $stderr
        }
    }

    foreach ($id in @($running.Keys)) {
        $job = $running[$id]
        if (-not $job.Process.HasExited) {
            continue
        }
        $job.Process.Refresh()
        if ($job.Process.ExitCode -ne 0) {
            $failures.Add([pscustomobject]@{
                Process = $job.Name
                ExitCode = $job.Process.ExitCode
                ErrorLog = $job.Stderr
            })
        }
        $running.Remove($id)
        $completed++
        Write-Output "[$completed/$total] $($job.Name)"
    }

    if ($running.Count -gt 0) {
        Start-Sleep -Milliseconds 250
    }
}

[pscustomobject]@{
    Total = $total
    Completed = $completed
    Failed = $failures.Count
    Failures = $failures
    StateDirectory = $stateDirectoryPath
    OutputDirectory = $outputDirectoryPath
} | ConvertTo-Json -Depth 5

if ($failures.Count -gt 0) {
    exit 1
}
