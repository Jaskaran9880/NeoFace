"""One-shot anti-spoof diagnostic: capture frames + scores like the daemon does."""
import os
import sys
import time

import cv2

sys.path.insert(0, r"C:\NeoFace")
from face_unlock.fast import FastEngine
from face_unlock.antispoof import SpoofGate
from face_unlock.liveness import LivenessChecker

OUT = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "neoface_diag")
os.makedirs(OUT, exist_ok=True)

engine = FastEngine(r"C:\NeoFace\models\yunet.onnx", r"C:\NeoFace\models\sface.onnx")
engine.load()
spoof = SpoofGate(r"C:\NeoFace\models\antifas_v2.onnx", threshold=0.3)
assert spoof.load(), "spoof model failed"
liveness = LivenessChecker()

for idx in (0, 1):
    cam = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print(f"camera {idx}: cannot open")
        continue
    cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cam.set(cv2.CAP_PROP_FPS, 30)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    time.sleep(1)
    ok0, probe = cam.read()
    if not ok0 or probe is None or probe.mean() < 5:
        print(f"camera {idx}: no frame ({ok0})")
        cam.release()
        continue
    print(f"camera {idx}: open OK")
    for _ in range(5):
        cam.grab()
    time.sleep(0.05)

    rows = []
    saved = 0
    for i in range(40):
        ok, frame = cam.read()
        if not ok:
            rows.append((i, "read-fail", None, None, None, None))
            continue
        h, w = frame.shape[:2]
        if w > 320:
            frame = cv2.resize(frame, (320, int(h * 320 / w)))
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lv = liveness.check_temporal_consistency(gray)
        emb, face = engine.embed(frame)
        if face is None:
            rows.append((i, "no-face", round(frame.mean(), 1), None, round(lv, 2), None))
            continue
        x, y, fw, fh = (int(v) for v in face[:4])
        crop = frame[max(0, y):y + fh, max(0, x):x + fw]
        crop_mean = float(crop.mean()) if crop.size else 0.0
        real = spoof.real_score(frame, face_bbox=face)
        rows.append((i, "face", round(frame.mean(), 1), round(crop_mean, 1),
                     round(float(lv), 2), round(float(real), 3)))
        if saved < 3 and i % 15 == 0:
            cv2.imwrite(os.path.join(OUT, f"cam{idx}_frame{i}.png"), frame)
            cv2.imwrite(os.path.join(OUT, f"cam{idx}_crop{i}.png"), crop)
            saved += 1
        time.sleep(0.05)
    cam.release()

    print(f"--- camera {idx} (frame_mean / face_mean / liveness / real_score) ---")
    for r in rows:
        print("  ", r)
    reals = [r[5] for r in rows if r[5] is not None]
    if reals:
        print(f"camera {idx}: real_score min={min(reals)} max={max(reals)} "
              f"pass(>=0.3)={sum(1 for v in reals if v >= 0.3)}/{len(reals)}")
    print(f"samples in {OUT}")
