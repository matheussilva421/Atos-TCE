[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $Url = 'about:blank',

    [ValidateRange(1, 65535)]
    [int] $Port = 9222,

    [string] $ProfileRoot,

    [string] $ExtensionRoot,

    [string] $NodePath,

    [string] $PlaywrightEntry,

    [string] $BrowserCachePath,

    [switch] $PlanOnly
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$labLauncher = Join-Path $repositoryRoot 'scripts\portal-lab\Start-AtosChrome.ps1'
$parameters = @{
    Port = $Port
    Url = $Url
}
foreach ($name in @('ProfileRoot', 'ExtensionRoot', 'NodePath', 'PlaywrightEntry', 'BrowserCachePath')) {
    if ($PSBoundParameters.ContainsKey($name)) { $parameters[$name] = $PSBoundParameters[$name] }
}
if ($PlanOnly) { $parameters.PlanOnly = $true }

& $labLauncher @parameters
