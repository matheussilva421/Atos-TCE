@echo off
setlocal
cd /d "%~dp0"
set "EMBEDDED=%~dp0runtime\python\python.exe"
if exist "%EMBEDDED%" (
  "%EMBEDDED%" -m app.main %*
) else (
  python -m app.main %*
)
exit /b %ERRORLEVEL%
