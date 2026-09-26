import json
import math
import os
import shutil
import sys
import subprocess
import threading
import time
import secrets
import urllib.request
from functools import wraps

ROOT = os.path.abspath(os.path.dirname(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from flask import Flask, render_template, request, jsonify
from werkzeug.exceptions import HTTPException
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

    Rate limiting applies ONLY to failed auth attempts (brute-force
    protection): after _RATE_LIMIT_MAX bad attempts from an IP within
    _RATE_LIMIT_WINDOW seconds, further bad attempts get 429 with a
    Retry-After header. A request carrying a valid key always succeeds
    and clears that IP's failure history, so legitimate dashboard use
    (status polling, thumbnails, Setup checks) can never be blocked.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr or "unknown"
        provided = request.args.get("key") or request.headers.get("X-API-Key")
        if provided and _key_matches(provided):
            _clear_rate_limit(ip)
            return f(*args, **kwargs)
        # Missing or invalid key: count the failure, then enforce the limit.
        _record_auth_failure(ip)
        allowed, retry_after = _rate_limit_status(ip)
        if not allowed:
            resp = jsonify({"error": "Too many failed attempts. Try again in %d seconds." % retry_after})
            resp.status_code = 429
            resp.headers["Retry-After"] = str(retry_after)
            return resp
        return jsonify({"error": "Unauthorized - provide ?key= parameter or X-API-Key header"}), 401
    return decorated


# --- Rate Limiting ---
# In-memory limiter for FAILED auth attempts per IP. Valid-key requests
# are exempt (see require_api_key) so normal UI traffic is never bricked.
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_failures = {}  # ip -> [list of failure timestamps]


def _prune_failures(ip, now):
    """Drop expired failure timestamps for ip; remove the entry if empty."""
    failures = [t for t in _rate_limit_failures.get(ip, []) if now - t < _RATE_LIMIT_WINDOW]
    if failures:
        _rate_limit_failures[ip] = failures
    else:
        _rate_limit_failures.pop(ip, None)
    return failures


def _record_auth_failure(ip):
    """Record a failed auth attempt for the given IP."""
    _rate_limit_failures.setdefault(ip, []).append(time.time())


def _rate_limit_status(ip):
    """Return (allowed, retry_after_seconds) with the latest failure counted."""
    now = time.time()
    failures = _prune_failures(ip, now)
    if len(failures) < _RATE_LIMIT_MAX:
        return True, 0
    # Blocked until the oldest failure ages out of the window.
    retry_after = int(math.ceil(min(failures) + _RATE_LIMIT_WINDOW - now))
    return False, max(1, retry_after)


def _clear_rate_limit(ip):
    """A successful authentication clears the IP's failure history."""
    _rate_limit_failures.pop(ip, None)


def _key_matches(provided):
    """Constant-time API key comparison; never raises on odd input."""
    try:
        return secrets.compare_digest(provided.encode("utf-8"), API_KEY.encode("utf-8"))
    except Exception:
        return False


# --- JSON error responses for /api/* (never surface HTML error pages) ---
@app.errorhandler(HTTPException)
def _handle_http_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": e.description or e.name}), e.code
    return e


@app.errorhandler(Exception)
def _handle_unexpected_error(e):
    if request.path.startswith("/api/"):
        app.logger.exception("Unhandled error on %s", request.path)
        return jsonify({"error": str(e) or e.__class__.__name__}), 500
    return "Internal Server Error", 500

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


def _read_config_values():
    """Parse config.toml into {section: {key: raw_value}}.

    - Raw value text is kept verbatim (including quotes) for lossless
      round-trip writes when saving settings.
    - Section-aware so duplicate keys (engine vs camera `backend`,
      camera vs pipe `buffer_size`) never collide.
    - Skips malformed lines instead of aborting the whole parse.
    """
    sections = {}
    current = ""
    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current = line[1:-1].strip()
                    sections.setdefault(current, {})
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                sections.setdefault(current, {})[key.strip()] = val.strip()
    except OSError:
        pass
    return sections


def _flat_get(sections, key, default=None):
    """Flat last-wins lookup - mirrors how daemon_pipe._read_config scans keys."""
    val = default
    for kv in sections.values():
        if key in kv:
            val = kv[key]
    return val


def _raw_number(raw, cast, default):
    """Cast a raw config value to a number, tolerating quotes/comments."""
    if raw is None:
        return default
    try:
        return cast(str(raw).split("#", 1)[0].strip().strip('"'))
    except (ValueError, TypeError):
        return default


def _serialize_config(sections):
    """Serialize {section: {key: raw_value}} back to TOML text."""
    lines = []
    for name, kv in sections.items():
        if name:
            lines.append("[%s]" % name)
        for k, v in kv.items():
            lines.append("%s = %s" % (k, v))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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

    photo_exts = PHOTO_EXTS
    try:
        photos = [f for f in os.listdir(PHOTOS_DIR) if f.lower().endswith(photo_exts)]
    except OSError:
        photos = []
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


# --- Update check (GET /api/update/check) --------------------------------
# Read-only by contract: ONLY status/rev-parse/describe/remote/fetch/log/diff
# are ever executed - never pull, checkout, reset, clean, submodule or any
# config change. Every call is a list-arg subprocess (shell=False) with a hard
# timeout, UTF-8/errors=replace output and no console window.
FALLBACK_VERSION = "0.4.3"
UPDATE_CACHE_FILE = os.path.join(ROOT, ".update_cache.json")
UPDATE_CACHE_TTL = 300                 # soft TTL for the automatic page-load check
UPDATE_FAILURE_TTL = 60                # back off after a failed network attempt
UPDATE_STALE_MAX_AGE = 7 * 24 * 3600   # serve the last good result up to 7 days
UPDATE_FETCH_TIMEOUT = 15              # git fetch budget (seconds)
UPDATE_FORCE_MIN_INTERVAL = 30         # hard floor: force still can't hit the network more than once / 30s
GITHUB_API_BASE = "https://api.github.com/repos/Jaskaran9880/NeoFace"
GITHUB_USER_AGENT = "NeoFace-Dashboard"

# Origin allow-list, checked BEFORE any network call. Candidates are compared
# after _normalize_origin() (lowercase, trailing "/" and ".git" stripped).
ALLOWED_ORIGINS = (
    "https://github.com/jaskaran9880/neoface",
    "git@github.com:jaskaran9880/neoface",
    "ssh://git@github.com/jaskaran9880/neoface",
)

_UPDATE_LOCK = threading.Lock()   # single-flight: a concurrent check gets 429
_GIT_EXE = None                   # None = not probed yet, "" = not installed
_VERSION_MEMO = {"at": 0.0, "version": None, "sha": None}
_VERSION_LOCK = threading.Lock()

# Self-heal: drop a temp file leaked by a hard kill mid-write so it can never
# show up as an untracked file in git status.
try:
    if os.path.exists(UPDATE_CACHE_FILE + ".tmp"):
        os.remove(UPDATE_CACHE_FILE + ".tmp")
except OSError:
    pass


class UpdateError(Exception):
    """Update check failure with a stable code and a user-facing message.

    cacheable=True marks network failures so they can be cached for 60s and
    stop every page load from re-hitting a dead network.
    """

    def __init__(self, code, message=None, cacheable=False):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.cacheable = cacheable


def _git_exe():
    """Locate git.exe once: PATH first, then the usual Windows install paths."""
    global _GIT_EXE
    if _GIT_EXE is not None:
        return _GIT_EXE or None
    found = shutil.which("git")
    if not found:
        for candidate in (r"C:\Program Files\Git\cmd\git.exe",
                          r"C:\Program Files (x86)\Git\cmd\git.exe",
                          r"C:\Program Files\Git\bin\git.exe",
                          os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
            if os.path.isfile(candidate):
                found = candidate
                break
    _GIT_EXE = found or ""
    return found


def _git(args, timeout=5):
    """Run a read-only git command; returns (ok, stdout, stderr).

    List args + shell=False keep the command injection-free; timeouts stop a
    hung network call from blocking the dashboard; GIT_TERMINAL_PROMPT=0 and
    GCM_INTERACTIVE=never stop credential helpers from waiting for input;
    CREATE_NO_WINDOW stops a console flashing up on Windows.
    """
    exe = _git_exe()
    if not exe:
        return False, "", "git executable not found"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            [exe] + list(args),
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return False, "", "git %s timed out after %ss" % (args[0], timeout)
    except OSError as exc:
        return False, "", str(exc)
    return result.returncode == 0, result.stdout or "", result.stderr or ""


def _normalize_origin(url):
    """Lowercase an origin URL and strip trailing slash / .git suffix."""
    origin = (url or "").strip().lower().rstrip("/")
    if origin.endswith(".git"):
        origin = origin[:-4].rstrip("/")
    return origin


def _update_payload(mode="git", error=None):
    """Empty payload carrying every key of the /api/update/check contract."""
    return {
        "ok": mode != "none",
        "mode": mode,
        "checked_at": int(time.time()),
        "cached": False,
        "cache_age_s": 0,
        "local_sha": None,
        "local_version": None,
        "dirty": False,
        "remote_sha": None,
        "behind_count": None,
        "ahead_count": None,
        "up_to_date": False,
        "commits": [],
        "commits_truncated": False,
        "changes_summary": "",
        "impact": "none",
        "stale": False,
        "error": error,
    }


def _finalize(payload):
    """Apply contract invariants: ok and up_to_date are always derived."""
    payload["ok"] = payload.get("mode") != "none"
    payload["up_to_date"] = bool(payload["ok"] and payload.get("behind_count") == 0)
    if not payload.get("checked_at"):
        payload["checked_at"] = int(time.time())
    return payload


# --- update cache (.update_cache.json, atomic writes, 300s/60s/7d) -------
def _read_update_cache():
    """Read the cache -> {"success": ..., "failure": ...} or {} on any problem."""
    try:
        with open(UPDATE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _write_update_cache(data):
    """Atomic cache write: temp file in ROOT, then os.replace()."""
    tmp = UPDATE_CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, UPDATE_CACHE_FILE)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _save_update_cache(success=None, failure=None):
    """Merge-write the cache; a success clears any recorded failure."""
    data = _read_update_cache()
    now = int(time.time())
    if success is not None:
        data["success"] = {"saved_at": now, "payload": success}
        data["failure"] = None
    if failure is not None:
        data["failure"] = {"saved_at": now, "payload": failure}
    _write_update_cache(data)


def _cache_view(payload, now=None):
    """Serve a cached payload with cached/cache_age_s filled in."""
    now = now if now is not None else time.time()
    out = dict(payload)
    out["cached"] = True
    out["cache_age_s"] = int(max(0, now - (payload.get("checked_at") or now)))
    return out


def _fresh_cached_update(now=None):
    """Response for an auto (no ?force=1) call, or None when a re-check is due.

    Failures are honoured for 60s (network backoff); a good result for 300s.
    """
    now = now if now is not None else time.time()
    data = _read_update_cache()
    failure = data.get("failure")
    if isinstance(failure, dict) and isinstance(failure.get("payload"), dict):
        if now - (failure.get("saved_at") or 0) < UPDATE_FAILURE_TTL:
            return _cache_view(failure["payload"], now)
        return None  # backoff expired -> re-check so we recover promptly
    success = data.get("success")
    if isinstance(success, dict) and isinstance(success.get("payload"), dict):
        payload = success["payload"]
        if payload.get("ok") and now - (payload.get("checked_at") or 0) < UPDATE_CACHE_TTL:
            return _cache_view(payload, now)
    return None


def _stale_update_payload(now=None):
    """Last good result, if it is at most 7 days old (else None)."""
    now = now if now is not None else time.time()
    success = _read_update_cache().get("success") or {}
    payload = success.get("payload")
    if isinstance(payload, dict) and payload.get("ok"):
        age = now - (payload.get("checked_at") or 0)
        if 0 <= age <= UPDATE_STALE_MAX_AGE:
            return payload
    return None


def _stale_response(stale, err):
    """Last good result + stale flag + the error that blocked the refresh."""
    payload = dict(stale)
    payload["stale"] = True
    payload["error"] = err.message
    payload["cached"] = True
    payload["cache_age_s"] = int(max(0, time.time() - (payload.get("checked_at") or time.time())))
    _save_update_cache(failure=payload)   # 60s backoff before we hit the network again
    return _finalize(payload)


@app.route("/")
def index():
    return render_template("index.html", api_key=API_KEY)


@app.route("/api/status")
@require_api_key
def api_status():
    try:
        return jsonify(get_status())
    except Exception as e:
        # Never let a status failure become an HTML 500 page.
        return jsonify({"error": "Failed to load status: %s" % e}), 500


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
    try:
        files = os.listdir(PHOTOS_DIR)
    except OSError as e:
        return jsonify({"error": "Cannot access photos directory: %s" % e}), 500
    deleted = 0
    for f in files:
        if f.lower().endswith(PHOTO_EXTS):
            try:
                os.remove(os.path.join(PHOTOS_DIR, f))
                deleted += 1
            except OSError:
                continue
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
    # Flat last-wins lookup matches exactly what the daemon reads, so the
    # UI never shows a stale/default threshold the daemon isn't using.
    sections = _read_config_values()

    def _num(key, cast, default):
        return _raw_number(_flat_get(sections, key), cast, default)

    settings = {
        "threshold": _num("cosine_threshold", float, 0.35),
        "frames": _num("frames", int, 3),
        "hit_required": _num("hit_required", int, 2),
        "image_size": _num("image_size", int, 320),
        "camera_index": _num("index", int, 0),
        "camera_width": _num("width", int, 640),
        "camera_height": _num("height", int, 480),
    }
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
@require_api_key
def api_settings_save():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data"}), 400

    # Merge into the existing config instead of overwriting the whole file:
    # preserves unknown sections/keys (hotkey, paths, antispoof tuning,
    # pipe name, detector paths, ...) and daemon-critical keys such as
    # antispoof_threshold, which the old fixed template silently dropped.
    sections = _read_config_values()

    # Validate all inputs are numeric to prevent TOML injection.
    # Defaults fall back to the CURRENT config value (not hardcoded) so a
    # save from the UI never resets keys the form doesn't show.
    try:
        image_size = int(data.get('image_size', _raw_number(_flat_get(sections, "image_size"), int, 320)))
        frames = int(data.get('frames', _raw_number(_flat_get(sections, "frames"), int, 3)))
        hit_required = int(data.get('hit_required', _raw_number(_flat_get(sections, "hit_required"), int, 2)))
        threshold = float(data.get('threshold', _raw_number(_flat_get(sections, "cosine_threshold"), float, 0.35)))
        camera_index = int(data.get('camera_index', _raw_number(_flat_get(sections, "index"), int, 0)))
        camera_width = int(data.get('camera_width', _raw_number(_flat_get(sections, "width"), int, 640)))
        camera_height = int(data.get('camera_height', _raw_number(_flat_get(sections, "height"), int, 480)))
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

    def _set(section, key, value):
        """Set a managed key, removing stale copies elsewhere so the daemon's
        flat (last-wins) key match can't keep reading an old value."""
        for kv in sections.values():
            kv.pop(key, None)
        sections.setdefault(section, {})[key] = str(value)

    _set("fast", "image_size", image_size)
    _set("fast", "frames", frames)
    _set("fast", "hit_required", hit_required)
    _set("match", "cosine_threshold", threshold)
    _set("camera", "index", camera_index)
    _set("camera", "width", camera_width)
    _set("camera", "height", camera_height)

    # Daemon-critical keys must never disappear (see config.example.toml).
    if not any("antispoof_threshold" in kv for kv in sections.values()):
        sections.setdefault("match", {})["antispoof_threshold"] = "0.3"

    content = _serialize_config(sections)
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
    # Camera index may have changed - drop the cached detection result.
    global _camera_index_cache
    _camera_index_cache = None
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
        try:
            with open(log_file, "r", errors="ignore") as f:
                all_lines = f.readlines()
                content = "".join(all_lines[-lines:])
        except OSError:
            content = ""
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
        # Read threshold exactly like the daemon does (flat, last-wins).
        threshold = _raw_number(
            _flat_get(_read_config_values(), "cosine_threshold"), float, 0.35
        )
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
    data = request.get_json(silent=True) or {}
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
