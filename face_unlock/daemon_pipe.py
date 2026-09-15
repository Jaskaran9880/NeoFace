import os
import sys
import cv2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
LOG = r"C:\ProgramData\NeoFace\daemon.log"
os.makedirs(os.path.dirname(LOG), exist_ok=True)
def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)
import win32pipe
import win32file
from face_unlock.camera import Camera
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import vote

PIPE = r"\\.\pipe\NeoFace"

engine = FastEngine(os.path.join(ROOT, "models", "yunet.onnx"),
                    os.path.join(ROOT, "models", "sface.onnx"))
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
gallery.load()
cam = Camera(0, 640, 480)
log(f"daemon loaded - {sum(len(v) for v in gallery.templates.values())} fast templates")

import time
log(f"{time.strftime('%H:%M:%S')} creating pipe {PIPE}")

try:
    pipe = win32pipe.CreateNamedPipe(PIPE,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        1, 65536, 65536, 0, None)
    log(f"{time.strftime('%H:%M:%S')} pipe created handle={pipe}")
except Exception as e:
    log(f"FATAL: CreateNamedPipe failed: {e}")
    sys.exit(1)

log(f"{time.strftime('%H:%M:%S')} listening")
while True:
    try:
        log(f"{time.strftime('%H:%M:%S')} waiting for client...")
        win32pipe.ConnectNamedPipe(pipe, None)
        log(f"{time.strftime('%H:%M:%S')} client connected")
        _, data = win32file.ReadFile(pipe, 65536)
        log(f"{time.strftime('%H:%M:%S')} read {data!r}")
        req = data.decode("utf-8", "ignore").strip().rstrip("\x00")
        user = req.split(" ", 1)[1].strip().rstrip("\x00") if req.startswith("VERIFY") else "perve"
        log(f"{time.strftime('%H:%M:%S')} verify {user}...")
        cam.open()
        for _ in range(5):
            cam.read()
        scores = []
        frames_ok = 0
        faces_seen = 0
        for _ in range(5):
            ok, f = cam.read()
            if not ok:
                continue
            frames_ok += 1
            h, w = f.shape[:2]
            if w > 640:
                f = cv2.resize(f, (640, int(h * 640 / w)))
            emb, face = engine.embed(f)
            if face is not None:
                faces_seen += 1
            if emb is None:
                continue
            scores.append(gallery.best(user, emb))
        cam.close()
        good = bool(scores) and vote(scores, 0.35, 2)
        best = max(scores) if scores else 0.0
        log(f"{time.strftime('%H:%M:%S')} frames={frames_ok} faces={faces_seen} scores={[round(s,2) for s in scores]} best={round(best,2)} -> {'OK' if good else 'FAIL'}")
        win32file.WriteFile(pipe, ("OK" if good else "FAIL").encode())
        win32pipe.DisconnectNamedPipe(pipe)
        log(f"{time.strftime('%H:%M:%S')} disconnected, ready for next client")
    except Exception as e:
        log(f"{time.strftime('%H:%M:%S')} error: {e}")
        try:
            win32pipe.DisconnectNamedPipe(pipe)
        except Exception:
            pass
