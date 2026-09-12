$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "NeoFace-Daemon removed. Face tile will show PIN fallback until reinstalled."
