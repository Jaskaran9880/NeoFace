$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
if (!$ROOT) { $ROOT = Get-Location }

Write-Host "`n=== NeoFace Unlock Installer ===" -ForegroundColor Cyan
Write-Host "Face unlock for Windows 10/11 (no IR camera needed)`n"

# --- Step 1: Check Python ---
Write-Host "[1/7] Checking Python..." -ForegroundColor Yellow
try {
    $pyVer = python --version 2>&1
    Write-Host "  $pyVer" -ForegroundColor Green
} catch {
    throw "Python not found. Install Python 3.10+ from https://python.org and add to PATH."
}

# --- Step 2: Install dependencies ---
Write-Host "`n[2/7] Installing Python packages..." -ForegroundColor Yellow
pip install -r "$ROOT\requirements.txt" --quiet 2>&1 | Out-Null
Write-Host "  Dependencies installed" -ForegroundColor Green

# --- Step 3: Download models ---
Write-Host "`n[3/7] Checking models..." -ForegroundColor Yellow
if (!(Test-Path "$ROOT\models\yunet.onnx") -or !(Test-Path "$ROOT\models\sface.onnx")) {
    Write-Host "  Downloading YuNet + SFace models..." -ForegroundColor Gray
    python "$ROOT\tools\fetch_fast.py"
}
$yunet = Get-Item "$ROOT\models\yunet.onnx" -ErrorAction SilentlyContinue
$sface = Get-Item "$ROOT\models\sface.onnx" -ErrorAction SilentlyContinue
if ($yunet -and $sface) {
    Write-Host "  Models ready (yunet: $([math]::Round($yunet.Length/1MB,1))MB, sface: $([math]::Round($sface.Length/1MB,1))MB)" -ForegroundColor Green
} else {
    throw "Model download failed. Run: python tools\fetch_fast.py"
}

# --- Step 4: Set password vault ---
Write-Host "`n[4/7] Password vault..." -ForegroundColor Yellow
$credPath = "C:\ProgramData\NeoFace\cred.bin"
if (!(Test-Path $credPath)) {
    Write-Host "  Setting up password vault (you'll enter your Windows password once)..." -ForegroundColor Gray
    python "$ROOT\tools\set_password_machine.py"
    if (!(Test-Path $credPath)) {
        throw "Password vault setup failed. Run as Admin: python tools\set_password_machine.py"
    }
}
Write-Host "  Vault ready at $credPath" -ForegroundColor Green

# --- Step 5: Enroll face ---
Write-Host "`n[5/7] Face enrollment..." -ForegroundColor Yellow
$fastGal = "C:\ProgramData\NeoFace\faces_fast.dat"
if (!(Test-Path $fastGal)) {
    $photos = "$ROOT\photos"
    if (Test-Path $photos) {
        $photoCount = (Get-ChildItem $photos -File | Where-Object { $_.Extension -match "\.(jpg|jpeg|png|heic|heif)$" }).Count
        if ($photoCount -gt 0) {
            Write-Host "  Found $photoCount photos. Enrolling from photos..." -ForegroundColor Gray
            python "$ROOT\tools\enroll_fast.py"
        } else {
            Write-Host "  No photos found in $photos" -ForegroundColor Red
            Write-Host "  Place front-facing photos (JPG/PNG/HEIC) in $photos" -ForegroundColor Gray
            Write-Host "  Then run: python tools\enroll_fast.py" -ForegroundColor Gray
        }
    } else {
        Write-Host "  No photos folder found." -ForegroundColor Red
        Write-Host "  Create $photos and add front-facing photos of yourself." -ForegroundColor Gray
        Write-Host "  Then run: python tools\enroll_fast.py" -ForegroundColor Gray
    }
}
if (Test-Path $fastGal) {
    Write-Host "  Face gallery ready" -ForegroundColor Green
} else {
    Write-Host "  WARNING: No face gallery. You need to enroll first!" -ForegroundColor Red
    Write-Host "  Add photos to photos\ and run: python tools\enroll_fast.py" -ForegroundColor Red
}

# --- Step 6: Build + register CP DLL (needs admin) ---
Write-Host "`n[6/7] Credential Provider DLL..." -ForegroundColor Yellow
$dllPath = "C:\Program Files\NeoFace\FaceUnlockCP.dll"
$builtDll = "$ROOT\cp\FaceUnlockCP.dll"
if (!(Test-Path $dllPath) -or (Get-Item $builtDll -ErrorAction SilentlyContinue).LastWriteTime -gt (Get-Item $dllPath -ErrorAction SilentlyContinue).LastWriteTime) {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        if (!(Test-Path $builtDll)) {
            Write-Host "  Building DLL..." -ForegroundColor Gray
            Push-Location "$ROOT\cp"
            & .\build_cp.ps1
            Pop-Location
        }
        if (Test-Path $builtDll) {
            New-Item -ItemType Directory -Path "C:\Program Files\NeoFace" -Force | Out-Null
            Copy-Item $builtDll $dllPath -Force
            regsvr32 /s $dllPath
            $guid = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
            New-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$guid" -Force | Out-Null
            Write-Host "  DLL registered" -ForegroundColor Green
        } else {
            Write-Host "  DLL build failed. Install VS2022 Build Tools + Desktop C++ workload." -ForegroundColor Red
        }
    } else {
        Write-Host "  Run this script as Admin to deploy DLL, or run: .\cp\deploy_all.ps1" -ForegroundColor Yellow
    }
} else {
    Write-Host "  DLL already deployed" -ForegroundColor Green
}

# --- Step 7: Install daemon ---
Write-Host "`n[7/7] Daemon service..." -ForegroundColor Yellow
$daemonTask = Get-ScheduledTask -TaskName "NeoFace-Daemon" -ErrorAction SilentlyContinue
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
    $pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
    $act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$ROOT\face_unlock\daemon_pipe.py`""
    $trig = New-ScheduledTaskTrigger -AtLogOn
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
    Write-Host "  Daemon installed (starts at logon)" -ForegroundColor Green
} else {
    if (!$daemonTask) {
        Write-Host "  Run as Admin to install daemon, or run: .\cp\deploy_all.ps1" -ForegroundColor Yellow
    } else {
        Write-Host "  Daemon already installed" -ForegroundColor Green
    }
}

# --- Done ---
Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "`nHow to use:"
Write-Host "  1. Log in with PIN (daemon starts automatically)"
Write-Host "  2. Press Win+L to lock"
Write-Host "  3. Look at camera, click 'Unlock with face'"
Write-Host "  4. Done!`n"
Write-Host "Commands:"
Write-Host "  python tools\enroll_fast.py     - Re-enroll faces"
Write-Host "  python tools\test_unlock.py     - Test face scan"
Write-Host "  .\cp\deploy_all.ps1             - Full deploy (Admin)" -ForegroundColor Gray
