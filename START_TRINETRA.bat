@echo off
title TRINETRA (त्रिनेत्र) Launcher
color 0A
cd /d "D:\trinetra"

echo ====================================================================
echo   TRINETRA (त्रिनेत्र) — Offline Assistive AI Platform
echo ====================================================================
echo.
echo [1/3] Starting Trinetra Vision Engine...
set "PYTHONPATH=%~dp0services\vision-engine;%~dp0packages\trinetra-core"
start /b "" python -m uvicorn app.main:app --app-dir "%~dp0services\vision-engine" --host 127.0.0.1 --port 8000

echo [2/3] Starting UI Interface...
start /b "" cmd /c "npm run dev --prefix apps/desktop"

echo [3/3] Waiting for servers to initialize...
timeout /t 3 /nobreak >nul

echo [4/4] Launching Trinetra Application Window...
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --app=http://localhost:5175 --window-size=1280,850
) else if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    start "" "C:\Program Files\Microsoft\Edge\Application\msedge.exe" --app=http://localhost:5175 --window-size=1280,850
) else if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:5175 --window-size=1280,850
) else (
    start http://localhost:5175
)

echo.
echo ====================================================================
echo   TRINETRA IS NOW RUNNING!
echo   Close this terminal window when you are done testing.
echo ====================================================================
echo.
pause
