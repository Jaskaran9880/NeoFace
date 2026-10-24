# Security notes

## Current implementation (v0.6)

- **Camera**: RGB only, no depth sensing. Passive anti-spoofing via SpoofGate (when model available).
- **Gallery**: Face vectors only (128-d), DPAPI user-scope encrypted on disk.
- **Password vault**: Windows password encrypted with DPAPI machine-scope (`cred.bin`).
- **Named pipe**: `\\.\pipe\NeoFace` — message mode, created with default DACL.
- **CP DLL**: Registered via COM + regsvr32, runs in LogonUI context. Tile logo (`icon.bmp`) is loaded from `C:\Program Files\NeoFace\` via `GetBitmapValue` (bitmap only, no code path).
- **Daemon**: Python scheduled task, Interactive logon type, runs in user session (boot-time variant `deploy_boot.ps1` registers SYSTEM - see below).

## Update pipeline (v0.6)

- **Integrity**: the `NeoFace-Setup.exe` asset is SHA256-pinned against the SHA published in the GitHub release notes (fence first, bare fallback); a mismatch deletes the staged `.part` file and never executes anything.
- **Origin allow-list**: release/download URLs are restricted to the GitHub releases origin, and the allow-list is re-verified at apply time (not just at check time).
- **Staged apply with rollback**: downloads land in `.part` and are atomically renamed only after verification; apply progress is tracked in `apply_state.json` with rollback to `failed` on error and stale in-progress states reconciled after 30 minutes.
- **Double-apply guard**: `POST /api/update/apply` returns `409 in_progress` while an apply is under way (state-file backed), so a second click can never start a concurrent installer.
- **Elevation**: the elevated apply handoff runs through the `NeoFace-UpdateApply` scheduled task (`-RunLevel Highest`) with a far-future (`+1 year`) trigger — elevation is standing consent registered at install time; the task never self-fires.
- **Renderer**: the post-update what-changed modal renders release notes through an allowlist markdown renderer — raw HTML escaped, `javascript:` URLs never become links, https links get `rel="noopener noreferrer"`.

## Threat model

| Attack | Mitigation |
|--------|------------|
| Photo replay | Cosine threshold 0.45, anti-spoof threshold 0.3, multiple frames required |
| Screen replay | Camera captures live frames, not screen content |
| 3D mask | Not blocked in v1 (deferred to v2) |
| Spoofing (photo/video) | SpoofGate anti-spoof model (when model available) |
| Dictionary attack | Pipe only accepts "VERIFY username" commands |
| Privilege escalation | Daemon runs as user, not SYSTEM |

## Password vault security

`cred.bin` is encrypted with DPAPI **machine-scope** (`CRYPTPROTECT_LOCAL_MACHINE`). This means:

- Any process running as **SYSTEM** on this machine can decrypt it.
- The real security boundary is "don't let untrusted code get SYSTEM access," not "the password is safe from all local attackers."
- The vault exists to avoid storing the password in plaintext — it is not a defense against local privilege escalation.
- If you need stronger protection, consider Windows Hello or a hardware security key.

## Limitations

- No liveness detection (passive only for v1)
- No depth sensing (RGB webcam only)
- Camera accessible from user session only (Windows limitation)
- PIN required once per boot/wake; face unlock available for all subsequent locks

## Always keep PIN enabled

Face unlock is a convenience feature, not a security boundary. Keep your Windows PIN as a backup.
