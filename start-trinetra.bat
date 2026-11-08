@echo off
setlocal
cd /d "%~dp0"
echo ====================================================================
echo   TRINETRA (त्रिनेत्र) — Launching Assistive Vision Platform...
echo ====================================================================
echo.

:: Launch silent pythonw launcher (Zero black terminal windows)
if exist services\vision-engine\.venv\Scripts\pythonw.exe (
    start "" services\vision-engine\.venv\Scripts\pythonw.exe launch_trinetra.py
) else (
    start "" pythonw launch_trinetra.py
)

echo Trinetra is starting in an independent window.
echo You can close this window at any time.
timeout /t 2 >nul
exit /b 0
