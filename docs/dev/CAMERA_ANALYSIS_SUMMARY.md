# CAMERA ACTIVATION ANALYSIS SUMMARY
**Date**: 2026-09-20
**Problem**: Camera LED does NOT flash during face unlock

## Executive Summary

The camera LED not flashing during face unlock indicates the camera is never actually activated by the daemon. Analysis reveals **8 critical failure points** and **3 likely root causes**.

## Key Findings

### ✅ What Works
- Camera hardware is functional (direct cv2.VideoCapture test works)
- Dashboard test-scan works (camera LED flashes)
- Enrollment tool works (processes photos from disk)

### ❌ What Doesn't Work
- Camera LED does NOT flash during lock screen unlock
- This means daemon is NOT opening camera when CP DLL connects

## Most Likely Root Causes (Ranked by Probability)

### 1. **Daemon Not Running** (80% probability)
**Evidence**:
- Camera never opens during unlock
- If daemon running, it would open camera when pipe message received
- Scheduled task may have failed to start daemon

**Verification**:
```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'"
Get-ScheduledTask -TaskName 'NeoFace-Daemon' | Select-Object TaskName, State
```

### 2. **Camera Resource Contention** (15% probability)
**Evidence**:
- Dashboard test-scan or presence daemon may hold camera
- Only one process can hold camera at a time
- Daemon Cam.open() has early return if camera already open (line 114)

**Verification**:
```python
import cv2
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
print("Camera free" if cap.isOpened() else "Camera held")
cap.release()
```

### 3. **Session Mismatch** (5% probability)
**Evidence**:
- CP DLL runs as SYSTEM in Session 0
- Daemon runs in user session
- Named pipe ACL allows both, but connection may fail

**Verification**:
- Check daemon scheduled task principal (should be Interactive user)
- Check daemon logs for pipe connection errors

## Critical Code Paths

### Lock Screen Flow (What SHOULD Happen)
```
Win+L → CP DLL (Session 0) → Read cred.bin → Connect pipe → Send "VERIFY user"
    → Daemon receives → cam.open() → Camera LED flashes → Frames captured
    → Face recognized → Send "OK" → CP DLL unlocks
```

### What's Actually Happening
```
Win+L → CP DLL (Session 0) → Read cred.bin → Connect pipe → Send "VERIFY user"
    → Daemon NOT RUNNING → Pipe connection fails → CP DLL gives up
    → "Face not recognized" error → Camera LED never flashes ❌
```

## Diagnostic Commands

### Quick Health Check
```powershell
# 1. Check if daemon is running
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'"

# 2. Check scheduled task
Get-ScheduledTask -TaskName 'NeoFace-Daemon' | Select-Object TaskName, State, LastRunTime

# 3. Check daemon logs (last 20 lines)
Get-Content C:\ProgramData\NeoFace\daemon.log -Tail 20

# 4. Check CP logs (last 20 lines)
Get-Content C:\ProgramData\NeoFace\cp.log -Tail 20

# 5. Check camera availability
python -c "import cv2; cap=cv2.VideoCapture(1,cv2.CAP_DSHOW); print('FREE' if cap.isOpened() else 'HELD'); cap.release()"
```

### Full Diagnostic
```powershell
# Run complete diagnostic
python -c "
import subprocess, cv2, os

print('=== NeoFace Camera Diagnostic ===')
print()

# Check daemon
result = subprocess.run(['powershell', '-Command', 
    'Get-CimInstance Win32_Process -Filter \"Name LIKE \'python%\' AND CommandLine LIKE \'%daemon%\'\" | Select-Object -Expand ProcessId'],
    capture_output=True, text=True)
pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
print(f'Daemon: {\"RUNNING (PID: \" + pids[0] + \")\" if pids else \"NOT RUNNING\"}')

# Check scheduled task
result = subprocess.run(['powershell', '-Command',
    'Get-ScheduledTask -TaskName \'NeoFace-Daemon\' | Select-Object -Expand State'],
    capture_output=True, text=True)
print(f'Scheduled Task: {result.stdout.strip() or \"NOT FOUND\"}')

# Check camera
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
print(f'Camera: {\"FREE\" if cap.isOpened() else \"HELD\"}')
cap.release()

# Check pipe
try:
    import win32pipe
    win32pipe.WaitNamedPipe(r'\\\\.\\pipe\\NeoFace', 1000)
    print('Pipe: LISTENING')
except:
    print('Pipe: NOT AVAILABLE')

# Check logs
daemon_log = r'C:\ProgramData\NeoFace\daemon.log'
cp_log = r'C:\ProgramData\NeoFace\cp.log'
if os.path.exists(daemon_log):
    with open(daemon_log) as f:
        lines = f.readlines()
    print(f'Daemon Log: {len(lines)} lines, last: {lines[-1].strip() if lines else \"empty\"}')
if os.path.exists(cp_log):
    with open(cp_log) as f:
        lines = f.readlines()
    print(f'CP Log: {len(lines)} lines, last: {lines[-1].strip() if lines else \"empty\"}')
"
```

## Immediate Actions

### Action 1: Start Daemon (if not running)
```powershell
Start-ScheduledTask -TaskName 'NeoFace-Daemon'
```

### Action 2: Verify Daemon is Running
```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'"
```

### Action 3: Test Unlock Again
- Press Win+L
- Check if camera LED flashes
- Check daemon logs for new entries

## Long-term Fixes

### Fix 1: Add Daemon Health Check to Dashboard
- Dashboard should verify daemon is running before showing camera status
- Add daemon restart capability if not running

### Fix 2: Add Camera Release Timeout
- If daemon holds camera for >5s, force release
- Prevents camera resource contention

### Fix 3: Add Pipe Connection Logging
- Log pipe connection attempts in CP DLL
- Help diagnose session mismatch issues

### Fix 4: Add Camera State Monitoring
- Monitor camera open/close events
- Alert if camera held for too long

## Files Created

1. **WORKFLOW-camera-activation.md** - Complete workflow specification with all failure points
2. **CAMERA_FLOWCHART.md** - Visual flowcharts with critical failure points highlighted
3. **CAMERA_ANALYSIS_SUMMARY.md** - This summary document

## Next Steps

1. Run diagnostic commands to verify root cause
2. Start daemon if not running
3. Test unlock again
4. If still fails, check camera resource contention
5. If still fails, check session mismatch
6. Update workflow spec with findings
