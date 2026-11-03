@echo off
chcp 65001 >nul
title Laptop Remote - secure link with Tailscale
cd /d "%~dp0"

rem Turns on the secure https link through Tailscale. Needed only once.
py server.py --tailscale-https
if %errorlevel% neq 9009 goto end

python server.py --tailscale-https
if %errorlevel% neq 9009 goto end

echo.
echo  Python is not installed, or it was not added to PATH.
echo  See README.md, section 1 (Install Python).

:end
echo.
pause
