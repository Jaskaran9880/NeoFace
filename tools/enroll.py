import argparse
import os
import sys
import cv2
import time
import threading
import queue

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from face_unlock.camera import Camera
from face_unlock.engine import FaceEngine
from face_unlock.store import Gallery

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, default=9)
parser.add_argument("--user", default=os.getlogin())
parser.add_argument("--phase_secs", type=float, default=3.0)
parser.add_argument("--photo", action="append", default=[])
parser.add_argument("--dir", default=r"A:\Face Unlock For mypc\photos")
parser.add_argument("--video", action="append", default=[])
parser.add_argument("--video_frames", type=int, default=10)
args = parser.parse_args()

engine = FaceEngine("models")
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces.dat")
gallery.load()

def load_image(p):
    img = cv2.imread(p)
    if img is not None:
        return img
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        from PIL import Image
        import numpy as np
        pil = Image.open(p).convert("RGB")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"skip unreadable {p}: {e}")
        return None

def photo_paths():
    files = list(args.photo)
    if args.dir and os.path.isdir(args.dir):
        for n in os.listdir(args.dir):
            if n.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")):
                files.append(os.path.join(args.dir, n))
    return files

paths = photo_paths()
if args.video:
    saved = 0
    for vp in args.video:
        cap = cv2.VideoCapture(vp)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, total // args.video_frames)
        idx, taken = 0, 0
        while taken < args.video_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, img = cap.read()
            if not ok:
                break
            h, w = img.shape[:2]
            if w > 640:
                img = cv2.resize(img, (640, int(h * 640 / w)))
            print(f"processing {os.path.basename(vp)} frame {idx}...", flush=True)
            emb, face = engine.embed(img)
            if emb is None:
                print("no face in frame - skipped")
            else:
                gallery.add(args.user, emb)
                saved += 1
                print(f"saved {saved} from video")
            idx += step
            taken += 1
        cap.release()
    gallery.save()
    print(f"done - {saved} video templates for {args.user}")
    sys.exit(0)
if paths:
    saved = 0
    for p in paths:
        img = load_image(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        if w > 640:
            img = cv2.resize(img, (640, int(h * 640 / w)))
        print(f"processing {os.path.basename(p)}...", flush=True)
        emb, face = engine.embed(img)
        if emb is None:
            print(f"no face in {p} - use clear front photo")
            continue
        gallery.add(args.user, emb)
        saved += 1
        print(f"saved {saved} from {os.path.basename(p)}")
    gallery.save()
    print(f"done - {saved} photo templates for {args.user}")
    sys.exit(0)

def on_battery():
    try:
        import ctypes
        class PS(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte), ("Reserved1", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        ps = PS()
        ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps))
        return ps.ACLineStatus == 0
    except Exception:
        return False

battery = on_battery()
tick = 1.2 if battery else 0.6
print(f"{'BATTERY' if battery else 'AC'} mode - tick {tick}s")

cam = Camera(0, 640, 480)
cam.open()
for _ in range(5):
    cam.read()

latest = {}
lock = threading.Lock()
running = True

def grabber():
    while running:
        ok, frame = cam.read()
        if ok:
            with lock:
                latest["f"] = frame

t = threading.Thread(target=grabber, daemon=True)
t.start()

work = queue.Queue()

def infer_loop():
    while running:
        time.sleep(tick)
        with lock:
            f = latest.get("f")
            f = f.copy() if f is not None else None
        if f is None:
            continue
        h, w = f.shape[:2]
        if w > 640:
            f = cv2.resize(f, (640, int(h * 640 / w)))
        emb, face = engine.embed(f)
        work.put((emb is not None, emb))

it = threading.Thread(target=infer_loop, daemon=True)
it.start()

saved = 0
phase = ["front", "slight-left", "slight-right"]
per_phase = max(1, args.count // 3)
print("Hold still - front 3s, left 3s, right 3s. Q quits.")
while saved < args.count:
    with lock:
        show = latest.get("f")
        show = show.copy() if show is not None else None
    if show is not None:
        h, w = show.shape[:2]
        if w > 640:
            show = cv2.resize(show, (640, int(h * 640 / w)))
        label = phase[min(saved // per_phase, 2)]
        cv2.putText(show, f"{saved+1}/{args.count} {label}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("NeoFace enroll", show)
    if cv2.waitKey(30) & 0xFF == ord("q"):
        break
    while not work.empty():
        ok, emb = work.get()
        if not ok:
            print("no face - hold still")
            continue
        gallery.add(args.user, emb)
        saved += 1
        print(f"saved {saved}/{args.count}")
        if saved % per_phase == 0 and saved < args.count:
            print(f"now: {phase[min(saved // per_phase, 2)]}")

running = False
cam.close()
cv2.destroyAllWindows()
gallery.save()
print(f"done - {saved} templates")
