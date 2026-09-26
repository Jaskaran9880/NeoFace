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
git clone https://github.com/Jaskaran9880/NeoFace.git
cd NeoFace

# 2. Install (run as Admin for full setup)
.\install\install.ps1
```

## Manual install

```powershell
# 1. Clone and install dependencies
git clone https://github.com/Jaskaran9880/NeoFace.git
cd NeoFace
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

## Uninstall

Run either of these **as Admin** (both raise a UAC prompt if needed):

```bat
uninstall.bat                        (double-click, repo root)
```
```powershell
.\install\uninstall.ps1              (Admin terminal)
.\install\uninstall.ps1 -Purge       (Admin terminal, also wipes user data)
```

What it removes:

- **Lock screen tile**: `FaceUnlockCP.dll` unregistered (`regsvr32 /u`) and `C:\Program Files\NeoFace` deleted — the NeoFace tile disappears from the Win+L screen
- **Scheduled tasks**: `NeoFace-Daemon` plus any older NeoFace task variants
- **Processes**: dashboard (port 8080) and daemon, stopped before anything is deleted
- **Shortcuts**: Start Menu / desktop shortcuts pointing at NeoFace, if any

What it keeps:

- `C:\ProgramData\NeoFace` — face gallery, password vault, logs. Kept by default so a reinstall works; delete it too by answering `y`/`purge` at the prompt or running with `-Purge`
- `C:\NeoFace` itself (the repo) — uninstall only removes installed components; delete the folder manually to finish
- Python packages from `requirements.txt` (shared with other projects)

Notes: if the lock screen (LogonUI) is holding the DLL, deletion is scheduled for the next reboot — **reboot to finish**. PIN login keeps working throughout. A summary of removed/kept items is printed at the end (exit code 1 if anything failed).

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
    antispoof.py        - SpoofGate anti-spoofing (optional model)
  cp/
    dllmain.cpp         - C++ DLL entry + COM factory
    provider.cpp        - Credential Provider (tile UI)
    credential.cpp      - Tile logic + pipe communication
    kerb.cpp            - Kerberos unlock packager
  tools/
    enroll_fast.py      - Enroll from photos + video
    test_unlock.py      - Test face scan
    set_password_machine.py - Store Windows password (DPAPI)
  dashboard.py          - Flask dashboard (status, photos, troubleshoot)
  templates/index.html  - Dashboard UI (Tailwind dark glass)
  static/logo.png       - Dashboard header logo
  install/install.ps1   - One-click installer
  cp/icon.bmp, cp/tile.bmp - Lock screen logo assets (deployed to Program Files)
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
- **Anti-spoofing**: SpoofGate (ONNX, optional — rejects photo/video replays when model available)
- **Gallery**: Variable-length vectors, NF02 format, DPAPI encrypted
- **Pipe protocol**: Message-mode named pipe (`\\.\pipe\NeoFace`)
- **Lock screen tile**: C++ Credential Provider (registered via COM + regsvr32)
- **Daemon**: Python scheduled task, Interactive logon type

## Known limitations

- Camera requires user session (Windows blocks SYSTEM access at login screen)
- PIN required once per boot/wake; face unlock available for all subsequent locks
- Keep PIN enabled as backup

## Check for Updates

The dashboard's **Settings** tab has a **Check for Updates** card (the header shows a badge when new commits are available). It compares your local clone with the `main` branch on GitHub and shows your local version/SHA, the upstream SHA, how many commits you're behind, and the list of new commits.

- Requires your dashboard API key; results are cached for 5-10 minutes
- **Read-only**: it only checks — no pull, and your settings, faces, photos, vault, and models are never modified
- Degrades gracefully: shows "unavailable" instead of erroring when offline, when git isn't installed, or on a zip (non-git) install

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Update check unavailable | Git not installed or installed from a zip — clone the repo to enable update checks |
| "Camera not available" | Stop the daemon first (`Stop-ScheduledTask -TaskName NeoFace-Daemon`), then try again |
| "Pipe not available" | Start the daemon: `Start-ScheduledTask -TaskName NeoFace-Daemon` |
| "Face not recognized" | Re-enroll: `python tools\enroll_fast.py`, ensure good lighting |
| Camera opens slowly | Normal for DSHOW backend (~2-3s first open), subsequent opens are faster |
| Daemon not starting | Check `C:\ProgramData\NeoFace\daemon.log` for errors |
| DLL not showing on lock screen | Re-register: `regsvr32 "C:\Program Files\NeoFace\FaceUnlockCP.dll"` |
| No logo on the NeoFace tile | Re-run `.\cp\deploy_all.ps1` (or `register_cp.ps1`) so `icon.bmp`/`tile.bmp` land in `C:\Program Files\NeoFace` |

## License

MIT

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for threat model, password vault security notes, and known limitations.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and code style guidelines.
