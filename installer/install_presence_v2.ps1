$Task = "NeoFace-Presence"
$Py = (Get-Command python).Source
$Script = "C:\NeoFace\face_unlock\presence_daemon.py"
$Act = New-ScheduledTaskAction -Execute $Py -Argument "`"$Script`""
$Trig = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName $Task -Action $Act -Trigger $Trig -RunLevel Highest -Force
Write-Host "installed $Task - runs at logon. Disable via Task Scheduler if needed."
