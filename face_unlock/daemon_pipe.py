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
print(f"NeoFace pipe daemon - {sum(len(v) for v in gallery.templates.values())} fast templates. Run before Win+L.", flush=True)

while True:
    pipe = win32pipe.CreateNamedPipe(PIPE, win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        1, 65536, 65536, 0, None)
    win32pipe.ConnectNamedPipe(pipe, None)
    try:
        _, data = win32file.ReadFile(pipe, 65536)
        req = data.decode("utf-8", "ignore").strip()
        user = req.split(" ", 1)[1] if req.startswith("VERIFY") else os.getlogin()
        import time as _t
        log(f"{_t.strftime('%H:%M:%S')} verify {user}...")
        cam.open()
        for _ in range(5):
            cam.read()
        scores = []
        frames_ok = 0
        faces_seen = 0
        means = []
        for _ in range(5):
            ok, f = cam.read()
            if not ok:
                continue
            frames_ok += 1
            means.append(round(float(f.mean()), 1))
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
        log(f"frames={frames_ok} faces={faces_seen} means={means} scores={[round(s, 2) for s in scores]} best={round(best, 2)} -> {'OK' if good else 'FAIL'}")
        win32file.WriteFile(pipe, ("OK" if good else "FAIL").encode())
    except Exception as e:
        print(f"pipe error: {e}", flush=True)
        try:
            win32file.WriteFile(pipe, b"FAIL")
        except Exception:
            pass
    finally:
        win32file.CloseHandle(pipe)
