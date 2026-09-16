# Security notes

## Current implementation (v0.2)

- **Camera**: RGB only, no depth sensing. No anti-spoofing in v1.
- **Gallery**: Face vectors only (128-d), DPAPI user-scope encrypted on disk.
- **Password vault**: Windows password encrypted with DPAPI machine-scope (`cred.bin`).
- **Named pipe**: `\\.\pipe\NeoFace` — message mode, created with default DACL.
- **CP DLL**: Registered via COM + regsvr32, runs in LogonUI context.
- **Daemon**: Python scheduled task, Interactive logon type, runs in user session.

## Threat model

| Attack | Mitigation |
|--------|------------|
| Photo replay | Cosine threshold 0.35, multiple frames required |
| Screen replay | Camera captures live frames, not screen content |
| 3D mask | Not blocked in v1 (deferred to v2) |
| Dictionary attack | Pipe only accepts "VERIFY username" commands |
| Privilege escalation | Daemon runs as user, not SYSTEM |

## Limitations

- No liveness detection (passive only for v1)
- No depth sensing (RGB webcam only)
- Camera accessible from user session only (Windows limitation)
- PIN required at cold boot (daemon starts after logon)

## Always keep PIN enabled

Face unlock is a convenience feature, not a security boundary. Keep your Windows PIN as a backup.
