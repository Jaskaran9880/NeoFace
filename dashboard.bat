@echo off
title NeoFace Dashboard
echo.
echo  Starting NeoFace Dashboard...
echo  Browser will open at http://localhost:8080
echo  Press Ctrl+C to stop
echo.
start http://localhost:8080
python "%~dp0dashboard.py"
pause
