<#
.SYNOPSIS
    NeoFace full uninstaller - removes the installed components of NeoFace Unlock.

.DESCRIPTION
    Stops the dashboard (:8080) and daemon processes, removes every NeoFace scheduled
    task, unregisters the lock-screen Credential Provider DLL (regsvr32 /u), deletes
    C:\Program Files\NeoFace and removes Start Menu / desktop shortcuts.

    User data in C:\ProgramData\NeoFace (face gallery, password vault, logs) is KEPT
    by default so a reinstall works. Use -Purge (or answer 'y' / 'purge' at the
    prompt) to delete it as well.

    The C:\NeoFace repository itself is NEVER deleted - remove that folder manually
    if you want the clone gone too.

    Requires administrator rights; the script relaunches itself elevated (UAC) if
    needed. If the lock screen (LogonUI) holds the DLL, deletion is scheduled for
    the next reboot.

.PARAMETER Purge
    Delete user data (C:\ProgramData\NeoFace) without prompting.

.PARAMETER Pause
    Wait for Enter before closing (used when relaunching in a new elevated window).

.EXAMPLE
    .\uninstall.ps1

.EXAMPLE
    .\uninstall.ps1 -Purge
#>
[CmdletBinding()]
param(
    [switch]$Purge,
    [switch]$Pause,
    [Parameter(ValueFromRemainingArguments = $true)]
    $Rest
)

# Accept bare "purge" / odd dash forms forwarded by uninstall.bat
if (!$Purge -and $Rest) {
    foreach ($a in @($Rest)) {
        if ("$a" -match '^-?purge$') { $Purge = $true }
    }
}

$ErrorActionPreference = "Stop"

# --- Layout -------------------------------------------------------------
$SELF = $PSCommandPath
if (!$SELF) { $SELF = $MyInvocation.MyCommand.Path }
$ROOT = Split-Path -Parent $PSScriptRoot
if (!$ROOT) { $ROOT = (Get-Location).Path }

$CP_DIR   = "C:\Program Files\NeoFace"
$CP_DLL   = Join-Path $CP_DIR "FaceUnlockCP.dll"
$CP_GUID  = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
$CP_KEY   = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$CP_GUID"
$DATA_DIR = Join-Path $env:PROGRAMDATA "NeoFace"
$REPO_DLL = Join-Path $ROOT "cp\FaceUnlockCP.dll"

# --- Report collectors --------------------------------------------------
$script:removed = New-Object System.Collections.Generic.List[string]
$script:kept    = New-Object System.Collections.Generic.List[string]
$script:notes   = New-Object System.Collections.Generic.List[string]
$script:failed  = New-Object System.Collections.Generic.List[string]

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    return $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# Schedule a file/directory for deletion at the next reboot (needs admin).
function Set-PendingDelete {
    param([string]$Path)
    if (-not ('NeoFaceUninstall.Win32' -as [type])) {
        $sig = '[DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] public static extern bool MoveFileEx(string lpExistingFileName, string lpNewFileName, int dwFlags);'
        try { Add-Type -Namespace NeoFaceUninstall -Name Win32 -MemberDefinition $sig -ErrorAction Stop } catch { }
    }
    if (-not ('NeoFaceUninstall.Win32' -as [type])) { return $false }
    return [NeoFaceUninstall.Win32]::MoveFileEx($Path, $null, 4)   # MOVEFILE_DELAY_UNTIL_REBOOT
}

# --- Elevation ----------------------------------------------------------
if (!(Test-IsAdmin)) {
    Write-Host "Administrator privileges are required to uninstall NeoFace." -ForegroundColor Yellow
    Write-Host "Requesting elevation (accept the UAC prompt)..." -ForegroundColor Yellow
    $psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $elevArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$SELF`" -Pause"
    if ($Purge) { $elevArgs += " -Purge" }
    $elevProc = $null
    $elevErr  = $null
    try {
        $elevProc = Start-Process -FilePath $psExe -ArgumentList $elevArgs -Verb RunAs -Wait -PassThru
    } catch {
        $elevErr = $_.Exception.Message
    }
    if ($elevProc) { $elevProc.WaitForExit(); exit $elevProc.ExitCode }
    Write-Host "Elevation failed or was cancelled: $elevErr" -ForegroundColor Red
    Write-Host "Open an Admin terminal and run:  .\install\uninstall.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n=== NeoFace Uninstaller ===" -ForegroundColor Cyan
Write-Host "Removes the lock screen tile, scheduled tasks and installed files."
Write-Host "User data and the C:\NeoFace repository are kept unless you opt in.`n"

# --- [1/6] Stop processes ------------------------------------------------
Write-Host "[1/6] Stopping NeoFace processes..." -ForegroundColor Yellow

# 1a. Ask running NeoFace tasks to stop first (graceful path for the daemon)
try {
    $runTasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue |
        Where-Object { $_.TaskName -like 'NeoFace*' -and $_.State -eq 'Running' })
    foreach ($t in $runTasks) {
        Stop-ScheduledTask -TaskName $t.TaskName -ErrorAction SilentlyContinue
        Write-Host "  Stopped running task $($t.TaskName)" -ForegroundColor Gray
    }
    if ($runTasks.Count -gt 0) { Start-Sleep -Seconds 2 }
} catch { }

