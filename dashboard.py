import os
import sys
import subprocess
import time
import secrets

ROOT = os.path.abspath(os.path.dirname(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder=os.path.join(ROOT, "templates"))

# --- Authentication ---
# Dashboard API key: set NEOFACE_API_KEY env var, or it's auto-generated and
# written to NEOFACE_KEY_FILE on first launch so it persists across restarts.
NEOFACE_KEY_FILE = os.path.join(ROOT, ".dashboard_key")

def _load_or_create_api_key():
    """Return the dashboard API key, creating one if it doesn't exist."""
    if os.path.exists(NEOFACE_KEY_FILE):
        try:
            with open(NEOFACE_KEY_FILE, "r") as f:
                key = f.read().strip()
                if key:
                    return key
        except Exception:
            pass
    key = secrets.token_urlsafe(32)
    try:
        with open(NEOFACE_KEY_FILE, "w") as f:
            f.write(key)
    except Exception:
        pass
    return key

API_KEY = os.environ.get("NEOFACE_API_KEY") or _load_or_create_api_key()


def require_api_key(f):
    """Decorator: require ?key=... or X-API-Key header on every /api/* route.
    Includes rate limiting: after 5 failed attempts from an IP, return 429 for 60s.
    """
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        if not _check_rate_limit(ip):
            return jsonify({"error": "Too many failed attempts. Try again in 60 seconds."}), 429
        provided = request.args.get("key") or request.headers.get("X-API-Key")
        if not provided or not secrets.compare_digest(provided, API_KEY):
            _record_auth_failure(ip)
            return jsonify({"error": "Unauthorized - provide ?key= parameter or X-API-Key header"}), 401
        return f(*args, **kwargs)
    return decorated


# --- Rate Limiting ---
# Simple in-memory rate limiter for failed auth attempts per IP.
# After _RATE_LIMIT_MAX failures, the IP is blocked for _RATE_LIMIT_WINDOW seconds.
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_failures = {}  # ip -> [list of failure timestamps]


def _check_rate_limit(ip):
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    if ip not in _rate_limit_failures:
        return True
    # Prune old entries outside the window
    _rate_limit_failures[ip] = [t for t in _rate_limit_failures[ip] if now - t < _RATE_LIMIT_WINDOW]
    if not _rate_limit_failures[ip]:
        del _rate_limit_failures[ip]
        return True
    return len(_rate_limit_failures[ip]) < _RATE_LIMIT_MAX


def _record_auth_failure(ip):
    """Record a failed auth attempt for the given IP."""
    now = time.time()
    if ip not in _rate_limit_failures:
        _rate_limit_failures[ip] = []
    _rate_limit_failures[ip].append(now)

PHOTOS_DIR = os.path.join(ROOT, "photos")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")
LOGS_DIR = r"C:\ProgramData\NeoFace"
DAEMON_LOG = os.path.join(LOGS_DIR, "daemon.log")
CP_LOG = os.path.join(LOGS_DIR, "cp.log")
GALLERY_FAST = os.path.join(LOGS_DIR, "faces_fast.dat")
GALLERY_ACC = os.path.join(LOGS_DIR, "faces.dat")
CRED_BIN = os.path.join(LOGS_DIR, "cred.bin")
CONFIG_FILE = os.path.join(ROOT, "config.toml")
DLL_PATH = r"C:\Program Files\NeoFace\FaceUnlockCP.dll"

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)


_camera_index_cache = None

def _get_camera_index():
    """Read camera index from config, auto-detect if missing or broken. Cached after first success."""
    global _camera_index_cache
    if _camera_index_cache is not None:
        return _camera_index_cache
    idx = 0
    try:
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("index") and "=" in line:
                    idx = int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    try:
        import cv2
        cam = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        import time
        time.sleep(0.5)
        cam.grab()
        ok, frame = cam.read()
        cam.release()
        if ok and frame.mean() > 5:
            _camera_index_cache = idx
            return idx
    except Exception:
        pass
    for i in range(4):
        try:
            import cv2
            cam = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            import time
            time.sleep(0.5)
            cam.grab()
            ok, frame = cam.read()
            cam.release()
            if ok and frame.mean() > 5:
                _camera_index_cache = i
                return i
        except Exception:
            continue
    _camera_index_cache = idx
    return idx


