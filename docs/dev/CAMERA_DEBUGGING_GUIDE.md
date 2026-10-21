# CAMERA ACTIVATION DEBUGGING GUIDE
**Date**: 2026-09-20
**Purpose**: Step-by-step guide to diagnose why camera LED doesn't flash

## Step 1: Check if Daemon is Running

### Command
```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'" | Select-Object ProcessId, Name, CommandLine
```

### Expected Output (If Running)
```
ProcessId  Name     CommandLine
---------  ----     -----------
1234       python.exe  "...face_unlock\daemon_pipe.py"
```

### Expected Output (If Not Running)
```
(no output)
```

### Action if Not Running
```powershell
Start-ScheduledTask -TaskName 'NeoFace-Daemon'
```

## Step 2: Check Scheduled Task Status

### Command
```powershell
Get-ScheduledTask -TaskName 'NeoFace-Daemon' | Select-Object TaskName, State, LastRunTime, NextRunTime
```

### Expected Output
```
TaskName          State      LastRunTime          NextRunTime
--------          -----      -----------          -----------
NeoFace-Daemon    Running    9/20/2026 10:00 AM   9/21/2026 8:00 AM
```

### Possible Issues
- **State: Not Running** → Task failed to start
- **State: Disabled** → Task is disabled
- **LastRunTime: Never** → Task never ran

## Step 3: Check Daemon Logs

### Command
```powershell
Get-Content C:\ProgramData\NeoFace\daemon.log -Tail 50
```

### What to Look For

#### Good Signs
```
10:00:00 creating pipe \\.\pipe\NeoFace
10:00:00 pipe created handle=123 (ACL: user + SYSTEM)
10:00:00 listening
10:00:00 waiting for client...
```

#### Bad Signs
```
FATAL: Cannot create pipe: ...  ← Pipe creation failed
WARNING: no working camera found  ← Camera not detected
scan error: ...  ← Camera read failed
```

#### Recent Activity
```
10:05:00 client connected  ← Someone connected to pipe
10:05:01 read 32 bytes  ← Message received
10:05:02 user=(redacted) total=1.5s scan=1.2s frames=3 faces=1 scores=[0.85] best=0.85 -> OK
10:05:02 disconnected, ready for next client  ← Scan completed
```

## Step 4: Check CP DLL Logs

### Command
```powershell
Get-Content C:\ProgramData\NeoFace\cp.log -Tail 50
```

### What to Look For

#### Good Signs
```
10:05:00 GetSerialization enter
10:05:00 cred read OK
10:05:00 pipe sent VERIFY
10:05:01 pipe read OK rr=2 r0=79 r1=75  ← "OK" response
10:05:01 returning credential  ← Unlock succeeded
```

#### Bad Signs
```
cred read FAIL  ← cred.bin missing or corrupted
pipe open FAIL  ← Daemon not running
pipe read TIMEOUT  ← Daemon didn't respond in 30s
pipe verify FAIL  ← Face not recognized
kerb pack FAIL  ← Kerberos packaging failed
```

## Step 5: Test Camera Directly

### Command
```python
python -c "
import cv2
print('Testing camera...')
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
if cap.isOpened():
    print('Camera OPENED successfully')
    ret, frame = cap.read()
    if ret:
        print(f'Frame captured: {frame.shape}')
    else:
        print('Frame read FAILED')
    cap.release()
else:
    print('Camera FAILED to open')
"
```

### Expected Output (Working)
```
Testing camera...
Camera OPENED successfully
Frame captured: (480, 640, 3)
```

### Expected Output (Not Working)
```
Testing camera...
Camera FAILED to open
```

## Step 6: Test Named Pipe

### Command
```python
python -c "
import win32pipe
print('Testing named pipe...')
try:
    win32pipe.WaitNamedPipe(r'\\\\.\\pipe\\NeoFace', 1000)
    print('Pipe is LISTENING')
except Exception as e:
    print(f'Pipe NOT AVAILABLE: {e}')
"
```

### Expected Output (Daemon Running)
```
Testing named pipe...
Pipe is LISTENING
```

### Expected Output (Daemon Not Running)
```
Testing named pipe...
Pipe NOT AVAILABLE: ...
```

## Step 7: Test Camera Resource Contention

### Command
```python
python -c "
import cv2
print('Checking camera availability...')

# Try camera index 1 (configured)
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
if cap.isOpened():
    print('Camera index 1: FREE')
    cap.release()
else:
    print('Camera index 1: HELD by another process')

# Try camera index 0 (default)
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if cap.isOpened():
    print('Camera index 0: FREE')
    cap.release()
else:
    print('Camera index 0: HELD by another process')
"
```

## Step 8: Check Camera Configuration

### Command
```powershell
Get-Content C:\NeoFace\config.toml | Select-String -Pattern "index|camera" -Context 0,1
```

### Expected Output
```
[camera]
index = 1
```

## Step 9: Test Daemon Camera Detection

### Command
```python
python -c "
import sys
sys.path.insert(0, 'C:\\NeoFace')
from face_unlock.daemon_pipe import _detect_camera, CAMERA_INDEX
print(f'Detected camera index: {CAMERA_INDEX}')
"
```

## Step 10: Manual Camera Test with Daemon

