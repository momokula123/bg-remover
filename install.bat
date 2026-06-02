@echo off
chcp 65001 >nul
title Install Dependencies

cd /d "%~dp0"

echo.
echo ======================================================
echo   Installing Dependencies
echo ======================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

echo Installing packages...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

if %errorlevel% neq 0 (
    echo [ERROR] Installation failed. Check your network.
    pause
    exit /b 1
)

echo.
echo ======================================================
echo   Done! Run start.bat to launch the server
echo ======================================================
echo.

pause
