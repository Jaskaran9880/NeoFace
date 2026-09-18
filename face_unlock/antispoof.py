import logging
import cv2
import numpy as np

logger = logging.getLogger("neoface.antispoof")


class SpoofGate:
    def __init__(self, model_path="models/antifas_v2.onnx", threshold=0.7):
        self.model_path = model_path
        self.threshold = threshold
        self.net = None
        self._available = False

    def load(self):
        try:
            self.net = cv2.dnn.readNetFromONNX(self.model_path)
            self._available = True
            return True
        except Exception:
            self._available = False
            return False

    @property
    def is_loaded(self):
        return self._available and self.net is not None

    def real_score(self, face_crop):
        if not self.is_loaded:
            logger.warning("SpoofGate bypassed: anti-spoof model not loaded, returning default score 1.0")
            return 1.0
        try:
            blob = cv2.dnn.blobFromImage(face_crop, 1.0 / 255.0, (80, 80), (0, 0, 0), swapRB=True)
            self.net.setInput(blob)
            out = self.net.forward().flatten()
            return float(out[1] if len(out) > 1 else out[0])
        except Exception:
            logger.warning("SpoofGate inference failed, returning default score 1.0")
            return 1.0
