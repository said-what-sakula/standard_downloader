@echo off
chcp 65001 >nul
title Standard Downloader

echo ============================================================
echo  Standard Downloader v2.0
echo ============================================================
echo.

:: ── Python ───────────────────────────────────────────────────
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install Python 3.9+
    pause & exit /b 1
)

echo Checking Python dependencies...
python -m pip install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo ERROR: pip install failed. Run manually:
    echo   python -m pip install -r requirements.txt
    pause & exit /b 1
)
echo Python OK.
echo.

:: ── Frontend (npm) ───────────────────────────────────────────
set HAS_NPM=1
where npm >nul 2>&1
if %ERRORLEVEL% equ 0 set HAS_NPM=0

if %HAS_NPM% neq 0 (
    echo npm not found, skipping frontend.
    echo.
)

if %HAS_NPM% equ 0 if exist "frontend\dist\index.html" (
    echo Frontend: production build found, served by backend.
    echo.
    set HAS_NPM=99
)

if %HAS_NPM% equ 0 (
    if not exist "frontend\node_modules" (
        echo Installing frontend dependencies (first time^)...
        cd frontend
        call npm install
        if %ERRORLEVEL% neq 0 (
            echo ERROR: npm install failed.
            cd ..
            pause & exit /b 1
        )
        cd ..
    )
    echo Starting frontend dev server in new window: http://localhost:5173
    start "Frontend Dev" cmd /k "cd /d %~dp0frontend && npm run dev"
    echo.
)

:: ── Backend ──────────────────────────────────────────────────
echo Starting backend: http://127.0.0.1:8000
echo Press Ctrl+C to stop.
echo ============================================================
echo.

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

:: ── 退出时关闭前端开发服务器窗口 ──────────────────────────────────────────────
echo.
echo Shutting down frontend dev server...
taskkill /FI "WINDOWTITLE eq Frontend Dev" /T /F >nul 2>&1

pause
