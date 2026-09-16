# Changelog

## 0.3.0 - 2026-09-16
- Speed optimization: 7-8s → 3.5s per unlock
- Threaded camera reads (read next frame while processing)
- Reduced processing: 5 → 3 frames, 640px → 320px
- Camera on-demand (fully off between uses)
- Fixed CP DLL pipe connection (removed broken WaitNamedPipe)
- Fixed ReadFile byte count bug (overlapped I/O)
- Fixed null-byte username from C++ DLL
- One-click install/uninstall scripts
- Updated README with full setup guide
- Added deploy_all.ps1 for full deployment
- Project moved to C:\NeoFace

## 0.2.0 - 2026-09-15
- Named pipe daemon with camera + face recognition
- C++ Credential Provider tile for Win+L lock screen
- COM registration + Kerberos unlock packaging
- DPAPI encrypted face gallery (NF02 format)
- Password vault (DPAPI machine-scope)

## 0.1.0 - 2026-09-12
- First working build on Neo 16, tested end-to-end
- Fast backend YuNet+SFace default (0.06s), accurate buffalo_l optional
- Enroll via photo/video/live, 20 fast + 29 accurate templates verified
- Fullscreen lock test `tools/lock_screen.py` UNLOCK confirmed
- Vault + live console test pass

## v2 next
- Walk-away auto-lock daemon
- Active liveness detection (MiniFASNet)
- QML FaceID-style ring animation
- Adaptive thresholds
