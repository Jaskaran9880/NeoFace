# WORKFLOW: Camera Activation Flow (NeoFace)
**Version**: 0.1
**Date**: 2026-09-20
**Author**: Workflow Architect
**Status**: Draft
**Problem**: Camera LED does NOT flash when user tries to use face unlock via CP DLL. Camera works when tested directly with `cv2.VideoCapture(1, cv2.CAP_DSHOW)`.

## Overview
This document maps every code path that opens the camera in the NeoFace system. The camera is a shared resource accessed by multiple components: the daemon (daemon_pipe.py), the dashboard (dashboard.py), the enrollment tool (tools/enroll_fast.py), and the presence daemon (presence_daemon.py). Understanding these flows is critical for diagnosing why the camera LED does not activate during lock screen unlock.

## Actors
| Actor | Role in this workflow |
|---|---|
| CP DLL (credential.cpp) | Runs as SYSTEM in Session 0, requests face verification via named pipe |
| Daemon (daemon_pipe.py) | Runs in user session, owns the named pipe, opens camera for face verification |
| Dashboard (dashboard.py) | Runs in user session, opens camera for test scans |
| Enrollment Tool (enroll_fast.py) | Runs in user session, opens camera for face enrollment |
| Presence Daemon (presence_daemon.py) | Runs in user session, periodically opens camera to detect presence |
| Camera Hardware | Shared resource, exclusive access required, DSHOW backend |

## Prerequisites
- Camera hardware connected and functional (verified with direct cv2.VideoCapture test)
- Models present: models/yunet.onnx, models/sface.onnx
- Gallery file exists: C:\ProgramData\NeoFace\faces_fast.dat
- Password vault exists: C:\ProgramData\NeoFace\cred.bin
- Daemon registered as scheduled task: NeoFace-Daemon
- Named pipe ACL allows SYSTEM account access

## Flow 1: Lock Screen (Win+L) - Camera Activation Path

### STEP 1: User Presses Win+L
**Actor**: Windows OS
**Action**: Locks workstation, displays lock screen, loads credential providers
**Timeout**: N/A
**Input**: User input
**Output on SUCCESS**: Lock screen displayed with NeoFace credential tile
**Output on FAILURE**: N/A

**Observable states during this step**:
- Customer sees: Windows lock screen with NeoFace tile
- Operator sees: N/A
- Database: N/A
- Logs: N/A

### STEP 2: CP DLL Runs as SYSTEM in Session 0
**Actor**: Windows Credential Provider Framework
**Action**: Loads FaceUnlockCP.dll, creates NeoFaceProvider instance
**Timeout**: N/A
**Input**: DLL registration in registry
**Output on SUCCESS**: NeoFaceProvider::SetUsageScenario() called with CPUS_UNLOCK_WORKSTATION
**Output on FAILURE**:
  - `FAILURE(dll_not_found)`: DLL not registered -> [recovery: show error, no camera activation]
  - `FAILURE(wrong_session)`: DLL loaded in wrong session -> [recovery: DLL fails to load]

**Observable states during this step**:
- Customer sees: NeoFace tile appears on lock screen
- Operator sees: N/A
- Database: N/A
- Logs: cp.log entry "GetSerialization enter" (when triggered)

### STEP 3: CP DLL Reads cred.bin
**Actor**: NeoFaceCredential::GetSerialization()
**Action**: Calls ReadMachineCred() to read C:\ProgramData\NeoFace\cred.bin
**Timeout**: 5s (file I/O)
**Input**: cred.bin file
**Output on SUCCESS**: Domain, username, password extracted
**Output on FAILURE**:
  - `FAILURE(file_not_found)`: cred.bin missing -> [recovery: show "NeoFace not set up", no camera activation]
  - `FAILURE(decryption_failed)`: DPAPI decryption fails -> [recovery: show error, no camera activation]

**Observable states during this step**:
- Customer sees: "NeoFace not set up - run set_password_machine (admin) first"
- Operator sees: cp.log entry "cred read FAIL"
- Database: N/A
- Logs: cp.log entry "cred read OK" or "cred read FAIL"

