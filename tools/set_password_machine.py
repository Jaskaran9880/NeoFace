import os
import sys
import getpass
import socket

domain = os.environ.get("USERDOMAIN", socket.gethostname())
user = os.getlogin()
print(f"Storing unlock credential for {domain}\\{user} (DPAPI machine-scope).")
print("Use your Windows PASSWORD (not PIN). Run in Terminal (Admin).")
pw = getpass.getpass("Password: ")
pw2 = getpass.getpass("Repeat: ")
if not pw or pw != pw2:
    print("mismatch / empty - aborted")
    sys.exit(1)

import win32crypt
raw = f"{domain}\n{user}\n{pw}".encode("utf-8")
blob = win32crypt.CryptProtectData(raw, None, None, None, None, 0x04)
out = r"C:\ProgramData\NeoFace\cred.bin"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(blob)
print(f"saved {len(blob)} bytes to {out} - SYSTEM-readable, PIN untouched")
