#!/usr/bin/env python3
"""NeoFace dashboard API test suite.

================================================================================
  DESTRUCTIVE TESTS ARE OPT-IN - READ THIS FIRST
================================================================================
By default this suite runs READ-ONLY checks only (health, status, photos GET,
settings GET, logs GET, troubleshoot, update-check 27-32, static XSS guard).

Tests [5] [6] [7] [10] [11] [12] [23] [24] [25] [26] MUTATE the live
install and are SKIPPED unless the env flag is set:

    PowerShell:  $env:NEOFACE_TEST_DESTRUCTIVE = "1"; python test_dashboard_api.py
    cmd:         set NEOFACE_TEST_DESTRUCTIVE=1 && python test_dashboard_api.py
    bash:        NEOFACE_TEST_DESTRUCTIVE=1 python test_dashboard_api.py
    Off again:   Remove-Item Env:NEOFACE_TEST_DESTRUCTIVE   (or set to 0)

What a destructive run touches (do NOT enable casually):
    [5]  POST /api/settings   - rewrites config.toml (threshold etc).
                                Backed up and RESTORED automatically.
    [6]  POST /api/test-scan  - grabs the camera
    [7]  POST /api/enroll     - rebuilds the face gallery templates
    [9]  POST /api/setup/password - SAFE: asserts the Windows Hello consent
                                gate rejects a save without a token (403)
    [10] POST /api/setup/daemon   - re-registers the scheduled task
    [11] POST /api/daemon/start   - starts the daemon
    [12] POST /api/daemon/stop    - STOPS the daemon
    [23] POST /api/logs/clear     - truncates daemon/cp logs
    [24] POST /api/photos/upload  - uploads a test photo
    [25] DELETE /api/photos/...   - deletes a photo
    [26] POST /api/photos/clear   - DELETES THE ENTIRE PHOTO GALLERY

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
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".dashboard_key")
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
    _cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
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
_template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "templates", "index.html")
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

_UN_PATH = r"C:\NeoFace\tools\update_notifier.py"
_UN_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              ".update_notify.json")
_UN_CONSTANTS = ("REPO_ROOT", "STATE_FILE", "LOG_FILE", "NOTIFY_MIN_INTERVAL_S")
_UN_FUNCTIONS = ("load_state", "save_state", "should_notify", "show_prompt",
                 "apply_update", "run_once", "main")
_UN_DEFAULTS = {"declined_sha": None, "last_notified": 0, "last_notified_sha": None}


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
              "last_notified_sha": "0123456789abcdef0123456789abcdef01234567"}
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
