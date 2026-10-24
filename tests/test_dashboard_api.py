#!/usr/bin/env python3
"""NeoFace dashboard API test suite.

================================================================================
  DESTRUCTIVE TESTS ARE OPT-IN - READ THIS FIRST
================================================================================
By default this suite runs READ-ONLY checks only (health, status, photos GET,
settings GET, logs GET, read-only troubleshoot [15]-[20], update-check 27-32,
static XSS guard, the scheduled-task read-only query [40], the in-process
unit tests [34]-[35], the update-notifier unit tests [41], the camera
settle/warmup unit tests [44]-[46], the updater unit tests [47]-[49] and the
update-cadence checks [50]).

Tests [5] [6] [7] [8] [10] [11] [12] [13] [14] [23] [24] [25] [26] [27] have SIDE
EFFECTS on the live install (config, camera, model downloads, daemon, logs,
photos) and are SKIPPED unless the env flag is set:

    PowerShell:  $env:NEOFACE_TEST_DESTRUCTIVE = "1"; python test_dashboard_api.py
    cmd:         set NEOFACE_TEST_DESTRUCTIVE=1 && python test_dashboard_api.py
    bash:        NEOFACE_TEST_DESTRUCTIVE=1 python test_dashboard_api.py
    Off again:   Remove-Item Env:NEOFACE_TEST_DESTRUCTIVE   (or set to 0)

What a destructive run touches (do NOT enable casually):
    [5]  POST /api/settings   - rewrites config.toml (threshold etc).
                                Backed up and RESTORED automatically.
    [6]  POST /api/test-scan  - grabs the camera
    [7]  POST /api/enroll     - rebuilds the face gallery templates
    [8]  POST /api/setup/models - runs tools/fetch_fast.py: downloads ~40MB
                                of models when any model file is missing
    [9]  POST /api/setup/password - SAFE: asserts the Windows Hello consent
                                gate rejects a save without a token (403)
    [10] POST /api/setup/daemon   - re-registers the scheduled task
    [11] POST /api/daemon/start   - starts the daemon
    [12] POST /api/daemon/stop    - STOPS the daemon
    [13] POST /api/troubleshoot/all - opens the camera: the "all" branch runs
                                the same cv2.VideoCapture probe as [6]/[14]
    [14] POST /api/troubleshoot/camera - opens the camera
    [23] POST /api/logs/clear     - truncates daemon/cp logs
    [24] POST /api/photos/upload  - uploads a test photo
    [25] DELETE /api/photos/...   - deletes a photo
    [26] POST /api/photos/clear   - DELETES THE ENTIRE PHOTO GALLERY
    [27] POST /api/update/apply   - stages a fake "installing"
                                apply_state.json (backed up + RESTORED) to
                                assert the 409 double-apply guard; it never
                                starts a real update

Skipped tests are reported as SKIP in the summary table.
================================================================================
"""

import requests
import json
import os
import re
import sys
import base64
import time
from datetime import datetime

BASE_URL = "http://127.0.0.1:8080"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEY_FILE = os.path.join(_REPO_ROOT, ".dashboard_key")
if not os.path.exists(_KEY_FILE):
    print("ERROR: .dashboard_key not found - start the dashboard once so it can create one")
    sys.exit(1)
with open(_KEY_FILE) as _kf:
    KEY = _kf.read().strip()

results = []

# ── Destructive test gate ─────────────────────────────────────────────
# True only when NEOFACE_TEST_DESTRUCTIVE=1 (exact match). Default: off.
DESTRUCTIVE_ENABLED = os.environ.get("NEOFACE_TEST_DESTRUCTIVE") == "1"


def destructive(n, endpoint, method):
    """Gate for tests that mutate the live install (config/vault/photos/daemon).

    Returns True when NEOFACE_TEST_DESTRUCTIVE=1 is set; otherwise prints a
    SKIP notice, records a SKIP row for the summary table, and returns False
    so the caller's block is skipped.
    """
    if DESTRUCTIVE_ENABLED:
        return True
    try:
        print("  [SKIP] destructive test %d \u2014 set NEOFACE_TEST_DESTRUCTIVE=1 to run" % n)
    except UnicodeEncodeError:
        # Legacy console codepage without the em dash - keep the notice ASCII.
        print("  [SKIP] destructive test %d - set NEOFACE_TEST_DESTRUCTIVE=1 to run" % n)
    log_result(endpoint, method, "-", "SKIP",
               "destructive test %d skipped - set NEOFACE_TEST_DESTRUCTIVE=1" % n)
    return False


def log_result(endpoint, method, status_code, pass_fail, notes):
    results.append({
        "endpoint": endpoint,
        "method": method,
        "status_code": str(status_code),
        "pass_fail": pass_fail,
        "notes": notes
    })
    if pass_fail == "PASS":
        symbol = "OK  "
    elif pass_fail == "SKIP":
        symbol = "SKIP"
    else:
        symbol = "FAIL"
    print("  [%s] %s %s -> %s [%s] %s" % (symbol, method, endpoint, status_code, pass_fail, notes))


def test_get(endpoint, expected_status=None, extra_params=None):
    # F5: the API key travels in the X-API-Key header (require_api_key reads
    # ?key= OR the header), never in the query string, so it cannot leak into
    # Werkzeug access logs during test runs. extra_params stays in the URL.
    params = dict(extra_params) if extra_params else {}
    headers = {"X-API-Key": KEY}
    try:
        r = requests.get("%s%s" % (BASE_URL, endpoint), params=params,
                         headers=headers, timeout=15)
        status = r.status_code
        body = ""
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]

        if expected_status and status != expected_status:
            log_result(endpoint, "GET", status, "FAIL", "Expected %s, body: %s" % (expected_status, body))
        else:
            log_result(endpoint, "GET", status, "PASS", "body: %s" % body)
        return body
    except Exception as e:
        log_result(endpoint, "GET", "ERR", "FAIL", str(e)[:200])
        return None


def test_post(endpoint, json_data=None, expected_status=None, files=None):
    # F5: key in the X-API-Key header, not ?key= in the URL (no key in logs).
    headers = {"X-API-Key": KEY}
    try:
        if files:
            r = requests.post("%s%s" % (BASE_URL, endpoint), headers=headers,
                              files=files, timeout=30)
        else:
            r = requests.post("%s%s" % (BASE_URL, endpoint), headers=headers,
                              json=json_data, timeout=30)

        status = r.status_code
        body = ""
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]

        if expected_status and status != expected_status:
            log_result(endpoint, "POST", status, "FAIL", "Expected %s, body: %s" % (expected_status, body))
        else:
            log_result(endpoint, "POST", status, "PASS", "body: %s" % body)
        return body
    except Exception as e:
        log_result(endpoint, "POST", "ERR", "FAIL", str(e)[:200])
        return None


def test_delete(endpoint, expected_status=None):
    # F5: key in the X-API-Key header, not ?key= in the URL (no key in logs).
    headers = {"X-API-Key": KEY}
    try:
        r = requests.delete("%s%s" % (BASE_URL, endpoint), headers=headers, timeout=10)
        status = r.status_code
        body = ""
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]

        if expected_status and status != expected_status:
            log_result(endpoint, "DELETE", status, "FAIL", "Expected %s, body: %s" % (expected_status, body))
        else:
            log_result(endpoint, "DELETE", status, "PASS", "body: %s" % body)
        return body
    except Exception as e:
        log_result(endpoint, "DELETE", "ERR", "FAIL", str(e)[:200])
        return None


# ── F20 helpers: config.toml assertions (destructive test [5] only) ──
def _toml_flat_get(raw, key):
    """Flat, last-wins lookup of `key` anywhere in a TOML document.

    Mirrors dashboard._flat_get / daemon_pipe._read_config (flat scan,
    last occurrence wins), but returns the PARSED value via tomllib so the
    F20 assertion compares what the daemon actually loads.
    `raw` is bytes or str; returns None when the key is absent (TOML has no
    null, so None is unambiguous). Raises ValueError on an unparseable file.
    """
    import tomllib  # stdlib since Python 3.11 - repo runs 3.12, no new deps
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = tomllib.loads(raw)
    found = None
    for section in data.values():
        if isinstance(section, dict) and key in section:
            found = section[key]
    return found


def _toml_values_equal(a, b):
    """True when two parsed TOML values are the same (numeric-tolerant)."""
    if (isinstance(a, (int, float)) and isinstance(b, (int, float))
            and not isinstance(a, bool) and not isinstance(b, bool)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


print("=" * 80)
print("  NeoFace Dashboard API Test Suite")
print("  Time: %s" % datetime.now().isoformat())
print("  Target: %s" % BASE_URL)
print("  Key: %s...%s" % (KEY[:6], KEY[-4:]))
if DESTRUCTIVE_ENABLED:
    print("  Mode: DESTRUCTIVE tests ENABLED (NEOFACE_TEST_DESTRUCTIVE=1)")
else:
    print("  Mode: read-only - destructive tests SKIPPED "
          "(set NEOFACE_TEST_DESTRUCTIVE=1 to run them)")
print("=" * 80)

# ── 1. GET /api/health ─────────────────────────────────────────────
print("\n[1] GET /api/health")
test_get("/api/health", expected_status=200)

# ── 2. GET /api/status ─────────────────────────────────────────────
print("\n[2] GET /api/status")
test_get("/api/status", expected_status=200)

# ── 3. GET /api/photos ─────────────────────────────────────────────
print("\n[3] GET /api/photos")
photos_resp = test_get("/api/photos", expected_status=200)

# ── 4. GET /api/settings ───────────────────────────────────────────
print("\n[4] GET /api/settings")
test_get("/api/settings", expected_status=200)

# ── 5. POST /api/settings ──────────────────────────────────────────
# DESTRUCTIVE: rewrites config.toml (threshold -> 0.35, frames, ...).
# The original config.toml is backed up first and restored afterwards so
# an opt-in run never leaves the install with changed settings.
# F20: after a SUCCESSFUL save, config.toml must still contain the
# daemon-critical antispoof_threshold with its pre-test value - that is the
# entire point of the api_settings_save() merge-write fix. Checked BEFORE
# the finally-restore below.
print("\n[5] POST /api/settings")
if destructive(5, "/api/settings", "POST"):
    # Key names must match what dashboard.api_settings_save() reads:
    # camera_width / camera_height. The old resolution_w / resolution_h
    # names are silently ignored by the endpoint (verified in dashboard.py).
    settings_body = {
        "threshold": 0.35,
        "frames": 3,
        "hit_required": 2,
        "camera_index": 0,
        "camera_width": 640,
        "camera_height": 480
    }
    _cfg_path = os.path.join(_REPO_ROOT, "config.toml")
    _cfg_backup = None
    _antispoof_before = None
    if os.path.exists(_cfg_path):
        with open(_cfg_path, "rb") as _cf:
            _cfg_backup = _cf.read()
        try:
            _antispoof_before = _toml_flat_get(_cfg_backup, "antispoof_threshold")
        except Exception as _e:
            log_result("/api/settings#pre", "POST", "-", "FAIL",
                       "cannot parse config.toml before save: %s" % str(_e)[:150])
    try:
        _settings_resp = test_post("/api/settings", json_data=settings_body,
                                   expected_status=200)
        # F20 assertion - only meaningful once the save actually happened.
        if isinstance(_settings_resp, dict) and _settings_resp.get("saved"):
            if not os.path.exists(_cfg_path):
                log_result("/api/settings#merge", "POST", "-", "FAIL",
                           "config.toml missing after save - cannot verify merge write")
            else:
                try:
                    with open(_cfg_path, "rb") as _cf:
                        _antispoof_after = _toml_flat_get(_cf.read(),
                                                          "antispoof_threshold")
                    if _antispoof_after is None:
                        log_result("/api/settings#merge", "POST", "-", "FAIL",
                                   "antispoof_threshold vanished after save "
                                   "(merge-write regression); pre-test value: %r"
                                   % (_antispoof_before,))
                    elif _antispoof_before is not None and not _toml_values_equal(
                            _antispoof_before, _antispoof_after):
                        log_result("/api/settings#merge", "POST", "-", "FAIL",
                                   "antispoof_threshold changed by save: %r -> %r "
                                   "(merge-write regression)"
                                   % (_antispoof_before, _antispoof_after))
                    else:
                        log_result("/api/settings#merge", "POST", "-", "PASS",
                                   "antispoof_threshold survives save: %r (pre-test %r)"
                                   % (_antispoof_after, _antispoof_before))
                except Exception as _e:
                    log_result("/api/settings#merge", "POST", "-", "FAIL",
                               "cannot verify antispoof_threshold after save: %s"
                               % str(_e)[:150])
        else:
            print("      save did not report saved - antispoof merge check skipped")
    finally:
        if _cfg_backup is not None:
            with open(_cfg_path, "wb") as _cf:
                _cf.write(_cfg_backup)
            print("      config.toml restored from pre-test backup")
        else:
            print("      WARNING: no config.toml backup to restore")

# ── 6. POST /api/test-scan ─────────────────────────────────────────
# DESTRUCTIVE: grabs the camera (and the daemon's frame source).
# Requires camera + engine; expect 200 on success or 500 if no camera
print("\n[6] POST /api/test-scan")
if destructive(6, "/api/test-scan", "POST"):
    test_post("/api/test-scan", json_data={})

# ── 7. POST /api/enroll ────────────────────────────────────────────
# DESTRUCTIVE: rebuilds the face gallery (changes template count).
# Requires gallery + photos; may succeed or return output with 0 templates
print("\n[7] POST /api/enroll")
if destructive(7, "/api/enroll", "POST"):
    test_post("/api/enroll", json_data={})

# ── 8. POST /api/setup/models ──────────────────────────────────────
# DESTRUCTIVE: runs tools/fetch_fast.py, which downloads ~40MB of models
# when any model file is missing (network + disk write). Skipped by default
# so the default run stays read-only.
print("\n[8] POST /api/setup/models")
if destructive(8, "/api/setup/models", "POST"):
    test_post("/api/setup/models", json_data={})

# ── 9. POST /api/setup/password (consent gate) ──────────────────────
# SAFE: posts WITHOUT a Windows Hello consent token, so the server must
# reject with 403 consent_required before touching the vault. The happy
# path (PIN prompt -> save) is interactive and cannot be automated; it is
# exercised manually from the dashboard. Wrong-password checks are also
# unreachable without a token, so this never mutates cred.bin.
print("\n[9] POST /api/setup/password (no consent token -> 403)")
body9 = test_post("/api/setup/password",
                  json_data={"password": "testpass123"},
                  expected_status=403)
if isinstance(body9, dict) and body9.get("code") != "consent_required":
    log_result("/api/setup/password", "POST", 403, "FAIL",
               "expected code=consent_required, got: %s" % body9)

# ── 10. POST /api/setup/daemon ─────────────────────────────────────
# DESTRUCTIVE: re-registers the NeoFace-Daemon scheduled task.
print("\n[10] POST /api/setup/daemon")
if destructive(10, "/api/setup/daemon", "POST"):
    test_post("/api/setup/daemon", json_data={}, expected_status=200)

# ── 11. POST /api/daemon/start ─────────────────────────────────────
# DESTRUCTIVE: starts the daemon (claims the camera + named pipe).
print("\n[11] POST /api/daemon/start")
_daemon_was_running = False
if destructive(11, "/api/daemon/start", "POST"):
    _status_before = test_get("/api/status", expected_status=200)
    if isinstance(_status_before, dict):
        try:
            _daemon_was_running = bool(_status_before.get("daemon", {}).get("running"))
        except Exception:
            _daemon_was_running = False
    test_post("/api/daemon/start", json_data={}, expected_status=200)

# ── 12. POST /api/daemon/stop ──────────────────────────────────────
# DESTRUCTIVE: stops the daemon. If it was running before test [11] it is
# started again afterwards so an opt-in run leaves the daemon as it found it.
print("\n[12] POST /api/daemon/stop")
if destructive(12, "/api/daemon/stop", "POST"):
    test_post("/api/daemon/stop", json_data={}, expected_status=200)
    if _daemon_was_running:
        time.sleep(2)
        test_post("/api/daemon/start", json_data={}, expected_status=200)
        print("      daemon was running before [11] - restarted to restore state")

# ── 13. POST /api/troubleshoot/all ─────────────────────────────────
# DESTRUCTIVE (same class as [6]/[14]): the troubleshoot "all" branch runs
# the camera diagnostic first - cv2.VideoCapture opens the camera and reads
# a frame (dashboard.py api_troubleshoot: component == "all" hits the same
# code path as component == "camera"). Skipped by default so the default
# run never touches the camera.
print("\n[13] POST /api/troubleshoot/all")
if destructive(13, "/api/troubleshoot/all", "POST"):
    test_post("/api/troubleshoot/all", json_data={}, expected_status=200)

# ── 14. POST /api/troubleshoot/camera ──────────────────────────────
# DESTRUCTIVE (same class as [6]): opens the camera and reads a frame.
# Skipped by default so the default run never touches the camera.
print("\n[14] POST /api/troubleshoot/camera")
if destructive(14, "/api/troubleshoot/camera", "POST"):
    test_post("/api/troubleshoot/camera", json_data={}, expected_status=200)

# ── 15. POST /api/troubleshoot/engine ──────────────────────────────
print("\n[15] POST /api/troubleshoot/engine")
test_post("/api/troubleshoot/engine", json_data={}, expected_status=200)

# ── 16. POST /api/troubleshoot/gallery ─────────────────────────────
print("\n[16] POST /api/troubleshoot/gallery")
test_post("/api/troubleshoot/gallery", json_data={}, expected_status=200)

# ── 17. POST /api/troubleshoot/pipe ────────────────────────────────
print("\n[17] POST /api/troubleshoot/pipe")
test_post("/api/troubleshoot/pipe", json_data={}, expected_status=200)

# ── 18. POST /api/troubleshoot/vault ───────────────────────────────
print("\n[18] POST /api/troubleshoot/vault")
test_post("/api/troubleshoot/vault", json_data={}, expected_status=200)

# ── 19. POST /api/troubleshoot/dll ─────────────────────────────────
print("\n[19] POST /api/troubleshoot/dll")
test_post("/api/troubleshoot/dll", json_data={}, expected_status=200)

# ── 20. POST /api/troubleshoot/daemon ──────────────────────────────
print("\n[20] POST /api/troubleshoot/daemon")
test_post("/api/troubleshoot/daemon", json_data={}, expected_status=200)

# ── 21. GET /api/logs?type=daemon ──────────────────────────────────
print("\n[21] GET /api/logs?type=daemon")
test_get("/api/logs", expected_status=200, extra_params={"type": "daemon"})

# ── 22. GET /api/logs?type=cp ──────────────────────────────────────
print("\n[22] GET /api/logs?type=cp")
test_get("/api/logs", expected_status=200, extra_params={"type": "cp"})

# ── 23. POST /api/logs/clear ───────────────────────────────────────
# DESTRUCTIVE: truncates the daemon / cp logs.
print("\n[23] POST /api/logs/clear")
if destructive(23, "/api/logs/clear", "POST"):
    test_post("/api/logs/clear", json_data={"type": "daemon"}, expected_status=200)

# ── 24. POST /api/photos/upload ────────────────────────────────────
# DESTRUCTIVE: adds a photo to the real gallery.
print("\n[24] POST /api/photos/upload")
test_file_path = None
if destructive(24, "/api/photos/upload", "POST"):
    # Create a minimal 1x1 PNG for testing
    minimal_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )
    test_file_path = os.path.join(os.environ.get("TEMP", "."), "test_upload.png")
    with open(test_file_path, "wb") as f:
        f.write(minimal_png)

    with open(test_file_path, "rb") as f:
        # Dashboard expects field name "files" (getlist)
        files = {"files": ("test_upload.png", f, "image/png")}
        upload_resp = test_post("/api/photos/upload", files=files, expected_status=200)

