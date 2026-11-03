@echo off
chcp 65001 >nul
title Update Laptop Remote
cd /d "%~dp0"

rem Downloads the newest version. Your config.ini and connected phones are kept.
py server.py --update
if %errorlevel% neq 9009 goto end

python server.py --update
if %errorlevel% neq 9009 goto end

echo.
echo  Python is not installed, or it was not added to PATH.
echo  See README.md, section 1 (Install Python).

:end
echo.
pause
