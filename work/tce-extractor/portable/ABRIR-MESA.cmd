@echo off
setlocal
cd /d "%~dp0"
call "%~dp0INICIAR.cmd" abrir-mesa
exit /b %ERRORLEVEL%
