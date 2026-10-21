# CAMERA ACTIVATION FLOWCHART - NeoFace
**Date**: 2026-09-20
**Problem**: Camera LED does NOT flash during face unlock

## Visual Flow: Lock Screen (Win+L)

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCK SCREEN ACTIVATION                       │
└─────────────────────────────────────────────────────────────────┘

[User presses Win+L]
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Windows loads credential providers                     │
│ File: credential.cpp (NeoFaceProvider)                         │
│ Session: SYSTEM (Session 0)                                    │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: NeoFaceCredential::GetSerialization()                  │
│ File: credential.cpp line 150                                  │
│ Action: ReadMachineCred() reads cred.bin                       │
│ File: C:\ProgramData\NeoFace\cred.bin                          │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → "NeoFace not set up - run set_password_machine"
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: PipeVerify() called                                    │
│ File: credential.cpp line 94                                   │
│ Action: Connect to \\.\pipe\NeoFace                            │
│ Retry: 5 attempts, 2s sleep each (10s total)                  │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → "Face not recognized - try again or use PIN"
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Send "VERIFY username" to pipe                         │
│ File: credential.cpp line 114 (WriteFile)                      │
│ Timeout: N/A (write is synchronous)                            │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Wait for response (30s timeout)                        │
│ File: credential.cpp line 129 (WaitForSingleObject)            │
│ Action: Overlapped read with 30s timeout                       │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ TIMEOUT → "Face not recognized - try again or use PIN"
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Daemon receives message                                │
│ File: daemon_pipe.py line 200 (ConnectNamedPipe)               │
│ File: daemon_pipe.py line 203 (ReadFile)                       │
│ Action: Parse "VERIFY username" message                        │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Send "FAIL", disconnect
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: Daemon opens camera                                    │
│ File: daemon_pipe.py line 233 (cam.open())                     │
│ File: daemon_pipe.py line 116 (cv2.VideoCapture)               │
│ Camera Index: From config.toml (line 15: index = 1)           │
│ Backend: cv2.CAP_DSHOW                                         │
│ Warmup: 1s sleep + 5 frame reads                              │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Exception caught, send "FAIL"
        │         Camera LED does NOT flash ❌
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 8: Daemon captures frames                                 │
│ File: daemon_pipe.py line 239 (for _ in range(FRAMES))         │
│ File: daemon_pipe.py line 130 (_grab thread)                   │
│ Action: Read 3 frames from camera                              │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Skip frame, continue
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 9: Daemon processes face                                  │
│ File: daemon_pipe.py line 247 (engine.embed)                   │
│ File: fast.py line 17 (FastEngine.embed)                       │
│ Action: Detect face, extract embedding, match against gallery  │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Skip frame, continue
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 10: Daemon sends response                                 │
│ File: daemon_pipe.py line 266 (WriteFile)                      │
│ Action: Send "OK" or "FAIL"                                    │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 11: CP DLL receives response                              │
│ File: credential.cpp line 147 (check resp)                     │
│ Action: If "OK", pack credentials and unlock                   │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → "Face not recognized - try again or use PIN"
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 12: Unlock succeeds                                       │
│ File: credential.cpp line 193 (return CPGSR_RETURN_...)        │
│ Action: NeoPackUnlockLogon() packs domain/user/pass            │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   [UNLOCKED]
```

## Visual Flow: Dashboard Test Scan

```
┌─────────────────────────────────────────────────────────────────┐
│                    DASHBOARD TEST SCAN                          │
└─────────────────────────────────────────────────────────────────┘

[User clicks "Test" tab]
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Dashboard receives API request                         │
│ File: dashboard.py line 522 (api_test_scan)                    │
│ Endpoint: POST /api/test-scan?key=...                          │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → 401 Unauthorized
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Get camera index                                       │
│ File: dashboard.py line 105 (_get_camera_index)                │
│ Action: Read config.toml, auto-detect if needed                │
│ Cache: Result cached in _camera_index_cache                    │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Use default index 0
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Open camera                                            │
│ File: dashboard.py line 540 (cv2.VideoCapture)                 │
│ Camera Index: From _get_camera_index()                         │
│ Backend: cv2.CAP_DSHOW                                         │
│ Warmup: 1.5s sleep + 5 frame reads                            │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → "Camera not available" (500 error)
        │         Camera LED does NOT flash ❌
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Capture frames                                         │
│ File: dashboard.py line 557 (for _ in range(3))                │
│ Action: Read 3 frames from camera                              │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Skip frame, continue
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Process face                                           │
│ File: dashboard.py line 565 (engine.embed)                     │
│ File: fast.py line 17 (FastEngine.embed)                       │
│ Action: Detect face, extract embedding, match against gallery  │
└─────────────────────────────────────────────────────────────────┘
        │
        ├─ FAIL → Skip frame, continue
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Return result                                          │
│ File: dashboard.py line 575 (cam.release())                    │
│ File: dashboard.py line 589 (return jsonify)                   │
│ Action: Release camera, return JSON response                   │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   [RESULT: OK/FAIL with scores]
```

## CRITICAL FAILURE POINTS

### ❌ FAILURE POINT 1: Camera Resource Contention
**Location**: daemon_pipe.py line 114, dashboard.py line 540, presence_daemon.py line 57
**Problem**: Only one process can hold camera at a time
**Scenario**: Dashboard test-scan running when Win+L triggered
**Evidence**:
```python
# daemon_pipe.py line 114 - Early return if camera already open
def open(self):
    if self.cap and self.cap.isOpened():
        return  # Camera already held by previous scan
