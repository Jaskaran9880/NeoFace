import os
from insightface.app import FaceAnalysis

out = os.path.join(os.path.dirname(__file__), "..", "models")
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)
print("downloading buffalo_l to", out)
app = FaceAnalysis(name="buffalo_l", root=out, providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=(640, 640))
print("done - check", out)
