@echo off
cd /d "%~dp0"
chcp 65001 > nul
title RSS SENTINEL
echo.
echo [RSS SENTINEL] Starting...
echo.
python main.py --gui
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application exited with code: %ERRORLEVEL%
    pause
)