### Command
```python
python -c "
import sys
sys.path.insert(0, 'C:\\NeoFace')
from face_unlock.daemon_pipe import cam, CAMERA_INDEX
import time

print(f'Opening camera index {CAMERA_INDEX}...')
cam.open()
print('Camera opened, waiting 2 seconds...')
time.sleep(2)
ok, frame = cam.read()
print(f'Frame read: {\"OK\" if ok else \"FAILED\"}')
if ok:
    print(f'Frame shape: {frame.shape}')
cam.close()
print('Camera closed')
"
```

## Common Issues and Solutions

### Issue 1: Daemon Not Running
**Symptoms**: Pipe not available, no daemon logs
**Solution**:
```powershell
Start-ScheduledTask -TaskName 'NeoFace-Daemon'
```

### Issue 2: Camera Held by Dashboard
**Symptoms**: Camera index 1 shows "HELD", daemon logs show scan error
**Solution**:
- Wait for dashboard test-scan to complete
- Or stop dashboard: `Stop-Process -Name python -Force`

### Issue 3: Camera Held by Presence Daemon
**Symptoms**: Camera index 1 shows "HELD", presence daemon running
**Solution**:
- Wait for presence daemon tick to complete (45s interval)
- Or stop presence daemon: `Stop-Process -Name python -Force`

### Issue 4: Wrong Camera Index
**Symptoms**: Camera index 1 fails, but index 0 works
**Solution**:
```toml
# Edit config.toml
[camera]
index = 0
```

### Issue 5: Camera Not Detected
**Symptoms**: Daemon logs show "WARNING: no working camera found"
**Solution**:
- Check camera connection
- Try different USB port
- Check Windows Device Manager

### Issue 6: Pipe ACL Issue
**Symptoms**: CP DLL cannot connect to pipe
**Solution**:
- Check daemon logs for ACL errors
- Restart daemon with admin privileges

## Diagnostic Script

Save this as `C:\NeoFace\tools\diagnose_camera.py`:

```python
import subprocess
import cv2
import os
import sys

def run_powershell(cmd):
    try:
        result = subprocess.run(
            ["powershell", "-Command", cmd],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except:
        return "ERROR"

def check_daemon():
    output = run_powershell(
        'Get-CimInstance Win32_Process -Filter "Name LIKE \'python%\' AND CommandLine LIKE \'%daemon%\'" | Select-Object -Expand ProcessId'
    )
    pids = [p.strip() for p in output.split('\n') if p.strip()]
    return len(pids) > 0, pids[0] if pids else None

def check_camera():
    results = {}
    for i in range(4):
        try:
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            results[i] = cap.isOpened()
            cap.release()
        except:
            results[i] = False
    return results

def check_pipe():
    try:
        import win32pipe
        win32pipe.WaitNamedPipe(r'\\\\.\\pipe\\NeoFace', 1000)
        return True
    except:
        return False

def check_config():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.toml')
    if os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                if line.strip().startswith('index') and '=' in line:
                    return int(line.split('=', 1)[1].strip())
    return 0

print("=== NeoFace Camera Diagnostic ===")
print()

# Check daemon
daemon_running, daemon_pid = check_daemon()
print(f"1. Daemon: {'RUNNING (PID: ' + daemon_pid + ')' if daemon_running else 'NOT RUNNING'}")

# Check scheduled task
task_state = run_powershell(
    'Get-ScheduledTask -TaskName \'NeoFace-Daemon\' | Select-Object -Expand State'
)
print(f"2. Scheduled Task: {task_state or 'NOT FOUND'}")

# Check camera
cameras = check_camera()
print(f"3. Camera Availability:")
for idx, available in cameras.items():
    status = "FREE" if available else "HELD/UNAVAILABLE"
    print(f"   Index {idx}: {status}")

# Check pipe
pipe_available = check_pipe()
print(f"4. Named Pipe: {'LISTENING' if pipe_available else 'NOT AVAILABLE'}")

# Check config
config_index = check_config()
print(f"5. Config Camera Index: {config_index}")

# Check logs
daemon_log = r'C:\ProgramData\NeoFace\daemon.log'
cp_log = r'C:\ProgramData\NeoFace\cp.log'

if os.path.exists(daemon_log):
    with open(daemon_log) as f:
        lines = f.readlines()
    print(f"6. Daemon Log: {len(lines)} lines")
    if lines:
        print(f"   Last: {lines[-1].strip()}")
else:
    print("6. Daemon Log: NOT FOUND")

if os.path.exists(cp_log):
    with open(cp_log) as f:
        lines = f.readlines()
    print(f"7. CP Log: {len(lines)} lines")
    if lines:
        print(f"   Last: {lines[-1].strip()}")
else:
    print("7. CP Log: NOT FOUND")

print()
print("=== Recommendations ===")

if not daemon_running:
    print("⚠️  Daemon is NOT running. Start it with:")
    print("   Start-ScheduledTask -TaskName 'NeoFace-Daemon'")

if not pipe_available:
    print("⚠️  Named pipe is NOT available. Daemon may not be running.")

if not any(cameras.values()):
    print("⚠️  No cameras are available. Check camera connection.")

if daemon_running and pipe_available and any(cameras.values()):
    print("✅ All systems appear healthy. Test unlock with Win+L.")
```

## Next Steps

1. Run diagnostic script: `python C:\NeoFace\tools\diagnose_camera.py`
2. Based on output, take appropriate action
3. Test unlock with Win+L
4. Check if camera LED flashes
5. If still fails, check daemon logs after unlock attempt
