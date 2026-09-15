$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run in Terminal (Admin)." }
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
$script = "C:\NeoFace\face_unlock\daemon_pipe.py"
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$script`""
$trig = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
Write-Host "NeoFace-Daemon installed - runs interactively at logon (AC + battery)."
Write-Host "To start now: Start-ScheduledTask -TaskName 'NeoFace-Daemon'"
Write-Host "Note: face tile works for Win+L unlock after logon."
