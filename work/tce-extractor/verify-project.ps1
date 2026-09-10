[CmdletBinding()]
param(
    [string]$ProjectRoot = '',
    [ValidateRange(1, 86400)][int]$TimeoutSeconds = 900,
    [string]$LogRoot = '',
    [string]$CommandOverridesPath = '',
    [switch]$DryRun,
    [switch]$Authenticated,
    [switch]$Collect,
    [switch]$Send
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:ExitCodes = [ordered]@{
    extension = 10
    web = 11
    python = 12
    powershell = 13
    package = 14
    diff = 15
}
$script:TimeoutCode = 124
$script:SafetyCode = 64

function Write-FatalVerificationMessage {
    param([Parameter(Mandatory)][string]$Message, [Parameter(Mandatory)][int]$Code)
    Write-Output ('ERROR: ' + $Message)
    exit $Code
}

if ($Authenticated -or $Collect -or $Send) {
    Write-FatalVerificationMessage 'verification is offline only; authenticated, collection, and send modes are refused' $script:SafetyCode
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
} else {
    $ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
}
if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    Write-FatalVerificationMessage ('project root does not exist: ' + $ProjectRoot) $script:SafetyCode
}

function Resolve-ExecutablePath {
    param([Parameter(Mandatory)][string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) { return $command.Source }
    return $Name
}

function Get-WindowsPowerShellPath {
    $candidate = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return (Resolve-ExecutablePath 'powershell.exe')
}

function ConvertTo-ProcessArgument {
    param([AllowNull()][object]$Value)
    $text = [string]$Value
    if ($text -notmatch '[\s"]') { return $text }
    return '"' + $text.Replace('"', '\"') + '"'
}

function ConvertTo-ProcessArguments {
    param([AllowNull()][object[]]$Arguments)
    return ((@($Arguments) | ForEach-Object { ConvertTo-ProcessArgument $_ }) -join ' ')
}

function Get-ObjectPropertyValue {
    param([AllowNull()][object]$InputObject, [Parameter(Mandatory)][string]$Name)
    if ($null -eq $InputObject) { return $null }
    $property = $InputObject.PSObject.Properties[$Name]
    if ($null -eq $property) { return $null }
    return $property.Value
}

function New-VerificationCommand {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [AllowNull()][object[]]$Arguments,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$DisplayCommand
    )
    [pscustomobject]@{
        FilePath = $FilePath
        Arguments = @($Arguments | ForEach-Object { [string]$_ })
        WorkingDirectory = $WorkingDirectory
        DisplayCommand = $DisplayCommand
    }
}

function New-VerificationStage {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][int]$Code,
        [Parameter(Mandatory)][object[]]$Commands,
        [Parameter(Mandatory)][string]$DisplayCommand
    )
    [pscustomobject]@{
        Name = $Name
        Code = $Code
        Commands = @($Commands)
        DisplayCommand = $DisplayCommand
    }
}