def _find_daemon_pids():
    """Return list of PIDs for running daemon processes."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%' AND CommandLine LIKE '%daemon%'\" | Select-Object -Expand ProcessId"],
            capture_output=True, text=True, timeout=5
        )
        return [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    except Exception:
        return []


def get_status():
    status = {}

    model_map = {"yunet": "models/yunet.onnx", "sface": "models/sface.onnx", "antispoof": "models/antifas_v2.onnx"}
    status["models"] = {name: os.path.exists(os.path.join(ROOT, path)) for name, path in model_map.items()}
    status["models"]["all"] = all(status["models"].values())

    status["gallery"] = os.path.exists(GALLERY_FAST)
    status["gallery_templates"] = 0
    if status["gallery"]:
        try:
            from face_unlock.store import Gallery
            g = Gallery(GALLERY_FAST)
            g.load()
            status["gallery_templates"] = sum(len(v) for v in g.templates.values())
        except Exception:
            pass

    status["vault"] = os.path.exists(CRED_BIN)
    status["dll"] = os.path.exists(DLL_PATH)

    daemon_running = False
    daemon_pid = None
    try:
        import ctypes
        pids = _find_daemon_pids()
        daemon_running = len(pids) > 0
        daemon_pid = pids[0] if pids else None
    except Exception:
        pass
    status["daemon"] = {"running": daemon_running, "pid": daemon_pid}

    status["camera"] = {"available": False, "name": "unknown"}
    if not daemon_running:
        try:
            import cv2
            cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
            if cap.isOpened():
                status["camera"]["available"] = True
                status["camera"]["name"] = cap.getBackendName()
                cap.release()
        except Exception:
            pass
    else:
        status["camera"] = {"available": True, "name": "in use by daemon"}

    photo_exts = (".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")
    photos = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(photo_exts)]
    status["photos"] = {"count": len(photos), "files": photos}

    task_exists = False
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-ScheduledTask -TaskName 'NeoFace-Daemon' -ErrorAction SilentlyContinue | Select-Object -Expand TaskName"],
            capture_output=True, text=True, timeout=5
        )
        task_exists = "NeoFace-Daemon" in result.stdout
    except Exception:
        pass
    status["task"] = task_exists

    return status


@app.route("/")
def index():
    return render_template("index.html", api_key=API_KEY)


@app.route("/api/status")
@require_api_key
def api_status():
    return jsonify(get_status())


@app.route("/api/health")
@require_api_key
def api_health():
    return jsonify({"status": "ok", "version": "0.4.0"})


@app.route("/api/photos")
@require_api_key
def api_photos():
    photos = []
    try:
        files = os.listdir(PHOTOS_DIR)
    except PermissionError:
        return jsonify({"error": "Permission denied", "photos": []}), 403
    for f in sorted(files):
        if f.lower().endswith(PHOTO_EXTS):
            path = os.path.join(PHOTOS_DIR, f)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            photos.append({"name": f, "size": size, "size_kb": round(size / 1024, 1)})
    return jsonify({"photos": photos})


@app.route("/api/photos/upload", methods=["POST"])
@require_api_key
def api_photos_upload():
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400
    files = request.files.getlist("files")
    saved = 0
    for f in files:
        if f.filename:
            name = secure_filename(f.filename)
            if not name:
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext in PHOTO_EXTS:
                dest = os.path.join(PHOTOS_DIR, name)
                # Prevent overwrite: add numeric suffix if file already exists
                if os.path.exists(dest):
                    base, extension = os.path.splitext(name)
                    counter = 1
                    while os.path.exists(os.path.join(PHOTOS_DIR, f"{base}_{counter}{extension}")):
                        counter += 1
                    dest = os.path.join(PHOTOS_DIR, f"{base}_{counter}{extension}")
                f.save(dest)
                saved += 1
    return jsonify({"saved": saved})


@app.route("/api/photos/<name>", methods=["DELETE"])
@require_api_key
def api_photos_delete(name):
    safe_name = secure_filename(name)
    if not safe_name or safe_name != name:
        return jsonify({"error": "Invalid filename"}), 400
    path = os.path.join(PHOTOS_DIR, safe_name)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"deleted": safe_name})
    return jsonify({"error": "Photo not found"}), 404


@app.route("/api/photos/<name>/thumb")
@require_api_key
def api_photo_thumb(name):
    safe_name = secure_filename(name)
    if not safe_name or safe_name != name:
        return "Invalid filename", 400
    path = os.path.join(PHOTOS_DIR, safe_name)
    if not os.path.exists(path):
        return "Not found", 404
    ext = os.path.splitext(name)[1].lower()
    if ext in (".heic", ".heif"):
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            from PIL import Image
            import io
            img = Image.open(path).convert("RGB")
            img.thumbnail((400, 400))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            buf.seek(0)
            from flask import send_file
            return send_file(buf, mimetype="image/jpeg")
        except Exception:
            return "Preview not available", 404
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
        from flask import send_file
        return send_file(path)
    return "Unsupported format", 404


@app.route("/api/photos/clear", methods=["POST"])
@require_api_key
def api_photos_clear():
    deleted = 0
    for f in os.listdir(PHOTOS_DIR):
        if f.lower().endswith(PHOTO_EXTS):
            os.remove(os.path.join(PHOTOS_DIR, f))
            deleted += 1
    return jsonify({"deleted": deleted})


@app.route("/api/enroll", methods=["POST"])
@require_api_key
def api_enroll():
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "enroll_fast.py")],
            capture_output=True, text=True, timeout=120, cwd=ROOT
        )
        output = result.stdout + result.stderr
        success = "done" in output.lower()
        templates = 0
        for line in output.split("\n"):
            if "done" in line.lower() and "templates" in line.lower():
                parts = line.split()
                for i, p in enumerate(parts):
                    if p.isdigit() and i > 0 and parts[i - 1] == "-":
                        templates = int(p)
                        break
        return jsonify({"success": success, "output": output, "templates": templates})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Enrollment timed out (120s)"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
@require_api_key
def api_settings_get():
    settings = {
        "threshold": 0.35,
        "frames": 3,
        "hit_required": 2,
        "image_size": 320,
        "camera_index": 0,
        "camera_width": 640,
        "camera_height": 480,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("[") and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"')
                        if key == "cosine_threshold":
                            settings["threshold"] = float(val)
                        elif key == "frames":
                            settings["frames"] = int(val)
                        elif key == "hit_required":
                            settings["hit_required"] = int(val)
                        elif key == "image_size":
                            settings["image_size"] = int(val)
                        elif key == "index":
                            settings["camera_index"] = int(val)
        except Exception:
            pass
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
@require_api_key
def api_settings_save():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    # Validate all inputs are numeric to prevent TOML injection
    try:
        image_size = int(data.get('image_size', 320))
        frames = int(data.get('frames', 3))
        hit_required = int(data.get('hit_required', 2))
        threshold = float(data.get('threshold', 0.35))
        camera_index = int(data.get('camera_index', 0))
        camera_width = int(data.get('camera_width', 640))
        camera_height = int(data.get('camera_height', 480))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid settings values - all must be numeric"}), 400

    # Validate ranges
    if not (0.0 <= threshold <= 1.0):
        return jsonify({"error": "threshold must be between 0.0 and 1.0"}), 400
    if not (1 <= frames <= 30):
        return jsonify({"error": "frames must be between 1 and 30"}), 400
    if not (1 <= hit_required <= frames):
        return jsonify({"error": "hit_required must be between 1 and frames"}), 400
    if not (128 <= image_size <= 1024):
        return jsonify({"error": "image_size must be between 128 and 1024"}), 400
    if not (0 <= camera_index <= 10):
        return jsonify({"error": "camera_index must be between 0 and 10"}), 400

    content = f"""[engine]
