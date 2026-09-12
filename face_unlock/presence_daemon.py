import os
import sys
import time
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.presence import Presence, idle_seconds

user = os.getlogin()
engine = FastEngine()
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
gallery.load()
if not gallery.templates.get(user):
    gallery = Gallery(r"C:\ProgramData\NeoFace\faces.dat")
    gallery.load()

import cv2 as cv
det = cv.FaceDetectorYN.create("models/yunet.onnx", "", (320, 320), 0.6, 0.3, 5000)

presence = Presence(interval_s=45, strikes=2)
print(f"presence live for {user} - any face = stay, empty x2 = lock. Ctrl+C stops.")

while True:
    time.sleep(presence.interval_s)
    try:
        cap = cv.VideoCapture(0, cv.CAP_DSHOW)
        cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            continue
        h, w = frame.shape[:2]
        det.setInputSize((w, h))
        _, faces = det.detect(frame)
        found = faces is not None and len(faces) > 0
        if presence.tick(found):
            print("walked away - locked")
    except Exception as e:
        print(f"tick skipped: {e}")
