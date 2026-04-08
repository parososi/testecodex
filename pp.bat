@echo off
python "%~dp0pp" %*
if %ERRORLEVEL% NEQ 0 (pause) else if "%~1"=="" (pause)
