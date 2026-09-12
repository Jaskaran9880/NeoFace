# NeoFace Unlock

Face unlock for my Predator Helios Neo 16 (Win 11, no IR cam). Normal 1080p webcam only.

I got tired of typing PIN every time I lock with Win+L, and Windows Hello needs an IR camera which this laptop doesn't have. So I'm building my own - hotkey gated, waits for you to look in, then unlocks.

## v1 scope

Enroll (photo/video/live) + console test + `test_unlock.py` simulation + vault. Walk-away auto-lock moved to v2.

## How it works

```
Win+L -> tile says Press [F] -> camera wakes -> Look here prompt
  -> guiding (closer / straight / light) -> Scanning ring
  -> match -> desktop
```

## v2 roadmap

- Walk-away daemon (YuNet, 45s tick, always-on AC+battery)
- Lock-screen CP tile auto-register

## Stack

- Recognition: InsightFace buffalo_l (SCRFD det_10g + ArcFace w600k_r50, 512-d)
- Anti-spoof: Silent-Face MiniFASNet v2 (passive only for v1)
- Presence: YuNet lightweight detector
- Service: Python LocalSystem service + named pipe
- Lock tile: C++ Credential Provider (thin shim)
- Console: PySide6 + QML FaceID-style ring (redrawn by me)
- Password vault: LSA Secret, gallery DPAPI-machine, vectors only

## Status

v0.1 skeleton. Enrollment + test works in console. CP tile registers but treat as beta - keep PIN enabled.

See `docs/FLOW.md` for full hotkey flow, `docs/SECURITY.md` for limits.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\fetch_fast.py
python tools\enroll_fast.py
python tools\test_unlock.py
```

## Performance (open-source friendly)

Two backends, auto-picked:

- `fast` default: YuNet + SFace (OpenCV Zoo) - ~0.06s/frame CPU, 128-d, runs on any i3 laptop, no GPU needed. Threshold 0.35.
- `accurate` optional: InsightFace buffalo_l - ~2.6s/frame CPU, ~0.15s on RTX 4050 CUDA, 512-d. Threshold 0.42.

Unlock test: `python tools/test_unlock.py`. Enroll fast gallery: `python tools/enroll_fast.py`.

## Real Windows unlock status (v1)

- DONE: fast enroll (photo/video/live), `test_unlock.py` unlock simulation, DPAPI vault (`tools/set_password.py`)
- V2: walk-away auto-lock daemon + lock-screen CP tile. Steps then:
  1. Run PowerShell as admin, create restore point
  2. Keep PIN enabled (built-in Administrator stays OFF for security)
  3. `python tools/set_password.py`
  4. CP DLL in `cp/` - build with VS2022, `regsvr32`, test with Win+L + hotkey F

Tested on: Predator Helios Neo 16, i7-13700HX, RTX 4050, Win 11 23H2.
