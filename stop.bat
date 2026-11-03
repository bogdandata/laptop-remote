@echo off
chcp 65001 >nul
title Stop Laptop Remote
cd /d "%~dp0"

rem Stops Laptop Remote on this laptop, even if you cannot find its window.
py server.py --stop
if %errorlevel% neq 9009 goto end

python server.py --stop
if %errorlevel% neq 9009 goto end

echo.
echo  Python is not installed, or it was not added to PATH.
echo  See README.md, section 1 (Install Python).

:end
echo.
pause