### STEP 4: CP DLL Calls PipeVerify()
**Actor**: NeoFaceCredential::GetSerialization()
**Action**: Calls PipeVerify(user) to connect to named pipe
**Timeout**: 30s (overlapped read timeout)
**Input**: Username string
**Output on SUCCESS**: Pipe connection established, "VERIFY username" sent
**Output on FAILURE**:
  - `FAILURE(pipe_open_failed)`: Cannot open pipe after 5 retries -> [recovery: show "Face not recognized", no camera activation]
  - `FAILURE(pipe_write_failed)`: WriteFile fails -> [recovery: close handle, show error]
  - `FAILURE(pipe_read_timeout)`: WaitForSingleObject times out after 30s -> [recovery: CancelIo, show error]

**Observable states during this step**:
- Customer sees: "Face not recognized - try again or use PIN" (on failure)
- Operator sees: cp.log entry "pipe open FAIL" or "pipe read TIMEOUT"
- Database: N/A
- Logs: cp.log entries for pipe operations

**CRITICAL TIMING NOTE**: PipeVerify() uses overlapped I/O with 30s timeout. If daemon doesn't respond within 30s, CP DLL gives up.

### STEP 5: Daemon Receives "VERIFY" Message
**Actor**: daemon_pipe.py main loop
**Action**: ConnectNamedPipe(), ReadFile(), parse message
**Timeout**: Infinite (blocking on ConnectNamedPipe)
**Input**: Pipe message "VERIFY username"
**Output on SUCCESS**: Message parsed, user extracted
**Output on FAILURE**:
  - `FAILURE(message_too_long)`: >8192 bytes -> [recovery: send "FAIL", disconnect]
  - `FAILURE(invalid_format)`: Not "VERIFY user" -> [recovery: send "FAIL", disconnect]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: daemon.log entry "client connected"
- Database: N/A
- Logs: daemon.log entries

### STEP 6: Daemon Opens Camera
**Actor**: Cam class in daemon_pipe.py
**Action**: cam.open() called at line 233
**Timeout**: 1s warmup + 5 frame reads (~0.5s)
**Input**: CAMERA_INDEX from config (default 0, but config says 1)
**Output on SUCCESS**: Camera opened, frames available
**Output on FAILURE**:
  - `FAILURE(camera_busy)`: Camera reserved by another app -> [recovery: exception caught at line 267, send "FAIL"]
  - `FAILURE(camera_not_found)`: No working camera -> [recovery: exception caught at line 267, send "FAIL"]
  - `FAILURE(permission_denied)`: Camera access denied -> [recovery: exception caught at line 267, send "FAIL"]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: daemon.log entry with timestamp before scan
- Database: N/A
- Logs: daemon.log entry "scan error: ..." on failure

**CRITICAL FAILURE POINT**: If camera is held by dashboard or presence daemon, this step fails.

### STEP 7: Daemon Captures Frames
**Actor**: Cam._grab() thread + Cam.read()
**Action**: Read FRAMES (3) frames from camera
**Timeout**: 3 frames * (1/30 fps) = ~0.1s + processing time
**Input**: Camera stream
**Output on SUCCESS**: Frames captured and processed
**Output on FAILURE**:
  - `FAILURE(frame_read_error)`: cam.read() returns False -> [recovery: skip frame, continue]
  - `FAILURE(no_face_detected)`: engine.embed() returns None -> [recovery: skip frame, continue]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: daemon.log entry with frame/face counts
- Database: N/A
- Logs: daemon.log entries

### STEP 8: Daemon Processes Face Recognition
**Actor**: FastEngine.embed(), SpoofGate.real_score(), cosine_score()
**Action**: Detect face, extract embedding, compare against gallery
**Timeout**: ~100ms per frame
**Input**: Captured frames
**Output on SUCCESS**: Score computed, match determined
**Output on FAILURE**:
  - `FAILURE(spoof_detected)`: real_score < threshold -> [recovery: skip frame, continue]
  - `FAILURE(no_match)`: best score < THRESHOLD -> [recovery: send "FAIL"]
  - `FAILURE(insufficient_hits)`: Not enough frames with score >= THRESHOLD -> [recovery: send "FAIL"]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: daemon.log entry with scores and result
- Database: N/A
- Logs: daemon.log entries

