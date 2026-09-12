$ErrorActionPreference = "Stop"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "Run in Terminal (Admin)." }
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
$script = "A:\Face Unlock For mypc\face_unlock\daemon_pipe.py"
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$script`""
$trig = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Force | Out-Null
Start-ScheduledTask -TaskName "NeoFace-Daemon"
Write-Host "NeoFace-Daemon installed - starts at every logon (AC + battery), hidden window."
Write-Host "Note: cold-boot sign-in still uses PIN first; face tile works for Win+L unlock after logon."
