import os
import sys
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery

user = os.getlogin()
engine = FastEngine()
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
gallery.load()

def load_image(p):
    img = cv2.imread(p)
    if img is not None:
        return img
    from pillow_heif import register_heif_opener
    register_heif_opener()
    from PIL import Image
    import numpy as np
    return cv2.cvtColor(np.array(Image.open(p).convert("RGB")), cv2.COLOR_RGB2BGR)

base = r"A:\Face Unlock For mypc\photos"
vids = [r"C:\Users\perve\Downloads\Blip Iphone Transfer\IMG_0894.MOV"]
saved = 0
if os.path.isdir(base):
    for n in os.listdir(base):
        if not n.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")):
            continue
        img = load_image(os.path.join(base, n))
        if img is None:
            continue
        h, w = img.shape[:2]
        if w > 640:
            img = cv2.resize(img, (640, int(h * 640 / w)))
        emb, face = engine.embed(img)
        if emb is None:
            print(f"no face {n}")
            continue
        gallery.add(user, emb)
        saved += 1
        print(f"saved {saved} {n}")

for vp in vids:
    if not os.path.exists(vp):
        continue
    cap = cv2.VideoCapture(vp)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, total // 10)
    for idx in range(0, total, step):
        if saved >= 20:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        if not ok:
            break
        h, w = img.shape[:2]
        if w > 640:
            img = cv2.resize(img, (640, int(h * 640 / w)))
        emb, face = engine.embed(img)
        if emb is None:
            continue
        gallery.add(user, emb)
        saved += 1
        print(f"saved {saved} video f{idx}")
    cap.release()

gallery.save()
print(f"done - {saved} fast templates for {user}")
