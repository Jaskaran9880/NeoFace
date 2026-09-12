import os


class FaceEngine:
    def __init__(self, model_dir="models"):
        self.model_dir = model_dir
        self.app = None

    def load(self, device="auto"):
        from insightface.app import FaceAnalysis
        import onnxruntime as ort
        avail = ort.get_available_providers()
        order = []
        if device in ("auto", "4050"):
            order += ["CUDAExecutionProvider", "DmlExecutionProvider"]
        if device in ("auto", "igpu"):
            order += ["DmlExecutionProvider", "OpenVINOExecutionProvider"]
        order += ["CPUExecutionProvider"]
        use = next((p for p in order if p in avail), "CPUExecutionProvider")
        self.provider = use
        self.app = FaceAnalysis(name="buffalo_l", root=self.model_dir, providers=[use])
        self.app.prepare(ctx_id=0, det_size=(320, 320))
        print(f"FaceEngine on {use}")
        return True

    def embed(self, frame):
        faces = self.app.get(frame)
        if not faces:
            return None, None
        f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        return f.embedding, f
