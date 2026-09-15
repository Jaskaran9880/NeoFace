# NeoFace Unlock

Open-source face unlock for Windows 10/11 laptops with a regular RGB webcam (no IR camera needed).

Built for my Predator Helios Neo 16 (i7-13700HX, RTX 4050, Win 11). Uses a normal 1080p webcam + AI face recognition to unlock via the Windows lock screen tile.

## How it works

```
Win+L lock screen
  -> NeoFace tile appears (C++ Credential Provider DLL)
  -> Look at camera, click "Unlock with face"
  -> Daemon scans face (YuNet detection + SFace recognition, 0.06s/frame)
  -> Match found -> desktop unlocked
  -> No match -> "Face not recognized" -> use PIN
```

## Requirements

- Windows 10/11
- Python 3.10+
- Any RGB webcam (USB or built-in)
- VS2022 Build Tools (for building the C++ DLL)

## Quick install

```powershell
# 1. Clone
git clone https://github.com/Jaskaran9880/windows-face-unlock.git
cd windows-face-unlock

# 2. Install (run as Admin for full setup)
.\install\install.ps1
```

## Manual install

```powershell
# 1. Clone and install dependencies
git clone https://github.com/Jaskaran9880/windows-face-unlock.git
cd windows-face-unlock
pip install -r requirements.txt

# 2. Download face detection/recognition models
python tools\fetch_fast.py

# 3. Add your face photos
#    Place front-facing photos (JPG/PNG/HEIC) in the photos\ folder

# 4. Enroll your face
python tools\enroll_fast.py

# 5. Set up password vault (one-time, your Windows password)
python tools\set_password_machine.py

# 6. Build and register the lock screen tile (Admin)
cd cp
.\build_cp.ps1
.\register_cp.ps1
cd ..

# 7. Install daemon service (Admin)
.\installer\install_daemon.ps1

# 8. Test
python tools\test_unlock.py
```

## Usage

1. Log in with PIN once (daemon starts automatically at logon)
2. Press **Win+L** to lock
3. Look at the camera
4. Click **"Unlock with face"** on the NeoFace tile
5. Unlocked!

## Architecture

```
C:\NeoFace\
  face_unlock/
    daemon_pipe.py      - Named pipe daemon (runs as pythonw, hidden)
    fast.py             - YuNet + SFace engine (0.06s/frame, 128-d)
    engine.py           - InsightFace buffalo_l (optional, 512-d)
    store.py            - DPAPI encrypted face gallery
    matcher.py          - Cosine similarity scoring
    camera.py           - DSHOW camera with MJPG codec
  cp/
    dllmain.cpp         - C++ DLL entry + COM factory
    provider.cpp        - Credential Provider (tile UI)
    credential.cpp      - Tile logic + pipe communication
    kerb.cpp            - Kerberos unlock packager
  tools/
    enroll_fast.py      - Enroll from photos + video
    test_unlock.py      - Test face scan
    set_password_machine.py - Store Windows password (DPAPI)
  photos/               - Your face photos (for enrollment)
  models/
    yunet.onnx          - Face detection (232KB)
    sface.onnx          - Face recognition (37MB)
```

## Performance

| Backend | Speed | Dimensions | Accuracy | GPU needed |
|---------|-------|------------|----------|------------|
| **fast** (default) | 0.06s/frame | 128-d | Good (0.54-0.73) | No |
| accurate (optional) | 2.6s/frame | 512-d | Best | Optional |

## Technical details

- **Detection**: YuNet (OpenCV DNN, CPU-optimized)
- **Recognition**: SFace (OpenCV FaceRecognizerSF)
- **Gallery**: Variable-length vectors, NF02 format, DPAPI encrypted
- **Pipe protocol**: Message-mode named pipe (`\\.\pipe\NeoFace`)
- **Lock screen tile**: C++ Credential Provider (registered via COM + regsvr32)
- **Daemon**: Python scheduled task, Interactive logon type

## Known limitations

- Camera requires user session (Windows blocks SYSTEM access at login screen)
- Face scan runs after PIN login (not at cold-boot login screen)
- Keep PIN enabled as backup
- No anti-spoofing in v1 (passive liveness deferred to v2)

## License

MIT
