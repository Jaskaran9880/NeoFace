import os
import urllib.request

BASE = os.path.join(os.path.dirname(__file__), "..", "models")
BASE = os.path.abspath(BASE)
URLS = {
    "yunet.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "sface.onnx": "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "antifas_v2.onnx": "https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx/resolve/main/minifasnet_v2.onnx",
}

os.makedirs(BASE, exist_ok=True)
for name, url in URLS.items():
    out = os.path.join(BASE, name)
    if os.path.exists(out):
        print(f"exists {name}")
        continue
    print(f"downloading {name}...")
    urllib.request.urlretrieve(url, out)
    print(f"saved {out}")
print("done")
