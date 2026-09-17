$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $PSScriptRoot
if (!$ROOT) { $ROOT = Get-Location }
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run this in Terminal (Admin). Right-click Start > Terminal (Admin)." }

Write-Host "=== NeoFace Full Deploy ===" -ForegroundColor Cyan

# 1. Kill old daemon
Write-Host "`n[1/4] Stopping old daemon..."
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue

# 2. Deploy DLL
Write-Host "[2/4] Deploying DLL..."
$src = Join-Path $ROOT "cp\FaceUnlockCP.dll"
$dstDir = "C:\Program Files\NeoFace"
New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
Copy-Item $src "$dstDir\FaceUnlockCP.dll" -Force
regsvr32 /s "$dstDir\FaceUnlockCP.dll"
$guid = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
New-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$guid" -Force | Out-Null
Write-Host "  DLL deployed and registered" -ForegroundColor Green

# 3. Install daemon scheduled task (interactive, not Session 0)
Write-Host "[3/4] Installing daemon task..."
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
$script = Join-Path $ROOT "face_unlock\daemon_pipe.py"
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$script`""
$trig = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
Write-Host "  Daemon task installed (Interactive logon, not Session 0)" -ForegroundColor Green

# 4. Start daemon now
Write-Host "[4/4] Starting daemon..."
Start-ScheduledTask -TaskName "NeoFace-Daemon"
Start-Sleep 15
$log = Get-Content (Join-Path $env:PROGRAMDATA "NeoFace\daemon.log") -ErrorAction SilentlyContinue | Select-Object -Last 3
if ($log) { $log | ForEach-Object { Write-Host "  $_" } }
Write-Host "`n=== Deploy Complete ===" -ForegroundColor Cyan
Write-Host "Test: press Win+L, look at camera, click 'Unlock with face'"
Write-Host "Or run: python $ROOT\tools\probe_system.py"
