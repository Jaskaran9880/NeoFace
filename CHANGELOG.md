# Changelog

## 0.4.3 - 2026-09-23
- Credential Provider tile logo: 3-field schema with `CPFT_TILE_IMAGE` (deselected-tile logo via `GetBitmapValue`)
- Logo assets `cp/icon.bmp` + `cp/tile.bmp` now shipped by deploy_all, register_cp, deploy_boot, and the installer
- Dashboard header renders NeoFace logo (`static/logo.png`) instead of the letter mark
- Synced daemon fallback thresholds with retune (cosine 0.45, anti-spoof 0.3) when config keys are missing
- New `tools/prep_cp_logo.py` regenerates logo assets from one source image
- New sanity checks: Python/PS1 syntax, CP field schema consistency, repo hygiene (secrets stay untracked)
- Dashboard API test now reads `.dashboard_key` instead of a stale hardcoded key
- Fixed config.example missing `hit_required`/`antispoof_threshold` and stale `frames = 5`
- Docs: refreshed cp/README field schema, fixed CONTRIBUTING clone URLs, corrected SECURITY thresholds, README architecture + logo troubleshooting
- Added `.gitattributes` for binaries/CRLF; ignore `Thumbs.db`/`Desktop.ini`

## 0.4.2 - 2026-09-22
- Retuned match thresholds: cosine 0.50->0.45, anti-spoof 0.7->0.3
- Fixed dashboard model status dict so sface/antispoof keys resolve (Loading... bug)
- Added render error handling with retry to dashboard tabs
- Removed per-frame rejection log spam from daemon
- Synced SpoofGate default threshold and config.example.toml with retune

## 0.4.1 - 2026-09-17
- Wired SpoofGate anti-spoofing into daemon pipe
- Added try/except around gallery struct parsing to handle corruption
- Documented SYSTEM-readable password vault in SECURITY.md
- Reworded cold-boot limitation as intentional design
- Fixed camera leak causing CameraReservedByAnotherApp error

## 0.4.0 - 2026-09-17
- Web dashboard with liquid glass dark UI (Flask + Tailwind)
- Photo management with HEIC thumbnail previews
- Component diagnostics and live face test
- Security: fixed path traversal in photo upload/delete
- Removed hardcoded personal paths from tools
- Fixed DPAPI error handling in gallery store
- Fixed inconsistent matcher defaults
- Added troubleshooting docs

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
- Dashboard added with web-based management UI

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
