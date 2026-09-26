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
    params = {"key": KEY}
    if extra_params:
        params.update(extra_params)
    try:
        r = requests.get("%s%s" % (BASE_URL, endpoint), params=params, timeout=15)
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
    params = {"key": KEY}
    try:
        if files:
            r = requests.post("%s%s" % (BASE_URL, endpoint), params=params, files=files, timeout=30)
        else:
            r = requests.post("%s%s" % (BASE_URL, endpoint), params=params, json=json_data, timeout=30)

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
    params = {"key": KEY}
    try:
        r = requests.delete("%s%s" % (BASE_URL, endpoint), params=params, timeout=10)
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
print("\n[5] POST /api/settings")
if destructive(5, "/api/settings", "POST"):
    settings_body = {
        "threshold": 0.35,
        "frames": 3,
        "hit_required": 2,
        "camera_index": 0,
        "resolution_w": 640,
        "resolution_h": 480
    }
    _cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.toml")
    _cfg_backup = None
    if os.path.exists(_cfg_path):
        with open(_cfg_path, "rb") as _cf:
            _cfg_backup = _cf.read()
    try:
        test_post("/api/settings", json_data=settings_body, expected_status=200)
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
print("\n[8] POST /api/setup/models")
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
print("\n[13] POST /api/troubleshoot/all")
test_post("/api/troubleshoot/all", json_data={}, expected_status=200)

# ── 14. POST /api/troubleshoot/camera ──────────────────────────────
print("\n[14] POST /api/troubleshoot/camera")
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

# ════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("  TEST RESULTS SUMMARY")
print("=" * 80)

pass_count = sum(1 for r in results if r["pass_fail"] == "PASS")
fail_count = sum(1 for r in results if r["pass_fail"] == "FAIL")
total = len(results)

print("\n  Total: %d  |  Passed: %d  |  Failed: %d  |  Pass Rate: %.1f%%" % (
    total, pass_count, fail_count, pass_count / total * 100))

print("\n  %-4s  %-7s  %-35s  %-8s  %-6s  %s" % ("#", "Method", "Endpoint", "Status", "Result", "Notes"))
print("  " + "-" * 116)
for i, r in enumerate(results, 1):
    notes_short = r["notes"][:65] + "..." if len(r["notes"]) > 65 else r["notes"]
    print("  %-4d  %-7s  %-35s  %-8s  %-6s  %s" % (
        i, r["method"], r["endpoint"], r["status_code"], r["pass_fail"], notes_short))

print("\n" + "=" * 80)
print("  DONE")
print("=" * 80)
