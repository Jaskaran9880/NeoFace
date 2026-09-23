# Security notes

## Current implementation (v0.4)

- **Camera**: RGB only, no depth sensing. Passive anti-spoofing via SpoofGate (when model available).
- **Gallery**: Face vectors only (128-d), DPAPI user-scope encrypted on disk.
- **Password vault**: Windows password encrypted with DPAPI machine-scope (`cred.bin`).
- **Named pipe**: `\\.\pipe\NeoFace` — message mode, created with default DACL.
- **CP DLL**: Registered via COM + regsvr32, runs in LogonUI context. Tile logo (`icon.bmp`) is loaded from `C:\Program Files\NeoFace\` via `GetBitmapValue` (bitmap only, no code path).
- **Daemon**: Python scheduled task, Interactive logon type, runs in user session (boot-time variant `deploy_boot.ps1` registers SYSTEM - see below).

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