# ── 25. DELETE /api/photos/{photo_name} ────────────────────────────
# DESTRUCTIVE: removes a photo from the real gallery. Prefers the test
# upload from [24] so a real face photo is only a last resort.
print("\n[25] DELETE /api/photos/{name}")
if destructive(25, "/api/photos/{name}", "DELETE"):
    # Re-fetch photos to find the uploaded one
    photos_resp2 = test_get("/api/photos", expected_status=200)
    photo_name = None
    if photos_resp2 and isinstance(photos_resp2, dict):
        photo_list = photos_resp2.get("photos", [])
        if isinstance(photo_list, list) and len(photo_list) > 0:
            # 1) the file we uploaded in [24], 2) any earlier test_upload*, 3) first photo
            for _p in photo_list:
                _n = _p.get("name") if isinstance(_p, dict) else None
                if _n == "test_upload.png":
                    photo_name = _n
                    break
            if not photo_name:
                for _p in photo_list:
                    _n = _p.get("name") if isinstance(_p, dict) else None
                    if _n and _n.startswith("test_upload"):
                        photo_name = _n
                        break
            if not photo_name:
                photo_name = photo_list[0].get("name")

    if photo_name:
        test_delete("/api/photos/%s" % photo_name, expected_status=200)
    else:
        # Try deleting the one we just uploaded
        test_delete("/api/photos/test_upload.png", expected_status=200)

# ── 26. POST /api/photos/clear ─────────────────────────────────────
# DESTRUCTIVE: DELETES EVERY PHOTO in the gallery (requires re-upload +
# re-enroll afterwards). Opt-in only.
print("\n[26] POST /api/photos/clear")
if destructive(26, "/api/photos/clear", "POST"):
    test_post("/api/photos/clear", json_data={}, expected_status=200)

# Clean up temp file
if test_file_path and os.path.exists(test_file_path):
    os.remove(test_file_path)

# ====================================================================
#  27-32. "CHECK FOR UPDATES" CONTRACT  (GET /api/update/check)
#  Read-only against the live dashboard on :8080.
#  Never restarts the dashboard, never clears photos/vault.
# ====================================================================

UPDATE_ENDPOINT = "/api/update/check"
UPDATE_REQUIRED_KEYS = (
    "ok", "mode", "local_sha", "remote_sha",
    "behind_count", "up_to_date", "commits", "checked_at",
)
_ESCAPERS = re.compile(r"escapeHtml|escHtml|\besc\s*\(")
_update_state = {"endpoint_missing": False}


def load_dashboard_key(path=None):
    """Load the API key from .dashboard_key (same pattern as the module header)."""
    key_path = path if path else _KEY_FILE
    if not os.path.exists(key_path):
        return None
    with open(key_path) as kf:
        return kf.read().strip()


def _server_reachable(timeout=3):
    """True if anything answers on BASE_URL (so we can skip gracefully if it is down)."""
    try:
        requests.get(BASE_URL + "/api/health", timeout=timeout)
        return True
    except Exception:
        return False


def update_get(params, label, expected_status=200, timeout=20):
    """GET the update-check endpoint, log the outcome, return the JSON body on success.

    A 404 is reported as 'endpoint missing - restart dashboard' (the running
    dashboard process has not loaded the new route) instead of a contract fail.

    F5: a "key" entry in `params` is moved into the X-API-Key header so the
    key never appears in the URL (or Werkzeug access logs). Callers keep
    passing params exactly as before; {} still means "no key -> 401".
    """
    url = BASE_URL + UPDATE_ENDPOINT
    params = dict(params) if params else {}
    _key = params.pop("key", None)
    headers = {"X-API-Key": _key} if _key else {}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception as e:
        log_result(UPDATE_ENDPOINT, "GET", "ERR", "FAIL", "%s: %s" % (label, str(e)[:160]))
        return None

    status = r.status_code
    try:
        body = r.json()
    except Exception:
        body = r.text[:300]

    if status == 404:
        _update_state["endpoint_missing"] = True
        log_result(UPDATE_ENDPOINT, "GET", 404, "FAIL",
                   "%s: endpoint missing - restart dashboard" % label)
        return None
    if status != expected_status:
        log_result(UPDATE_ENDPOINT, "GET", status, "FAIL",
                   "%s: expected %s, body: %s" % (label, expected_status, body))
        return None
    log_result(UPDATE_ENDPOINT, "GET", status, "PASS", "%s: body: %s" % (label, body))
    return body if isinstance(body, dict) else None


if not _server_reachable():
    print("\n[SKIP] update-check tests: no server on %s - start dashboard.py and rerun"
          % BASE_URL)
else:
    update_key = load_dashboard_key() or KEY

    # ── 27. without key -> 401 ──────────────────────────────────────
    print("\n[27] GET %s (no key -> 401)" % UPDATE_ENDPOINT)
    update_get({}, "no key", expected_status=401)

    if _update_state["endpoint_missing"]:
        print("      -> skipping live update-check tests: endpoint missing - restart dashboard")
    else:
        # ── 28. with key -> 200 + contract keys ─────────────────────
        print("\n[28] GET %s (with key -> 200, contract keys)" % UPDATE_ENDPOINT)
        update_body = update_get({"key": update_key}, "with key", expected_status=200)

        if update_body is None:
            print("      -> contract checks skipped (request failed; see result above)")
        else:
            missing = [k for k in UPDATE_REQUIRED_KEYS if k not in update_body]
            if missing:
                log_result(UPDATE_ENDPOINT, "GET", 200, "FAIL",
                           "contract keys missing: %s" % ", ".join(missing))
            else:
                log_result(UPDATE_ENDPOINT, "GET", 200, "PASS",
                           "contract keys present: %s" % ", ".join(UPDATE_REQUIRED_KEYS))

            # ── 29. git-mode invariants ─────────────────────────────
            if not missing:
                print("\n[29] update-check invariants (mode=git)")
                mode = update_body.get("mode")
                if mode != "git":
                    log_result(UPDATE_ENDPOINT, "GET", 200, "PASS",
                               "mode=%r - git invariants not applicable" % mode)
                else:
                    problems = []

                    local_sha = update_body.get("local_sha")
                    if not (isinstance(local_sha, str) and local_sha.strip()):
                        problems.append("local_sha empty: %r" % local_sha)

                    behind_raw = update_body.get("behind_count")
                    try:
                        behind = int(behind_raw)
                    except (TypeError, ValueError):
                        behind = None
                        problems.append("behind_count not an int: %r" % behind_raw)

                    up_to_date = update_body.get("up_to_date")
                    if behind is not None and up_to_date != (behind == 0):
                        problems.append("up_to_date=%r contradicts behind_count=%d"
                                        % (up_to_date, behind))

                    commits = update_body.get("commits")
                    if not isinstance(commits, list):
                        problems.append("commits not a list: %r" % type(commits).__name__)
                    elif len(commits) > 20:
                        problems.append("commits length %d > 20" % len(commits))

                    if not isinstance(update_body.get("commits_truncated"), bool):
                        problems.append("commits_truncated missing/not bool: %r"
                                        % update_body.get("commits_truncated"))

                    if problems:
                        log_result(UPDATE_ENDPOINT, "GET", 200, "FAIL",
                                   "git invariants: %s" % "; ".join(problems))
                    else:
                        log_result(UPDATE_ENDPOINT, "GET", 200, "PASS",
                                   "git invariants ok: local_sha=%s behind=%d commits=%d "
                                   "commits_truncated=%r"
                                   % (local_sha[:8], behind, len(commits),
                                      update_body.get("commits_truncated")))

            # ── 30. ?force=1 -> 200 ─────────────────────────────────
            if not _update_state["endpoint_missing"]:
                print("\n[30] GET %s?force=1 (with key -> 200)" % UPDATE_ENDPOINT)
                update_get({"key": update_key, "force": "1"},
                           "force=1", expected_status=200)

            # ── 31. rapid x3, each <= 20s ───────────────────────────
            if _update_state["endpoint_missing"]:
                print("\n[31] rapid x3 skipped: endpoint missing - restart dashboard")
            else:
                print("\n[31] GET %s x3 rapid (each <= 20s)" % UPDATE_ENDPOINT)
                timings = []
                rapid_status = 200
                rapid_fail = None
                for i in range(3):
                    t0 = time.time()
                    try:
                        # F5: key in the header, never in the query string.
                        rr = requests.get(BASE_URL + UPDATE_ENDPOINT,
                                          headers={"X-API-Key": update_key},
                                          timeout=20)
                    except Exception as e:
                        rapid_status, rapid_fail = "ERR", "call %d: %s" % (i + 1, str(e)[:120])
                        break
                    elapsed = time.time() - t0
                    timings.append("%.2fs" % elapsed)
                    if rr.status_code == 404:
                        _update_state["endpoint_missing"] = True
                        rapid_status = 404
                        rapid_fail = "call %d: endpoint missing - restart dashboard" % (i + 1)
                        break
                    if rr.status_code != 200:
                        rapid_status = rr.status_code
                        rapid_fail = "call %d: HTTP %s" % (i + 1, rr.status_code)
                        break
                    if elapsed > 20:
                        rapid_status = rr.status_code
                        rapid_fail = "call %d took %.1fs (>20s)" % (i + 1, elapsed)
                        break

                if rapid_fail:
                    log_result(UPDATE_ENDPOINT, "GET", rapid_status, "FAIL",
                               "rapid x3: %s" % rapid_fail)
                else:
                    log_result(UPDATE_ENDPOINT, "GET", 200, "PASS",
                               "3 sequential calls OK in %s" % ", ".join(timings))

# ── 32. XSS guard (static, no server needed) ──────────────────────
print("\n[32] XSS guard (static): subject/commit rendering goes through escapeHtml")
_template_path = os.path.join(_REPO_ROOT, "templates", "index.html")
if not os.path.exists(_template_path):
    log_result("templates/index.html", "STATIC", "-", "FAIL",
               "index.html not found - cannot verify XSS guard")
else:
    with open(_template_path, encoding="utf-8", errors="replace") as _tf:
        _src = _tf.read()
    _xss_problems = []

    if not re.search(r"function\s+escapeHtml\s*\(", _src):
        _xss_problems.append("escapeHtml() helper not defined")

    # Heuristic: a ${...subject...} interpolation with no escaping call inside it.
    _raw_subject = []
    for _m in re.finditer(r"\$\{([^{}]*)\}", _src):
        _expr = _m.group(1)
        if re.search(r"\bsubject\b", _expr) and not _ESCAPERS.search(_expr):
            _raw_subject.append(_expr.strip()[:60])
    if _raw_subject:
        _xss_problems.append("unescaped ${...subject...} interpolation(s): %s"
                             % "; ".join(_raw_subject[:3]))

    # If the update UI is wired into this page, its render path must escape.
    if UPDATE_ENDPOINT in _src:
        _i = _src.index(UPDATE_ENDPOINT)
        _win = _src[max(0, _i - 1500):_i + 4000]
        if not any(_t in _win for _t in ("escapeHtml", "textContent", "innerText")):
            _xss_problems.append("update UI fetches endpoint but never escapes "
                                 "(no escapeHtml/textContent near render)")

    if _xss_problems:
        log_result("templates/index.html", "STATIC", "-", "FAIL",
                   "; ".join(_xss_problems)[:300])
    else:
        log_result("templates/index.html", "STATIC", "-", "PASS",
                   "escapeHtml defined; no raw ${...subject...} interpolation")

# ====================================================================
#  34-35. UNIT TESTS - security-critical pure functions (always on)
#  Read-only: dashboard.py is imported IN-PROCESS, never started as a
#  server (app.run() is behind `if __name__ == "__main__"`; module import
#  only builds the Flask app, reads the existing .dashboard_key and defines
#  routes). No second server on :8080, no git subprocess (the update origin
#  check runs with _git patched), no network, no camera, no PIN prompt.
#  Every outcome is logged through log_result() so it lands in the summary;
#  the whole section is guarded so a failed import logs FAIL rows instead
#  of crashing the suite.
# ====================================================================
_dash = None
_dash_import_err = None
try:
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    import dashboard as _dash
except Exception as _unit_err:
    _dash_import_err = "%s: %s" % (type(_unit_err).__name__, _unit_err)

# ── 34. unit: origin allow-list ───────────────────────────────────
print("\n[34] unit: origin allow-list (_normalize_origin / _git_check_origin)")
if _dash is None:
    log_result("unit/_normalize_origin", "UNIT", "-", "FAIL",
               "cannot import dashboard: %s" % str(_dash_import_err)[:180])
    log_result("unit/_git_check_origin", "UNIT", "-", "FAIL",
               "skipped - dashboard import failed: %s" % str(_dash_import_err)[:150])