backend = "fast"

[fast]
detector = "models/yunet.onnx"
recognizer = "models/sface.onnx"
image_size = {image_size}
frames = {frames}
hit_required = {hit_required}

[match]
cosine_threshold = {threshold}

[camera]
index = {camera_index}
width = {camera_width}
height = {camera_height}
fps = 30
codec = "MJPG"
backend = "DSHOW"
buffer_size = 1

[pipe]
name = "\\\\.\\pipe\\NeoFace"
max_instances = 1
buffer_size = 65536

[presence]
enabled = false
tick_seconds = 45
idle_timeout = 60
"""
    # Atomic write: write to temp file first, then use os.replace() for consistency
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_FILE), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, CONFIG_FILE)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return jsonify({"saved": True})


@app.route("/api/logs")
@require_api_key
def api_logs():
    log_type = request.args.get("type", "daemon")
    if log_type not in ("daemon", "cp"):
        return jsonify({"error": "Invalid log type - must be 'daemon' or 'cp'"}), 400
    try:
        lines = max(1, min(1000, int(request.args.get("lines", 100))))
    except (ValueError, TypeError):
        lines = 100
    log_file = DAEMON_LOG if log_type == "daemon" else CP_LOG
    content = ""
    if os.path.exists(log_file):
        with open(log_file, "r", errors="ignore") as f:
            all_lines = f.readlines()
            content = "".join(all_lines[-lines:])
    return jsonify({"content": content, "type": log_type})


@app.route("/api/logs/clear", methods=["POST"])
@require_api_key
def api_logs_clear():
    data = request.get_json(silent=True) or {}
    log_type = data.get("type", "daemon")
    if log_type not in ("daemon", "cp"):
        return jsonify({"error": "Invalid log type - must be 'daemon' or 'cp'"}), 400
    log_file = DAEMON_LOG if log_type == "daemon" else CP_LOG
    if os.path.exists(log_file):
        with open(log_file, "w") as f:
            pass
    return jsonify({"cleared": log_type})


@app.route("/api/test-scan", methods=["POST"])
@require_api_key
def api_test_scan():
    try:
        import cv2
        from face_unlock.fast import FastEngine
        from face_unlock.store import Gallery
        from face_unlock.matcher import cosine_score

        engine = FastEngine(
            os.path.join(ROOT, "models", "yunet.onnx"),
            os.path.join(ROOT, "models", "sface.onnx")
        )
        engine.load()

        gallery = Gallery(GALLERY_FAST)
        gallery.load()

        cam = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
        cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cam.isOpened():
            return jsonify({"error": "Camera not available"}), 500

        time.sleep(1.5)
        for _ in range(5):
            cam.read()
        time.sleep(0.05)

        frames = 0
        faces = 0
        scores = []
        for _ in range(3):
            ok, f = cam.read()
            if not ok:
                continue
            frames += 1
            h, w = f.shape[:2]
            if w > 640:
                f = cv2.resize(f, (640, int(h * 640 / w)))
            emb, face = engine.embed(f)
            if face is not None:
                faces += 1
            if emb is None:
                continue
            user = os.getlogin()
            cands = [c for c in gallery.templates.get(user, []) if len(c) == len(emb)]
            if cands:
                scores.append(round(max(cosine_score(emb, c) for c in cands), 3))

        cam.release()

        best = max(scores) if scores else 0
        threshold = 0.35
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    for line in f:
                        if "cosine_threshold" in line:
                            threshold = float(line.split("=")[1].strip())
            except Exception:
                pass
        ok = best >= threshold and len(scores) >= 2

        return jsonify({
            "frames": frames,
            "faces": faces,
            "scores": scores,
            "best": best,
            "threshold": threshold,
            "result": "OK" if ok else "FAIL"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/setup/models", methods=["POST"])
@require_api_key
def api_setup_models():
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "fetch_fast.py")],
            capture_output=True, text=True, timeout=300, cwd=ROOT
        )
        models = {
            "yunet": os.path.exists(os.path.join(ROOT, "models", "yunet.onnx")),
            "sface": os.path.exists(os.path.join(ROOT, "models", "sface.onnx")),
            "antispoof": os.path.exists(os.path.join(ROOT, "models", "antifas_v2.onnx")),
        }
        all_ok = all(models.values())
        return jsonify({"success": all_ok, "models": models, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/setup/password", methods=["POST"])
@require_api_key
def api_setup_password():
    data = request.get_json()
    password = data.get("password", "")
    if not password:
        return jsonify({"error": "No password provided"}), 400
    try:
        import win32crypt
        import socket
        domain = os.environ.get("USERDOMAIN", socket.gethostname())
        user = os.environ.get("USERNAME", "perve")
        raw = f"{domain}\n{user}\n{password}".encode("utf-8")
        encrypted = win32crypt.CryptProtectData(raw, None, None, None, None, 0x04)
        os.makedirs(os.path.dirname(CRED_BIN), exist_ok=True)
        with open(CRED_BIN, "wb") as f:
            f.write(encrypted)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/setup/daemon", methods=["POST"])
@require_api_key
def api_setup_daemon():
    try:
        ps_cmd = """
