# CAMERA OPEN LOCATIONS - Quick Reference
**Date**: 2026-09-20
**Purpose**: Exact file and line numbers where camera is opened

## Flow 1: Lock Screen (Win+L)

### Primary Camera Open Location
**File**: `C:\NeoFace\face_unlock\daemon_pipe.py`
**Line**: 116
**Code**:
```python
self.cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)
```
**Called by**: `cam.open()` at line 233
**Camera Index**: From config.toml (line 15: `index = 1`)
**Backend**: `cv2.CAP_DSHOW`
**Warmup**: 1s sleep + 5 frame reads (lines 125-128)

### Secondary Camera Open (Auto-Detection)
**File**: `C:\NeoFace\face_unlock\daemon_pipe.py`
**Lines**: 55, 67
**Code**:
```python
cam = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)  # Line 55
cam = cv2.VideoCapture(i, cv2.CAP_DSHOW)              # Line 67
```
**Purpose**: Auto-detect working camera at daemon startup
**When**: Only during `_detect_camera()` at line 82

## Flow 2: Dashboard Test Scan

### Primary Camera Open Location
**File**: `C:\NeoFace\dashboard.py`
**Line**: 540
**Code**:
```python
cam = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
```
**Called by**: `api_test_scan()` at line 524
**Camera Index**: From `_get_camera_index()` (cached)
**Backend**: `cv2.CAP_DSHOW`
**Warmup**: 1.5s sleep + 5 frame reads (lines 549-552)

### Auto-Detection Camera Open
**File**: `C:\NeoFace\dashboard.py`
**Lines**: 121, 136
**Code**:
```python
cam = cv2.VideoCapture(idx, cv2.CAP_DSHOW)  # Line 121
cam = cv2.VideoCapture(i, cv2.CAP_DSHOW)    # Line 136
```
**Purpose**: Auto-detect working camera during `_get_camera_index()`
**When**: Only during first call or cache miss

### Status Check Camera Open
**File**: `C:\NeoFace\dashboard.py`
**Line**: 201
**Code**:
```python
cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
```
**Called by**: `get_status()` at line 165
**Purpose**: Check if camera is available
**Condition**: Only if daemon NOT running (line 198)

### Troubleshoot Camera Open
**File**: `C:\NeoFace\dashboard.py`
**Line**: 697
**Code**:
```python
cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
```
**Called by**: `api_troubleshoot()` at line 689
**Purpose**: Test camera functionality

## Flow 3: Dashboard Enrollment

### Enrollment Tool (No Live Camera)
**File**: `C:\NeoFace\tools\enroll_fast.py`
**Note**: Does NOT open live camera
**Purpose**: Processes photos from disk (`photos/` directory)
**Camera**: Only opens if processing video files (line 76)

## Flow 4: Presence Daemon

### Primary Camera Open Location
**File**: `C:\NeoFace\face_unlock\presence_daemon.py`
**Line**: 57
**Code**:
```python
cap = cv.VideoCapture(CAMERA_INDEX, cv.CAP_DSHOW)
```
**Purpose**: Periodic presence detection
**Frequency**: Every 45 seconds (configurable)
**Camera Index**: From config.toml (line 17)
**Backend**: `cv.CAP_DSHOW`
**Duration**: Single frame read, then release

### Auto-Detection Camera Open
**File**: `C:\NeoFace\face_unlock\presence_daemon.py`
**Lines**: 25
**Code**:
```python
cam = cv2.VideoCapture(i, cv2.CAP_DSHOW)
```
**Purpose**: Auto-detect working camera at startup
**When**: Only during `_detect_camera()` at line 37

## Camera Index Configuration

### Config File
**File**: `C:\NeoFace\config.toml`
**Line**: 15
**Value**: `index = 1`

### Daemon Default
**File**: `C:\NeoFace\face_unlock\daemon_pipe.py`
**Line**: 33
**Value**: `CAMERA_INDEX = 0` (default)
**Override**: Line 45 reads config.toml

### Dashboard Default
**File**: `C:\NeoFace\dashboard.py`
**Line**: 110
**Value**: `idx = 0` (default)
**Override**: Lines 112-117 read config.toml

### Presence Daemon Default
**File**: `C:\NeoFace\face_unlock\presence_daemon.py`
**Line**: 11
**Value**: `CAMERA_INDEX = 0` (default)
**Override**: Lines 13-18 read config.toml

## Camera Open/Close Summary

| Component | Opens Camera | Closes Camera | Duration |
|---|---|---|---|
| daemon_pipe.py | Line 116 (cam.open()) | Line 274 (cam.close()) | ~1-2s per scan |
| dashboard.py (test-scan) | Line 540 | Line 575 (cam.release()) | ~2-5s |
| dashboard.py (status) | Line 201 | Line 205 (cap.release()) | ~0.5s |
| dashboard.py (troubleshoot) | Line 697 | Line 714 (cap.release()) | ~0.5s |
| presence_daemon.py | Line 57 | Line 62 (cap.release()) | ~0.1s |

## Critical Notes

1. **Daemon holds camera longest** (~1-2s per scan)
2. **Dashboard test-scan holds camera second longest** (~2-5s)
3. **Presence daemon holds camera briefly** (~0.1s)
4. **Only one process can hold camera at a time**
5. **Camera index 1 is configured, but defaults are 0**
6. **All use cv2.CAP_DSHOW backend**
