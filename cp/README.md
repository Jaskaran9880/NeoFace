# Credential Provider

Thin C++ shim for LogonUI. Never does recognition itself.

- Tile shows `Press F to start`
- On hotkey -> named pipe `\\.\pipe\NeoFace` -> LocalSystem python service
- Service replies `{ok, scores}` -> CP submits LSA password or shows PIN fallback
- 3 attempts max, then focus moves to password box

Build: VS2022 Desktop C++, x64 Release, regsvr32 FaceUnlockCP.dll
Keep a second admin account + restore point before registering.
