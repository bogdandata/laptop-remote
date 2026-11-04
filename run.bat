@echo off
rem Laptop Remote, installed from an invitation (the setup file from the app's link).
rem The installer starts this file, and it starts minimized when you sign in to Windows.
rem Only control from anywhere: nothing listens on the home network.
rem (Keep this file short and unchanged: Windows reads it while it runs.)
chcp 65001 >nul
title Laptop Remote
cd /d "%~dp0"
set "LAPTOP_REMOTE_LAUNCHER=run.bat"
set "PY=%~dp0..\python\python.exe"
if not exist "%PY%" set "PY=py"
:run
"%PY%" server.py --anywhere-only %*
if %errorlevel% equ 3 goto run
if /i "%~1"=="--autostart" exit
