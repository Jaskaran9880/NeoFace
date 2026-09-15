$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run in Terminal (Admin)." }

Write-Host "`n=== NeoFace Uninstaller ===" -ForegroundColor Cyan

# Kill daemon
Write-Host "`n[1/4] Stopping daemon..."
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "NeoFace-Probe" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "  Tasks removed" -ForegroundColor Green

# Unregister DLL
Write-Host "`n[2/4] Unregistering DLL..."
$guid = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
regsvr32 /u /s "C:\Program Files\NeoFace\FaceUnlockCP.dll" -ErrorAction SilentlyContinue
Remove-Item "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$guid" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  DLL unregistered" -ForegroundColor Green

# Remove DLL
Write-Host "`n[3/4] Removing DLL..."
Remove-Item "C:\Program Files\NeoFace" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "  Removed C:\Program Files\NeoFace" -ForegroundColor Green

# Remove data (ask first)
Write-Host "`n[4/4] Data files..."
$confirm = Read-Host "Remove face gallery + password vault? (C:\ProgramData\NeoFace) [y/N]"
if ($confirm -eq "y" -or $confirm -eq "Y") {
    Remove-Item "C:\ProgramData\NeoFace" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  Data removed" -ForegroundColor Green
} else {
    Write-Host "  Data kept at C:\ProgramData\NeoFace" -ForegroundColor Yellow
}

Write-Host "`n=== Uninstalled ===" -ForegroundColor Cyan
Write-Host "NeoFace removed. PIN login restored as default."