### STEP 9: Daemon Sends Response
**Actor**: daemon_pipe.py main loop
**Action**: WriteFile() sends "OK" or "FAIL"
**Timeout**: N/A
**Input**: Scan result
**Output on SUCCESS**: Response sent to CP DLL
**Output on FAILURE**:
  - `FAILURE(write_error)`: WriteFile fails -> [recovery: exception caught, close pipe]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: daemon.log entry "disconnected, ready for next client"
- Database: N/A
- Logs: daemon.log entries

### STEP 10: CP DLL Receives Response
**Actor**: PipeVerify() in credential.cpp
**Action**: ReadFile() with overlapped I/O
**Timeout**: 30s
**Input**: Pipe response "OK" or "FAIL"
**Output on SUCCESS**: Response parsed
**Output on FAILURE**:
  - `FAILURE(read_error)`: ReadFile fails -> [recovery: return false]
  - `FAILURE(timeout)`: WaitForSingleObject times out -> [recovery: CancelIo, return false]

**Observable states during this step**:
- Customer sees: N/A (waiting on lock screen)
- Operator sees: cp.log entry "pipe read OK" or "pipe read FAIL"
- Database: N/A
- Logs: cp.log entries

### STEP 11: CP DLL Unlocks or Shows Error
**Actor**: NeoFaceCredential::GetSerialization()
**Action**: If PipeVerify() returns true, pack credentials and return CPGSR_RETURN_CREDENTIAL_FINISHED
**Timeout**: N/A
**Input**: PipeVerify() result
**Output on SUCCESS**: Credentials packed, unlock succeeds
**Output on FAILURE**:
  - `FAILURE(face_not_recognized)`: PipeVerify() returns false -> [recovery: show "Face not recognized - try again or use PIN"]
  - `FAILURE(kerberos_pack_failed)`: NeoPackUnlockLogon() fails -> [recovery: show "NeoFace logon packaging failed - use PIN"]

**Observable states during this step**:
- Customer sees: Unlocks to desktop (success) or error message (failure)
- Operator sees: cp.log entry "returning credential" or "kerb pack FAIL"
- Database: N/A
- Logs: cp.log entries

## Flow 2: Dashboard Test Scan - Camera Activation Path

### STEP 1: User Clicks "Test" Tab
**Actor**: Dashboard UI
**Action**: Triggers test-scan API call
**Timeout**: N/A
**Input**: User click
**Output on SUCCESS**: API request sent
**Output on FAILURE**: N/A

### STEP 2: Dashboard Receives API Request
**Actor**: dashboard.py api_test_scan()
**Action**: Validates API key, processes request
**Timeout**: 120s (enrollment timeout)
**Input**: POST /api/test-scan?key=...
**Output on SUCCESS**: Request accepted
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Invalid API key -> [recovery: return 401]
  - `FAILURE(rate_limited)`: Too many failed attempts -> [recovery: return 429]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: Flask request logs

### STEP 3: Dashboard Gets Camera Index
**Actor**: dashboard.py _get_camera_index()
**Action**: Reads config.toml, auto-detects working camera
**Timeout**: 2s (0.5s per camera index * 4)
**Input**: config.toml
**Output on SUCCESS**: Camera index (cached after first success)
**Output on FAILURE**:
  - `FAILURE(config_read_error)`: Cannot read config -> [recovery: use default index 0]
  - `FAILURE(no_working_camera)`: All cameras fail -> [recovery: return index 0]

**Observable states during this step**:
- Customer sees: N/A
- Operator sees: N/A
- Database: N/A
- Logs: N/A

**CRITICAL ISSUE**: Dashboard auto-detection opens and releases camera for each index. If daemon holds camera, this will fail.

### STEP 4: Dashboard Opens Camera
**Actor**: dashboard.py api_test_scan()
**Action**: cv2.VideoCapture(index, cv2.CAP_DSHOW)
**Timeout**: 1.5s warmup + 5 frame reads (~0.5s)
**Input**: Camera index
**Output on SUCCESS**: Camera opened
**Output on FAILURE**:
  - `FAILURE(camera_not_available)`: cam.isOpened() returns False -> [recovery: return 500 "Camera not available"]
  - `FAILURE(camera_busy)`: Camera reserved by daemon -> [recovery: return 500]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: N/A

**CRITICAL FAILURE POINT**: If daemon holds camera, dashboard cannot open it.

