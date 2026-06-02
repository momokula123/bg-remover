@echo off
chcp 65001 >nul
title AI Background Remover

cd /d "%~dp0"

echo.
echo ======================================================
echo   AI Background Remover - Starting...
echo ======================================================
echo.

if exist "venv\Scripts\python.exe" (
    echo [INFO] Using venv Python
    set "PYTHON=venv\Scripts\python.exe"
    set "PIP=venv\Scripts\pip.exe"
) else (
    echo [INFO] venv not found, using system Python
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found. Please install Python 3.10+
        pause
        exit /b 1
    )
    set "PYTHON=python"
    set "PIP=pip"
)

echo [1/3] Checking dependencies...
%PIP% show flask >nul 2>nul || (
    echo [INFO] First run - installing dependencies...
    %PIP% install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo [ERROR] Dependency installation failed
        pause
        exit /b 1
    )
)

echo [2/3] Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 "') do (
    taskkill /f /pid %%a >nul 2>nul && echo [INFO] Killed old process on port 5000
)
timeout /t 1 /nobreak >nul

echo [3/3] Starting server...
echo.
echo ======================================================
echo   Web UI:   http://127.0.0.1:5000
echo   API Docs: http://127.0.0.1:5000/api
echo   Close this window to stop the server
echo ======================================================
echo.

%PYTHON% app.py

echo.
echo Server stopped.
pause
