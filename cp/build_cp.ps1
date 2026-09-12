$ErrorActionPreference = "Stop"
$vs = "${env:ProgramFiles(x86)}\Microsoft Visual C++\Build Tools\VC\Auxiliary\Build\vcvars64.bat"
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $path = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($path) { $vs = "$path\VC\Auxiliary\Build\vcvars64.bat" }
}
if (!(Test-Path $vs)) { throw "VS Build Tools not found. Install VS2022 Build Tools + Desktop C++ first." }
cmd /c "`"$vs`" && cl /LD /EHsc /std:c++17 /O2 dllmain.cpp provider.cpp credential.cpp kerb.cpp /link /DEF:FaceUnlockCP.def /OUT:FaceUnlockCP.dll ole32.lib uuid.lib advapi32.lib user32.lib shlwapi.lib secur32.lib crypt32.lib"
Write-Host "built FaceUnlockCP.dll - test with register_cp.ps1 (admin)"