### STEP 5: Dashboard Captures and Processes Frames
**Actor**: dashboard.py api_test_scan()
**Action**: Read 3 frames, process with FastEngine
**Timeout**: ~1s
**Input**: Camera stream
**Output on SUCCESS**: Frames processed
**Output on FAILURE**:
  - `FAILURE(frame_read_error)`: cam.read() returns False -> [recovery: skip frame, continue]
  - `FAILURE(no_face_detected)`: engine.embed() returns None -> [recovery: skip frame, continue]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: N/A

### STEP 6: Dashboard Returns Result
**Actor**: dashboard.py api_test_scan()
**Action**: Release camera, return JSON response
**Timeout**: N/A
**Input**: Processed frames
**Output on SUCCESS**: Result returned
**Output on FAILURE**:
  - `FAILURE(exception)`: Any error -> [recovery: return 500 with error message]

**Observable states during this step**:
- Customer sees: Test result (OK/FAIL with scores)
- Operator sees: N/A
- Database: N/A
- Logs: Flask request logs

## Flow 3: Dashboard Enrollment - Camera Activation Path

### STEP 1: User Triggers Enrollment
**Actor**: Dashboard UI
**Action**: Calls /api/enroll endpoint
**Timeout**: N/A
**Input**: User click
**Output on SUCCESS**: API request sent
**Output on FAILURE**: N/A

### STEP 2: Dashboard Spawns Enrollment Process
**Actor**: dashboard.py api_enroll()
**Action**: subprocess.run([sys.executable, "tools/enroll_fast.py"])
**Timeout**: 120s
**Input**: POST /api/enroll?key=...
**Output on SUCCESS**: Process spawned
**Output on FAILURE**:
  - `FAILURE(unauthorized)`: Invalid API key -> [recovery: return 401]
  - `FAILURE(timeout)`: Process exceeds 120s -> [recovery: return 500]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: N/A

### STEP 3: Enrollment Tool Opens Camera
**Actor**: tools/enroll_fast.py
**Action**: cv2.VideoCapture(index, cv2.CAP_DSHOW)
**Timeout**: 0.5s
**Input**: Camera index (from config or auto-detect)
**Output on SUCCESS**: Camera opened
**Output on FAILURE**:
  - `FAILURE(camera_busy)`: Camera reserved by daemon -> [recovery: exception, enrollment fails]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: N/A

**CRITICAL NOTE**: Enrollment tool does NOT explicitly open camera in enroll_fast.py. It processes photos from disk, not live camera feed. Camera is only opened if video files are processed.

### STEP 4: Enrollment Tool Processes Photos
**Actor**: tools/enroll_fast.py
**Action**: Load images from photos/ directory, embed faces, save to gallery
**Timeout**: 120s
**Input**: Photo files
**Output on SUCCESS**: Face embeddings saved
**Output on FAILURE**:
  - `FAILURE(no_face)`: No face detected in photo -> [recovery: skip photo, continue]
  - `FAILURE(gallery_save_error)`: Cannot write gallery -> [recovery: exception]

**Observable states during this step**:
- Customer sees: Loading spinner
- Operator sees: N/A
- Database: N/A
- Logs: N/A

## Potential Failure Points and Blocking Issues

### 1. Camera Resource Contention
**Issue**: Camera is exclusive resource. Only one process can hold it at a time.
**Who can block**:
- Daemon (daemon_pipe.py) holds camera during scan (~1-2s per scan)
- Dashboard test-scan holds camera during test (~2-5s)
- Presence daemon holds camera during tick (~0.5s every 45s)

**Evidence from code**:
- daemon_pipe.py line 114: `if self.cap and self.cap.isOpened(): return` (early return if already open)
- daemon_pipe.py line 274: `cam.close()` in finally block (camera released after each scan)
- dashboard.py line 201: `cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)` (opens camera)
- presence_daemon.py line 57: `cap = cv.VideoCapture(CAMERA_INDEX, cv.CAP_DSHOW)` (opens camera)

**Race condition**: If dashboard test-scan is running when lock screen triggers, daemon cannot open camera.

### 2. Session Mismatch
**Issue**: CP DLL runs as SYSTEM in Session 0, daemon runs in user session.
**Evidence**:
- daemon_pipe.py scheduled task runs as Interactive user (dashboard.py line 647)
- CP DLL is loaded by Windows in Session 0 (SYSTEM context)
- Named pipe ACL allows both user and SYSTEM (daemon_pipe.py lines 172-173)