else:
    # -- allowed forms must normalize ONTO the allow-list entries --------
    _bad = []
    try:
        _allowed = tuple(_dash.ALLOWED_ORIGINS)
        _https = _dash._normalize_origin("https://github.com/Jaskaran9880/NeoFace.git")
        if not _allowed:
            _bad.append("ALLOWED_ORIGINS is empty")
        for _raw in ("https://github.com/Jaskaran9880/NeoFace.git",
                     "https://github.com/Jaskaran9880/NeoFace/",
                     "https://github.com/Jaskaran9880/NeoFace.git/",
                     "HTTPS://GitHub.com/Jaskaran9880/NeoFace"):
            _norm = _dash._normalize_origin(_raw)
            if _norm != _https:
                _bad.append("%r -> %r != %r" % (_raw, _norm, _https))
            elif _norm not in _allowed:
                _bad.append("%r -> %r not in ALLOWED_ORIGINS" % (_raw, _norm))
        # ssh form maps to the ssh allow-list entry, never the https one
        _ssh = _dash._normalize_origin("git@github.com:Jaskaran9880/NeoFace.git")
        if _ssh != "git@github.com:jaskaran9880/neoface":
            _bad.append("ssh form -> %r" % _ssh)
        elif _ssh not in _allowed:
            _bad.append("ssh form %r not in ALLOWED_ORIGINS" % _ssh)
        elif _ssh == _https:
            _bad.append("ssh form normalizes into the https entry (protocol confusion)")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/_normalize_origin allowed forms", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "https/.git/trailing-slash/mixed-case land on the https entry, "
               "ssh form on the ssh entry")

    # -- foreign origins must NOT normalize into the allow-list ----------
    _bad = []
    try:
        _foreign = ("https://github.com/jaskaran9880/neoface.evil.com",
                    "https://evil.com/Jaskaran9880/NeoFace",
                    "https://evil.com/Jaskaran9880/NeoFace.git",
                    "http://github.com/jaskaran9880/neoface",
                    "https://github.com/jaskaran9880/neoface-fork")
        for _raw in _foreign:
            if _dash._normalize_origin(_raw) in _dash.ALLOWED_ORIGINS:
                _bad.append("foreign %r normalized INTO the allow-list" % _raw)
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/_normalize_origin foreign origins", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "5 foreign origins (evil host, .git suffix, scheme downgrade, "
               "fork suffix) stay outside ALLOWED_ORIGINS")

    # -- _git_check_origin with _git patched: NO real git, NO network -----
    _bad = []
    _git_calls = []
    _orig_git = getattr(_dash, "_git", None)

    def _fake_git(args, timeout=5):
        _git_calls.append(list(args))
        if _fake_git.mode == "ok":
            return True, "https://github.com/Jaskaran9880/NeoFace.git\n", ""
        if _fake_git.mode == "mixed":   # one foreign URL among allowed ones
            return True, ("https://github.com/jaskaran9880/neoface\n"
                          "https://evil.com/Jaskaran9880/NeoFace.git\n"), ""
        if _fake_git.mode == "foreign":
            return True, "https://evil.com/Jaskaran9880/NeoFace\n", ""
        if _fake_git.mode == "down":
            return False, "", "git failed / network down"
        return True, "", ""             # "empty": ok but no origin URLs

    try:
        _dash._git = _fake_git
        _fake_git.mode = "ok"
        try:
            _dash._git_check_origin()
        except Exception as _unit_err:
            _bad.append("allow-listed origin rejected: %r" % _unit_err)
        for _mode in ("foreign", "mixed", "down", "empty"):
            _fake_git.mode = _mode
            _err = None
            try:
                _dash._git_check_origin()
            except Exception as _unit_err:
                _err = _unit_err
            if _err is None:
                _bad.append("mode=%s accepted - no origin_mismatch raised" % _mode)
            elif getattr(_err, "code", None) != "origin_mismatch":
                _bad.append("mode=%s raised code=%r, want origin_mismatch"
                            % (_mode, getattr(_err, "code", None)))
        if not _git_calls:
            _bad.append("patched _git was never called - assertions did not run")
        if not hasattr(_dash.UpdateError("probe"), "code"):
            _bad.append("UpdateError has no .code attribute")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    finally:
        _dash._git = _orig_git   # restore - later code can never hit real git
    log_result("unit/_git_check_origin patched _git", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "allow-listed passes; foreign/mixed/down/empty fail closed with "
               "code=origin_mismatch (git patched, %d fake call(s))" % len(_git_calls))

# ── 35. unit: consent token store ─────────────────────────────────
print("\n[35] unit: consent token store (TTL / single-use / expiry / cooldown)")
if _dash is None:
    log_result("unit/consent store", "UNIT", "-", "FAIL",
               "skipped - dashboard import failed: %s" % str(_dash_import_err)[:150])
else:
    _tokens = getattr(_dash, "_CONSENT_TOKENS", None)
    _lock = getattr(_dash, "_CONSENT_LOCK", None)
    _seeded = []

    def _seed(token, entry):
        """Insert a test entry under the store lock (mirrors api_setup_consent)."""
        _seeded.append(token)
        if _lock is not None:
            with _lock:
                _tokens[token] = entry
        else:
            _tokens[token] = entry

    # -- shape + TTL + single-use consume ---------------------------------
    _bad = []
    try:
        if _tokens is None:
            raise RuntimeError("_CONSENT_TOKENS missing")
        if _lock is None:
            _bad.append("_CONSENT_LOCK missing (pop must be lock-guarded)")
        _ttl = getattr(_dash, "_CONSENT_TTL", None)
        if (not isinstance(_ttl, (int, float)) or isinstance(_ttl, bool)
                or not (30 <= _ttl <= 300)):
            _bad.append("_CONSENT_TTL=%r outside the sane 30..300s window" % (_ttl,))
            _ttl = 60
        _tok = "unit-fresh-consent-token"
        _seed(_tok, {"exp": time.time() + _ttl, "method": "hello"})
        if _lock is not None:
            with _lock:
                _first = _tokens.pop(_tok, None)
                _second = _tokens.pop(_tok, None)
        else:
            _first = _tokens.pop(_tok, None)
            _second = _tokens.pop(_tok, None)
        if not (isinstance(_first, dict) and "exp" in _first and "method" in _first):
            _bad.append("consumed entry is not {exp, method} dict: %r" % (_first,))
        elif (not isinstance(_first.get("exp"), (int, float))
                or isinstance(_first.get("exp"), bool)
                or _first["exp"] <= time.time()):
            _bad.append("fresh entry exp is not a future timestamp: %r"
                        % (_first.get("exp"),))
        if _second is not None:
            _bad.append("replay accepted - second consume returned %r" % (_second,))
        if _tok in _tokens:
            _bad.append("token still present in store after consume")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/consent single-use + TTL", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "{exp, method} entry, fresh token consumed exactly once, replay "
               "rejected, _CONSENT_TTL=%ss in 30..300" % _ttl)

    # -- expired token: prune drops it; the real route must 403 -----------
    _bad = []
    try:
        _tok = "unit-expired-consent-token"
        _seed(_tok, {"exp": time.time() - 1, "method": "unavailable"})
        _dash._prune_consent_tokens()
        if _tok in _tokens:
            _bad.append("prune left an expired token in the store")

        # Real /api/setup/password consume path: an expired token must be
        # rejected with 403 consent_required BEFORE any Windows logon or
        # vault work. (api_setup_consent is deliberately NEVER called here -
        # it would pop the Windows Hello dialog.) method="unavailable" is
        # seeded so even a hypothetical expiry bug cannot write the vault:
        # that policy only writes after a successful LogonUserW, and the
        # password below is guaranteed wrong.
        _tok2 = "unit-expired-route-token"
        _seed(_tok2, {"exp": time.time() - 1, "method": "unavailable"})
        _client = _dash.app.test_client()
        _resp = _client.post("/api/setup/password",
                             json={"password": "unit-test-wrong-password-7c19",
                                   "consent_token": _tok2},
                             headers={"X-API-Key": _dash.API_KEY})
        _body = _resp.get_json()
        if _resp.status_code != 403:
            _bad.append("expired token -> HTTP %s (want 403), body=%r"
                        % (_resp.status_code, _body))
        elif not (isinstance(_body, dict) and _body.get("code") == "consent_required"):
            _bad.append("403 but code != consent_required: %r" % (_body,))
        if _tok2 in _tokens:
            _bad.append("expired token still in store after consume attempt")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/consent expiry rejected", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "prune removes expired entries; /api/setup/password consume "
               "re-checks exp -> 403 consent_required")

    # -- cooldown structure + guard order (never call api_setup_consent) --
    _bad = []
    try:
        _cs = getattr(_dash, "_consent_state", None)
        _cd = getattr(_dash, "_CONSENT_COOLDOWN", None)
        _lp = _cs.get("last_prompt") if isinstance(_cs, dict) else None
        if not isinstance(_lp, (int, float)) or isinstance(_lp, bool):
            _bad.append("_consent_state.last_prompt missing/not numeric: %r" % (_cs,))
        if not isinstance(_cd, (int, float)) or isinstance(_cd, bool) or _cd < 1:
            _bad.append("_CONSENT_COOLDOWN=%r is not a positive interval" % (_cd,))
        # Static guard-order check instead of a live call: the 429 anti-spam
        # branch must come BEFORE the subprocess that launches win_consent.ps1,
        # otherwise a spammed consent request would pop the Hello dialog.
        # (Marker = subprocess.run, not "win_consent.ps1" - the function
        # docstring mentions win_consent.ps1 before the guard.)
        import inspect as _inspect
        _csrc = _inspect.getsource(_dash.api_setup_consent)
        _i_guard = _csrc.find("Verification prompt requested too often")
        _i_launch = _csrc.find("subprocess.run")
        if _i_launch < 0:
            _i_launch = _csrc.rfind("win_consent.ps1")   # fallback marker
        if _i_guard < 0:
            _bad.append("cooldown 429 branch not found in api_setup_consent")
        elif _i_launch < 0:
            _bad.append("prompt launch site not found - cannot verify guard order")
        elif _i_guard > _i_launch:
            _bad.append("cooldown check runs AFTER the Hello prompt - anti-spam broken")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    finally:
        try:   # leave the store exactly as we found it
            if _lock is not None:
                with _lock:
                    for _t in _seeded:
                        _tokens.pop(_t, None)
            else:
                for _t in _seeded:
                    _tokens.pop(_t, None)
        except Exception:
            pass
    log_result("unit/consent cooldown guard", "UNIT", "-",
               "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "_consent_state/COOLDOWN sane; 429 anti-spam guard precedes the "
               "Hello prompt (prompt never invoked by this suite)")

# ====================================================================
#  40. SCHEDULED TASKS PRESENT  (read-only, always on)
#  Get-ScheduledTask is a pure query: no task is registered, started,
#  stopped or edited by this test. If the cmdlet itself fails (CIM /
#  session error) the python side reports FAIL instead of crashing, and a
#  transiently missing task (concurrent agent re-registering) is retried
#  once after 30s before the row is marked failed.
# ====================================================================
print("\n[40] scheduled tasks: NeoFace-Daemon + NeoFace-UpdateCheck (read-only query)")

import subprocess  # stdlib, local import - keeps the module header untouched

_PS_TASK_QUERY = (
    "$t = Get-ScheduledTask -TaskName 'NeoFace*' -ErrorAction SilentlyContinue; "
    "foreach ($x in @($t)) { "
    "Write-Output ('TASK|' + $x.TaskName); "
    "foreach ($a in @($x.Actions)) { Write-Output ('ARG|' + [string]$a.Arguments) } }"
)


def _query_neoface_tasks():
    """Read-only NeoFace* task query -> ({task: [args, ...]}, err_or_None).

    Never raises: a cmdlet/subprocess failure is returned as `err` so the
    caller can log a FAIL row instead of crashing the suite.
    """
    task_args = {}
    try:
        cp = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_TASK_QUERY],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60)
    except Exception as _e:
        return task_args, "%s: %s" % (type(_e).__name__, str(_e)[:160])

    current = None
    for _line in ((cp.stdout or "") + "\n" + (cp.stderr or "")).splitlines():
        _line = _line.strip()
        if _line.startswith("TASK|"):
            current = _line[5:].strip()
            task_args.setdefault(current, [])
        elif _line.startswith("ARG|") and current is not None:
            task_args[current].append(_line[4:].strip())

    if not task_args:
        _err = "no NeoFace* tasks returned (powershell exit %s)" % cp.returncode
        _stderr = (cp.stderr or "").strip()
        if _stderr:
            _err += "; stderr: %s" % _stderr[:140]
        return task_args, _err
    return task_args, None


def _eval_neoface_tasks(task_args):
    """Problems list (empty == pass): both tasks present + updater args."""
    _problems = []
    if "NeoFace-Daemon" not in task_args:
        _problems.append("task NeoFace-Daemon not registered")
    _updater = task_args.get("NeoFace-UpdateCheck")
    if _updater is None:
        _problems.append("task NeoFace-UpdateCheck not registered")
    elif not any("update_notifier.py" in _a for _a in _updater):
        _problems.append("NeoFace-UpdateCheck action does not run update_notifier.py "
                         "(args: %s)" % "; ".join(_updater)[:100])
    return _problems


_tasks, _tasks_err = _query_neoface_tasks()
_tasks_problems = [_tasks_err] if _tasks_err else _eval_neoface_tasks(_tasks)
if _tasks_problems:
    # Transient window: a concurrent agent may be re-registering the tasks.
    print("      -> %s - retrying once in 30s" % "; ".join(_tasks_problems)[:180])
    time.sleep(30)
    _tasks2, _tasks_err2 = _query_neoface_tasks()
    if _tasks_err2 is None:
        _tasks, _tasks_err = _tasks2, None
        _tasks_problems = _eval_neoface_tasks(_tasks2)
    else:
        _tasks, _tasks_err, _tasks_problems = _tasks2, _tasks_err2, [_tasks_err2]

_tasks_found = ", ".join(sorted(_tasks)) if _tasks else "none"
if _tasks_problems:
    log_result("scheduled/NeoFace*", "SCHED", "-", "FAIL",
               ("found: %s | %s" % (_tasks_found,
                                    "; ".join(_tasks_problems)))[:250])
else:
    log_result("scheduled/NeoFace*", "SCHED", "-", "PASS",
               ("found: %s | updater action args: %s"
                % (_tasks_found,
                   " ; ".join(_tasks.get("NeoFace-UpdateCheck", []))))[:250])

# ====================================================================
#  41. UNIT TESTS - logon update notifier (tools/update_notifier.py)
#  Read-only: the module is imported IN-PROCESS from its file path and
#  must be side-effect free on import (no MessageBox, no network, no git,
#  no .update_notify.json write) - asserted by snapshotting the real state
#  file around the import. show_prompt / apply_update / run_once / main
#  are NEVER called here; only should_notify, save_state and load_state
#  run, and the state rows point STATE_FILE at a temp path that is
#  restored + deleted in a finally, so the real state file is never
#  created or modified by this suite.
# ====================================================================
print("\n[41] unit: update notifier (tools/update_notifier.py)")

import importlib.util   # stdlib, local import - keeps the module header untouched
import tempfile          # stdlib - temp STATE_FILE for row [41c] only

_UN_PATH = os.path.join(_REPO_ROOT, "tools", "update_notifier.py")
_UN_STATE_PATH = os.path.join(_REPO_ROOT, ".update_notify.json")
_UN_CONSTANTS = ("REPO_ROOT", "STATE_FILE", "LOG_FILE", "NOTIFY_MIN_INTERVAL_S")
_UN_FUNCTIONS = ("load_state", "save_state", "should_notify", "show_prompt",
                 "apply_update", "run_once", "main")
_UN_DEFAULTS = {"declined_sha": None, "last_notified": 0, "last_notified_sha": None,
                "last_applied": None}


def _state_file_snapshot(path):
    """(exists, mtime) for a state file - used to prove we never touch it."""
    try:
        if os.path.exists(path):
            return (True, os.path.getmtime(path))
        return (False, None)
    except OSError as _e:
        return ("error", str(_e)[:80])


# Snapshot BEFORE the import so row [41a] can prove the import is clean.
_un_state_before = _state_file_snapshot(_UN_STATE_PATH)
_un = None
_un_import_err = None
for _attempt in (1, 2):
    try:
        _spec = importlib.util.spec_from_file_location("update_notifier", _UN_PATH)
        if _spec is None or _spec.loader is None:
            raise ImportError("spec_from_file_location returned %r" % (_spec,))
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)   # must not run main()/run_once()
        _un = _mod
        _un_import_err = None
        break
    except SyntaxError as _se:
        # The module may be mid-rewrite by a concurrent agent - wait once.
        _un = None
        _un_import_err = "SyntaxError: %s (line %s)" % (_se.msg, _se.lineno)
        if _attempt == 1:
            print("      update_notifier.py looks mid-rewrite - waiting 60s, "
                  "then retrying the import once")
            time.sleep(60)
    except Exception as _ue:
        _un = None
        _un_import_err = "%s: %s" % (type(_ue).__name__, _ue)
        break

