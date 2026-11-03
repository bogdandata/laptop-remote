@echo off
chcp 65001 >nul
title Laptop Remote
cd /d "%~dp0"

rem Try "py" (the Python launcher) first, then "python".
rem Exit code 9009 means Windows does not know that command.
py server.py
if %errorlevel% neq 9009 goto end

python server.py
if %errorlevel% neq 9009 goto end

echo.
echo  Python is not installed, or it was not added to PATH.
echo  See README.md, section 1 (Install Python).
echo.

:end
echo.
pause
