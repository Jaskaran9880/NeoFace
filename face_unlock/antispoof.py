import cv2
import numpy as np


class SpoofGate:
    def __init__(self, model_path="models/antifas_v2.onnx", threshold=0.7):
        self.model_path = model_path
        self.threshold = threshold
        self.net = None

    def load(self):
        try:
            self.net = cv2.dnn.readNetFromONNX(self.model_path)
            return True
        except Exception:
            return False

    def real_score(self, face_crop):
        if self.net is None:
            return 1.0
        blob = cv2.dnn.blobFromImage(face_crop, 1.0 / 255.0, (80, 80), (0, 0, 0), swapRB=True)
        self.net.setInput(blob)
        out = self.net.forward().flatten()
        return float(out[1] if len(out) > 1 else out[0])
