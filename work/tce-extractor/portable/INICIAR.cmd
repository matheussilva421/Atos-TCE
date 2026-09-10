@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "TCE_PORTABLE_PACKAGE_ROOT=%~dp0"
rem Start-Process -WindowStyle Hidden; helper local oculto; fluxo hibrido usa Area Restrita.
rem INICIAR.cmd ponte inicia e verifica a ponte sem abrir o menu.
if /I "%~1"=="parar" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$utf8 = New-Object System.Text.UTF8Encoding($false); [Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; $menuPath = Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app\menu.ps1'; $menu = [ScriptBlock]::Create([IO.File]::ReadAllText($menuPath, $utf8)); & $menu -MenuRoot (Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app') -StopLocalService"
) else if /I "%~1"=="ponte" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$utf8 = New-Object System.Text.UTF8Encoding($false); [Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; $menuPath = Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app\menu.ps1'; $menu = [ScriptBlock]::Create([IO.File]::ReadAllText($menuPath, $utf8)); & $menu -MenuRoot (Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app') -LaunchLocalService -BridgeStatusOnly"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$utf8 = New-Object System.Text.UTF8Encoding($false); [Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $OutputEncoding = $utf8; $menuPath = Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app\menu.ps1'; $menu = [ScriptBlock]::Create([IO.File]::ReadAllText($menuPath, $utf8)); & $menu -MenuRoot (Join-Path $env:TCE_PORTABLE_PACKAGE_ROOT 'app') -LaunchLocalService"
)
set "TCE_PORTABLE_PACKAGE_ROOT="
echo.
pause
