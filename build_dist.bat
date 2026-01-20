@echo off
cd /d "%~dp0"
echo [BUILD] Starting Production Build for RSS Sentinel...

:: 1. Setup Virtual Environment
if not exist ".venv" (
    echo [BUILD] Creating virtual environment...
    python -m venv .venv 2>nul
    if errorlevel 1 (
        echo [INFO] 'python' command failed, trying 'py' launcher...
        py -m venv .venv
        if errorlevel 1 (
            echo [ERROR] Failed to create virtual environment. Please ensure Python is installed.
            pause
            exit /b 1
        )
    )
)

:: 2. Install Dependencies (using module syntax to avoid launcher errors)

echo [BUILD] Installing dependencies...

.venv\Scripts\python.exe -m pip install -r requirements.txt

if %errorlevel% neq 0 (

    echo [ERROR] Failed to install requirements.

    pause

    exit /b 1

)



:: 3. Clean previous build
if exist "dist" (
    echo [BUILD] Cleaning dist/ directory...
    rmdir /s /q dist
)

:: 4. Build EXE
echo [BUILD] Packaging with PyInstaller (Venv)...
:: Using python -m PyInstaller is safer than calling the .exe directly.
:: --uac-admin: Requests admin rights (needed for RSS/Registry).
:: --collect-all: Ensures all submodules and data for these packages are included.
:: --clean: Removes cache before building.
.venv\Scripts\python.exe -m PyInstaller main.py --noconsole --onefile --uac-admin --icon "assets/icon.png" --name "RSS-Sentinel" --add-data "assets;assets" --collect-all flet --collect-all flet_core --collect-all pystray --collect-all PIL --collect-all pywin32 --clean

if %errorlevel% neq 0 (
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo [BUILD] Build Complete! Check the 'dist' folder.
pause
