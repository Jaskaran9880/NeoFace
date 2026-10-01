"""Connect to the NeoFace pipe exactly like the CP does; print OK/FAIL + timing."""
import sys
import time

import win32file
import win32pipe

user = sys.argv[1] if len(sys.argv) > 1 else "perve"
req = f"VERIFY {user}".encode() + b"\x00"

t0 = time.time()
h = win32pipe.CreateNamedPipe  # noqa: F401  (presence check: pywin32 available)
try:
    h = win32file.CreateFileW(r"\\.\pipe\NeoFace",
                              win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                              0, None, win32file.OPEN_EXISTING, 0, None)
except Exception as e:
    print(f"open FAIL: {e}")
    sys.exit(1)
win32pipe.SetNamedPipeHandleState(h, win32pipe.PIPE_READMODE_MESSAGE, None, None)
win32file.WriteFile(h, req)
_, resp = win32file.ReadFile(h, 64)
elapsed = time.time() - t0
h.Close()
print(f"resp={resp[:2]!r} elapsed={elapsed:.1f}s -> {'OK' if resp[:2] == b'OK' else 'FAIL'}")
