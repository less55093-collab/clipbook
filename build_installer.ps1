# Build Installer Script
$ErrorActionPreference = "Stop"

Write-Host "Starting Build Process..." -ForegroundColor Cyan

# 1. Check for PyInstaller
if (-not (Get-Command "pyinstaller" -ErrorAction SilentlyContinue)) {
    Write-Host "PyInstaller not found. Installing..." -ForegroundColor Yellow
    pip install pyinstaller
}

# 2. Run PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
# Remove dist/build folders to ensure clean build
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }

pyinstaller ClipboardHistory.spec --clean --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller failed!" -ForegroundColor Red
    exit 1
}

# 3. Check for Inno Setup
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $ISCC)) {
    Write-Host "Inno Setup Compiler (ISCC.exe) not found at: $ISCC" -ForegroundColor Red
    Write-Host "Please install Inno Setup 6 to generate the installer." -ForegroundColor Yellow
    exit 1
}

# 4. Run Inno Setup
Write-Host "Running Inno Setup Compiler..." -ForegroundColor Cyan
& $ISCC "installer_script.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Inno Setup failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "Installer is located in the 'setup' folder." -ForegroundColor Green
