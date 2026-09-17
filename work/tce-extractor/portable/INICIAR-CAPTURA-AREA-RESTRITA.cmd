@echo off
setlocal EnableExtensions
chcp 65001 >nul
for %%I in ("%~dp0.") do set "PACKAGE_ROOT=%%~fI"
cd /d "%PACKAGE_ROOT%"
set "OBSERVATION=%PACKAGE_ROOT%\dados-locais\observacao-portal-real.json"
set "RECORD_ROOT=%PACKAGE_ROOT%\dados-locais\real-portal-runs"

echo Iniciando a ponte local do pacote...
call "%PACKAGE_ROOT%\INICIAR.cmd" ponte
if errorlevel 1 (
    echo Falha ao iniciar a ponte local.
    pause
    exit /b 1
)

echo Abrindo Chrome isolado e o gravador estrutural.
echo Faca o login manualmente. Nenhuma credencial sera digitada por este script.
python "%PACKAGE_ROOT%\real_portal_session.py" --package-root "%PACKAGE_ROOT%" --output "%OBSERVATION%" --record-root "%RECORD_ROOT%" --stay-open
set "SESSION_EXIT=%ERRORLEVEL%"

echo Encerrando a ponte local...
call "%PACKAGE_ROOT%\INICIAR.cmd" parar
echo.
echo Observacao: %OBSERVATION%
echo Gravacoes privadas: %RECORD_ROOT%
pause
exit /b %SESSION_EXIT%
