$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SourceDir

Write-Host ""
Write-Host "======================================================"
Write-Host "  AI Background Remover - Portable Build"
Write-Host "======================================================"
Write-Host ""

# Check Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "[ERROR] Python not found. Please install Python 3.10+" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$OutputDir = Join-Path $SourceDir "bg-remover-portable"

Write-Host "[INFO] Output: $OutputDir"
Write-Host ""

# Step 1: Clean old package
Write-Host "[1/5] Cleaning old package..."
if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}

# Step 2: Create directory structure
Write-Host "[2/5] Creating directories..."
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\templates" -Force | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\models" -Force | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\inputs" -Force | Out-Null
New-Item -ItemType Directory -Path "$OutputDir\outputs" -Force | Out-Null

# Step 3: Create venv and install dependencies
Write-Host "[3/5] Creating venv and installing dependencies (this may take a few minutes)..."
python -m venv "$OutputDir\venv"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to create venv" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "[INFO] Installing packages..."
& "$OutputDir\venv\Scripts\pip.exe" install -r "$SourceDir\requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Step 4: Copy project files
Write-Host "[4/5] Copying project files..."
Copy-Item "$SourceDir\app.py" "$OutputDir\app.py"
Copy-Item "$SourceDir\requirements.txt" "$OutputDir\requirements.txt"
Copy-Item "$SourceDir\templates\index.html" "$OutputDir\templates\index.html"
Copy-Item "$SourceDir\templates\api.html" "$OutputDir\templates\api.html"

# Copy model files
Write-Host "[INFO] Copying model files (may be large)..."
Copy-Item "$SourceDir\models\birefnet-massive.onnx" "$OutputDir\models\birefnet-massive.onnx"
Copy-Item "$SourceDir\models\bria-rmbg.onnx" "$OutputDir\models\bria-rmbg.onnx"

# Step 5: Generate launcher script
Write-Host "[5/5] Generating launcher script..."
$launcherContent = @"
@echo off
chcp 65001 >nul
title AI Background Remover

cd /d "%~dp0"

echo.
echo ======================================================
echo   AI Background Remover - Starting...
echo ======================================================
echo.

echo [1/2] Checking port 5000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 "') do (
    taskkill /f /pid %%a >nul 2>nul && echo [INFO] Killed old process on port 5000
)
timeout /t 1 /nobreak >nul

echo [2/2] Starting server...
echo.
echo ======================================================
echo   Web UI:   http://127.0.0.1:5000
echo   API Docs: http://127.0.0.1:5000/api
echo   Close this window to stop the server
echo ======================================================
echo.

"venv\Scripts\python.exe" app.py

echo.
echo Server stopped.
pause
"@
Set-Content -Path "$OutputDir\start.bat" -Value $launcherContent -Encoding ASCII

# Generate readme
$readmeContent = @"
AI Background Remover - Portable Edition
=========================================

Usage:
  1. Double-click "start.bat" to launch
  2. Open browser at http://127.0.0.1:5000
  3. Close the command window to stop

Notes:
  - First launch may take a few seconds to load models
  - Port 5000 must be available
  - Processed images are saved in the outputs folder

Requirements:
  - Windows 10/11
  - No Python installation needed (venv included)
"@
Set-Content -Path "$OutputDir\README.txt" -Value $readmeContent -Encoding UTF8

Write-Host ""
Write-Host "======================================================"
Write-Host "  Build complete!"
Write-Host "  Output: $OutputDir"
Write-Host ""
Write-Host "  Zip the folder to distribute"
Write-Host "  Users run start.bat after extracting"
Write-Host "======================================================"
Write-Host ""

# Show folder size
$size = (Get-ChildItem -Recurse $OutputDir | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($size / 1MB, 1)
Write-Host "[INFO] Total size: ${sizeMB} MB"
Write-Host ""
