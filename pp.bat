@echo off
python "%~dp0pp" %*
if %ERRORLEVEL% NEQ 0 pause
