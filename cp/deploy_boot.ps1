$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run this in Terminal (Admin)." }

Write-Host "=== NeoFace Boot-Time Deploy ===" -ForegroundColor Cyan

# Kill old daemon
Write-Host "`n[1/3] Stopping old daemon..."
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Start-Sleep 2

# Deploy DLL
Write-Host "[2/3] Deploying DLL..."
Copy-Item "C:\NeoFace\cp\FaceUnlockCP.dll" "C:\Program Files\NeoFace\FaceUnlockCP.dll" -Force
regsvr32 /s "C:\Program Files\NeoFace\FaceUnlockCP.dll"

# Install daemon as SYSTEM at boot (runs before any user logs in)
Write-Host "[3/3] Installing boot-time daemon as SYSTEM..."
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"C:\NeoFace\face_unlock\daemon_pipe.py`""
$trig = New-ScheduledTaskTrigger -AtStartup
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
Write-Host "  Daemon registered as SYSTEM task (starts at boot, before login)" -ForegroundColor Green

# Start daemon now for immediate testing
Start-ScheduledTask -TaskName "NeoFace-Daemon"
Start-Sleep 15
Get-Content "C:\ProgramData\NeoFace\daemon.log" -Tail 3

Write-Host "`n=== DONE ===" -ForegroundColor Cyan
Write-Host "Reboot and test: face unlock should now work at the login screen!"
