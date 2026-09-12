$ErrorActionPreference = "Stop"
foreach ($dll in @("C:\Program Files\NeoFace\FaceUnlockCP.dll", (Join-Path $PSScriptRoot "FaceUnlockCP.dll"))) {
    if (Test-Path $dll) { regsvr32 /s /u "$dll" }
}
Remove-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}" -Force -ErrorAction SilentlyContinue
Write-Host "unregistered. Win+L back to stock."