**Potential problem**: If daemon is not running in the correct session, pipe connection may fail.

### 3. Camera Index Mismatch
**Issue**: Different components may use different camera indices.
**Evidence**:
- config.toml line 15: `index = 1` (config says camera 1)
- daemon_pipe.py line 33: `CAMERA_INDEX = 0` (default 0)
- daemon_pipe.py line 45: Reads config, sets CAMERA_INDEX to 1
- dashboard.py line 110: Reads config, sets idx to 1
- presence_daemon.py line 17: Reads config, sets CAMERA_INDEX to 1

**Potential problem**: Auto-detection may override config if camera 1 fails.

### 4. Daemon Holding Camera
**Issue**: Daemon may hold camera open if scan is slow or stuck.
**Evidence**:
- daemon_pipe.py line 114: Early return if camera already open
- daemon_pipe.py line 131-140: _grab() thread continuously reads frames
- daemon_pipe.py line 149: close() sets running=False and joins thread

**Potential problem**: If _grab() thread is stuck, camera remains held.

### 5. Dashboard Status Check Assumes Camera State
**Issue**: Dashboard status API assumes camera state based on daemon running.
**Evidence**:
- dashboard.py line 198: `if not daemon_running:` then check camera availability
- dashboard.py line 209: `status["camera"] = {"available": True, "name": "in use by daemon"}`

**Potential problem**: If daemon is running but not holding camera, dashboard incorrectly reports camera as "in use by daemon".

### 6. Warmup Timing Issues
**Issue**: Camera needs time to initialize after opening.
**Evidence**:
- daemon_pipe.py line 125: `time.sleep(1)` after opening camera
- daemon_pipe.py lines 126-128: Read 5 frames for warmup
- dashboard.py line 549: `time.sleep(1.5)` after opening camera
- dashboard.py lines 550-552: Read 5 frames for warmup

**Potential problem**: If warmup is insufficient, first frames may be black/corrupted.

## State Transitions

```
[Camera Free] -> (dashboard opens camera) -> [Camera Held by Dashboard]
[Camera Free] -> (daemon opens camera) -> [Camera Held by Daemon]
[Camera Free] -> (presence daemon opens camera) -> [Camera Held by Presence]
[Camera Held by Dashboard] -> (dashboard releases camera) -> [Camera Free]
[Camera Held by Daemon] -> (daemon releases camera) -> [Camera Free]
[Camera Held by Presence] -> (presence daemon releases camera) -> [Camera Free]
[Camera Free] -> (another app opens camera) -> [Camera Held by Other]
[Camera Held by Other] -> (CP DLL tries to open) -> [Camera Open Failed]
```

## Handoff Contracts

### CP DLL -> Daemon (Named Pipe)
**Endpoint**: `\\.\pipe\NeoFace`
**Payload**:
```c
char req[256]; // "VERIFY username"
```
**Success response**:
```c
char resp[16]; // "OK" or "FAIL"
```
**Failure response**:
```c
char resp[16]; // "FAIL"
```
**Timeout**: 30s (overlapped read)
**On FAILURE**: CP DLL shows "Face not recognized - try again or use PIN"

### Dashboard -> Camera (OpenCV)
**Endpoint**: cv2.VideoCapture(index, cv2.CAP_DSHOW)
**Payload**: Camera index, FOURCC, resolution, FPS, buffer size
**Success response**: cam.isOpened() returns True
**Failure response**: cam.isOpened() returns False
**Timeout**: 1.5s warmup + 5 frame reads
**On FAILURE**: Return 500 "Camera not available"

## Cleanup Inventory
| Resource | Created at step | Destroyed by | Destroy method |
|---|---|---|---|
| Camera handle (daemon) | Flow 1 Step 6 | Flow 1 Step 9 (finally block) | cam.close() |
| Camera handle (dashboard) | Flow 2 Step 4 | Flow 2 Step 6 | cam.release() |
| Camera handle (presence) | Flow 3 Step 3 | Flow 3 Step 3 (after read) | cap.release() |
| Named pipe connection | Flow 1 Step 5 | Flow 1 Step 9 | DisconnectNamedPipe() |

