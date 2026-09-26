@echo off
setlocal
title NeoFace Uninstaller

:: Double-click friendly uninstaller. Needs admin - relaunch elevated if needed.
:: Only the literal argument "purge" is ever forwarded: cmd would re-parse raw
:: %* across the UAC boundary (metachar injection), so everything else is dropped.
set "NFPURGE="
if /I "%~1"=="purge" set "NFPURGE=1"

net session >nul 2>&1
if errorlevel 1 (
    echo Requesting administrator privileges...
    set "NFBAT=%~f0"
    powershell -NoProfile -Command "if ($env:NFPURGE) { Start-Process -FilePath $env:NFBAT -Verb RunAs -ArgumentList 'purge' } else { Start-Process -FilePath $env:NFBAT -Verb RunAs }"
    exit /b
)

echo Running NeoFace uninstaller...
echo.
if defined NFPURGE (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\uninstall.ps1" -Purge
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install\uninstall.ps1"
)
if errorlevel 1 (
    echo.
    echo Uninstall finished with errors - see messages above.
) else (
    echo.
    echo Uninstall complete.
)
echo.
pause