# ── 41a. import safety + frozen contract ───────────────────────────
print("  [41a] import safety + frozen contract")
_bad = []
if _un is None:
    _bad.append("cannot import %s: %s" % (_UN_PATH, str(_un_import_err)[:180]))
else:
    for _name in _UN_CONSTANTS + _UN_FUNCTIONS:
        if not hasattr(_un, _name):
            _bad.append("missing frozen attribute %s" % _name)
        elif _name in _UN_FUNCTIONS and not callable(getattr(_un, _name)):
            _bad.append("%s is not callable" % _name)
    _interval = getattr(_un, "NOTIFY_MIN_INTERVAL_S", None)
    if _interval != 86400:
        _bad.append("NOTIFY_MIN_INTERVAL_S=%r, want 86400" % (_interval,))
    _un_state_after = _state_file_snapshot(_UN_STATE_PATH)
    if _un_state_after != _un_state_before:
        _bad.append("import had a side effect: .update_notify.json %r -> %r"
                    % (_un_state_before, _un_state_after))
log_result("unit/update_notifier contract", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "import side-effect free (real state file untouched); 4 constants + "
           "7 functions present, NOTIFY_MIN_INTERVAL_S=86400")

# ── 41b. should_notify matrix ──────────────────────────────────────
print("  [41b] should_notify matrix (14 must-not-notify / 3 must-notify, "
      "24h boundary exact)")
_bad = []
if _un is None:
    _bad.append("skipped - update_notifier import failed: %s"
                % str(_un_import_err)[:150])
else:
    _NOW = 1800000000                 # fixed clock - never depends on wall time
    _SHA = "0123456789abcdef0123456789abcdef01234567"

    def _payload(**_over):
        _p = {"ok": True, "stale": False, "error": None,
              "behind_count": 3, "remote_sha": _SHA}
        _p.update(_over)
        return _p

    def _state(**_over):
        _s = dict(_UN_DEFAULTS)
        _s.update(_over)
        return _s

    _cases = [
        # -- must NOT notify -------------------------------------------
        ("behind_count=0", _payload(behind_count=0), _state(), False),
        ("behind_count=None", _payload(behind_count=None), _state(), False),
        ("behind_count='3' (str)", _payload(behind_count="3"), _state(), False),
        ("behind_count=True (bool)", _payload(behind_count=True), _state(), False),
        ("stale=True", _payload(stale=True), _state(), False),
        ("error set", _payload(error="network down"), _state(), False),
        ("ok=False", _payload(ok=False), _state(), False),
        ("remote_sha=None", _payload(remote_sha=None), _state(), False),
        ("remote_sha == declined_sha", _payload(),
         _state(declined_sha=_SHA), False),
        ("same sha notified 1h ago", _payload(),
         _state(last_notified_sha=_SHA, last_notified=_NOW - 3600), False),
        ("same sha notified 86399s ago (inside 24h)", _payload(),
         _state(last_notified_sha=_SHA, last_notified=_NOW - 86399), False),
        ("empty payload {}", {}, _state(), False),
        ("non-dict payload (str)", "not-a-dict", _state(), False),
        ("None payload", None, _state(), False),
        # -- must notify ------------------------------------------------
        ("fresh behind=3", _payload(), _state(), True),
        ("behind=1 at exactly 24h (now-last==86400)", _payload(behind_count=1),
         _state(last_notified_sha=_SHA, last_notified=_NOW - 86400), True),
        ("behind=3 with unrelated declined_sha", _payload(),
         _state(declined_sha="ffffffffffffffffffffffffffffffffffffffff"), True),
    ]
    _want_true = 0
    for _label, _p, _s, _want in _cases:
        if _want:
            _want_true += 1
        try:
            _got = _un.should_notify(_p, _s, now=_NOW)
        except Exception as _e:
            _bad.append("%s raised %s: %s" % (_label, type(_e).__name__, _e))
            continue
        if not isinstance(_got, bool):
            _bad.append("%s -> %r (not a bool)" % (_label, _got))
        elif _got != _want:
            _bad.append("%s -> %r (want %r)" % (_label, _got, _want))
log_result("unit/should_notify matrix", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "%d cases ok (%d must-not-notify incl. bool/str behind, stale, error, "
           "declined, 1h/86399s cooldown; %d must-notify incl. exact 24h boundary "
           "at now-last==86400)" % (len(_cases), len(_cases) - _want_true, _want_true))

# ── 41c. state round-trip (temp STATE_FILE, real file untouched) ───
print("  [41c] state round-trip (STATE_FILE monkeypatched to a temp path)")
_bad = []
if _un is None:
    _bad.append("skipped - update_notifier import failed: %s"
                % str(_un_import_err)[:150])
else:
    _REAL_STATE = getattr(_un, "STATE_FILE", None)
    _TMP_STATE = os.path.join(tempfile.gettempdir(),
                              "nb_notifier_state_test.json")
    _saved = {"declined_sha": "abc123declined",
              "last_notified": 1790000000,
              "last_notified_sha": "0123456789abcdef0123456789abcdef01234567",
              "last_applied": "feedfacecafebeef0123456789abcdef01234567"}
    try:
        if (not _REAL_STATE
                or os.path.abspath(_REAL_STATE) == os.path.abspath(_TMP_STATE)):
            _bad.append("STATE_FILE %r collides with the temp test path - aborting"
                        % (_REAL_STATE,))
        else:
            _un.STATE_FILE = _TMP_STATE
            for _p in (_TMP_STATE, _TMP_STATE + ".tmp"):
                if os.path.exists(_p):
                    os.remove(_p)

            # (1) save_state -> load_state round trip
            _un.save_state(_saved)
            _loaded = _un.load_state()
            if _loaded != _saved:
                _bad.append("round-trip mismatch: saved %r, loaded %r"
                            % (_saved, _loaded))
            if os.path.exists(_TMP_STATE + ".tmp"):
                _bad.append("atomic write left the .tmp file behind")

            # (2) missing file -> defaults
            os.remove(_TMP_STATE)
            _defaults = _un.load_state()
            if _defaults != _UN_DEFAULTS:
                _bad.append("missing file -> %r, want defaults %r"
                            % (_defaults, _UN_DEFAULTS))

            # (3) corrupt file -> defaults
            with open(_TMP_STATE, "w", encoding="utf-8") as _f:
                _f.write("{not valid json !!!")
            _corrupt = _un.load_state()
            if _corrupt != _UN_DEFAULTS:
                _bad.append("corrupt file -> %r, want defaults %r"
                            % (_corrupt, _UN_DEFAULTS))
    except Exception as _e:
        _bad.append("%s: %s" % (type(_e).__name__, str(_e)[:180]))
    finally:
        try:   # restore FIRST, then drop the temp files
            _un.STATE_FILE = _REAL_STATE
        except Exception:
            pass
        for _p in (_TMP_STATE, _TMP_STATE + ".tmp"):
            try:
                if os.path.exists(_p):
                    os.remove(_p)
            except OSError:
                pass
    _un_state_end = _state_file_snapshot(_UN_STATE_PATH)
    if _un_state_end != _un_state_before:
        _bad.append("REAL .update_notify.json changed: %r -> %r"
                    % (_un_state_before, _un_state_end))
log_result("unit/update_notifier state", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "round-trip, missing->defaults, corrupt->defaults against a temp "
           "STATE_FILE; .tmp cleaned up, STATE_FILE restored, real "
            ".update_notify.json unchanged")

# ====================================================================
#  44-46. UNIT TESTS - camera settle/warmup (face_unlock/camera_warmup.py)
#  Read-only: the module is imported IN-PROCESS from its file path with
#  importlib (retrying while a concurrent writer finishes the file) and
#  must be side-effect free on import - no camera, no cv2, no files
#  created - asserted with a face_unlock/ file-list snapshot taken right
#  around the import (__pycache__ excluded: a CPython .pyc cache is an
#  interpreter artifact, not a module side effect). settle() only ever
#  runs against a fake read_fn and a fake clock advanced 0.1s per read,
#  so these rows are instant and never touch a camera, the daemon or
#  any real state.
# ====================================================================
print("\n[44] unit: camera warmup (face_unlock/camera_warmup.py)")

import importlib.util   # stdlib (row [41] imports it too) - repeated so
                         # rows [44]-[46] never depend on that block

_CW_PATH = os.path.join(_REPO_ROOT, "face_unlock", "camera_warmup.py")
_CW_DIR = os.path.dirname(_CW_PATH)
_CW_CONSTANTS = (("STABLE_DELTA", 3.0), ("STABLE_FRAMES", 3),
                 ("MIN_SETTLE_S", 1.0), ("MAX_SETTLE_S", 2.5), ("BLACK_MEAN", 5.0))
_CW_FUNCTIONS = ("frame_mean", "is_stable", "settle", "should_retry_scan")
_CW_KEYS = ("stable", "frames", "elapsed", "last_mean", "black")


def _cw_files(root):
    """Relative file paths under root - proves the import created nothing."""
    _names = set()
    for _dp, _dn, _fn in os.walk(root):
        _dn[:] = [_d for _d in _dn if _d != "__pycache__"]
        for _f in _fn:
            _names.add(os.path.relpath(os.path.join(_dp, _f), root))
    return _names


# Guarded import: the file may be missing or mid-write by a concurrent
# agent, so missing/partial files are retried (60s apart, up to 3
# retries). Any import failure only FAILS rows [44]-[46] - it is never
# allowed to crash the suite.
_cw = None
_cw_import_err = None
_cw_files_before = None
_cw_files_after = None
for _attempt in (1, 2, 3, 4):   # 1 initial try + up to 3 retries
    try:
        _spec = importlib.util.spec_from_file_location("camera_warmup", _CW_PATH)
        if _spec is None or _spec.loader is None:
            raise ImportError("spec_from_file_location returned %r" % (_spec,))
        _mod = importlib.util.module_from_spec(_spec)
        _cw_files_before = _cw_files(_CW_DIR)   # snapshot right before exec
        _spec.loader.exec_module(_mod)          # must not open a camera
        _cw_files_after = _cw_files(_CW_DIR)
        _cw = _mod
        _cw_import_err = None
        break
    except (OSError, SyntaxError, UnicodeError) as _we:
        # File missing or partially written: wait, then retry.
        _cw = None
        _cw_import_err = "%s: %s" % (type(_we).__name__, str(_we)[:160])
        if _attempt < 4:
            print("      camera_warmup.py not importable yet (%s) - "
                  "waiting 60s, retry %d of 3" % (type(_we).__name__, _attempt))
            time.sleep(60)
    except Exception as _ue:
        # The module itself blew up on import - retrying will not help.
        _cw = None
        _cw_import_err = "%s: %s" % (type(_ue).__name__, str(_ue)[:160])
        break

# ── 44. import safety + frozen contract ─────────────────────────────
print("  [44] import safety + frozen contract")
_bad = []
if _cw is None:
    _bad.append("cannot import %s: %s" % (_CW_PATH, str(_cw_import_err)[:180]))
else:
    for _name, _want in _CW_CONSTANTS:
        _got = getattr(_cw, _name, None)
        if _got is None:
            _bad.append("missing constant %s" % _name)
        elif _got != _want:
            _bad.append("%s=%r, want %r" % (_name, _got, _want))
    for _name in _CW_FUNCTIONS:
        if not callable(getattr(_cw, _name, None)):
            _bad.append("%s missing or not callable" % _name)
    if "cv2" in vars(_cw):
        _bad.append("cv2 imported at module level (contract: no cv2 dependency)")

    class _MeanFrame(object):
        """Duck-typed frame: the contract only requires .mean()."""
        def __init__(self, m):
            self._m = m

        def mean(self):
            return self._m

    if callable(getattr(_cw, "frame_mean", None)):
        for _label, _arg, _want in ((".mean() -> 111.0", _MeanFrame(111.0), 111.0),
                                    ("None", None, 0.0),
                                    ("object() (no .mean)", object(), 0.0)):
            try:
                _got = _cw.frame_mean(_arg)
            except Exception as _e:
                _bad.append("frame_mean(%s) raised %s: %s"
                            % (_label, type(_e).__name__, _e))
                continue
            if isinstance(_got, bool) or not isinstance(_got, (int, float)):
                _bad.append("frame_mean(%s) -> %r (not a number)" % (_label, _got))
            elif float(_got) != _want:
                _bad.append("frame_mean(%s) -> %r, want %r" % (_label, _got, _want))
    if _cw_files_before is not None and _cw_files_after != _cw_files_before:
        _added = sorted(_cw_files_after - _cw_files_before)
        _removed = sorted(_cw_files_before - _cw_files_after)
        _bad.append("import created/removed files: +%s -%s"
                    % (",".join(_added)[:80], ",".join(_removed)[:80]))
log_result("unit/camera_warmup contract", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "import side-effect free (face_unlock/ file list unchanged, no cv2); "
           "5 constants 3.0/3/1.0/2.5/5.0 + 4 callables; frame_mean duck-typed: "
           ".mean()->111.0, None->0.0, object()->0.0")

# ── 45. decision matrix: is_stable + should_retry_scan ──────────────
print("\n[45] unit: camera warmup decision matrix")
print("  [45] is_stable (9 cases) + should_retry_scan (5 cases)")
_bad = []
if _cw is None:
    _bad.append("skipped - camera_warmup import failed: %s"
                % str(_cw_import_err)[:150])
else:
    _stable_cases = [
        # (label, prev_mean, mean, want)
        ("within delta (100->102)", 100.0, 102.0, True),
        ("boundary abs==delta (100->103)", 100.0, 103.0, True),
        ("delta exceeded (100->104)", 100.0, 104.0, False),
        ("black current 4.9", 100.0, 4.9, False),
        ("black prev 4.0", 4.0, 100.0, False),
        ("both black", 4.0, 4.9, False),
        ("prev None", None, 100.0, False),
        ("current None", 100.0, None, False),
        ("both None", None, None, False),
    ]
    for _label, _prev, _mean, _want in _stable_cases:
        try:
            _got = _cw.is_stable(_prev, _mean)
        except Exception as _e:
            _bad.append("is_stable(%s) raised %s: %s"
                        % (_label, type(_e).__name__, _e))
            continue
        if not isinstance(_got, bool):
            _bad.append("is_stable(%s) -> %r (not a bool)" % (_label, _got))
        elif _got is not _want:
            _bad.append("is_stable(%s) -> %r, want %r" % (_label, _got, _want))

    _retry_cases = [
        # (label, (good, frames_ok, spoofs_rejected), want)
        ("not good, 3 frames, 3 spoofs", (False, 3, 3), True),
        ("not good, 1 frame, 1 spoof", (False, 1, 1), True),
        ("good scan", (True, 3, 3), False),
        ("0 frames ok", (False, 0, 3), False),
        ("0 spoofs rejected (liveness-only fail)", (False, 3, 0), False),
    ]
    for _label, _args, _want in _retry_cases:
        try:
            _got = _cw.should_retry_scan(*_args)
        except Exception as _e:
            _bad.append("should_retry_scan(%s) raised %s: %s"
                        % (_label, type(_e).__name__, _e))
            continue
        if not isinstance(_got, bool):
            _bad.append("should_retry_scan(%s) -> %r (not a bool)"
                        % (_label, _got))
        elif _got is not _want:
            _bad.append("should_retry_scan(%s) -> %r, want %r"
                        % (_label, _got, _want))
log_result("unit/camera_warmup decision matrix", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "is_stable 9 cases (delta 2/3/4, black prev/current/both, 3 None); "
           "should_retry_scan 5 cases (good, 0 frames, 0 spoofs - liveness-only "
           "failure must NOT retry); all real bools")

# ── 46. settle() - fake read_fn + fake clock (instant, no camera) ───
print("\n[46] unit: camera warmup settle (fake read_fn + fake clock)")
print("  [46] 7 scenarios on a synthetic 0.1s-per-read clock")
_bad = []
if _cw is None:
    _bad.append("skipped - camera_warmup import failed: %s"
                % str(_cw_import_err)[:150])
    _cw_default_note = "default time_fn not exercised (import failed)"
