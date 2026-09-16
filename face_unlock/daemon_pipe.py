import os
import sys
import cv2
import threading
import time

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
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import cosine_score

PIPE = r"\\.\pipe\NeoFace"
IMG_SIZE = 320
WARMUP = 2
FRAMES = 3
HIT_REQ = 2
THRESHOLD = 0.35

engine = FastEngine(os.path.join(ROOT, "models", "yunet.onnx"),
                    os.path.join(ROOT, "models", "sface.onnx"))
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
gallery.load()

log(f"daemon loaded - {sum(len(v) for v in gallery.templates.values())} fast templates")

class Cam:
    def __init__(self):
        self.cap = None
        self.lock = threading.Lock()
        self.latest = None
        self.running = False
        self._thread = None

    def open(self):
        if self.cap and self.cap.isOpened():
            return
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self._thread = threading.Thread(target=self._grab, daemon=True)
        self._thread.start()
        for _ in range(WARMUP):
            self.cap.read()
        time.sleep(0.05)

    def _grab(self):
        while self.running and self.cap and self.cap.isOpened():
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.latest = f
            else:
                time.sleep(0.01)

    def read(self):
        with self.lock:
            if self.latest is not None:
                return True, self.latest.copy()
        return False, None

    def close(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        if self.cap:
            self.cap.release()
            self.cap = None
            self.latest = None

cam = Cam()

import time as _t
log(f"{_t.strftime('%H:%M:%S')} creating pipe {PIPE}")

try:
    pipe = win32pipe.CreateNamedPipe(PIPE,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        1, 65536, 65536, 0, None)
    log(f"{_t.strftime('%H:%M:%S')} pipe created handle={pipe}")
except Exception as e:
    log(f"FATAL: CreateNamedPipe failed: {e}")
    sys.exit(1)

log(f"{_t.strftime('%H:%M:%S')} listening")
while True:
    try:
        log(f"{_t.strftime('%H:%M:%S')} waiting for client...")
        win32pipe.ConnectNamedPipe(pipe, None)
        log(f"{_t.strftime('%H:%M:%S')} client connected")
        _, data = win32file.ReadFile(pipe, 65536)
        log(f"{_t.strftime('%H:%M:%S')} read {data!r}")
        req = data.decode("utf-8", "ignore").strip().rstrip("\x00")
        user = req.split(" ", 1)[1].strip().rstrip("\x00") if req.startswith("VERIFY") else "perve"

        t0 = _t.time()
        cam.open()
        t1 = _t.time()
        scores = []
        frames_ok = 0
        faces_seen = 0
        for _ in range(FRAMES):
            ok, f = cam.read()
            if not ok:
                continue
            frames_ok += 1
            h, w = f.shape[:2]
            if w > IMG_SIZE:
                f = cv2.resize(f, (IMG_SIZE, int(h * IMG_SIZE / w)))
            emb, face = engine.embed(f)
            if face is not None:
                faces_seen += 1
            if emb is None:
                continue
            cands = [c for c in gallery.templates.get(user, []) if len(c) == len(emb)]
            if cands:
                scores.append(max(cosine_score(emb, c) for c in cands))
        cam.close()
        t_scan = _t.time() - t1

        good = bool(scores) and sum(1 for s in scores if s >= THRESHOLD) >= HIT_REQ
        best = max(scores) if scores else 0.0
        total = _t.time() - t0
        log(f"{_t.strftime('%H:%M:%S')} user={user} total={total:.1f}s scan={t_scan:.1f}s frames={frames_ok} faces={faces_seen} scores={[round(s,2) for s in scores]} best={round(best,2)} -> {'OK' if good else 'FAIL'}")
        win32file.WriteFile(pipe, ("OK" if good else "FAIL").encode())
        win32pipe.DisconnectNamedPipe(pipe)
        log(f"{_t.strftime('%H:%M:%S')} disconnected, ready for next client")
    except Exception as e:
        log(f"{_t.strftime('%H:%M:%S')} error: {e}")
        try:
            win32pipe.DisconnectNamedPipe(pipe)
        except Exception:
            pass
