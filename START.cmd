@echo off
setlocal
cd /d "%~dp0"
python -m app.main %*
exit /b %ERRORLEVEL%
