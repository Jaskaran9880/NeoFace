import sys
sys.path.insert(0, r"C:\NeoFace")
import win32file
import time

out = r"C:\ProgramData\NeoFace\probe.log"

def note(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    open(out, "a").write(line + "\n")
    print(line, flush=True)

open(out, "w").write(f"{time.strftime('%H:%M:%S')} probe start\n")
resp = "NOATTEMPT"
for attempt in (1, 2, 3):
    try:
        h = win32file.CreateFile(r"\\.\pipe\NeoFace", 0xC0000000, 0, None, 3, 0, None)
        note(f"try{attempt} connected, sending VERIFY")
        win32file.WriteFile(h, b"VERIFY perve")
        hr, d = win32file.ReadFile(h, 16)
        h.close()
        resp = d.decode("utf-8", "ignore")
        note(f"try{attempt} RESP:{resp}")
        break
    except Exception as e:
        err = getattr(e, 'args', [0])[0]
        note(f"try{attempt} ERROR:{e!r}")
        if err == 231:
            time.sleep(8)
        else:
            time.sleep(3)
open(out, "a").write(f"final:{resp}\n")