function Get-DefaultVerificationStages {
    $portableRoot = Join-Path $ProjectRoot 'work\tce-extractor\portable'
    $extensionRoot = Join-Path $portableRoot 'extensao-complementar-ato'
    $webRoot = Join-Path $portableRoot 'app\web'
    $testsRoot = Join-Path $ProjectRoot 'work\tce-extractor\tests'
    $extractorRoot = Join-Path $ProjectRoot 'work\tce-extractor'
    $node = Resolve-ExecutablePath 'node.exe'
    $python = Resolve-ExecutablePath 'python.exe'
    $git = Resolve-ExecutablePath 'git.exe'
    $powershell = Get-WindowsPowerShellPath

    $extensionCommand = New-VerificationCommand -FilePath $node -Arguments @('--test') -WorkingDirectory $extensionRoot -DisplayCommand 'npm test (package.json -> node --test)'

    $webArguments = @('--test')
    $webTestsPath = Join-Path $webRoot 'tests'
    if (Test-Path -LiteralPath $webTestsPath -PathType Container) {
        foreach ($testFile in @(Get-ChildItem -LiteralPath $webTestsPath -File -Filter '*.test.mjs' | Sort-Object Name)) {
            $webArguments += $testFile.FullName
        }
    }
    $webCommand = New-VerificationCommand -FilePath $node -Arguments $webArguments -WorkingDirectory $webRoot -DisplayCommand 'node --test tests/*.test.mjs'

    $pythonCommand = New-VerificationCommand -FilePath $python -Arguments @('-m', 'unittest', 'discover', '-s', 'portable', '-p', 'test_*.py', '-q') -WorkingDirectory $extractorRoot -DisplayCommand 'python -m unittest discover -s portable -p test_*.py -q'

    $powerShellCommands = @()
    foreach ($testName in @('Test-DocumentationTracking.ps1', 'Test-PortableMenu.ps1', 'Test-PortableReset.ps1', 'Test-ProjectVerification.ps1', 'Test-TcePortable.ps1', 'Test-WorkspaceCleanup.ps1')) {
        $testPath = Join-Path $testsRoot $testName
        $powerShellCommands += New-VerificationCommand -FilePath $powershell -Arguments @('-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $testPath) -WorkingDirectory $extractorRoot -DisplayCommand ('powershell.exe -NoProfile -File tests/' + $testName)
    }

    $packageCommand = New-VerificationCommand -FilePath $python -Arguments @('-m', 'unittest', 'test_extension_zip_packager', 'test_package_complete_archive', 'test_package_audit', 'test_prepare_transfer', '-q') -WorkingDirectory $extractorRoot -DisplayCommand 'python -m unittest test_extension_zip_packager test_package_complete_archive test_package_audit test_prepare_transfer -q'
    $diffCommand = New-VerificationCommand -FilePath $git -Arguments @('diff', '--check') -WorkingDirectory $ProjectRoot -DisplayCommand 'git diff --check'

    @(
        (New-VerificationStage -Name 'extension' -Code $script:ExitCodes.extension -Commands @($extensionCommand) -DisplayCommand 'extension: npm test'),
        (New-VerificationStage -Name 'web' -Code $script:ExitCodes.web -Commands @($webCommand) -DisplayCommand 'web: node --test tests/*.test.mjs'),
        (New-VerificationStage -Name 'python' -Code $script:ExitCodes.python -Commands @($pythonCommand) -DisplayCommand 'python: unittest discover -s portable'),
        (New-VerificationStage -Name 'powershell' -Code $script:ExitCodes.powershell -Commands $powerShellCommands -DisplayCommand 'powershell: tests/Test-*.ps1'),
        (New-VerificationStage -Name 'package' -Code $script:ExitCodes.package -Commands @($packageCommand) -DisplayCommand 'package/audit: unittest package contracts'),
        (New-VerificationStage -Name 'diff' -Code $script:ExitCodes.diff -Commands @($diffCommand) -DisplayCommand 'git diff --check')
    )
}

function Apply-CommandOverrides {
    param([Parameter(Mandatory)][object[]]$Stages, [Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-FatalVerificationMessage ('command override file does not exist: ' + $Path) $script:SafetyCode
    }
    try {
        $overrides = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-FatalVerificationMessage ('command override file is not valid JSON: ' + $Path) $script:SafetyCode
    }
    $knownNames = @($Stages | ForEach-Object { $_.Name })
    foreach ($property in @($overrides.PSObject.Properties)) {
        if ($knownNames -notcontains $property.Name) {
            Write-FatalVerificationMessage ('unknown command override stage: ' + $property.Name) $script:SafetyCode
        }
    }
    foreach ($stage in $Stages) {
        $property = $overrides.PSObject.Properties[$stage.Name]
        if ($null -eq $property) { continue }
        $override = $property.Value
        $filePath = [string](Get-ObjectPropertyValue $override 'filePath')
        $workingDirectory = [string](Get-ObjectPropertyValue $override 'workingDirectory')
        $displayCommand = [string](Get-ObjectPropertyValue $override 'displayCommand')
        if ([string]::IsNullOrWhiteSpace($filePath) -or [string]::IsNullOrWhiteSpace($workingDirectory)) {
            Write-FatalVerificationMessage ('invalid command override for stage: ' + $stage.Name) $script:SafetyCode
        }
        if (-not (Test-Path -LiteralPath $workingDirectory -PathType Container)) {
            Write-FatalVerificationMessage ('override working directory does not exist: ' + $workingDirectory) $script:SafetyCode
        }
        $argumentValue = Get-ObjectPropertyValue $override 'arguments'
        $arguments = @()
        if ($null -ne $argumentValue) {
            if ($argumentValue -is [System.Array]) { $arguments = @($argumentValue | ForEach-Object { [string]$_ }) }
            else { $arguments = @([string]$argumentValue) }
        }
        if ([string]::IsNullOrWhiteSpace($displayCommand)) { $displayCommand = $stage.Name + ' override' }
        $stage.Commands = @(
            (New-VerificationCommand -FilePath $filePath -Arguments $arguments -WorkingDirectory $workingDirectory -DisplayCommand $displayCommand)
        )
    }
    return $Stages
}

function Stop-VerificationProcessTree {
    param([Parameter(Mandatory)][System.Diagnostics.Process]$Process)
    if ($Process.HasExited) { return }
    $taskkill = Join-Path $env:SystemRoot 'System32\taskkill.exe'
    if (Test-Path -LiteralPath $taskkill -PathType Leaf) {
        try {
            & $taskkill /PID ([string]$Process.Id) /T /F 2>$null | Out-Null
        } catch {
        }
    }
    try {
        if (-not $Process.HasExited) { $Process.Kill() }
    } catch {
    }
    try { [void]$Process.WaitForExit(5000) } catch { }
}

function Invoke-VerificationProcess {
    param(
        [Parameter(Mandatory)][object]$Command,
        [Parameter(Mandatory)][int]$Timeout,
        [Parameter(Mandatory)][string]$LogPath
    )
    $stdoutPath = $LogPath + '.stdout.log'
    $stderrPath = $LogPath + '.stderr.log'
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $Command.FilePath
    $startInfo.Arguments = ConvertTo-ProcessArguments $Command.Arguments
    $startInfo.WorkingDirectory = $Command.WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $stdout = ''
    $stderr = ''
    $timedOut = $false
    try {
        try {
            [void]$process.Start()
        } catch {
            $stderr = $_.Exception.Message
            [IO.File]::WriteAllText($stdoutPath, '', (New-Object Text.UTF8Encoding($false)))
            [IO.File]::WriteAllText($stderrPath, $stderr, (New-Object Text.UTF8Encoding($false)))
            return [pscustomobject]@{ Status = 'failed'; ExitCode = -1; StdoutPath = $stdoutPath; StderrPath = $stderrPath; Output = $stderr }
        }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($Timeout * 1000)) {
            $timedOut = $true
            Stop-VerificationProcessTree -Process $process
        }
        try { $stdout = $stdoutTask.GetAwaiter().GetResult() } catch { $stdout = '' }
        try { $stderr = $stderrTask.GetAwaiter().GetResult() } catch { $stderr = '' }
        [IO.File]::WriteAllText($stdoutPath, $stdout, (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText($stderrPath, $stderr, (New-Object Text.UTF8Encoding($false)))
        if ($timedOut) {
            return [pscustomobject]@{ Status = 'timeout'; ExitCode = $script:TimeoutCode; StdoutPath = $stdoutPath; StderrPath = $stderrPath; Output = ($stdout + "`n" + $stderr) }
        }
        return [pscustomobject]@{ Status = $(if ($process.ExitCode -eq 0) { 'passed' } else { 'failed' }); ExitCode = [int]$process.ExitCode; StdoutPath = $stdoutPath; StderrPath = $stderrPath; Output = ($stdout + "`n" + $stderr) }
    } finally {
        $process.Dispose()
    }
}

function Get-ObservedCounts {
    param([AllowNull()][string]$Output, [Parameter(Mandatory)][string]$Status)
    $text = if ($null -eq $Output) { '' } else { $Output }
    $executed = 0
    $passed = 0
    $failed = 0
    $skips = 0

    $match = [regex]::Match($text, '(?im)^\s*[^A-Za-z0-9]*tests\s+(\d+)\s*$')
    if ($match.Success) { $executed = [int]$match.Groups[1].Value }
    $match = [regex]::Match($text, '(?im)^\s*[^A-Za-z0-9]*pass\s+(\d+)\s*$')
    if ($match.Success) { $passed = [int]$match.Groups[1].Value }
    $match = [regex]::Match($text, '(?im)^\s*[^A-Za-z0-9]*fail\s+(\d+)\s*$')
    if ($match.Success) { $failed = [int]$match.Groups[1].Value }
    $match = [regex]::Match($text, '(?im)^\s*[^A-Za-z0-9]*skipped\s+(\d+)\s*$')
    if ($match.Success) { $skips = [int]$match.Groups[1].Value }

    if ($executed -eq 0) {
        $match = [regex]::Match($text, '(?i)(\d+)\s+passed,\s*(\d+)\s+failed(?:,\s*(\d+)\s+skipped)?')
        if ($match.Success) {
            $passed = [int]$match.Groups[1].Value
            $failed = [int]$match.Groups[2].Value
            if ($match.Groups[3].Success) { $skips = [int]$match.Groups[3].Value }
            $executed = $passed + $failed + $skips
        }
    }
    if ($executed -eq 0) {
        $match = [regex]::Match($text, '(?i)(\d+)\s+passaram;\s*(\d+)\s+falharam(?:;\s*(\d+)\s+skip(?:s)?)?')
        if ($match.Success) {
            $passed = [int]$match.Groups[1].Value
            $failed = [int]$match.Groups[2].Value
            if ($match.Groups[3].Success) { $skips = [int]$match.Groups[3].Value }
            $executed = $passed + $failed + $skips
        }
    }
    if ($executed -eq 0) {
        $match = [regex]::Match($text, '(?i)Ran\s+(\d+)\s+tests?')
        if ($match.Success) {
            $executed = [int]$match.Groups[1].Value
            $match = [regex]::Match($text, '(?i)skipped[=:]\s*(\d+)')
            if ($match.Success) { $skips = [int]$match.Groups[1].Value }
            $match = [regex]::Match($text, '(?i)failures?=(\d+)')
            if ($match.Success) { $failed += [int]$match.Groups[1].Value }
            $match = [regex]::Match($text, '(?i)errors?=(\d+)')
            if ($match.Success) { $failed += [int]$match.Groups[1].Value }
            if ($Status -eq 'passed') { $passed = $executed - $skips } else { $passed = [math]::Max(0, $executed - $skips - $failed) }
        }
    }
    if ($executed -eq 0 -and $Status -ne 'timeout') {
        $executed = 1
        if ($Status -eq 'passed') { $passed = 1 } else { $failed = 1 }
    }
    if ($executed -eq 0 -and $Status -eq 'timeout') {
        $executed = 1
        $failed = 1
    }
    [pscustomobject]@{ Executed = $executed; Passed = $passed; Failed = $failed; Skips = $skips }
}

function Add-VerificationCounts {
    param([Parameter(Mandatory)][object]$Target, [Parameter(Mandatory)][object]$Counts)
    $Target.Executed += $Counts.Executed
    $Target.Passed += $Counts.Passed
    $Target.Failed += $Counts.Failed
    $Target.Skips += $Counts.Skips
}

function Invoke-VerificationStage {
    param(
        [Parameter(Mandatory)][object]$Stage,
        [Parameter(Mandatory)][int]$Timeout,
        [Parameter(Mandatory)][string]$LogDirectory,
        [Parameter(Mandatory)][int]$StageIndex
    )
    $observed = [pscustomobject]@{ Executed = 0; Passed = 0; Failed = 0; Skips = 0 }
    $messages = New-Object System.Collections.ArrayList
    $status = 'passed'
    $stageExitCode = 0
    $commandIndex = 0
    foreach ($command in @($Stage.Commands)) {
        $logPath = Join-Path $LogDirectory (($StageIndex.ToString('00')) + '-' + $Stage.Name + '-' + $commandIndex.ToString('00'))
        $processResult = Invoke-VerificationProcess -Command $command -Timeout $Timeout -LogPath $logPath
        $counts = Get-ObservedCounts -Output $processResult.Output -Status $processResult.Status
        Add-VerificationCounts -Target $observed -Counts $counts
        [void]$messages.Add(('  ' + $Stage.Name + '[' + $commandIndex + '] ' + $processResult.Status + ' code=' + $processResult.ExitCode + ' executed=' + $counts.Executed + ' passed=' + $counts.Passed + ' failed=' + $counts.Failed + ' skips=' + $counts.Skips + ' log=' + $processResult.StdoutPath))
        if ($processResult.Status -eq 'timeout') {
            $status = 'timeout'
            $stageExitCode = $script:TimeoutCode
            break
        }
        if ($processResult.Status -ne 'passed' -and $status -eq 'passed') {
            $status = 'failed'
            $stageExitCode = $Stage.Code
        }
        $commandIndex++
    }
    if ($status -eq 'passed') { $stageExitCode = 0 }
    [pscustomobject]@{
        Name = $Stage.Name
        Code = $stageExitCode
        Status = $status
        Executed = 1
        Passed = $(if ($status -eq 'passed') { 1 } else { 0 })
        Failed = $(if ($status -eq 'failed' -or $status -eq 'timeout') { 1 } else { 0 })
        Skips = 0
        Observed = $observed
        DisplayCommand = $Stage.DisplayCommand
        Messages = $messages.ToArray()
    }
}

function Write-VerificationSummary {
    param([Parameter(Mandatory)][object[]]$Results, [Parameter(Mandatory)][string]$Invocation, [AllowNull()][string]$LogDirectory)
    $observations = @($Results | ForEach-Object { $_.Observed })
    $executed = [int](($observations | Measure-Object -Property Executed -Sum).Sum)
    $passed = [int](($observations | Measure-Object -Property Passed -Sum).Sum)
    $failed = [int](($observations | Measure-Object -Property Failed -Sum).Sum)
    $skips = [int](($observations | Measure-Object -Property Skips -Sum).Sum)
    Write-Output ''
    Write-Output 'Verification summary'
    Write-Output ('Command: ' + $Invocation)
    Write-Output ('Commands: ' + $Results.Count)
    Write-Output ('Executed: ' + $executed)
    Write-Output ('Passed: ' + $passed)
    Write-Output ('Failed: ' + $failed)
    Write-Output ('Skips: ' + $skips)
    foreach ($result in $Results) {
        Write-Output ('Stage ' + $result.Name + ': ' + $result.Status + ' code=' + $result.Code + ' command=' + $result.DisplayCommand)
    }
    if (-not [string]::IsNullOrWhiteSpace($LogDirectory)) { Write-Output ('Raw logs: ' + $LogDirectory) }
}

$stages = @(Get-DefaultVerificationStages)
if (-not [string]::IsNullOrWhiteSpace($CommandOverridesPath)) {
    $stages = @(Apply-CommandOverrides -Stages $stages -Path ([IO.Path]::GetFullPath($CommandOverridesPath)))
}

if ($DryRun) {
    $dryResults = @()
    foreach ($stage in $stages) {
        Write-Output ('Stage ' + $stage.Name + ': skipped (dry-run) command=' + $stage.DisplayCommand)
        $dryResults += [pscustomobject]@{ Name = $stage.Name; Code = 0; Status = 'skipped'; Executed = 0; Passed = 0; Failed = 0; Skips = 1; Observed = [pscustomobject]@{ Executed = 0; Passed = 0; Failed = 0; Skips = 1 }; DisplayCommand = $stage.DisplayCommand }
    }
    Write-VerificationSummary -Results $dryResults -Invocation 'verify-project.ps1 -DryRun' -LogDirectory ''
    exit 0
}

if ([string]::IsNullOrWhiteSpace($LogRoot)) {
    $LogRoot = Join-Path ([IO.Path]::GetTempPath()) ('tce-project-verification-' + [guid]::NewGuid().ToString('N'))
} else {
    $LogRoot = [IO.Path]::GetFullPath($LogRoot)
}
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

$results = @()
$firstFailureCode = 0
$stageIndex = 0
foreach ($stage in $stages) {
    Write-Output ('Stage ' + $stage.Name + ': running command=' + $stage.DisplayCommand)
    $result = Invoke-VerificationStage -Stage $stage -Timeout $TimeoutSeconds -LogDirectory $LogRoot -StageIndex $stageIndex
    foreach ($message in @($result.Messages)) { Write-Output $message }
    $results += $result
    if ($firstFailureCode -eq 0 -and $result.Status -eq 'timeout') { $firstFailureCode = $script:TimeoutCode }
    if ($firstFailureCode -eq 0 -and $result.Status -eq 'failed') { $firstFailureCode = $result.Code }
    $stageIndex++
}

$invocation = 'verify-project.ps1 -ProjectRoot ' + $ProjectRoot + ' -TimeoutSeconds ' + $TimeoutSeconds
Write-VerificationSummary -Results $results -Invocation $invocation -LogDirectory $LogRoot
if ($firstFailureCode -ne 0) { exit $firstFailureCode }
exit 0