else:
    _TICK = 0.1       # synthetic seconds 'spent' grabbing each frame
    _TOL = 1e-6       # 0.1 is not exact in binary floats - allow slack

    class _Runaway(BaseException):
        """settle() ignored max_s. BaseException so the `except Exception`
        a conforming settle() wraps around read_fn cannot swallow it and
        hang the suite."""

    class _FakeFrame(object):
        def __init__(self, m):
            self._m = float(m)

        def mean(self):
            return self._m

    def _make_settle(read_values=None, tick=_TICK, error=None):
        """(read_fn, time_fn, state): the fake clock only advances when
        read_fn is called, so settle() finishes instantly."""
        state = {"t": 0.0, "n": 0, "wall": time.monotonic()}

        def _time_fn():
            return state["t"]

        def _read_fn():
            if time.monotonic() - state["wall"] > 10.0:
                raise _Runaway("settle() still reading after 10s wall clock")
            state["t"] += tick              # grabbing a frame takes time
            if error is not None:
                raise error                 # failed read, loop must continue
            if read_values is None:
                return None                 # failed read, no frame counted
            _m = read_values[state["n"] % len(read_values)]
            state["n"] += 1
            return _FakeFrame(_m)

        return _read_fn, _time_fn, state

    def _is_num(_v):
        return isinstance(_v, (int, float)) and not isinstance(_v, bool)

    def _check(_label, _res, stable=None, frames_min=None, frames_exact=None,
               elapsed_min=None, elapsed_max=None, black_min=None,
               black_exact=None, last_mean_in=None):
        """Record contract violations for one settle() result dict."""
        if not isinstance(_res, dict):
            _bad.append("%s -> %r (not a dict)" % (_label, _res))
            return
        if sorted(_res.keys()) != sorted(_CW_KEYS):
            _bad.append("%s keys %r, want %r"
                        % (_label, sorted(_res.keys()), sorted(_CW_KEYS)))
            return
        if stable is not None and (not isinstance(_res["stable"], bool)
                                   or _res["stable"] is not stable):
            _bad.append("%s stable=%r, want %r" % (_label, _res["stable"], stable))
        if frames_exact is not None and _res["frames"] != frames_exact:
            _bad.append("%s frames=%r, want %d"
                        % (_label, _res["frames"], frames_exact))
        if frames_min is not None and not (
                isinstance(_res["frames"], int)
                and not isinstance(_res["frames"], bool)
                and _res["frames"] >= frames_min):
            _bad.append("%s frames=%r, want >= %d"
                        % (_label, _res["frames"], frames_min))
        if elapsed_min is not None and not (
                _is_num(_res["elapsed"]) and _res["elapsed"] >= elapsed_min - _TOL):
            _bad.append("%s elapsed=%r, want >= %.3f"
                        % (_label, _res["elapsed"], elapsed_min))
        if elapsed_max is not None and not (
                _is_num(_res["elapsed"]) and _res["elapsed"] <= elapsed_max + _TOL):
            _bad.append("%s elapsed=%r, want <= %.3f"
                        % (_label, _res["elapsed"], elapsed_max))
        if black_exact is not None and _res["black"] != black_exact:
            _bad.append("%s black=%r, want %d"
                        % (_label, _res["black"], black_exact))
        if black_min is not None and not (
                isinstance(_res["black"], int)
                and not isinstance(_res["black"], bool)
                and _res["black"] >= black_min):
            _bad.append("%s black=%r, want >= %d"
                        % (_label, _res["black"], black_min))
        if last_mean_in is not None and _res["last_mean"] not in last_mean_in:
            _bad.append("%s last_mean=%r, want in %r"
                        % (_label, _res["last_mean"], last_mean_in))

    def _run(read_values=None, error=None, tick=_TICK):
        _r, _t, _st = _make_settle(read_values=read_values, tick=tick,
                                   error=error)
        return _cw.settle(_r, _t)

    try:
        # (a) stable wobble: streak builds, returns once elapsed >= min_s
        _res = _run(read_values=[100.0, 101.0, 99.5])
        _check("(a) stable sequence", _res, stable=True, frames_min=3,
               elapsed_min=1.0, elapsed_max=2.0, black_exact=0,
               last_mean_in=(100.0, 101.0, 99.5))
    except _Runaway as _e:
        _bad.append("(a) %s" % _e)
    except Exception as _e:
        _bad.append("(a) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    try:
        # (b) never within delta: gives up at max_s, stable stays False
        _res = _run(read_values=[100.0, 200.0])
        _check("(b) oscillating means", _res, stable=False, frames_min=3,
               elapsed_min=2.5, elapsed_max=2.7, black_exact=0)
    except _Runaway as _e:
        _bad.append("(b) %s" % _e)
    except Exception as _e:
        _bad.append("(b) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    try:
        # (c) every read fails (falsy): no frames counted, loop continues
        _res = _run(read_values=None)
        _check("(c) read_fn -> None", _res, stable=False, frames_exact=0,
               elapsed_min=2.5, elapsed_max=2.7)
    except _Runaway as _e:
        _bad.append("(c) %s" % _e)
    except Exception as _e:
        _bad.append("(c) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    try:
        # (d) read_fn raises every call: still a dict, never a crash
        _res = _run(error=RuntimeError("camera exploded"))
        _check("(d) read_fn raises", _res, stable=False, frames_exact=0,
               elapsed_min=2.5, elapsed_max=2.7)
    except _Runaway as _e:
        _bad.append("(d) %s" % _e)
    except Exception as _e:
        _bad.append("(d) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    try:
        # (e) frames darker than BLACK_MEAN never advance the streak
        _res = _run(read_values=[0.0])
        _check("(e) all-black frames", _res, stable=False, frames_min=1,
               black_min=1, elapsed_min=2.5, elapsed_max=2.7)
    except _Runaway as _e:
        _bad.append("(e) %s" % _e)
    except Exception as _e:
        _bad.append("(e) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    try:
        # (f) stable from frame 1 but min_s not reached: must keep
        #     reading (>= min_s/tick = 10 reads), not return at streak==3
        _res = _run(read_values=[100.0])
        _check("(f) waits for min_s", _res, stable=True, frames_min=10,
               elapsed_min=1.0, elapsed_max=2.0, black_exact=0)
    except _Runaway as _e:
        _bad.append("(f) %s" % _e)
    except Exception as _e:
        _bad.append("(f) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

    # (g) time_fn omitted: exercise the module's own default clock. The
    # module-level clock name is rebound to a fake object (the stdlib
    # time module itself is never touched) and the original binding is
    # restored in finally, so the default path is instant too.
    _r, _t, _st = _make_settle(read_values=[100.0])
    _patch_name = None
    _patch_value = None
    if hasattr(_cw, "time") and callable(getattr(_cw.time, "monotonic", None)):
        class _FakeTimeNS(object):
            def monotonic(self):
                return _st["t"]

            def perf_counter(self):
                return _st["t"]

        _patch_name, _patch_value = "time", _FakeTimeNS()
    elif callable(getattr(_cw, "monotonic", None)):
        _patch_name = "monotonic"

        def _fake_monotonic():
            return _st["t"]

        _patch_value = _fake_monotonic

    if _patch_name is None:
        _cw_default_note = "default time_fn: no module-level clock to patch (skipped)"
    else:
        _cw_default_note = "default time.monotonic path exercised"
        _cw_patch_orig = getattr(_cw, _patch_name)
        try:
            setattr(_cw, _patch_name, _patch_value)
            _res = _cw.settle(_r)
            _check("(g) default time_fn", _res, stable=True, frames_min=10,
                   elapsed_min=1.0, elapsed_max=2.0, black_exact=0)
        except _Runaway as _e:
            _bad.append("(g) %s" % _e)
        except Exception as _e:
            _bad.append("(g) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))
        finally:
            setattr(_cw, _patch_name, _cw_patch_orig)   # restore first

    try:
        # (h) real numpy ndarray frame: bool(ndarray) is ambiguous, so an
        #     object whose truth value cannot be evaluated must count as a
        #     REAL frame -- regression guard for the `if not frame:` break
        #     that made every production settle raise ValueError.
        import numpy as _np_h
        _hb = [0.0]

        def _h_read():
            _hb[0] += _TICK
            return _np_h.full((8, 8, 3), 100, "uint8")

        _res = _cw.settle(_h_read, lambda: _hb[0])
        _check("(h) real ndarray frame", _res, stable=True, frames_min=3,
               elapsed_min=1.0, elapsed_max=2.0, black_exact=0,
               last_mean_in=(100.0,))
    except _Runaway as _e:
        _bad.append("(h) %s" % _e)
    except Exception as _e:
        _bad.append("(h) raised %s: %s" % (type(_e).__name__, str(_e)[:150]))

log_result("unit/camera_warmup settle", "UNIT", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "fake clock 0.1s/read (no real waiting, no camera): stable -> True at "
           "min_s, oscillation -> False at max_s, None/raising read_fn -> 0 "
           "frames, all-black -> black>0 & never stable, keeps reading until "
           "min_s, real ndarray -> stable; %s" % _cw_default_note)

# ====================================================================
#  47. UNIT TESTS - updater core (face_unlock/updater.py)
#  Read-only: the module is imported IN-PROCESS from its file path and
#  must be side-effect free on import (no network, no task IO, no state
#  writes). No download/apply/elevation path is ever executed here -
#  those are covered by the installer smoke flow, not this suite.
# ====================================================================
print("\n[47] unit: updater core (face_unlock/updater.py)")

import shutil as _shutil_tmp   # stdlib, local import - keeps the module header untouched

_up_import_err = None
_up = None
try:
    _spec = importlib.util.spec_from_file_location(
        "neoface_updater_under_test",
        os.path.join(_REPO_ROOT, "face_unlock", "updater.py"))
    if _spec is None or _spec.loader is None:
        raise ImportError("spec_from_file_location returned None")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)   # must not hit the network or write files
    _up = _mod
except Exception as _unit_err:
    _up_import_err = "%s: %s" % (type(_unit_err).__name__, _unit_err)

if _up is None:
    log_result("unit/updater import", "UNIT", "-", "FAIL",
               "cannot import face_unlock/updater.py: %s" % str(_up_import_err)[:180])
else:
    log_result("unit/updater import", "UNIT", "-", "PASS",
               "import-pure: no network, no task/state IO at import time")

    # -- parse_semver matrix ------------------------------------------------
    _bad = []
    try:
        _semver_cases = (
            ("v0.6.0", (0, 6, 0)),
            ("0.6.0", (0, 6, 0)),
            ("v0.5.0-12-gabc1234", (0, 5, 0)),   # git-describe -> nearest tag
            ("v1.10.2", (1, 10, 2)),
            ("v0.6.0+build5", (0, 6, 0)),
            ("", None),
            ("abc", None),
            ("v1.2", None),                      # incomplete: not a semver
            (None, None),
        )
        for _raw, _want in _semver_cases:
            _got = _up.parse_semver(_raw)
            if _got != _want:
                _bad.append("parse_semver(%r) -> %r != %r" % (_raw, _got, _want))
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/parse_semver", "UNIT", "-", "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "9 cases: v-prefix, git-describe suffix, build suffix, junk -> None")

    # -- is_newer matrix ----------------------------------------------------
    _bad = []
    try:
        _newer_cases = (
            ("v0.6.0", "v0.5.0", True),
            ("v0.5.1", "v0.5.0", True),
            ("v0.5.0", "v0.5.0", False),       # same version is never newer
            ("v0.4.9", "v0.5.0", False),       # older never applies
            ("v0.5.0-12-gabc1234", "v0.5.0", False),   # describe==tag -> not newer
            ("v0.6.0", "", False),             # unknown local never blocks wrongly
            ("", "v0.5.0", False),             # unparseable remote never applies
            (None, "v0.5.0", False),
        )
        for _remote, _local, _want in _newer_cases:
            _got = _up.is_newer(_remote, _local)
            if _got is not _want:
                _bad.append("is_newer(%r, %r) -> %r != %r" % (_remote, _local, _got, _want))
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/is_newer", "UNIT", "-", "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "8 cases: unknown side always yields False (never apply blindly)")

    # -- parse_sha256_from_body against the real release.yml template -------
    _bad = []
    try:
        _hash_hex = "84f6967d6bfe251513f75ba283722f06a7681dc57b88942c0dd414e01794ddd1"
        _body_tpl = ("## NeoFace Unlock 0.5.0\n\n"
                     "### Install (no Python, no Git, no compiler needed)\n"
                     "1. Download `NeoFace-Setup-0.5.0.exe` below\n\n"
                     "### SHA256\n"
                     "````\n%s\n````\n" % _hash_hex)
        _got = _up.parse_sha256_from_body(_body_tpl)
        if _got != _hash_hex:
            _bad.append("release.yml template -> %r != hash" % (_got,))
        if _up.parse_sha256_from_body("no hash here") is not None:
            _bad.append("hash-less body did not yield None")
        _bare = _up.parse_sha256_from_body("installer hash is\n%s\nthanks" % _hash_hex)
        if _bare != _hash_hex:
            _bad.append("bare-hash fallback -> %r" % (_bare,))
        _lower = _up.parse_sha256_from_body("### SHA256\n````\n%s\n````\n"
                                            % _hash_hex.upper())
        if _lower != _hash_hex:
            _bad.append("uppercase hash not lowercased -> %r" % (_lower,))
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/parse_sha256_from_body", "UNIT", "-", "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "release.yml fence template, bare fallback, uppercase, missing -> None")

    # -- find_setup_asset host allow-list -----------------------------------
    _bad = []
    try:
        _rel = {"assets": [
            {"name": "NeoFace-Setup-0.6.0.exe",
             "url": "https://github.com/Jaskaran9880/NeoFace/releases/download/v0.6.0/NeoFace-Setup-0.6.0.exe",
             "size": 100},
            {"name": "NeoFace-Setup-0.6.0.exe",
             "url": "https://evil.example.com/NeoFace-Setup-0.6.0.exe",
             "size": 100},
            {"name": "checksums.txt",
             "url": "https://github.com/Jaskaran9880/NeoFace/releases/download/v0.6.0/checksums.txt",
             "size": 10},
        ]}
        _asset = _up.find_setup_asset(_rel, "0.6.0")
        if not _asset or "github.com" not in _asset["url"]:
            _bad.append("allowed-host asset not selected: %r" % (_asset,))
        if _up.find_setup_asset(_rel, "0.7.0") is not None:
            _bad.append("missing version asset did not yield None")
        _evil = {"assets": [{"name": "NeoFace-Setup-0.6.0.exe",
                             "url": "https://evil.example.com/NeoFace-Setup-0.6.0.exe",
                             "size": 100}]}
        if _up.find_setup_asset(_evil, "0.6.0") is not None:
            _bad.append("foreign-host asset was NOT rejected")
        if _up.find_setup_asset(None, "0.6.0") is not None:
            _bad.append("None release did not yield None")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/find_setup_asset", "UNIT", "-", "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "allowed-host picked, foreign host rejected, missing -> None")

    # -- detect_install_mode + local_version on real and synthetic roots ----
    _bad = []
    try:
        _mode_real = _up.detect_install_mode(_REPO_ROOT)
        if _mode_real != "git":
            _bad.append("repo root detected as %r (want 'git')" % _mode_real)
        _ver_real = _up.local_version(_REPO_ROOT)
        if _ver_real.get("source") != "git" or not _ver_real.get("version"):
            _bad.append("repo local_version -> %r" % (_ver_real,))
        _tmp = tempfile.mkdtemp(prefix="nf-updater-test-")
        try:
            if _up.detect_install_mode(_tmp) != "installed":
                _bad.append("no-.git temp root not detected as 'installed'")
            os.makedirs(os.path.join(_tmp, ".git"))   # .git but no remote/origin
            if _up.detect_install_mode(_tmp) != "installed":
                _bad.append("foreign/uncloned .git not detected as 'installed'")
            with open(os.path.join(_tmp, "VERSION"), "w", encoding="utf-8") as _f:
                _f.write("9.9.9\n")
            _ver_tmp = _up.local_version(_tmp)
            if _ver_tmp != {"version": "9.9.9", "sha": None, "source": "version_file"}:
                _bad.append("VERSION-file root -> %r" % (_ver_tmp,))
        finally:
            _shutil_tmp.rmtree(_tmp, ignore_errors=True)
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    log_result("unit/mode+version", "UNIT", "-", "FAIL" if _bad else "PASS",
               "; ".join(_bad)[:250] if _bad else
               "repo=git+describe, bare root=installed, VERSION file=version_file")

# ====================================================================
#  48. UNIT TESTS - apply pipeline (face_unlock/updater.py + auto path)
#  Read-only: every engine is monkeypatched in-process. No network,
#  no scheduled-task IO, no ProgramData write and no elevation can
#  happen here - download_latest runs against a fake urlopen and a
#  temp dest dir, prepare_apply runs against fake mode/state/fetch/
#  task functions, and the notifier's silent auto path runs against
#  a fake updater plus a temp state file.
# ====================================================================
print("\n[48] unit: apply pipeline (face_unlock/updater.py + auto path)")

import hashlib as _hashlib_t48          # stdlib, local import - keeps the header untouched
import urllib.request as _urlreq_t48    # stdlib - patched (and restored) around download_latest

# -- 48a. verify_sha256 matrix -------------------------------------------
print("  [48a] verify_sha256 matrix (match / mismatch / missing / empty / case)")
_bad = []
if _up is None:
    _bad.append("skipped - updater import failed: %s" % str(_up_import_err)[:150])
else:
    _td = tempfile.mkdtemp(prefix="nf-sha-test-")
    try:
        _f = os.path.join(_td, "payload.bin")
        _payload = b"neoface-verify-sha256-matrix"
        with open(_f, "wb") as _h:
            _h.write(_payload)
        _good = _hashlib_t48.sha256(_payload).hexdigest()
        if _up.verify_sha256(_f, _good) is not True:
            _bad.append("correct hash did not return True")
        if _up.verify_sha256(_f, "0" * 64) is not False:
            _bad.append("wrong hash did not return False")
        if _up.verify_sha256(os.path.join(_td, "missing.bin"), _good) is not False:
            _bad.append("missing file did not return False")
        if _up.verify_sha256(_f, "") is not False:
            _bad.append("empty expected did not return False")
        if _up.verify_sha256(_f, None) is not False:
            _bad.append("None expected did not return False")
        if _up.verify_sha256(_f, "  %s \n" % _good.upper()) is not True:
            _bad.append("uppercase/whitespace expected did not return True "
                        "(case-insensitive constant-time compare)")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, _unit_err))
    finally:
        _shutil_tmp.rmtree(_td, ignore_errors=True)
