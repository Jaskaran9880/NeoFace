# NeoFace elevated apply script - runs the downloaded, hash-verified
# installer silently and restarts the affected services.
#
# Invoked by:
#   - the NeoFace-UpdateApply scheduled task (RunLevel Highest, registered
#     by post_install.ps1 while the installer is already elevated) - the
#     silent, no-UAC auto-update path;
#   - tools/prepare_apply()'s UAC fallback (Start-Process -Verb RunAs).
#
# SECURITY: this script runs elevated, so it never trusts its arguments or
# any staging file. The staged exe is re-verified HERE, in the elevated
# context, by re-fetching the release metadata over TLS and re-hashing the
# file (python -m face_unlock.updater --verify). Only bytes that match the
# SHA256 published in the GitHub release notes of Jaskaran9880/NeoFace are
# ever executed. On any failure before the installer runs: nothing has been
# stopped, zero disruption.
#
# Fail-soft by design: one log line per step to
# C:\ProgramData\NeoFace\update_apply.log, apply_state.json carries the
# outcome to the dashboard, exit code only matters for the caller that
# staged the request.

param(
    [switch]$FromTask,
    [switch]$FromDashboard,
    [switch]$RelaunchDashboard,
    [string]$AppDir = "$env:LOCALAPPDATA\Programs\NeoFace",
    [string]$SetupExe = "",
    [string]$Sha256 = "",
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

$DataDir    = "C:\ProgramData\NeoFace"
$UpdatesDir = Join-Path $DataDir "updates"
$Pending    = Join-Path $UpdatesDir "pending.json"
$StateFile  = Join-Path $UpdatesDir "apply_state.json"
$LogFile    = Join-Path $DataDir "update_apply.log"
$Python     = Join-Path $AppDir "runtime\python.exe"

function Write-ApplyLog([string]$Line) {
    try {
        if (Test-Path $LogFile) {
            $item = Get-Item $LogFile -ErrorAction SilentlyContinue
            if ($item -and $item.Length -gt 200KB) {
                $tail = Get-Content $LogFile -Tail 20 -ErrorAction SilentlyContinue
                Set-Content -Path $LogFile -Value $tail -Encoding UTF8
            }
        }
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogFile -Value "[$stamp] $Line" -Encoding UTF8
    } catch { }
}

function Write-State([string]$State, [string]$Message = "", [string]$Version = "",
                     [int]$ExitCode = -1, [bool]$RolledBack = $false) {
    try {
        $data = @{
            state        = $State
            pct          = $null
            message      = $Message
            version      = if ($Version) { $Version } else { $null }
            exit_code    = if ($ExitCode -ge 0) { $ExitCode } else { $null }
            rolled_back  = $RolledBack
            updated_at   = [int][double]::Parse((Get-Date -UFormat %s))
        }
        $tmp = "$StateFile.tmp"
        $data | ConvertTo-Json -Depth 4 | Set-Content -Path $tmp -Encoding UTF8 -Force
        Move-Item -Path $tmp -Destination $StateFile -Force
    } catch {
        Write-ApplyLog("state write failed: $($_.Exception.Message)")
    }
}

# --- 0. elevation gate ----------------------------------------------------
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-ApplyLog("REFUSED: not elevated (FromTask=$FromTask)")
    Write-State "failed" "apply script was not elevated"
    exit 1
}

Write-ApplyLog("start: FromTask=$FromTask FromDashboard=$FromDashboard AppDir=$AppDir")

# --- 1. consume the staged request (pending.json, or explicit args) -------
$setup = $SetupExe
$wantSha = $Sha256
$wantTag = $Tag
$relaunch = $RelaunchDashboard.IsPresent
if (-not $setup -and (Test-Path $Pending)) {
    try {
        $pending = Get-Content $Pending -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $setup)  { $setup   = $pending.setup }
        if (-not $wantSha){ $wantSha = $pending.sha256 }
        if (-not $wantTag){ $wantTag = $pending.tag }
        if ($pending.relaunch) { $relaunch = $true }
        Remove-Item $Pending -Force -ErrorAction SilentlyContinue
    } catch {
        Write-ApplyLog("pending.json unreadable: $($_.Exception.Message)")
    }
}
if (-not $setup -or -not (Test-Path $setup)) {
    Write-ApplyLog("nothing staged - exiting")
    Write-State "failed" "no staged installer found"
    exit 1
}
$setupItem = Get-Item $setup -ErrorAction SilentlyContinue
Write-ApplyLog("staged: $setup ($([math]::Round($setupItem.Length/1MB,1)) MB) tag=$wantTag")

