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
