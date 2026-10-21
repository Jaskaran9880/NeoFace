import os
import sys
import getpass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pw = getpass.getpass("Windows password (stored DPAPI user-scope, never uploaded): ")
pw2 = getpass.getpass("Repeat: ")
if pw != pw2 or not pw:
    print("mismatch / empty - aborted")
    sys.exit(1)

try:
    import win32crypt
    blob = win32crypt.CryptProtectData(pw.encode("utf-16-le"), None, None, None, None, 0)
    out = os.path.expandvars(r"%APPDATA%\NeoFace\pw.bin")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(blob)
    print(f"saved to {out} - used only by lock-screen tile")
except Exception as e:
    print(f"DPAPI failed: {e}")
    sys.exit(1)
