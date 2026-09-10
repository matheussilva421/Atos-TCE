@echo off
setlocal
rem Entrada legada do fluxo hibrido; INICIAR.cmd inicia a ponte, analise/lotes e aquisicao/OCR.
rem Use "INICIAR.bat ponte" para iniciar e verificar a ponte local sem abrir o menu.
call "%~dp0INICIAR.cmd" %*
exit /b %errorlevel%
