import sys
sys.path.insert(0, "face_unlock")

from camera import Camera
from engine import FaceEngine
from antispoof import SpoofGate
from matcher import vote
from store import Gallery
from auth import guide_for
from service import serve_loop

gallery = Gallery(r"%PROGRAMDATA%\NeoFace\faces.dat")
gallery.load()
engine = FaceEngine()
engine.load()
gate = SpoofGate()
gate.load()
cam = Camera()


def handle(req):
    if req.get("cmd") == "verify":
        user = req.get("user", "")
        if not cam.open():
            return {"ok": False, "reason": "camera-off"}
        scores = []
        for _ in range(5):
            ok, frame = cam.read()
            if not ok:
                continue
            emb, face = engine.embed(frame)
            if emb is None:
                continue
            scores.append(gallery.best(user, emb))
        cam.close()
        passed = vote(scores, 0.42, 3)
        return {"ok": passed, "scores": scores}
    return {"ok": False}


if __name__ == "__main__":
    serve_loop(handle)
