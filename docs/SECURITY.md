# Security notes

RGB only, no depth. Blocks photos and screen replays via MiniFASNet. Does not block 3D masks.

- Vectors only on disk, DPAPI-machine, atomic writes
- Password in LSA Secret, never sent over pipe
- Pipe ACL SYSTEM + Admins, PID check
- Rate limit 5 tries / 60s, audit to Event Viewer
- Always keep PIN enabled. Beta - don't use as sole login on work machine.