log_result("unit/verify_sha256", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "match/mismatch/missing/empty correct; case+whitespace tolerated")

# -- 48b. download_latest: verified staging (.part -> os.replace) ---------
print("  [48b] download_latest staging (fake urlopen, temp dest dir)")
_bad = []
if _up is None:
    _bad.append("skipped - updater import failed: %s" % str(_up_import_err)[:150])
else:
    _urlopen_orig = _urlreq_t48.urlopen
    _dl_calls = []
    _td = tempfile.mkdtemp(prefix="nf-dl-test-")
    try:
        _payload = b"NEOFACE-SETUP-FAKE-BYTES-" * 64
        _sha = _hashlib_t48.sha256(_payload).hexdigest()
        _name = "NeoFace-Setup-9.9.9.exe"
        _release = {"tag": "v9.9.9", "version": "9.9.9", "sha256": _sha,
                    "assets": [{"name": _name,
                                "url": "https://github.com/Jaskaran9880/NeoFace/"
                                       "releases/download/v9.9.9/" + _name,
                                "size": len(_payload)}]}
        _final = os.path.join(_td, _name)

        class _FakeResp(object):
            """Minimal urllib response: context manager + headers + read(n).

            Deliberately never raises URLError/OSError/ValueError - those
            would divert download_latest into its real curl fallback.
            """
            def __init__(self, data, headers=None):
                self._data = data
                self._pos = 0
                self.headers = dict(headers or {})

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def read(self, n):
                _chunk = self._data[self._pos:self._pos + n]
                self._pos += len(_chunk)
                return _chunk

        def _fake_urlopen(req, timeout=None, **_kw):
            _dl_calls.append(getattr(req, "full_url", "?"))
            return _FakeResp(_payload, {"Content-Length": str(len(_payload))})

        def _bomb_urlopen(*_a, **_kw):
            _dl_calls.append("BOMB")
            raise AssertionError("network touched on a path that must not fetch")

        _urlreq_t48.urlopen = _fake_urlopen

        # (1) wrong SHA256 -> hash_mismatch, .part deleted, exe never exists
        try:
            _up.download_latest(dict(_release, sha256="f" * 64), dest_dir=_td)
            _bad.append("hash_mismatch: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "hash_mismatch":
                _bad.append("hash_mismatch: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("hash_mismatch: %s: %s" % (type(_e).__name__, str(_e)[:80]))
        if os.path.exists(_final):
            _bad.append("hash_mismatch: final exe exists without verification")
        if os.path.exists(_final + ".part"):
            _bad.append("hash_mismatch: .part not deleted")

        # (2) correct SHA256 -> atomically finalized, no .part left behind
        try:
            _res = _up.download_latest(_release, dest_dir=_td)
        except Exception as _e:
            _bad.append("match: raised %s: %s" % (type(_e).__name__, str(_e)[:100]))
            _res = None
        if not isinstance(_res, dict) or _res.get("reused") is not False:
            _bad.append("match: result=%r" % (_res,))
        if not os.path.isfile(_final):
            _bad.append("match: final exe missing after download")
        elif not _up.verify_sha256(_final, _sha):
            _bad.append("match: final exe does not hash-match")
        if os.path.exists(_final + ".part"):
            _bad.append("match: .part left behind (atomic replace did not run)")

        # (3) reuse: a verified file short-circuits BEFORE any network call
        _before = len(_dl_calls)
        _urlreq_t48.urlopen = _bomb_urlopen
        try:
            _res = _up.download_latest(_release, dest_dir=_td)
        except Exception as _e:
            _bad.append("reuse: raised %s: %s" % (type(_e).__name__, str(_e)[:100]))
            _res = None
        if _dl_calls[_before:]:
            _bad.append("reuse: urlopen was called on the reuse path")
        if not isinstance(_res, dict) or _res.get("reused") is not True:
            _bad.append("reuse: result=%r" % (_res,))
        elif _res.get("path") != _final:
            _bad.append("reuse: path=%r" % _res.get("path"))

        # (4) no SHA256 published -> refused BEFORE any network call
        #     (the bomb stays installed from here on: cases 4-5 must not fetch)
        _before = len(_dl_calls)
        try:
            _up.download_latest(dict(_release, sha256=None), dest_dir=_td)
            _bad.append("no_hash: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "no_hash":
                _bad.append("no_hash: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("no_hash: %s: %s" % (type(_e).__name__, str(_e)[:80]))
        if _dl_calls[_before:]:
            _bad.append("no_hash: network touched before the refusal")

        # (5) foreign-host asset -> no_asset BEFORE any network call
        _foreign = dict(_release, assets=[{"name": _name,
                                           "url": "https://evil.example.com/" + _name,
                                           "size": len(_payload)}])
        _before = len(_dl_calls)
        try:
            _up.download_latest(_foreign, dest_dir=_td)
            _bad.append("no_asset: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "no_asset":
                _bad.append("no_asset: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("no_asset: %s: %s" % (type(_e).__name__, str(_e)[:80]))
        if _dl_calls[_before:]:
            _bad.append("no_asset: network touched before the refusal")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
    finally:
        _urlreq_t48.urlopen = _urlopen_orig
        _shutil_tmp.rmtree(_td, ignore_errors=True)
log_result("unit/download staging", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "mismatch never finalizes + deletes .part, match replaces atomically, "
           "reuse skips the network, no_hash/no_asset refuse pre-flight")

# -- 48c. prepare_apply decision gates ------------------------------------
print("  [48c] prepare_apply gates (git dispatch / in_progress / already_current /")
print("        task_missing staging / silent task handoff / runas / staging failure)")
_bad = []
if _up is None:
    _bad.append("skipped - updater import failed: %s" % str(_up_import_err)[:150])
else:
    _patch_names = ("detect_install_mode", "read_apply_state", "fetch_latest_release",
                    "local_version", "download_latest", "_task_exists",
                    "_start_apply_task", "_runas_apply_script", "apply_via_git",
                    "write_apply_state", "_write_json_atomic", "PENDING_FILE")
    _saved = {name: getattr(_up, name) for name in _patch_names}
    _calls = {"fetch": 0, "download": 0, "git": 0, "start_task": 0,
              "runas": 0, "write_state": [], "runas_relaunch": []}
    _td = tempfile.mkdtemp(prefix="nf-prepare-test-")
    try:
        _up.PENDING_FILE = os.path.join(_td, "pending.json")

        def _f_fetch(force=False, timeout=10):
            _calls["fetch"] += 1
            return {"tag": "v9.9.9", "version": "9.9.9", "body": "",
                    "assets": [], "sha256": "a" * 64}

        def _f_download(release=None, progress_cb=None, **_kw):
            _calls["download"] += 1
            return {"path": os.path.join(_td, "NeoFace-Setup-9.9.9.exe"),
                    "sha256": "a" * 64, "size": 12,
                    "tag": (release or {}).get("tag"), "reused": False}

        def _f_git(progress_cb=None):
            _calls["git"] += 1
            return {"ok": True, "method": "git", "message": "pulled"}

        def _f_start():
            _calls["start_task"] += 1
            return True

        def _f_runas(relaunch):
            _calls["runas"] += 1
            _calls["runas_relaunch"].append(bool(relaunch))
            return {"ok": True, "method": "runas"}

        def _f_write_state(state, **_kw):
            _calls["write_state"].append(state)
            return {}

        def _reset(*names):
            for _n in names:
                _calls[_n] = [] if isinstance(_calls.get(_n), list) else 0

        _state_idle = {"state": "idle", "pct": None, "message": "", "version": None,
                       "exit_code": None, "rolled_back": False, "updated_at": 0}

        # A. git mode -> straight to apply_via_git (never fetches a release)
        _up.detect_install_mode = lambda root=None: "git"
        _up.apply_via_git = _f_git
        _up.fetch_latest_release = _f_fetch
        _reset("fetch", "git")
        try:
            _res = _up.prepare_apply()
            if _res != {"ok": True, "method": "git", "message": "pulled"}:
                _bad.append("git: result=%r" % (_res,))
        except Exception as _e:
            _bad.append("git: raised %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if _calls["git"] != 1:
            _bad.append("git: apply_via_git called %d times" % _calls["git"])
        if _calls["fetch"] != 0:
            _bad.append("git: fetched a release anyway (dispatch should be enough)")

        # B. fresh in-progress state -> refused BEFORE any network
        _up.detect_install_mode = lambda root=None: "installed"
        _up.read_apply_state = lambda: dict(
            _state_idle, state="downloading", updated_at=time.time())
        _reset("fetch")
        try:
            _up.prepare_apply()
            _bad.append("in_progress: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "in_progress":
                _bad.append("in_progress: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("in_progress: %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if _calls["fetch"] != 0:
            _bad.append("in_progress: network fetch happened before the refusal")

        # C. already on the release tag -> already_current, nothing downloaded
        _up.read_apply_state = lambda: dict(_state_idle)
        _up.fetch_latest_release = _f_fetch        # returns v9.9.9
        _up.local_version = lambda root=None: {"version": "9.9.9", "sha": None,
                                               "source": "git"}
        _reset("download")
        try:
            _up.prepare_apply()
            _bad.append("already_current: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "already_current":
                _bad.append("already_current: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("already_current: %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if _calls["download"] != 0:
            _bad.append("already_current: downloaded anyway")
        if os.path.exists(_up.PENDING_FILE):
            _bad.append("already_current: staged a pending update anyway")

        # D. newer release, task missing, non-interactive -> task_missing,
        #    but only AFTER staging pending.json (installer-side handoff)
        _up.local_version = lambda root=None: {"version": "0.5.0", "sha": None,
                                               "source": "version_file"}
        _up.download_latest = _f_download
        _up._task_exists = lambda name: False
        _up._start_apply_task = _f_start
        _up._runas_apply_script = _f_runas
        _up.write_apply_state = _f_write_state
        if os.path.exists(_up.PENDING_FILE):
            os.remove(_up.PENDING_FILE)
        _reset("download", "start_task", "runas")
        try:
            _up.prepare_apply(interactive=False)
            _bad.append("task_missing: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "task_missing":
                _bad.append("task_missing: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("task_missing: %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if not os.path.exists(_up.PENDING_FILE):
            _bad.append("task_missing: pending.json was not staged first")
        else:
            try:
                with open(_up.PENDING_FILE, "r", encoding="utf-8") as _h:
                    _pend = json.load(_h)
                if not all(_k in _pend for _k in ("setup", "sha256", "tag",
                                                  "relaunch", "staged_at")):
                    _bad.append("task_missing: pending.json keys=%r" % sorted(_pend))
            except Exception as _e:
                _bad.append("task_missing: pending.json unreadable: %s" % str(_e)[:80])
        if _calls["start_task"] != 0 or _calls["runas"] != 0:
            _bad.append("task_missing: elevated handoff ran anyway (start=%d runas=%d)"
                        % (_calls["start_task"], _calls["runas"]))

        # E. task registered -> silent handoff, state marked installing, no UAC
        _up._task_exists = lambda name: True
        if os.path.exists(_up.PENDING_FILE):
            os.remove(_up.PENDING_FILE)
        _reset("start_task", "runas", "write_state")
        try:
            _res = _up.prepare_apply(interactive=False)
            if not (isinstance(_res, dict) and _res.get("ok") is True
                    and _res.get("method") == "task" and _res.get("tag") == "v9.9.9"):
                _bad.append("task: result=%r" % (_res,))
        except Exception as _e:
            _bad.append("task: raised %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if _calls["start_task"] != 1:
            _bad.append("task: _start_apply_task called %d times" % _calls["start_task"])
        if not os.path.exists(_up.PENDING_FILE):
            _bad.append("task: pending.json not staged")
        if "installing" not in _calls["write_state"]:
            _bad.append("task: apply state never marked installing (%r)"
                        % (_calls["write_state"],))
        if _calls["runas"] != 0:
            _bad.append("task: UAC fallback ran even though the task exists")

        # F. task missing but interactive -> UAC runas fallback, relaunch kept
        _up._task_exists = lambda name: False
        _reset("runas", "runas_relaunch")
        try:
            _res = _up.prepare_apply(interactive=True, relaunch_dashboard=True)
            if not (isinstance(_res, dict) and _res.get("ok") is True
                    and _res.get("method") == "runas" and _res.get("tag") == "v9.9.9"):
                _bad.append("runas: result=%r" % (_res,))
        except Exception as _e:
            _bad.append("runas: raised %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if _calls["runas"] != 1:
            _bad.append("runas: _runas_apply_script called %d times" % _calls["runas"])
        if _calls["runas_relaunch"] != [True]:
            _bad.append("runas: relaunch flag not forwarded (%r)"
                        % (_calls["runas_relaunch"],))

        # G. staging failure -> apply_failed, never reaches any elevation
        if os.path.exists(_up.PENDING_FILE):
            os.remove(_up.PENDING_FILE)
        _up._write_json_atomic = lambda path, data: False
        _reset("start_task", "runas")
        try:
            _up.prepare_apply(interactive=True)
            _bad.append("staging: no UpdaterError raised")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "apply_failed":
                _bad.append("staging: code=%r" % getattr(_e, "code", None))
        except Exception as _e:
            _bad.append("staging: %s: %s" % (type(_e).__name__, str(_e)[:100]))
        if os.path.exists(_up.PENDING_FILE):
            _bad.append("staging: pending.json written despite the failure")
        if _calls["start_task"] != 0 or _calls["runas"] != 0:
            _bad.append("staging: elevated handoff ran despite staging failure")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
    finally:
        for _name, _value in _saved.items():
            setattr(_up, _name, _value)
        _shutil_tmp.rmtree(_td, ignore_errors=True)
log_result("unit/prepare_apply gates", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "git dispatch / in_progress-before-fetch / already_current / "
           "task_missing-stages-first / silent task handoff / runas relaunch / "
           "staging failure stops elevation")

# -- 48d. notifier silent auto path (mode=auto) ---------------------------
print("  [48d] notifier _auto_apply matrix (git dedupe + installed handoff)")
_bad = []
_rcs = []
if _un is None:
    _bad.append("skipped - update_notifier import failed: %s" % str(_un_import_err)[:150])
else:
    _td = tempfile.mkdtemp(prefix="nf-auto-test-")
    _logs = []
    _apply_payloads = []
    _un_saved = {"_log": _un._log, "STATE_FILE": _un.STATE_FILE,
                 "apply_update": _un.apply_update}
    try:
        _un._log = lambda line: _logs.append(line)
        _un.STATE_FILE = os.path.join(_td, "state.json")

        def _f_apply_update(payload):
            _apply_payloads.append(payload)
            return {"ok": True, "message": "fake git apply"}

        _un.apply_update = _f_apply_update

        class _FakeUE(Exception):
            """UpdaterError-shaped failure for the notifier contract."""
            def __init__(self, code, message):
                super().__init__(message)
                self.code = code
                self.message = message

        class _FakeUp(object):
            """Just enough updater surface for _auto_apply."""
            def __init__(self, mode="installed", tag="v9.9.9", local="0.5.0",
                         newer=True, fetch_err=None, no_tag=False,
                         prepare_err=None):
                self._mode = mode
                self.tag = tag
                self.local = local
                self.newer = newer
                self.fetch_err = fetch_err
                self.no_tag = no_tag
                self.prepare_err = prepare_err
                self.prepare_calls = 0

            def detect_install_mode(self):
                return self._mode

            def fetch_latest_release(self):
                if self.fetch_err is not None:
                    raise self.fetch_err
                return {} if self.no_tag else {"tag": self.tag,
                                               "version": self.tag.lstrip("v")}

            def local_version(self):
                return {"version": self.local, "sha": None, "source": "test"}

            def is_newer(self, tag, ver):
                return self.newer

            def prepare_apply(self, interactive=True, relaunch_dashboard=False,
                              progress_cb=None):
                self.prepare_calls += 1
                if self.prepare_err is not None:
                    raise self.prepare_err
                return {"ok": True, "method": "task", "message": "staged"}

        def _run(label, updater, payload, state):
            _rc = _un._auto_apply(updater, payload, state)
            _rcs.append((label, _rc))
            if _rc != 0:
                _bad.append("%s returned %r (auto path must always return 0)"
                            % (label, _rc))

        def _persisted():
            try:
                with open(_un.STATE_FILE, "r", encoding="utf-8") as _h:
                    return json.load(_h)
            except Exception as _e:
                _bad.append("state file unreadable: %s" % str(_e)[:80])
                return {}

        _state0 = dict(_un._STATE_DEFAULTS)
        _solid = {"ok": True, "stale": False, "error": None, "behind_count": 3,
                  "remote_sha": "remote-sha-1"}
        _up_git = _FakeUp(mode="git")

        # (0) no updater module -> quiet 0
        _run("no-updater", None, dict(_solid), dict(_state0))

        # (1) git + solid fresh payload -> applies once, persists last_applied
        _n0 = len(_apply_payloads)
        _state = dict(_state0)
        _run("git-apply", _up_git, dict(_solid), _state)
        if len(_apply_payloads) != _n0 + 1:
            _bad.append("git-apply: apply_update not called exactly once")
        if _state.get("last_applied") != "remote-sha-1":
            _bad.append("git-apply: last_applied=%r" % _state.get("last_applied"))
        if _persisted().get("last_applied") != "remote-sha-1":
            _bad.append("git-apply: not persisted to the state file")

        # (2) same remote already applied -> dedupe, no second apply
        _n0 = len(_apply_payloads)
        _run("git-dedupe", _up_git, dict(_solid), _state)
        if len(_apply_payloads) != _n0:
            _bad.append("git-dedupe: apply_update ran again for the same sha")

        # (3) stale / error / not-ok / behind<=0 / bool-behind / no remote -> never
        for _label, _pl in (
                ("stale", dict(_solid, stale=True)),
                ("error", dict(_solid, error="offline")),
                ("not-ok", dict(_solid, ok=False)),
                ("behind-0", dict(_solid, behind_count=0)),
                ("behind-bool", dict(_solid, behind_count=True)),
                ("no-remote", dict(_solid, remote_sha=None))):
            _n0 = len(_apply_payloads)
            _run("git-" + _label, _up_git, _pl, dict(_state0))
            if len(_apply_payloads) != _n0:
                _bad.append("git-%s: applied anyway" % _label)

        # (4) declined version stays declined
        _n0 = len(_apply_payloads)
        _run("git-declined", _up_git, dict(_solid),
             dict(_state0, declined_sha="remote-sha-1"))
        if len(_apply_payloads) != _n0:
            _bad.append("git-declined: applied a declined sha anyway")

        # (5) installed + release fetch fails -> skip, no crash
        _up_ins = _FakeUp(fetch_err=RuntimeError("offline"))
        _run("ins-fetch-fail", _up_ins, None, dict(_state0))
        if _up_ins.prepare_calls != 0:
            _bad.append("ins-fetch-fail: prepare_apply was attempted")

        # (6) installed + no tag / already applied / not newer -> skip
        for _label, _kw in (("no-tag", {"no_tag": True}),
                            ("dedupe", {}),
                            ("not-newer", {"newer": False})):
            _up2 = _FakeUp(**_kw)
            _st = dict(_state0)
            if _label == "dedupe":
                _st["last_applied"] = _up2.tag
            _run("ins-" + _label, _up2, None, _st)
            if _up2.prepare_calls != 0:
                _bad.append("ins-%s: prepare_apply was attempted" % _label)

        # (7) installed + already_current / in_progress -> fail-soft info logs
        for _code in ("already_current", "in_progress"):
            _up3 = _FakeUp(prepare_err=_FakeUE(_code, "simulated %s" % _code))
            _run("ins-" + _code, _up3, None, dict(_state0))
            if not any(_code in _line for _line in _logs):
                _bad.append("ins-%s: info log missing" % _code)

        # (8) installed + unexpected failure -> still 0, logged as a failure
        _logs[:] = []
        _up4 = _FakeUp(prepare_err=_FakeUE("uac_declined", "user declined"))
        _run("ins-uac", _up4, None, dict(_state0))
        if not any("apply failed" in _line for _line in _logs):
            _bad.append("ins-uac: failure log missing")

        # (9) installed + staged ok -> last_applied = tag, persisted, logged
        _logs[:] = []
        _up5 = _FakeUp()
        _state = dict(_state0)
        _run("ins-ok", _up5, None, _state)
        if _state.get("last_applied") != "v9.9.9":
            _bad.append("ins-ok: last_applied=%r" % _state.get("last_applied"))
        if _persisted().get("last_applied") != "v9.9.9":
            _bad.append("ins-ok: not persisted to the state file")
        if _up5.prepare_calls != 1:
            _bad.append("ins-ok: prepare_apply called %d times" % _up5.prepare_calls)
        if not any("staged install apply" in _line for _line in _logs):
            _bad.append("ins-ok: success log missing")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
    finally:
        for _name, _value in _un_saved.items():
            setattr(_un, _name, _value)
        _shutil_tmp.rmtree(_td, ignore_errors=True)
log_result("unit/auto_apply", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "%d cases: git dedupe+guards, installed fetch/tag/version gates, "
           "already_current/in_progress fail-soft, ok persists last_applied; "
           "every path returns 0" % len(_rcs))

# ====================================================================
#  49. UNIT + LIVE - update preferences, what-changed renderer, card API
#  49a/49b run against TEMP stores (the live ProgramData mirror and the
#  repo config.toml are snapshotted and must stay byte-identical). 49c is
#  read-only against the live dashboard; the staged-409 apply check sits
#  behind destructive() and restores apply_state.json afterwards.
# ====================================================================
print("\n[49] unit: update prefs + release-notes renderer (+ live card API)")

# -- 49a. preference store round-trip (temp mirror + temp config) ----------
print("  [49a] prefs round-trip (temp stores, newest-wins both ways)")
_bad = []
if _up is None:
    _bad.append("skipped - updater import failed: %s" % str(_up_import_err)[:150])
else:
    _real_before = (_state_file_snapshot(_up.PREFS_MIRROR),
                    _state_file_snapshot(_up.CONFIG_FILE))
    _td = tempfile.mkdtemp(prefix="nf-prefs-test-")
    _saved = {"PREFS_MIRROR": _up.PREFS_MIRROR, "CONFIG_FILE": _up.CONFIG_FILE}
    try:
        _up.PREFS_MIRROR = os.path.join(_td, "update_prefs.json")
        _up.CONFIG_FILE = os.path.join(_td, "config.toml")
        with open(_up.CONFIG_FILE, "w", encoding="utf-8") as _f:
            _f.write("[face]\nthreshold = 0.42\n")   # unrelated section must survive

        # (1) fresh stores == the one-time-prompt "never asked" state
        _p = _up.get_update_prefs()
        if _p != {"mode": None, "asked": False, "last_shown_notes_version": None}:
            _bad.append("fresh state -> %r" % (_p,))

        # (2) set_update_prefs writes BOTH stores surgically
        _p = _up.set_update_prefs("auto")
        if _p.get("mode") != "auto" or _p.get("asked") is not True:
            _bad.append("set(auto) -> %r" % (_p,))
        with open(_up.PREFS_MIRROR, "r", encoding="utf-8") as _f:
            _mirror = json.load(_f)
        if _mirror.get("mode") != "auto" or _mirror.get("asked") is not True \
                or not isinstance(_mirror.get("updated_at"), int):
            _bad.append("mirror -> %r" % (_mirror,))
        with open(_up.CONFIG_FILE, "r", encoding="utf-8") as _f:
            _conf = _f.read()
        for _frag in ("[update]", 'mode = "auto"', "asked = true"):
            if _frag not in _conf:
                _bad.append("config missing %r" % _frag)
        if "[face]" not in _conf or "threshold = 0.42" not in _conf:
            _bad.append("config upsert clobbered the unrelated [face] section")

        # (3) newest-wins: a NEWER config beats the mirror
        _t0 = _mirror["updated_at"]
        _up._write_prefs_config("notify", True)
        os.utime(_up.CONFIG_FILE, (_t0 + 10, _t0 + 10))
        _p = _up.get_update_prefs()
        if _p.get("mode") != "notify":
            _bad.append("newer config should win -> %r" % (_p,))

        # (4) newest-wins: a NEWER mirror beats the config again
        _mirror["updated_at"] = _t0 + 20
        with open(_up.PREFS_MIRROR, "w", encoding="utf-8") as _f:
            json.dump(_mirror, _f)
        _p = _up.get_update_prefs()
        if _p.get("mode") != "auto":
            _bad.append("newer mirror should win -> %r" % (_p,))

        # (5) installer clobber: [update] wiped from config -> mirror survives
        with open(_up.CONFIG_FILE, "w", encoding="utf-8") as _f:
            _f.write("[face]\nthreshold = 0.42\n")
        _p = _up.get_update_prefs()
        if _p.get("mode") != "auto" or _p.get("asked") is not True:
            _bad.append("config clobber lost the choice -> %r" % (_p,))

        # (6) restore_prefs_after_update re-seeds config from the mirror
        _up.restore_prefs_after_update()
        with open(_up.CONFIG_FILE, "r", encoding="utf-8") as _f:
            _conf = _f.read()
        if 'mode = "auto"' not in _conf or "asked = true" not in _conf:
            _bad.append("restore did not re-seed config: %r" % _conf[:120])

        # (7) set_notes_shown records the version but keeps the mode
        _p = _up.set_notes_shown("v9.9.9")
        if _p.get("last_shown_notes_version") != "v9.9.9" or _p.get("mode") != "auto":
            _bad.append("set_notes_shown -> %r" % (_p,))

        # (8) bad mode raises BEFORE any write (the write-free 400 contract)
        with open(_up.PREFS_MIRROR, "rb") as _f:
            _m_before = _f.read()
        with open(_up.CONFIG_FILE, "rb") as _f:
            _c_before = _f.read()
        try:
            _up.set_update_prefs("bogus")
            _bad.append("bad mode did not raise")
        except _up.UpdaterError as _e:
            if getattr(_e, "code", None) != "bad_mode":
                _bad.append("bad-mode code=%r" % getattr(_e, "code", None))
        with open(_up.PREFS_MIRROR, "rb") as _f:
            _m_after = _f.read()
        with open(_up.CONFIG_FILE, "rb") as _f:
            _c_after = _f.read()
        if _m_after != _m_before or _c_after != _c_before:
            _bad.append("bad mode wrote to a store before raising")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
    finally:
        for _k, _v in _saved.items():
            setattr(_up, _k, _v)
        _shutil_tmp.rmtree(_td, ignore_errors=True)
    _real_after = (_state_file_snapshot(_up.PREFS_MIRROR),
                   _state_file_snapshot(_up.CONFIG_FILE))
    if _real_after != _real_before:
        _bad.append("live prefs stores were touched: %r -> %r"
                    % (_real_before, _real_after))
log_result("unit/update prefs", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "fresh=never-asked, dual-store write, newest-wins both ways, "
           "clobber+restore, notes-shown keeps mode, bad_mode write-free; "
           "live stores untouched")

# -- 49b. release_notes_html (the what-changed modal) ----------------------
print("  [49b] release_notes_html (XSS-safe allowlist markdown)")
_bad = []
if _up is None:
    _bad.append("skipped - updater import failed: %s" % str(_up_import_err)[:150])
else:
    try:
        _h = _up.release_notes_html("<script>alert(1)</script>")
        if "<script" in _h.lower() or "&lt;script&gt;" not in _h:
            _bad.append("script not escaped: %r" % _h[:120])
        _h = _up.release_notes_html("## <img src=x onerror=alert(1)>")
        if "<img" in _h.lower() or "<h3>" not in _h:
            _bad.append("img not inert in heading: %r" % _h[:120])
        _h = _up.release_notes_html("[x](javascript:alert(1))")
        if "<a " in _h.lower() or 'href="javascript' in _h.lower():
            _bad.append("javascript: link became an anchor: %r" % _h[:120])
        _h = _up.release_notes_html("See [docs](https://example.com/a).")
        if ('<a href="https://example.com/a" target="_blank" '
                'rel="noopener noreferrer">docs</a>') not in _h:
            _bad.append("https link wrong: %r" % _h[:160])
        _h = _up.release_notes_html("## Title\n\n**bold** and `code`\n\n- one\n- two")
        for _frag in ("<h3>Title</h3>", "<strong>bold</strong>", "<code>code</code>",
                      "<ul>", "<li>one</li>", "<li>two</li>"):
            if _frag not in _h:
                _bad.append("missing %r" % _frag)
        _h = _up.release_notes_html("```js\n**bold** [x](https://e.com)\n```")
        if "<strong>" in _h or "<a " in _h.lower() or "**bold**" not in _h:
            _bad.append("fence content not literal: %r" % _h[:160])
        if not _up.release_notes_html("```\nunclosed").endswith("</code></pre>"):
            _bad.append("unclosed fence not terminated")
        if _up.release_notes_html("") != "" or _up.release_notes_html(None) != "":
            _bad.append("empty/None did not render empty")
    except Exception as _unit_err:
        _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
log_result("unit/release notes renderer", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "script/img escaped, javascript: never linked, https+noopener, "
           "structure renders, fences literal + auto-close, empty->''")

# -- 49c. live card API (/api/update/*) -----------------------------------
if not _server_reachable():
    print("\n[SKIP] update-card live tests: no server on %s - start dashboard.py "
          "and rerun" % BASE_URL)
else:
    print("\n[49c] live: /api/update/{status,apply-status,notes,preferences}")

    def _upd_get(path, key=None, timeout=25):
        _h = {"X-API-Key": key} if key else {}
        _r = requests.get(BASE_URL + path, headers=_h, timeout=timeout)
        try:
            return _r.status_code, _r.json()
        except Exception:
            return _r.status_code, {}

    def _upd_post(path, data, key=None, timeout=25):
        _h = {"X-API-Key": key} if key else {}
        _r = requests.post(BASE_URL + path, headers=_h, json=data, timeout=timeout)
        try:
            return _r.status_code, _r.json()
        except Exception:
            return _r.status_code, {}

    _ukey = load_dashboard_key() or KEY
    _STATUS_KEYS = ("mode", "install_mode", "local_version", "local_sha",
                    "remote_version", "update_available", "behind_count",
                    "commits", "impact", "notes_html", "stale", "error",
                    "cache_age_s", "apply", "prefs", "checked_at")
    _APPLY_KEYS = ("state", "pct", "message", "version", "exit_code",
                   "rolled_back", "updated_at")
    _PREFS_KEYS = ("mode", "asked", "last_shown_notes_version")

    # (1) no key -> 401 (rate limit safe: followed by keyed calls)
    try:
        _st, _b = _upd_get("/api/update/status")
        if _st == 401:
            log_result("/api/update/status", "GET", 401, "PASS",
                       "no key -> 401")
        elif _st == 404:
            log_result("/api/update/status", "GET", 404, "FAIL",
                       "endpoint missing - restart dashboard")
            print("      -> skipping the remaining update-card tests: "
                  "restart dashboard.py and rerun")
        else:
            log_result("/api/update/status", "GET", _st, "FAIL",
                       "no key expected 401, got %s" % _st)
    except Exception as _e:
        log_result("/api/update/status", "GET", "ERR", "FAIL",
                   "%s: %s" % (type(_e).__name__, str(_e)[:120]))
        _st = 404   # connection dead - skip the rest

    if _st not in (404, "ERR"):
        # (2) keyed status contract
        try:
            _st, _b = _upd_get("/api/update/status", key=_ukey)
            _bad = []
            if _st != 200:
                _bad.append("status=%s" % _st)
            else:
                for _k in _STATUS_KEYS:
                    if _k not in _b:
                        _bad.append("missing %s" % _k)
                if not isinstance(_b.get("update_available"), bool):
                    _bad.append("update_available=%r" % (_b.get("update_available"),))
                _ap = _b.get("apply")
                if not isinstance(_ap, dict):
                    _bad.append("apply=%r" % (_ap,))
                else:
                    for _k in _APPLY_KEYS:
                        if _k not in _ap:
                            _bad.append("apply missing %s" % _k)
                _pf = _b.get("prefs")
                if not isinstance(_pf, dict):
                    _bad.append("prefs=%r" % (_pf,))
                else:
                    for _k in _PREFS_KEYS:
                        if _k not in _pf:
                            _bad.append("prefs missing %s" % _k)
            log_result("/api/update/status", "GET", _st,
                       "FAIL" if _bad else "PASS",
                       "; ".join(_bad)[:250] if _bad else
                       "16-key contract + apply/prefs sub-dicts "
                       "(install_mode=%s, update_available=%s)"
                       % (_b.get("install_mode"), _b.get("update_available")))
        except Exception as _e:
            log_result("/api/update/status", "GET", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (3) apply-status
        try:
            _st, _b = _upd_get("/api/update/apply-status", key=_ukey)
            _bad = []
            if _st != 200:
                _bad.append("status=%s" % _st)
            else:
                for _k in _APPLY_KEYS:
                    if _k not in _b:
                        _bad.append("missing %s" % _k)
            log_result("/api/update/apply-status", "GET", _st,
                       "FAIL" if _bad else "PASS",
                       "; ".join(_bad)[:250] if _bad else
                       "7-key state contract (state=%s)" % _b.get("state"))
        except Exception as _e:
            log_result("/api/update/apply-status", "GET", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (4) notes: 200 fail-soft contract
        try:
            _st, _b = _upd_get("/api/update/notes", key=_ukey)
            _bad = []
            if _st != 200:
                _bad.append("status=%s" % _st)
            elif not any(_k in _b for _k in ("notes_html", "error")):
                _bad.append("no notes_html/error in %r" % (sorted(_b),))
            log_result("/api/update/notes", "GET", _st,
                       "FAIL" if _bad else "PASS",
                       "; ".join(_bad)[:250] if _bad else
                       "200 fail-soft (%s)" %
                       ("error" if "error" in _b else "notes_html"))
        except Exception as _e:
            log_result("/api/update/notes", "GET", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (5) preferences GET
        try:
            _st, _b = _upd_get("/api/update/preferences", key=_ukey)
            _bad = []
            if _st != 200:
                _bad.append("status=%s" % _st)
            else:
                for _k in _PREFS_KEYS:
                    if _k not in _b:
                        _bad.append("missing %s" % _k)
            log_result("/api/update/preferences", "GET", _st,
                       "FAIL" if _bad else "PASS",
                       "; ".join(_bad)[:250] if _bad else
                       "mode=%r asked=%r" % (_b.get("mode"), _b.get("asked")))
        except Exception as _e:
            log_result("/api/update/preferences", "GET", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (6) preferences POST bad mode -> 400, write-free
        try:
            _st0, _before = _upd_get("/api/update/preferences", key=_ukey)
            _st, _b = _upd_post("/api/update/preferences", {"mode": "bogus"},
                                key=_ukey)
            _st1, _after = _upd_get("/api/update/preferences", key=_ukey)
            _bad = []
            if _st != 400:
                _bad.append("expected 400, got %s" % _st)
            if _b.get("ok") is not False or not _b.get("error"):
                _bad.append("body=%r" % (_b,))
            if _after != _before:
                _bad.append("bad mode mutated prefs: %r -> %r" % (_before, _after))
            log_result("/api/update/preferences", "POST", _st,
                       "FAIL" if _bad else "PASS",
                       "; ".join(_bad)[:250] if _bad else
                       "400 ok:False + write-free (stores unchanged)")
        except Exception as _e:
            log_result("/api/update/preferences", "POST", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (7) apply POST without key -> 401 (never starts anything)
        try:
            _st, _b = _upd_post("/api/update/apply", {"relaunch": False})
            if _st == 401:
                log_result("/api/update/apply", "POST", 401, "PASS",
                           "no key -> 401 (nothing applied)")
            else:
                log_result("/api/update/apply", "POST", _st, "FAIL",
                           "no key expected 401, got %s" % _st)
        except Exception as _e:
            log_result("/api/update/apply", "POST", "ERR", "FAIL",
                       "%s: %s" % (type(_e).__name__, str(_e)[:120]))

        # (8) staged-409: in_progress state -> keyed apply refused [DESTRUCTIVE]
        if destructive(27, "/api/update/apply", "POST"):
            _bad = []
            _st = _b = None
            _as_path = getattr(_up, "APPLY_STATE_FILE", None) \
                if _up is not None else None
            if not _as_path:
                log_result("/api/update/apply", "POST", "-", "FAIL",
                           "updater import failed - cannot locate APPLY_STATE_FILE")
            else:
                _existed = os.path.exists(_as_path)
                _snap = None
                if _existed:
                    try:
                        with open(_as_path, "rb") as _f:
                            _snap = _f.read()
                    except OSError as _e:
                        _bad.append("snapshot failed: %s" % str(_e)[:100])
                _staged = {"state": "installing", "pct": 42,
                           "message": "suite staged-409 probe", "version": None,
                           "exit_code": None, "rolled_back": False,
                           "updated_at": int(time.time())}
                _wrote = False
                try:
                    _cs, _cur = _upd_get("/api/update/apply-status", key=_ukey)
                    if _cur.get("state") not in ("downloading", "verifying",
                                                 "installing"):
                        # stage a FRESH in-progress state (fresh updated_at so
                        # apply_status's stale-reconcile leaves it alone)
                        os.makedirs(os.path.dirname(_as_path), exist_ok=True)
                        with open(_as_path, "w", encoding="utf-8") as _f:
                            json.dump(_staged, _f)
                        _wrote = True
                    _cs, _conf = _upd_get("/api/update/apply-status", key=_ukey)
                    if _conf.get("state") not in ("downloading", "verifying",
                                                  "installing"):
                        _bad.append("in_progress state not visible (got %r) - "
                                    "POST withheld: it would START a real update"
                                    % (_conf.get("state"),))
                    else:
                        _st, _b = _upd_post("/api/update/apply",
                                            {"relaunch": False}, key=_ukey)
                        if _st != 409:
                            _bad.append("expected 409, got %s (%r)" % (_st, _b))
                        elif _b.get("code") != "in_progress":
                            _bad.append("409 code=%r" % (_b.get("code"),))
                except Exception as _e:
                    _bad.append("%s: %s" % (type(_e).__name__, str(_e)[:120]))
                finally:
                    try:
                        if _wrote:
                            if _snap is not None:
                                with open(_as_path, "wb") as _f:
                                    _f.write(_snap)
                            elif os.path.exists(_as_path):
                                os.remove(_as_path)
                    except OSError as _e:
                        _bad.append("restore failed: %s" % str(_e)[:100])
                try:
                    _cs, _rest = _upd_get("/api/update/apply-status", key=_ukey)
                    _want = "idle"
                    if _existed and _snap is not None:
                        try:
                            _want = json.loads(_snap.decode("utf-8")).get(
                                "state") or "idle"
                        except Exception:
                            _want = None
                    if _want is not None and _rest.get("state") != _want:
                        _bad.append("restore mismatch: state=%r want=%r"
                                    % (_rest.get("state"), _want))
                except Exception as _e:
                    _bad.append("restore confirm: %s" % str(_e)[:100])
                log_result("/api/update/apply", "POST", _st if _st else "-",
                           "FAIL" if _bad else "PASS",
                           "; ".join(_bad)[:250] if _bad else
                           "staged installing -> POST 409 in_progress; "
                           "apply_state.json restored")

# ====================================================================
#  50. UPDATE CADENCE - hourly check task + elevated apply handoff
#  50a asserts the shipped source (hard); 50b/50c query the LIVE tasks.
#  The live cadence assertions stay informational until a 0.6.0-era
#  install re-registers the tasks (the current registration predates
#  the hourly graft), so a pre-0.6.0 machine is PASS-with-note, not FAIL.
# ====================================================================
print("\n[50] scheduled tasks: hourly update check + elevated apply handoff")

# -- 50a. the idiom exists in every registrar (hard) -----------------------
print("  [50a] source: hourly idiom + UpdateApply handoff in all registrars")
_bad = []
try:
    _srcs = ("installer/post_install.ps1", "installer/install.ps1", "dashboard.py")
    _need = ("-RepetitionInterval (New-TimeSpan -Hours 1)",
             "New-TimeSpan -Days 9999", "NeoFace-UpdateApply", ".AddYears(1)",
             "-RunLevel Highest")
    for _rel in _srcs:
        _p = os.path.join(_REPO_ROOT, _rel.replace("/", os.sep))
        try:
            with open(_p, "r", encoding="utf-8", errors="replace") as _f:
                _text = _f.read()
        except OSError as _e:
            _bad.append("%s unreadable: %s" % (_rel, str(_e)[:80]))
            continue
        for _frag in _need:
            if _frag not in _text:
                _bad.append("%s missing %r" % (_rel, _frag))
    _idx = os.path.join(_REPO_ROOT, "templates", "index.html")
    try:
        with open(_idx, "r", encoding="utf-8", errors="replace") as _f:
            _text = _f.read()
        if "3600e3" not in _text:
            _bad.append("index.html missing hourly dashboard polling (3600e3)")
        if "visibilitychange" not in _text:
            _bad.append("index.html missing visibilitychange re-check")
    except OSError as _e:
        _bad.append("index.html unreadable: %s" % str(_e)[:80])
except Exception as _unit_err:
    _bad.append("%s: %s" % (type(_unit_err).__name__, str(_unit_err)[:160]))
log_result("schtasks/hourly idiom (source)", "UNIT", "-", "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else
           "PT1H + 9999d + UpdateApply(Highest, +1y) in all 3 registrars; "
           "dashboard polls hourly + on visibilitychange")

# -- 50b/50c. live task query (read-only) ----------------------------------
_PS_CADENCE = (
    "$ErrorActionPreference='SilentlyContinue'; "
    "foreach ($n in @('NeoFace-UpdateCheck','NeoFace-UpdateApply')) { "
    "$t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue; "
    "if (-not $t) { Write-Output ('ABSENT|' + $n); continue } "
    "$rl=''; try { $rl=[string]$t.Principal.RunLevel } catch {}; "
    "Write-Output ('TASK|' + $n + '|RunLevel=' + $rl); "
    "foreach ($tr in @($t.Triggers)) { "
    "$cls=$tr.CimClass.CimClassName; $iv=''; $sb=''; "
    "try { $iv=[string]$tr.Repetition.Interval } catch {}; "
    "try { $sb=[string]$tr.StartBoundary } catch {}; "
    "Write-Output ('TRIG|' + $n + '|' + $cls + '|Interval=' + $iv + "
    "'|StartBoundary=' + $sb) } }")

_tasks, _trigs, _cad_err = {}, {}, None
try:
    _cp = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_CADENCE],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, shell=False)
    for _line in (_cp.stdout or "").splitlines():
        _line = _line.strip()
        if _line.startswith("ABSENT|"):
            _tasks[_line.split("|", 1)[1]] = None
        elif _line.startswith("TASK|"):
            _parts = _line.split("|")
            if len(_parts) >= 3:
                _tasks[_parts[1]] = _parts[2].split("=", 1)[1]
        elif _line.startswith("TRIG|"):
            _parts = _line.split("|")
            if len(_parts) >= 5:
                _trigs.setdefault(_parts[1], []).append(
                    (_parts[2], _parts[3].split("=", 1)[1],
                     _parts[4].split("=", 1)[1]))
    if not _tasks and (_cp.returncode or 0) != 0:
        _cad_err = "powershell exit %s: %s" % ((_cp.returncode or 0),
                                              (_cp.stderr or "")[:120])
except Exception as _e:
    _cad_err = "%s: %s" % (type(_e).__name__, str(_e)[:140])

# -- 50b. UpdateCheck runs HOURLY (not once per logon) ---------------------
_bad, _note = [], ""
if _cad_err:
    _bad.append("task query failed: %s" % _cad_err)
elif "NeoFace-UpdateCheck" not in _tasks:
    _note = "task not registered here - see row [40] for presence"
elif any(iv == "PT1H" for _cls, iv, _sb in _trigs.get("NeoFace-UpdateCheck", [])):
    _note = "PT1H repetition registered live"
elif _tasks.get("NeoFace-UpdateApply") is not None:
    _bad.append("UpdateApply exists (0.6.0-era install) but UpdateCheck has "
                "no PT1H repetition - hourly graft missing")
else:
    _note = ("pre-0.6.0 registration (logon-only): hourly idiom verified in "
             "source row [50a]; re-registers hourly on next install/setup")
log_result("schtasks/NeoFace-UpdateCheck hourly", "GET", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else _note)

# -- 50c. UpdateApply: standing-consent elevation, far-future trigger -------
_bad, _note = [], ""
if _cad_err:
    _bad.append("task query failed: %s" % _cad_err)
elif _tasks.get("NeoFace-UpdateApply") is None:
    _note = ("not registered (pre-0.6.0 install): handoff verified in source "
             "row [50a]; installer/post_install/dashboard-setup register it")
else:
    if _tasks.get("NeoFace-UpdateApply") != "Highest":
        _bad.append("RunLevel=%r (want Highest - silent apply needs standing "
                    "consent)" % _tasks.get("NeoFace-UpdateApply"))
    _sb = next((sb for _c, _iv, sb in _trigs.get("NeoFace-UpdateApply", []) if sb),
               "")
    _m = re.search(r"(\d{4})-(\d{2})-(\d{2})", _sb)
    if _m:
        try:
            _bdate = datetime(int(_m.group(1)), int(_m.group(2)),
                              int(_m.group(3))).date()
            if _bdate <= datetime.now().date():
                _bad.append("Once trigger already due (%s) - elevated task "
                            "could self-fire" % _sb[:10])
            else:
                _note = "RunLevel=Highest, far-future trigger %s" % _sb[:10]
        except ValueError:
            _note = "RunLevel=Highest; StartBoundary unparsable (%r)" % _sb[:24]
    else:
        _note = "RunLevel=Highest; no StartBoundary reported"
log_result("schtasks/NeoFace-UpdateApply handoff", "GET", "-",
           "FAIL" if _bad else "PASS",
           "; ".join(_bad)[:250] if _bad else _note)

# ====================================================================
#  SUMMARY TABLE
# ====================================================================
print("\n" + "=" * 80)
print("  TEST RESULTS SUMMARY")
print("=" * 80)

pass_count = sum(1 for r in results if r["pass_fail"] == "PASS")
fail_count = sum(1 for r in results if r["pass_fail"] == "FAIL")
skip_count = sum(1 for r in results if r["pass_fail"] == "SKIP")
total = len(results)
executed = pass_count + fail_count
rate = (pass_count / executed * 100) if executed else 0.0

print("\n  Total: %d  |  Passed: %d  |  Failed: %d  |  Skipped: %d  |  Pass Rate: %.1f%%" % (
    total, pass_count, fail_count, skip_count, rate))
if skip_count:
    print("  %d destructive test(s) skipped - set NEOFACE_TEST_DESTRUCTIVE=1 to run them"
          % skip_count)

print("\n  %-4s  %-7s  %-35s  %-8s  %-6s  %s" % ("#", "Method", "Endpoint", "Status", "Result", "Notes"))
print("  " + "-" * 116)
for i, r in enumerate(results, 1):
    notes_short = r["notes"][:65] + "..." if len(r["notes"]) > 65 else r["notes"]
    print("  %-4d  %-7s  %-35s  %-8s  %-6s  %s" % (
        i, r["method"], r["endpoint"], r["status_code"], r["pass_fail"], notes_short))

print("\n" + "=" * 80)
print("  DONE")
print("=" * 80)
