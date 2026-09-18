import os
import sys
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery

try:
    user = os.getlogin()
except OSError:
    user = os.environ.get("USERNAME", "default")
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

def embed_with_crop(engine, img):
    """Detect face at full resolution, crop, then embed."""
    h, w = img.shape[:2]
    eng = engine
    eng.det.setInputSize((w, h))
    _, faces = eng.det.detect(img)
    if faces is None or len(faces) == 0:
        return None, None
    f = max(faces, key=lambda x: x[2] * x[3])
    x, y, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
    pad = int(max(fw, fh) * 0.3)
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(w, x + fw + pad)
    y2 = min(h, y + fh + pad)
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return None, None
    crop = cv2.resize(crop, (112, 112))
    emb = eng.rec.feature(crop)
    return emb.flatten() if emb is not None else None, f

base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "photos")
vids = []
saved = 0
if os.path.isdir(base):
    for n in sorted(os.listdir(base)):
        if not n.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")):
            continue
        img = load_image(os.path.join(base, n))
        if img is None:
            continue
        emb, face = embed_with_crop(engine, img)
        if emb is None:
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
