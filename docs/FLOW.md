# Full hotkey flow

1. Win+L. Tile: `Face Unlock - Press F`. Camera off.
2. Press F. Service wakes camera (~0.8s on Neo 16). Prompt: `Look here`.
3. Guide loop: no-face / dark / far / yaw>25 / multi-face. No scoring yet.
4. Ready -> Scanning ring 1s, 5 frames, need 3/5 over 0.42 + spoof>0.7.
5. Pass -> desktop + success ring. Fail x3 -> PIN box focused.
6. Walk-away daemon: 45s tick, any-face = stay, empty x2 + idle>60s = Win+L.
7. Esc cancels anytime. Uninstall restores stock login.
