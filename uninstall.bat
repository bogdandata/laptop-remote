@echo off
chcp 65001 >nul
title Remove Laptop Remote
cd /d "%~dp0"

rem Stops Laptop Remote, ends its autostart and deletes every access to this laptop.
set "PY=%~dp0..\python\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" server.py --uninstall
if %errorlevel% neq 9009 goto end

python server.py --uninstall
if %errorlevel% neq 9009 goto end

echo.
echo  Python is not installed, or it was not added to PATH.
echo  See README.md, section 1 (Install Python).

:end
echo.
pause