$pyw = Join-Path (Split-Path (Get-Command python).Source) "pythonw.exe"
$script = "${ROOT}\\face_unlock\\daemon_pipe.py"
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$script`""
$trig = New-ScheduledTaskTrigger -AtLogOn
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Unregister-ScheduledTask -TaskName "NeoFace-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName "NeoFace-Daemon" -Action $act -Trigger $trig -Settings $set -Principal $principal -Force | Out-Null
Write-Host "OK"
"""
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30
        )
        success = "OK" in result.stdout
        return jsonify({"success": success, "output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/daemon/start", methods=["POST"])
@require_api_key
def api_daemon_start():
    try:
        subprocess.run(
            ["powershell", "-Command", "Start-ScheduledTask -TaskName 'NeoFace-Daemon'"],
            capture_output=True, timeout=10
        )
        return jsonify({"started": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/daemon/stop", methods=["POST"])
@require_api_key
def api_daemon_stop():
    try:
        subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%' AND CommandLine LIKE '%daemon%'\" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            capture_output=True, timeout=10
        )
        return jsonify({"stopped": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/troubleshoot/<component>", methods=["POST"])
@require_api_key
def api_troubleshoot(component):
    results = {}

    if component == "camera" or component == "all":
        try:
            import cv2
            cap = cv2.VideoCapture(_get_camera_index(), cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok = cap.isOpened()
            if ok:
                ret, f = cap.read()
                if ret:
                    h, w = f.shape[:2]
                    results["camera"] = {"ok": True, "resolution": f"{w}x{h}", "read_ok": True}
                else:
                    results["camera"] = {"ok": False, "error": "Camera opened but cannot read frames"}
            else:
                results["camera"] = {"ok": False, "error": "Camera failed to open"}
        except Exception as e:
            results["camera"] = {"ok": False, "error": str(e)}
        finally:
            try:
                cap.release()
            except Exception:
                pass

    if component == "engine" or component == "all":
        try:
            from face_unlock.fast import FastEngine
            import numpy as np
            eng = FastEngine(
                os.path.join(ROOT, "models", "yunet.onnx"),
                os.path.join(ROOT, "models", "sface.onnx")
            )
            eng.load()
            dummy = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            emb, face = eng.embed(dummy)
            results["engine"] = {"ok": True, "embedding_dim": len(emb) if emb is not None else 0, "face_detected": face is not None}
        except Exception as e:
            results["engine"] = {"ok": False, "error": str(e)}

    if component == "gallery" or component == "all":
        try:
            from face_unlock.store import Gallery
            g = Gallery(GALLERY_FAST)
            g.load()
            total = sum(len(v) for v in g.templates.values())
            users = list(g.templates.keys())
            results["gallery"] = {"ok": total > 0, "templates": total, "users": users}
        except Exception as e:
            results["gallery"] = {"ok": False, "error": str(e)}

    if component == "pipe" or component == "all":
        try:
            import win32pipe
            win32pipe.WaitNamedPipe(r"\\.\pipe\NeoFace", 1000)
            results["pipe"] = {"ok": True, "message": "Pipe is listening"}
        except Exception:
            results["pipe"] = {"ok": False, "message": "Pipe not available (daemon may be stopped)"}

    if component == "vault" or component == "all":
        ok = os.path.exists(CRED_BIN)
        results["vault"] = {"ok": ok, "message": "Password vault exists" if ok else "No vault found"}

    if component == "dll" or component == "all":
        ok = os.path.exists(DLL_PATH)
        results["dll"] = {"ok": ok, "message": "DLL registered" if ok else "DLL not installed"}

    if component == "daemon" or component == "all":
        running = False
        pid = None
        try:
            pids = _find_daemon_pids()
            running = len(pids) > 0
            pid = pids[0] if pids else None
        except Exception:
            pass
        results["daemon"] = {"ok": running, "pid": pid, "message": f"Running (PID {pid})" if running else "Not running"}

    return jsonify(results)


if __name__ == "__main__":
    print("=" * 50)
    print("  NeoFace Dashboard")
    print("  http://localhost:8080")
    print("  API key loaded from .dashboard_key")
    print("  Use ?key=<key> or header X-API-Key: <key>")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    app.run(host="127.0.0.1", port=8080, debug=False)
