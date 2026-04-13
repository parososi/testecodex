@echo off
title Pied Piper - Compressor Universal de Arquivos
python "%~dp0pp" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   [ERRO] O programa terminou com um erro. Leia a mensagem acima.
    echo   Dica: se faltar dependencias, execute: pip install --user Pillow numpy
    echo.
    pause
) else if "%~1"=="" (
    pause
)
