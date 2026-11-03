@echo off
setlocal enabledelayedexpansion
title Trinetra Hardware Testing Workstation

echo ====================================================================
echo   TRINETRA (त्रिनेत्र) — Assistive Vision Hardware Testing Suite
echo ====================================================================
echo.

:: 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found on your system PATH!
    echo Please install Python 3.11+ and try again.
    pause
    exit /b 1
)

:: 2. Check Node
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js/npm is not found on your system PATH!
    echo Please install Node.js 18+ and try again.
    pause
    exit /b 1
)

echo [1/3] Starting Vision Engine (FastAPI on http://127.0.0.1:8000)...
start "Trinetra Vision Engine" cmd /k "cd services\vision-engine && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

echo [2/3] Waiting for Vision Engine to initialize...
timeout /t 3 /nobreak >nul

echo [3/3] Starting Trinetra Desktop Application...
cd apps\desktop

if not exist node_modules (
    echo Installing desktop UI dependencies...
    call npm install
)

echo Launching Trinetra interface...
:: If tauri release exists, open it, else run vite dev server
if exist src-tauri\target\release\trinetra-desktop.exe (
    start "" "src-tauri\target\release\trinetra-desktop.exe"
) else if exist src-tauri\target\release\trinetra_desktop.exe (
    start "" "src-tauri\target\release\trinetra_desktop.exe"
) else (
    start "Trinetra Desktop Host" cmd /k "npm run tauri dev"
)

echo.
echo ====================================================================
echo   TRINETRA IS RUNNING!
echo   - Vision Engine: http://127.0.0.1:8000
echo   - Camera Test: Select 'Network Stream (ESP32-CAM)' in the app
echo   - Default ESP32 Stream URL: http://<ESP32_IP>:81/stream
echo ====================================================================
echo.
