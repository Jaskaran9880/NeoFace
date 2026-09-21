AI models are downloaded here by `tools/fetch_fast.py`.

## Files
- `yunet.onnx` - YuNet face detector (232KB)
- `sface.onnx` - SFace face recognizer (37MB)
- `antifas_v2.onnx` - MiniFASNetV2 anti-spoof model (1.7MB)

## Download
```powershell
python tools\fetch_fast.py
```

Models are downloaded from OpenCV Zoo and HuggingFace, and are not included in the git repository.