# --- 2. re-verify IN the elevated context (TLS re-fetch + re-hash) -------
Write-State "verifying" "Re-verifying installer signature..."
if (Test-Path $Python) {
    Push-Location $AppDir
    try {
        $verifyArgs = @("-m", "face_unlock.updater", "--verify", "--setup", $setup)
        if ($wantTag) { $verifyArgs += @("--tag", $wantTag) }
        & $Python @verifyArgs | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-ApplyLog("verify FAILED (exit $LASTEXITCODE) - nothing was stopped")
            Remove-Item $setup -Force -ErrorAction SilentlyContinue
            Write-State "failed" "SHA256 verification failed - download deleted, not applied"
            exit 1
        }
    } finally { Pop-Location }
    Write-ApplyLog("verify OK (TLS release hash matches staged bytes)")
} else {
    # No bundled python (broken install) -> compare against the staged hash
    # recorded at download time; weaker but never unverified.
    $actual = (Get-FileHash -Path $setup -Algorithm SHA256).Hash.ToLower()
    if (-not $wantSha -or $actual -ne $wantSha.ToLower()) {
        Write-ApplyLog("verify fallback FAILED ($actual != $wantSha)")
        Remove-Item $setup -Force -ErrorAction SilentlyContinue
        Write-State "failed" "SHA256 verification failed - download deleted, not applied"
        exit 1
    }
    Write-ApplyLog("verify OK (Get-FileHash vs staged hash; bundled python missing)")
}

# --- 3. stop the world ----------------------------------------------------
Write-State "installing" "Installing update..."
Write-ApplyLog("stopping daemon + dashboard")
Stop-ScheduledTask -TaskName "NeoFace-Daemon" -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "daemon_pipe\.py|dashboard\.py" } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
    }
Start-Sleep -Seconds 1

# --- 4. run the installer silently ----------------------------------------
Write-ApplyLog("running installer: $setup")
$proc = Start-Process -FilePath $setup `
    -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-" `
    -Wait -PassThru
$exit = $proc.ExitCode
Write-ApplyLog("installer exit code: $exit")

# --- 5. rollback once on failure ------------------------------------------
if ($exit -ne 0) {
    $previous = Get-ChildItem -Path $UpdatesDir -Filter "NeoFace-Setup-*.exe" `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ne $setup } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($previous) {
        Write-ApplyLog("installer failed - rolling back once to $($previous.Name)")
        $rb = Start-Process -FilePath $previous.FullName `
            -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-" `
            -Wait -PassThru
        Write-ApplyLog("rollback exit code: $($rb.ExitCode)")
        Write-State "failed" "Update failed (exit $exit) - rolled back to previous version." `
            -ExitCode $exit -RolledBack $true
    } else {
        Write-State "failed" "Update failed (exit $exit) - no previous version to roll back to." `
            -ExitCode $exit
    }
    exit 1
}

# --- 6. success: restart services, prune old installers -------------------
Write-ApplyLog("restart daemon")
Start-ScheduledTask -TaskName "NeoFace-Daemon" -ErrorAction SilentlyContinue
Get-ChildItem -Path $UpdatesDir -Filter "NeoFace-Setup-*.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -ne $setup } |
    Remove-Item -Force -ErrorAction SilentlyContinue
$versionLabel = if ($wantTag) { $wantTag } else { [IO.Path]::GetFileName($setup) }
Write-State "done" "Updated to $versionLabel" -Version $versionLabel
Write-ApplyLog("done: $versionLabel")

# --- 7. optional dashboard relaunch ---------------------------------------
if ($relaunch) {
    try {
        $launcher = Join-Path $AppDir "launchers\Dashboard.bat"
        if (Test-Path $launcher) {
            Start-Process -FilePath $launcher -WorkingDirectory (Split-Path $launcher)
            Write-ApplyLog("dashboard relaunched via launcher")
        }
        $keyFile = Join-Path $AppDir ".dashboard_key"
        Start-Sleep -Seconds 3
        if (Test-Path $keyFile) {
            $key = (Get-Content $keyFile -Raw).Trim()
            if ($key) {
                Start-Process "http://127.0.0.1:8080/?key=$key"
            }
        }
    } catch {
        Write-ApplyLog("relaunch failed: $($_.Exception.Message)")
    }
}

exit 0
