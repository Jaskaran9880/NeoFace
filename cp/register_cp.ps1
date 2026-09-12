$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run this in Terminal (Admin). Right-click Start > Terminal (Admin), then rerun." }
$src = Join-Path $PSScriptRoot "FaceUnlockCP.dll"
if (!(Test-Path $src)) { throw "Build first: .\build_cp.ps1" }
$dstDir = "C:\Program Files\NeoFace"
New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
Copy-Item $src "$dstDir\FaceUnlockCP.dll" -Force
$dll = "$dstDir\FaceUnlockCP.dll"
regsvr32 /s "$dll"
$guid = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
New-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$guid" -Force | Out-Null
Write-Host "registered NeoFace tile. Press Win+L to see it. PIN still works. Unregister: .\unregister_cp.ps1"
