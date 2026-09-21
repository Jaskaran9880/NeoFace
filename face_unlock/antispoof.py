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

    def real_score(self, face_crop, face_bbox=None):
        if not self.is_loaded:
            logger.error("SpoofGate FAIL-CLOSED: anti-spoof model not loaded, returning 0.0 (reject)")
            return 0.0
        try:
            # Crop face from frame if bbox provided
            if face_bbox is not None:
                x, y, fw, fh = int(face_bbox[0]), int(face_bbox[1]), int(face_bbox[2]), int(face_bbox[3])
                h, w = face_crop.shape[:2]
                x1 = max(0, x)
                y1 = max(0, y)
                x2 = min(w, x + fw)
                y2 = min(h, y + fh)
                face_crop = face_crop[y1:y2, x1:x2]

            # Resize to 80x80
            resized = cv2.resize(face_crop, (80, 80))

            # Model expects: [0, 255] range, BGR, NCHW
            # blobFromImage with scale=1.0 keeps [0,255], swapRB=False keeps BGR
            blob = cv2.dnn.blobFromImage(resized, 1.0, (80, 80), (0, 0, 0), swapRB=False)
            self.net.setInput(blob)
            out = self.net.forward().flatten()

            # Apply softmax to get probabilities
            exp_out = np.exp(out - np.max(out))
            softmax = exp_out / exp_out.sum()

            # Liveness score = 1 - (p[print] + p[replay])
            live_score = 1.0 - (softmax[1] + softmax[2])
            return float(live_score)
        except Exception as e:
            logger.error("SpoofGate inference failed, FAIL-CLOSED returning 0.0 (reject): %s", e)
            return 0.0