```

### ❌ FAILURE POINT 2: Daemon Not Running
**Location**: daemon_pipe.py line 200 (ConnectNamedPipe)
**Problem**: If daemon stopped, pipe has no listener
**Scenario**: Scheduled task failed to start daemon
**Evidence**:
```python
# daemon_pipe.py line 200 - Blocking wait for client
win32pipe.ConnectNamedPipe(pipe, None)  # Blocks until client connects
```

### ❌ FAILURE POINT 3: Camera Index Mismatch
**Location**: config.toml line 15, daemon_pipe.py line 33
**Problem**: Config says index=1, but daemon default is 0
**Scenario**: Config read fails, daemon uses wrong index
**Evidence**:
```python
# daemon_pipe.py line 33 - Default camera index
CAMERA_INDEX = 0  # Default
# daemon_pipe.py line 45 - Override from config
if k == "index": CAMERA_INDEX = int(v)  # Should be 1
```

### ❌ FAILURE POINT 4: Camera Warmup Insufficient
**Location**: daemon_pipe.py line 125, dashboard.py line 549
**Problem**: Camera needs time to initialize after opening
**Scenario**: First frames may be black/corrupted
**Evidence**:
```python
# daemon_pipe.py line 125-128 - Warmup sequence
time.sleep(1)  # Wait 1 second
for _ in range(5):
    self.cap.read()  # Read 5 frames to warm up
time.sleep(0.05)  # Wait 50ms more
```

### ❌ FAILURE POINT 5: Session Mismatch
**Location**: credential.cpp (Session 0), daemon_pipe.py (user session)
**Problem**: CP DLL runs as SYSTEM in Session 0, daemon runs in user session
**Scenario**: Named pipe connection may fail across sessions
**Evidence**:
```cpp
// credential.cpp line 102 - CP DLL connects to pipe
h = CreateFileW(L"\\\\.\\pipe\\NeoFace", GENERIC_READ | GENERIC_WRITE,
    0, NULL, OPEN_EXISTING, 0, NULL);
```

### ❌ FAILURE POINT 6: Pipe Timeout Mismatch
**Location**: credential.cpp line 129, daemon_pipe.py line 200
**Problem**: CP DLL waits 30s, daemon may take longer or shorter
**Scenario**: Daemon scan takes >30s, CP DLL gives up
**Evidence**:
```cpp
// credential.cpp line 129 - 30 second timeout
DWORD w = WaitForSingleObject(ov.hEvent, 30000);
```

### ❌ FAILURE POINT 7: Camera Held by _grab() Thread
**Location**: daemon_pipe.py line 130-140
**Problem**: _grab() thread continuously reads frames, may hang
**Scenario**: Camera read fails repeatedly, thread stuck
**Evidence**:
```python
# daemon_pipe.py line 130-140 - Continuous frame reading
def _grab(self):
    while self.running:
        cap = self.cap
        if not cap or not cap.isOpened():
            break
        ok, f = cap.read()
        if ok:
            with self.lock:
                self.latest = f
        else:
            time.sleep(0.01)  # May loop forever if camera broken
```

### ❌ FAILURE POINT 8: Dashboard Status Check Inaccuracy
**Location**: dashboard.py line 198-209
**Problem**: Dashboard assumes camera state based on daemon running
**Scenario**: Daemon running but not holding camera, dashboard reports "in use by daemon"
**Evidence**:
```python
# dashboard.py line 198-209 - Status check
if not daemon_running:
    # Check camera availability
    cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
    if cap.isOpened():
        status["camera"]["available"] = True
else:
    status["camera"] = {"available": True, "name": "in use by daemon"}  # WRONG!
```

## DIAGNOSTIC CHECKLIST

### 1. Check if Daemon is Running
```powershell
Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'"
```

### 2. Check if Camera is Held by Another Process
```python
import cv2
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
if cap.isOpened():
    print("Camera is FREE")
    cap.release()
else:
    print("Camera is HELD by another process")
```

### 3. Check Camera Index
```powershell
# Check config.toml
Get-Content C:\NeoFace\config.toml | Select-String "index"
```

### 4. Check Daemon Logs
```powershell
Get-Content C:\ProgramData\NeoFace\daemon.log -Tail 50
```

### 5. Check CP DLL Logs
```powershell
Get-Content C:\ProgramData\NeoFace\cp.log -Tail 50
```

### 6. Test Camera Directly
```python
import cv2
cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
ret, frame = cap.read()
if ret:
    print(f"Camera works! Frame size: {frame.shape}")
else:
    print("Camera read FAILED")
cap.release()
```

### 7. Test Named Pipe
```python
import win32pipe
try:
    win32pipe.WaitNamedPipe(r"\\.\pipe\NeoFace", 1000)
    print("Pipe is listening")
except:
    print("Pipe not available (daemon may be stopped)")
```

## ROOT CAUSE HYPOTHESIS

Based on the flowchart analysis, the most likely root cause is:

**The daemon is NOT running when Win+L is triggered.**

Why?
1. Camera works when tested directly (`cv2.VideoCapture(1, cv2.CAP_DSHOW)` works)
2. Camera LED does NOT flash during unlock (camera never opened)
3. If daemon were running, it would open camera when CP DLL connects to pipe
4. If daemon not running, CP DLL cannot connect to pipe, unlock fails immediately

**Next steps to verify**:
1. Check if daemon is running: `Get-CimInstance Win32_Process -Filter "Name LIKE 'python%' AND CommandLine LIKE '%daemon%'"`
2. Check scheduled task status: `Get-ScheduledTask -TaskName 'NeoFace-Daemon'`
3. Check daemon logs for recent activity: `Get-Content C:\ProgramData\NeoFace\daemon.log -Tail 20`
