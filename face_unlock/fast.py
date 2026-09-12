import cv2
import numpy as np


class FastEngine:
    def __init__(self, det_path="models/yunet.onnx", rec_path="models/sface.onnx"):
        self.det_path = det_path
        self.rec_path = rec_path
        self.det = None
        self.rec = None

    def load(self):
        self.det = cv2.FaceDetectorYN.create(self.det_path, "", (320, 320), 0.6, 0.3, 5000)
        self.rec = cv2.FaceRecognizerSF.create(self.rec_path, "")
        return True

    def embed(self, frame):
        h, w = frame.shape[:2]
        self.det.setInputSize((w, h))
        _, faces = self.det.detect(frame)
        if faces is None or len(faces) == 0:
            return None, None
        f = max(faces, key=lambda x: x[2] * x[3])
        aligned = self.rec.alignCrop(frame, f)
        emb = self.rec.feature(aligned)
        return emb.flatten(), f

    @staticmethod
    def score(a, b):
        a = a / (np.linalg.norm(a) + 1e-9)
        b = b / (np.linalg.norm(b) + 1e-9)
        return float(np.dot(a, b))