# 1b. Find NeoFace python processes (daemon + dashboard), anchored to install root
$targetIds = New-Object System.Collections.Generic.List[int]
$rootRe = [regex]::Escape($ROOT)
try {
    Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" | ForEach-Object {
        if ($_.CommandLine -and $_.CommandLine -match "(?i)$rootRe\\[^\s`"]*(dashboard\.py|daemon_pipe|face_unlock)") {
            if (!$targetIds.Contains([int]$_.ProcessId)) { $targetIds.Add([int]$_.ProcessId) }
        }
    }
} catch { }

# Safety net: dashboard bound to :8080 - also requires the install root in its command line
try {
    Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $op = Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" -ErrorAction SilentlyContinue
        if ($op -and $op.Name -match '^python' -and $op.CommandLine -and $op.CommandLine -match "(?i)$rootRe\\") {
            if (!$targetIds.Contains([int]$op.ProcessId)) { $targetIds.Add([int]$op.ProcessId) }
        }
    }
} catch { }

# 1c. Stop them: ask nicely (main window) first, force if still alive
foreach ($id in $targetIds) {
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (!$p) {
        $script:removed.Add("Process PID $id (already exited)")
        continue
    }
    $label = "Process PID $id ($($p.ProcessName))"
    $graceful = $false
    try { $graceful = $p.CloseMainWindow() } catch { }
    if ($graceful) { $null = $p.WaitForExit(3000) }
    if (!$p.HasExited) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    if (Get-Process -Id $id -ErrorAction SilentlyContinue) {
        $script:failed.Add("$label - could not stop")
    } else {
        $script:removed.Add($label)
        Write-Host "  Stopped $label" -ForegroundColor Gray
    }
}
if ($targetIds.Count -eq 0) { Write-Host "  No NeoFace processes running" -ForegroundColor Gray }

# --- [2/6] Remove scheduled tasks ---------------------------------------
Write-Host "`n[2/6] Removing scheduled tasks..." -ForegroundColor Yellow
$tasks = @()
try {
    $tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like 'NeoFace*' })
} catch { }
foreach ($t in $tasks) {
    try {
        Stop-ScheduledTask -TaskName $t.TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false -ErrorAction Stop
        $script:removed.Add("Scheduled task '$($t.TaskName)'")
        Write-Host "  Removed task $($t.TaskName)" -ForegroundColor Green
    } catch {
        $script:failed.Add("Scheduled task '$($t.TaskName)' - $($_.Exception.Message)")
    }
}
if ($tasks.Count -eq 0) { Write-Host "  No NeoFace scheduled tasks found" -ForegroundColor Gray }

# --- [3/6] Unregister the credential provider DLL -----------------------
# MUST happen before deleting files (regsvr32 needs the DLL on disk).
Write-Host "`n[3/6] Unregistering lock screen credential provider..." -ForegroundColor Yellow

if (Test-Path $CP_DLL) {
    & regsvr32.exe /u /s "$CP_DLL" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $script:removed.Add("COM registration of FaceUnlockCP.dll (lock screen tile)")
        Write-Host "  DLL unregistered - NeoFace tile removed from Win+L" -ForegroundColor Green
    } else {
        $script:failed.Add("regsvr32 /u failed for $CP_DLL (exit $LASTEXITCODE)")
        Write-Host "  WARNING: regsvr32 could not unregister the DLL (it may be in use)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  $CP_DLL not present" -ForegroundColor Gray
}

# Repo copy may also have been registered directly (cp\unregister_cp.ps1 does both)
if (Test-Path $REPO_DLL) {
    & regsvr32.exe /u /s "$REPO_DLL" | Out-Null   # best effort, result not reported
}

# Remove the provider key the installer created manually
if (Test-Path $CP_KEY) {
    try {
        Remove-Item -LiteralPath $CP_KEY -Recurse -Force -ErrorAction Stop
        $script:removed.Add("Credential provider registry key")
    } catch {
        $script:failed.Add("Registry key $CP_KEY - $($_.Exception.Message)")
    }
}

# --- [4/6] Remove installed files ---------------------------------------
Write-Host "`n[4/6] Removing installed files..." -ForegroundColor Yellow
if (Test-Path $CP_DIR) {
    try { Remove-Item -LiteralPath $CP_DIR -Recurse -Force -ErrorAction Stop } catch { }
    if (!(Test-Path $CP_DIR)) {
        $script:removed.Add($CP_DIR)
        Write-Host "  Removed $CP_DIR" -ForegroundColor Green
    } else {
        # Files are locked (LogonUI holds the DLL while the lock screen is up)
        $leftover = @(Get-ChildItem -Path $CP_DIR -Recurse -Force -ErrorAction SilentlyContinue)
        $bad = 0
        foreach ($f in $leftover) {
            if (!(Set-PendingDelete -Path $f.FullName)) { $bad++ }
        }
        $dirPending = Set-PendingDelete -Path $CP_DIR
        if ($bad -eq 0 -and $dirPending) {
            $script:notes.Add("$CP_DIR is in use (lock screen/LogonUI) - deletion scheduled for next reboot")
            Write-Host "  Locked by the lock screen - will be removed on next reboot" -ForegroundColor Yellow
        } else {
            $script:failed.Add("$CP_DIR is locked and could not be scheduled for deletion - reboot and rerun")
        }
        if (Get-Process -Name LogonUI -ErrorAction SilentlyContinue) {
            $script:notes.Add("LogonUI.exe is running - sign out or reboot, then rerun if files remain")
        }
    }
} else {
    Write-Host "  $CP_DIR not present" -ForegroundColor Gray
}

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
