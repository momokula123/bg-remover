@echo off
chcp 65001 >nul
title 分块抠图服务 (Tiled Background Removal)

cd /d "%~dp0"

echo.
echo ======================================================
echo   分块抠图服务 - Starting...
echo ======================================================
echo.

if exist "venv\Scripts\python.exe" (
    echo [INFO] Using venv Python
    set "PYTHON=venv\Scripts\python.exe"
) else (
    echo [ERROR] venv not found. Please run start.bat first to create venv.
    pause
    exit /b 1
)

echo [1/2] Checking port 5001...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5001 "') do (
    taskkill /f /pid %%a >nul 2>nul && echo [INFO] Killed old process on port 5001
)
timeout /t 1 /nobreak >nul

echo [2/2] Starting tiled server...
echo.
echo ======================================================
echo   Web UI:   http://127.0.0.1:5001
echo   Health:   http://127.0.0.1:5001/api/health
echo   Close this window to stop the server
echo ======================================================
echo.

%PYTHON% tiled_app.py

echo.
echo Server stopped.
pause