## Reality Checker Findings

| # | Finding | Severity | Spec section affected | Resolution |
|---|---|---|---|---|
| RC-1 | Daemon Cam.open() has early return if camera already open (line 114) | High | Flow 1 Step 6 | If camera stuck open from previous scan, next scan won't reopen |
| RC-2 | Dashboard _get_camera_index() opens/releases camera for each index during detection | Medium | Flow 2 Step 3 | May fail if daemon holds camera during detection |
| RC-3 | Dashboard status API incorrectly reports camera "in use by daemon" when daemon running but not holding camera | Low | Flow 2 Step 2 | Status check is inaccurate |
| RC-4 | Enrollment tool (enroll_fast.py) processes photos from disk, not live camera | Medium | Flow 3 | Camera not opened during enrollment unless video files processed |
| RC-5 | Daemon _grab() thread may hang if camera read fails repeatedly | High | Flow 1 Step 7 | No timeout on _grab() loop, camera may stay held |
| RC-6 | Config says camera index 1, but daemon default is 0 | Medium | Flow 1 Step 6 | Config override may fail if _read_config() exception |
| RC-7 | Dashboard test-scan resizes to 640px for YuNet, but daemon resizes to 320px | Low | Flow 2 Step 5 | Inconsistent processing may affect accuracy |
| RC-8 | CP DLL pipe retry is 5 attempts with 2s sleep (10s total), but read timeout is 30s | Medium | Flow 1 Step 4 | Potential mismatch in timeout expectations |

## Test Cases

| Test | Trigger | Expected behavior |
|---|---|---|
| TC-01: Happy path lock screen | Win+L, daemon running, camera free | Camera LED flashes, face recognized, unlock succeeds |
| TC-02: Dashboard blocks daemon | Dashboard test-scan running, Win+L triggered | Daemon cannot open camera, unlock fails |
| TC-03: Daemon blocks dashboard | Daemon scanning, dashboard test-scan triggered | Dashboard cannot open camera, returns error |
| TC-04: Camera index mismatch | Config index=1, camera 1 disconnected | Auto-detection finds working camera |
| TC-05: Daemon not running | Win+L, daemon stopped | CP DLL cannot connect to pipe, unlock fails |
| TC-06: Camera warmup insufficient | Fast scan after camera open | First frames may be black, accuracy affected |
| TC-07: Presence daemon blocks | Presence tick running, Win+L triggered | Daemon cannot open camera |
| TC-08: Multiple dashboard users | Two browser tabs open test-scan | Second request may fail if first holds camera |

## Assumptions
| # | Assumption | Where verified | Risk if wrong |
|---|---|---|---|
| A1 | Camera hardware works with cv2.VideoCapture(1, cv2.CAP_DSHOW) | User report | All camera flows fail |
| A2 | Daemon is running in user session, not SYSTEM | Scheduled task config (dashboard.py line 647) | Pipe connection fails |
| A3 | Named pipe ACL allows SYSTEM account | daemon_pipe.py lines 172-173 | CP DLL cannot connect |
| A4 | Only one process can hold camera at a time | OpenCV DSHOW behavior | Race conditions |
| A5 | Camera needs ~1s warmup after opening | daemon_pipe.py line 125, dashboard.py line 549 | First frames corrupted |
| A6 | Config.toml camera index is correct | config.toml line 15 | Wrong camera opened |

## Open Questions
- Is the daemon currently running? (Check with Get-CimInstance Win32_Process)
- Is the daemon holding the camera? (Check Cam class state - cap.isOpened())
- Is there a camera reservation conflict? (Check if dashboard/presence daemon holds camera)
- Does the scheduled task start daemon in correct session? (Check task principal)
- Is the camera index in config.toml correct? (Test with direct cv2.VideoCapture)

## Spec vs Reality Audit Log
| Date | Finding | Action taken |
|---|---|---|
| 2026-09-20 | Initial spec created | Mapped all camera activation flows |
| 2026-09-20 | Found daemon Cam.open() early return bug | Added to Reality Checker Findings |
| 2026-09-20 | Found enrollment tool doesn't use live camera | Clarified Flow 3 behavior |
| 2026-09-20 | Found dashboard status check inaccuracy | Added to Reality Checker Findings |
