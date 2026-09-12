import os
import sys
import time
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from face_unlock.camera import Camera
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import vote

user = os.getlogin()
backend = os.environ.get("NEOFACE_BACKEND", "fast")
threshold = float(os.environ.get("NEOFACE_THRESHOLD", "0.35"))

gallery = Gallery(r"C:\ProgramData\NeoFace\faces.dat")
gallery.load()
fast_gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
fast_gallery.load()
gal = fast_gallery if backend == "fast" and fast_gallery.templates else gallery

engine = FastEngine() if backend == "fast" else None
if backend == "fast":
    engine.load()
else:
    from face_unlock.engine import FaceEngine
    engine = FaceEngine("models")
    engine.load()

cam = Camera(0, 640, 480)
print("hotkey F pressed - waking camera...")
cam.open()
for _ in range(5):
    cam.read()

print("Look here - scanning 5 frames...")
scores = []
times = []
for i in range(5):
    ok, f = cam.read()
    if not ok:
        continue
    h, w = f.shape[:2]
    if w > 640:
        f = cv2.resize(f, (640, int(h * 640 / w)))
    s = time.time()
    emb, face = engine.embed(f)
    dt = time.time() - s
    times.append(dt)
    if emb is None:
        print(f"frame {i+1}: no face ({dt:.2f}s)")
        continue
    sc = gal.best(user, emb)
    scores.append(sc)
    print(f"frame {i+1}: score {sc:.3f} ({dt:.2f}s)")

cam.close()
avg = sum(times) / len(times) if times else 0
if not scores:
    print(f"RESULT NO FACE - avg {avg:.2f}s/frame. Check light/distance.")
elif vote(scores, threshold, 2):
    print(f"RESULT UNLOCK user={user} best={max(scores):.3f} avg={avg:.2f}s/frame")
else:
    print(f"RESULT NO MATCH best={max(scores):.3f} scores={[round(s,3) for s in scores]} avg={avg:.2f}s/frame")
    print("Fallback: use PIN. Run Test again or re-enroll with --dir photos.")
