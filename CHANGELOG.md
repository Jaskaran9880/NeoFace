# Changelog

## 0.4.5 - 2026-09-26
- Full uninstaller: new double-clickable `uninstall.bat` (auto-elevates) + enhanced `install/uninstall.ps1` — stops dashboard (:8080) and daemon first, removes all NeoFace scheduled tasks, unregisters the lock-screen DLL before deleting files, removes `C:\Program Files\NeoFace` and NeoFace shortcuts
- User data (`C:\ProgramData\NeoFace`: face gallery, password vault, logs) kept by default for reinstall; `-Purge` switch or `y`/`purge` at the prompt deletes it — the `C:\NeoFace` repo is never touched
- Handles a DLL locked by the lock screen (LogonUI) by scheduling deletion on reboot; prints a removed/kept/failed summary with exit codes
- Dashboard: change your Windows password from Settings (password-change option)
- Windows Hello gate: saving a password now requires the system PIN/biometric prompt (`UserConsentVerifier`, like Google Password Manager) - new `POST /api/setup/consent` issues a single-use 120s token that `POST /api/setup/password` refuses to work without; wrong password never overwrites the vault (server-side `LogonUserW` check)
- Dashboard: eye toggle to show/hide the password field
- Fixed dashboard header logo not rendering
- Destructive-test guard so tests can no longer wipe real gallery/vault data

## 0.4.4 - 2026-09-25
- Added "Check for Updates" card in dashboard Settings tab, plus header badge when the maintainer pushed new commits to GitHub
- New `GET /api/update/check` (API-key protected): `git fetch` primary, GitHub API fallback, 5-10 min cache, origin allow-list
- Shows local version/SHA (`git describe`), upstream SHA, behind count, up to 20 new commits, changes summary, and up-to-date state
- Update check is read-only: never pulls, never touches gallery/vault/config/models/photos
- Auto-apply and scheduled polling intentionally deferred to Phase 2
- Fixed `/api/health` stale hardcoded `0.4.0` version -> now `git describe` with `0.4.3` fallback
- Rate limiter validates the API key before counting requests; JSON error handlers for API routes (4a58b1e)
- Settings save now merge-writes so `antispoof_threshold` is preserved; photo thumbnails require auth (b7c7cdd)

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
