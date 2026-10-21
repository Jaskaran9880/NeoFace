# Assemble dist\ for installer.iss: app payload + bundled Python runtime.
# Used by CI (see .github/workflows) and locally:
#   powershell -File installer\build_dist.ps1 -DllPath cp\FaceUnlockCP.dll
param(
    [string]$DllPath = "",
    [string]$PyEmbedVersion = "3.13.16",
    [switch]$SkipRuntime,
    [switch]$SkipSmokeTest
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ROOT = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $ROOT "dist"
$runtimeDir = Join-Path $dist "runtime"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Get-FileWithRetry([string]$Url, [string]$OutFile, [int]$Tries = 4) {
    # curl.exe first (PS 5.1 Invoke-WebRequest is flaky against python.org)
    for ($i = 1; $i -le $Tries; $i++) {
        & curl.exe -fsSL --retry 3 --retry-delay 2 --connect-timeout 30 -o $OutFile $Url 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and (Get-Item $OutFile).Length -gt 0) { return }
        Write-Host ("    curl try {0}/{1} failed for {2}" -f $i, $Tries, $Url)
        if ($i -lt $Tries) { Start-Sleep -Seconds (2 * $i) }
    }
    # fallback: Invoke-WebRequest
    for ($i = 1; $i -le 2; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 300
            return
        } catch {
            Write-Host ("    iwr try {0}/2 failed: {1}" -f $i, $_.Exception.Message)
            Start-Sleep -Seconds 3
        }
    }
    throw "download failed after $Tries tries: $Url"
}

Write-Host "== build_dist: assembling $dist"
if (Test-Path $dist) { Remove-Item $dist -Recurse -Force }
New-Item -ItemType Directory -Path $dist -Force | Out-Null

function Copy-Tree([string]$Src, [string]$Dst) {
    if (!(Test-Path $Src)) { throw "missing source: $Src" }
    $parent = Split-Path -Parent $Dst
    if (!(Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    # /MIR mirror, skip caches; robocopy exit 0-7 are success codes
    robocopy $Src $Dst /MIR /XD __pycache__ .venv /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $Src -> $Dst" }
}

# --- app payload --------------------------------------------------------
Write-Host "  copying app payload"
Copy-Tree (Join-Path $ROOT "face_unlock") (Join-Path $dist "face_unlock")
Copy-Tree (Join-Path $ROOT "templates")   (Join-Path $dist "templates")
Copy-Tree (Join-Path $ROOT "static")      (Join-Path $dist "static")

New-Item -ItemType Directory -Path (Join-Path $dist "tools") -Force | Out-Null
foreach ($t in @("enroll_fast.py", "fetch_fast.py", "set_password_machine.py",
                 "test_unlock.py", "update_notifier.py", "setup_wizard.py",
                 "win_consent.ps1")) {
    Copy-Item (Join-Path $ROOT "tools\$t") (Join-Path $dist "tools\$t") -Force
}

Copy-Item (Join-Path $ROOT "dashboard.py")        (Join-Path $dist "dashboard.py") -Force
Copy-Item (Join-Path $ROOT "config.example.toml") (Join-Path $dist "config.example.toml") -Force
# Installed default config (the daemon and dashboard read config.toml)
Copy-Item (Join-Path $ROOT "config.example.toml") (Join-Path $dist "config.toml") -Force

# --- CP DLL + bitmaps ---------------------------------------------------
if (!$DllPath) { $DllPath = Join-Path $ROOT "cp\FaceUnlockCP.dll" }
if (!(Test-Path $DllPath)) { throw "FaceUnlockCP.dll not found: $DllPath (build it first: cd cp; .\build_cp.ps1)" }
New-Item -ItemType Directory -Path (Join-Path $dist "cp") -Force | Out-Null
Copy-Item $DllPath (Join-Path $dist "cp\FaceUnlockCP.dll") -Force
foreach ($bmp in @("icon.bmp", "tile.bmp")) {
    $src = Join-Path $ROOT "cp\$bmp"
    if (Test-Path $src) { Copy-Item $src (Join-Path $dist "cp\$bmp") -Force }
    else { throw "missing $src" }
}

# --- installer helper scripts + launchers -------------------------------
New-Item -ItemType Directory -Path (Join-Path $dist "installer_scripts") -Force | Out-Null
Copy-Item (Join-Path $ROOT "installer\post_install.ps1") (Join-Path $dist "installer_scripts\post_install.ps1") -Force
Copy-Tree (Join-Path $ROOT "installer\launchers") (Join-Path $dist "launchers")

# --- bundled Python runtime ---------------------------------------------
if (!$SkipRuntime) {
    Write-Host "  bundling Python $PyEmbedVersion (embeddable)"
    $zipUrl = "https://www.python.org/ftp/python/$PyEmbedVersion/python-$PyEmbedVersion-embed-amd64.zip"
    $zipPath = Join-Path $env:TEMP "python-$PyEmbedVersion-embed-amd64.zip"
    Get-FileWithRetry -Url $zipUrl -OutFile $zipPath
    Expand-Archive -Path $zipPath -DestinationPath $runtimeDir -Force
    Remove-Item $zipPath -Force

    # enable site-packages: append `import site` to pythonXY._pth
    $pth = Get-ChildItem $runtimeDir -Filter "python*._pth" | Select-Object -First 1
    if (!$pth) { throw "python*._pth not found in embeddable runtime" }
    Add-Content -Path $pth.FullName -Value "`nimport site"

    Write-Host "  installing runtime packages (pip)"
    $getPip = Join-Path $env:TEMP "get-pip.py"
    Get-FileWithRetry -Url "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
    & (Join-Path $runtimeDir "python.exe") $getPip --no-warn-script-location -q
    if ($LASTEXITCODE -ne 0) { throw "get-pip.py failed (exit $LASTEXITCODE)" }
    Remove-Item $getPip -Force
    & (Join-Path $runtimeDir "python.exe") -m pip install --no-warn-script-location -q -r (Join-Path $ROOT "requirements-runtime.txt")
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)" }

    # pywin32 on embeddable Python: expose its DLLs at interpreter startup
    $sitePkgs = Join-Path $runtimeDir "Lib\site-packages"
    $siteCustomize = @"
import os
_d = os.path.join(os.path.dirname(__file__), "pywin32_system32")
if os.path.isdir(_d):
    os.add_dll_directory(_d)
"@
    Set-Content -Path (Join-Path $sitePkgs "sitecustomize.py") -Value $siteCustomize -Encoding ASCII

    if (!$SkipSmokeTest) {
        Write-Host "  smoke-testing bundled runtime"
        Push-Location $dist
        try {
            # note: embeddable ._pth makes `.` = runtime dir, so pass the app dirs explicitly
            $appDirQuoted = $dist -replace '\\', '\\'
            $toolsDirQuoted = (Join-Path $dist "tools") -replace '\\', '\\'
            & (Join-Path $runtimeDir "python.exe") -c "import sys; sys.path.insert(0, r'$appDirQuoted'); sys.path.insert(0, r'$toolsDirQuoted'); import cv2, numpy, flask, PIL, pillow_heif, win32crypt, win32pipe, win32api; import face_unlock.fast, face_unlock.antispoof, face_unlock.store; import setup_wizard; print('runtime smoke OK, opencv', cv2.__version__)"
            if ($LASTEXITCODE -ne 0) { throw "runtime smoke test failed (exit $LASTEXITCODE)" }
        } finally { Pop-Location }
    }
}

$sizeMB = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "== build_dist: done ($sizeMB MB in $dist)"
