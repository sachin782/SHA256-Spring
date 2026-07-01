#Requires -Version 5.1
<#
.SYNOPSIS
    Build SHA256 Spring executable and Windows installer.

.DESCRIPTION
    1. Installs Python packages from requirements.txt
    2. Installs build tools from build_requirements.txt
    3. Prepares icon.ico from icon.png
    4. Builds a standalone .exe with PyInstaller
    5. Builds a Windows setup installer with Inno Setup (if installed)

    App name:    SHA256 Spring
    Publisher:   Sachin Rawat
    Setup icon:  icon.png (converted to icon.ico)
#>

$ErrorActionPreference = "Stop"

$AppName = "SHA256 Spring"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

Write-Step "Installing application prerequisites (requirements.txt)"
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install application prerequisites." }

Write-Step "Installing build tools (build_requirements.txt)"
python -m pip install -r build_requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install build tools." }

if (-not (Test-Path "icon.png")) {
    throw "icon.png not found in $ProjectDir"
}

Write-Step "Preparing Windows icon from icon.png"
python prepare_icon.py
if ($LASTEXITCODE -ne 0) { throw "Failed to prepare icon.ico." }

Write-Step "Building standalone executable ($AppName)"
python -m PyInstaller sha256_generator.spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

$exePath = Join-Path $ProjectDir "dist\$AppName.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected executable was not created: $exePath"
}

Write-Host "Executable created: $exePath" -ForegroundColor Green

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    Write-Step "Building Windows installer (Inno Setup)"
    & $iscc "installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed." }

    $setupPath = Join-Path $ProjectDir "installer_output\SHA256 Spring Setup.exe"
    Write-Host "Installer created: $setupPath" -ForegroundColor Green
} else {
    Write-Warning "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php"
    Write-Warning "The standalone executable is still available at dist\$AppName.exe"
}

Write-Step "Build complete"
