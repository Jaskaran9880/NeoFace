# NeoFace installer post-install: models, CP DLL, scheduled tasks.
# Called by installer.iss (admin). Also runnable standalone against an
# installed tree:  powershell -File post_install.ps1 -AppDir "C:\...\NeoFace"
param(
    [Parameter(Mandatory = $true)]
    [string]$AppDir
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) { throw "post_install.ps1 must run as Administrator." }
if (!(Test-Path $AppDir)) { throw "AppDir not found: $AppDir" }

$py = Join-Path $AppDir "runtime\python.exe"
$pyw = Join-Path $AppDir "runtime\pythonw.exe"
if (!(Test-Path $py)) { throw "Bundled Python missing: $py" }

$pd = "C:\ProgramData\NeoFace"
Write-Host "[post-install] data dir $pd"
New-Item -ItemType Directory -Path $pd -Force | Out-Null
# Ensure the Limited daemon user can write the gallery (locale-proof SIDs)
& icacls $pd /grant "*S-1-1-0:(OI)(CI)M" /grant "*S-1-5-32-545:(OI)(CI)M" /T /Q | Out-Null

# --- Models (cloud, pinned SHA256) ------------------------------------
Write-Host "[post-install] checking models"
$models = @(
    @{ Name = "yunet.onnx";
       Url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx";
       Sha256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4" },
    @{ Name = "sface.onnx";
       Url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx";
       Sha256 = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79" },
    @{ Name = "antifas_v2.onnx";
       Url = "https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx/resolve/main/minifasnet_v2.onnx";
       Sha256 = "d7b3cd9ba8a7ceb13baa8c4720902e27ca3112eff52f926c08804af6b6eecc7b" }
)
$modelDir = Join-Path $AppDir "models"
New-Item -ItemType Directory -Path $modelDir -Force | Out-Null

function Get-FileSha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
}

foreach ($m in $models) {
    $out = Join-Path $modelDir $m.Name
    $ok = $false
    if (Test-Path $out) {
        if ((Get-FileSha256 $out) -eq $m.Sha256) {
            Write-Host ("  {0} ok" -f $m.Name)
            $ok = $true
        } else {
            Write-Host ("  {0} hash mismatch - re-downloading" -f $m.Name)
            Remove-Item $out -Force
        }
    }
    if (!$ok) {
        $tmp = "$out.download"
        $done = $false
        for ($try = 1; $try -le 3 -and !$done; $try++) {
            try {
                Write-Host ("  {0} downloading (try {1}/3)..." -f $m.Name, $try)
                [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                # curl first (more reliable), Invoke-WebRequest as fallback
                & curl.exe -fsSL --retry 3 --retry-delay 2 --connect-timeout 30 -o $tmp $m.Url 2>$null
                if ($LASTEXITCODE -ne 0 -or !(Test-Path $tmp) -or (Get-Item $tmp).Length -eq 0) {
                    Invoke-WebRequest -Uri $m.Url -OutFile $tmp -UseBasicParsing -TimeoutSec 300
                }
                if ((Get-FileSha256 $tmp) -eq $m.Sha256) {
                    Move-Item $tmp $out -Force
                    $done = $true
                    Write-Host ("  {0} saved" -f $m.Name)
                } else {
                    Write-Host ("  {0} hash mismatch after download" -f $m.Name)
                    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                }
            } catch {
                Write-Host ("  {0} download failed: {1}" -f $m.Name, $_.Exception.Message)
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 3
            }
        }
        if (!$done) { throw "Model download failed: $($m.Name). Check your connection and re-run the installer." }
    }
}

# --- Stop old instances ------------------------------------------------
Write-Host "[post-install] stopping old NeoFace processes"
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match "daemon_pipe\.py|dashboard\.py" } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch { }
    }

# --- Credential Provider DLL -------------------------------------------
Write-Host "[post-install] registering credential provider"
$cpDir = Join-Path ${env:ProgramFiles} "NeoFace"
New-Item -ItemType Directory -Path $cpDir -Force | Out-Null
$dllSrc = Join-Path $AppDir "cp\FaceUnlockCP.dll"
if (!(Test-Path $dllSrc)) { throw "FaceUnlockCP.dll missing from install: $dllSrc" }
Copy-Item $dllSrc (Join-Path $cpDir "FaceUnlockCP.dll") -Force
foreach ($bmp in @("icon.bmp", "tile.bmp")) {
    $src = Join-Path $AppDir "cp\$bmp"
    if (Test-Path $src) { Copy-Item $src (Join-Path $cpDir $bmp) -Force }
}
$dll = Join-Path $cpDir "FaceUnlockCP.dll"
& regsvr32 /s $dll
if ($LASTEXITCODE -ne 0) { throw "regsvr32 failed for $dll (exit $LASTEXITCODE)" }
$guid = "{8F3B2C1D-4E5A-4B7C-9D1F-2A3B4C5D6E7F}"
New-Item -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Authentication\Credential Providers\$guid" -Force | Out-Null
Write-Host "  tile registered"

# --- Scheduled tasks ---------------------------------------------------
Write-Host "[post-install] installing scheduled tasks"
foreach ($legacy in @("NeoFaceDaemon", "NeoFace-UpdateNotifier")) {
    Unregister-ScheduledTask -TaskName $legacy -Confirm:$false -ErrorAction SilentlyContinue
}

$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$AppDir\face_unlock\daemon_pipe.py`"" -WorkingDirectory $AppDir
$trig = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
Write-Host "  NeoFace-Daemon (starts at logon)"

$uAct = New-ScheduledTaskAction -Execute $pyw -Argument "`"$AppDir\tools\update_notifier.py`"" -WorkingDirectory $AppDir
$uTrig = New-ScheduledTaskTrigger -AtLogOn
$uTrig.Delay = 'PT1M'
$uSet = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$uPrincipal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "NeoFace-UpdateCheck" -Action $uAct -Trigger $uTrig -Settings $uSet -Principal $uPrincipal -Force | Out-Null
Write-Host "  NeoFace-UpdateCheck (checks at sign-in)"

Write-Host "[post-install] done"
