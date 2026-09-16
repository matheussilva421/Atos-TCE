@echo off
setlocal
cd /d "%~dp0"
call "%~dp0ABRIR-MESA.cmd"
exit /b %ERRORLEVEL%
