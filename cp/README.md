# Credential Provider

Thin C++ shim for LogonUI. Never does recognition itself.

- Tile shows status text "NeoFace - look at camera, then click below"
- Selected tile adds an "Unlock with face" button (PIN fallback still works)
- On submit -> named pipe `\\.\pipe\NeoFace` -> python service (daemon_pipe.py)
- Service replies `{ok, scores}` -> CP submits LSA password or shows error status
- 3 attempts max, then focus moves to the password box / PIN

## Field schema (3 fields)

| id | type | state | purpose |
|----|------|-------|---------|
| 0 | `CPFT_TILE_IMAGE` | deselected tile only | Logo, loaded via `GetBitmapValue` from `icon.bmp` |
| 1 | `CPFT_LARGE_TEXT` | selected + deselected | Status / instruction text |
| 2 | `CPFT_SUBMIT_BUTTON` | selected tile | "Unlock with face" (adjacent field = 1) |

`tools/check_cp_fields.py` verifies provider.cpp and credential.cpp agree on this schema.

## Logo assets

- `cp/icon.bmp` (256x256) - deployed to `C:\Program Files\NeoFace\icon.bmp`, loaded by `GetBitmapValue`
- `cp/tile.bmp` (512x512) - full-size spare tile art, deployed alongside
- Regenerate both from one source image: `python tools\prep_cp_logo.py <image> [--dashboard]`
- Dashboard header logo lives at `static/logo.png` (served by Flask at `/static/logo.png`)

## Deploy

All of these copy the DLL **and** the logo bitmaps to `C:\Program Files\NeoFace`:

- `.\build_cp.ps1` then `.\register_cp.ps1` - build + register only
- `.\deploy_all.ps1` - full redeploy (also used by the installer flow)
- `.\deploy_boot.ps1` - DLL + boot-time SYSTEM daemon task
- Unregister: `.\unregister_cp.ps1`

Build: VS2022 Desktop C++, x64 Release, regsvr32 FaceUnlockCP.dll
Keep a second admin account + restore point before registering.
