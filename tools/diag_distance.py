"""Distance/detection sweep for the NeoFace YuNet detector + SFace matcher.

Usage: python tools\\diag_distance.py [camera_index] [frames_per_variant]

For each camera resolution the daemon could use (640x480, 1280x720) this
captures live frames and reports, for the daemon's CURRENT pipeline (frame
shrunk to 320px wide, score threshold 0.6) and for full-resolution variants
(thresholds 0.6 and 0.5):

  - detection rate over N frames
  - face bounding-box pixel size (what distance costs)
  - detector confidence
  - cosine match vs the enrolled gallery (does it still clear 0.45?)
  - anti-spoof real_score (does it still clear 0.3?)

One sample frame per resolution is saved to %TEMP% for visual inspection.

Read-only: opens the camera, writes only sample PNGs to %TEMP%, never
touches config/vault/state. The daemon must be idle (no lock-screen scan
running) or the two will fight over the webcam.
"""
import os
import sys
import time

import cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import cosine_score
from face_unlock.antispoof import SpoofGate

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 0
FRAMES = int(sys.argv[2]) if len(sys.argv) > 2 else 8
USER = os.getlogin()
GALLERY = r"C:\ProgramData\NeoFace\faces_fast.dat"


def open_cam(index, w, h):
    cam = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cam.set(cv2.CAP_PROP_FPS, 30)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    time.sleep(1.2)
    for _ in range(5):
        cam.read()
    return cam


def record(st, faces, frame, engine, cands, spoof):
    if faces is None or len(faces) == 0:
        st["det"].append(0)
        return
    face = max(faces, key=lambda x: x[2] * x[3])
    st["det"].append(1)
    st["size"].append((int(face[2]), int(face[3])))
    # YuNet row = [x, y, w, h, *10 landmarks, score]: score is LAST.
    st["dscore"].append(float(face[-1]))
    try:
        aligned = engine.rec.alignCrop(frame, face)
        emb = engine.rec.feature(aligned).flatten()
        pairs = [cosine_score(emb, c) for c in cands if len(c) == len(emb)]
        if pairs:
            st["match"].append(max(pairs))
    except Exception:
        pass
    try:
        st["spoof"].append(spoof.real_score(frame, face_bbox=face))
    except Exception:
        pass


def fmt_range(vals):
    if not vals:
        return "-"
    return "%.2f-%.2f" % (min(vals), max(vals))


def main():
    engine = FastEngine(os.path.join(ROOT, "models", "yunet.onnx"),
                        os.path.join(ROOT, "models", "sface.onnx"))
    engine.load()
    gal = Gallery(GALLERY)
    gal.load()
    cands = gal.templates.get(USER, [])
    spoof = SpoofGate(os.path.join(ROOT, "models", "antifas_v2.onnx"), 0.3)
    spoof.load()
    det320 = cv2.FaceDetectorYN.create(
        os.path.join(ROOT, "models", "yunet.onnx"), "", (320, 240), 0.6, 0.3, 5000)
    print("user=%s gallery_templates=%d antispoof_loaded=%s"
          % (USER, len(cands), spoof.is_loaded))

    # This camera ignores requested sizes and always delivers 1280x720.
    for target_w, target_h in ((1280, 720),):
        cam = open_cam(INDEX, target_w, target_h)
        if not cam.isOpened():
            print("camera %d failed to open at %dx%d" % (INDEX, target_w, target_h))
            continue

        variants = {}
        saved = False
        got = 0
        deadline = time.time() + 45
        while got < FRAMES and time.time() < deadline:
            ok, f = cam.read()
            if not ok or f is None:
                continue
            got += 1
            h, w = f.shape[:2]
            if not saved:
                out = os.path.join(os.environ.get("TEMP", "."),
                                   "neoface_distance_%dx%d.png" % (w, h))
                try:
                    cv2.imwrite(out, f)
                    print("sample frame -> %s" % out)
                except Exception:
                    pass
                saved = True

            f320 = cv2.resize(f, (320, int(h * 320 / w)))
            det320.setInputSize((320, f320.shape[0]))
            det320.setScoreThreshold(0.6)
            _, faces = det320.detect(f320)
            key = "daemon_now  320w  thr0.6"
            st = variants.setdefault(key, {"det": [], "size": [], "dscore": [],
                                           "match": [], "spoof": []})
            record(st, faces, f320, engine, cands, spoof)

            for thr in (0.6, 0.5):
                engine.det.setInputSize((w, h))
                engine.det.setScoreThreshold(thr)
                _, faces = engine.det.detect(f)
                key = "full %dx%d thr%.1f" % (w, h, thr)
                st = variants.setdefault(key, {"det": [], "size": [], "dscore": [],
                                               "match": [], "spoof": []})
                record(st, faces, f, engine, cands, spoof)
        cam.release()

        print("--- actual %dx%d, %d frames ---" % (w, h, got))
        for key, st in variants.items():
            det_n = sum(st["det"])
            if st["size"]:
                avg_w = sum(s[0] for s in st["size"]) // len(st["size"])
                avg_h = sum(s[1] for s in st["size"]) // len(st["size"])
                face_s = "%dx%dpx" % (avg_w, avg_h)
            else:
                face_s = "-"
            print("%-26s det %d/%d | face %-9s | det_score %-11s | "
                  "match %-11s | spoof %s"
                  % (key, det_n, got, face_s, fmt_range(st["dscore"]),
                     fmt_range(st["match"]), fmt_range(st["spoof"])))


if __name__ == "__main__":
    main()
