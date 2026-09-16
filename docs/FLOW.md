# Full hotkey flow (v0.2 - current)

1. **Log in with PIN** (cold boot). Daemon starts at logon (Interactive mode).
2. **Win+L** → Lock screen appears.
3. **NeoFace tile** shows: "NeoFace - look at camera, then click below"
4. **Click "Unlock with face"** → CP DLL sends VERIFY request to daemon via named pipe.
5. **Daemon opens camera** (~3s DSHOW init). Reads 3 frames at 320px.
6. **YuNet detects face** in each frame → **SFace embeds** to 128-d vector.
7. **Cosine similarity** against enrolled templates. Need 2/3 frames ≥ 0.35.
8. **Match → desktop unlocked**. No match → "Face not recognized" → use PIN.
9. **Camera closes** after scan. Fully off between requests.

## Architecture

```
Win+L lock screen
  → LogonUI loads CP DLL tile
  → User clicks "Unlock with face"
  → CP DLL opens \\.\pipe\NeoFace
  → Daemon reads VERIFY command
  → Opens camera, captures 3 frames
  → YuNet detection → SFace recognition
  → Scores compared against gallery
  → OK/FAIL written back to pipe
  → CP DLL packages Kerberos unlock
  → Desktop unlocked
```

## Pipeline timing

| Phase | Time |
|-------|------|
| Camera open (DSHOW) | ~3.0s |
| Frame capture × 3 | ~0.3s |
| YuNet detection × 3 | ~0.1s |
| SFace recognition × 3 | ~0.1s |
| Gallery matching × 3 | ~0.01s |
| **Total** | **~3.5s** |
