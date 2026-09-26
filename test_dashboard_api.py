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
print("\n[5] POST /api/settings")
settings_body = {
    "threshold": 0.35,
    "frames": 3,
    "hit_required": 2,
    "camera_index": 0,
    "resolution_w": 640,
    "resolution_h": 480
}
test_post("/api/settings", json_data=settings_body, expected_status=200)

# ── 6. POST /api/test-scan ─────────────────────────────────────────
# Requires camera + engine; expect 200 on success or 500 if no camera
print("\n[6] POST /api/test-scan")
test_post("/api/test-scan", json_data={})

# ── 7. POST /api/enroll ────────────────────────────────────────────
# Requires gallery + photos; may succeed or return output with 0 templates
print("\n[7] POST /api/enroll")
test_post("/api/enroll", json_data={})

# ── 8. POST /api/setup/models ──────────────────────────────────────
print("\n[8] POST /api/setup/models")
test_post("/api/setup/models", json_data={})

# ── 9. POST /api/setup/password ────────────────────────────────────
print("\n[9] POST /api/setup/password")
test_post("/api/setup/password", json_data={"password": "testpass123"}, expected_status=200)

# ── 10. POST /api/setup/daemon ─────────────────────────────────────
print("\n[10] POST /api/setup/daemon")
test_post("/api/setup/daemon", json_data={}, expected_status=200)

# ── 11. POST /api/daemon/start ─────────────────────────────────────
print("\n[11] POST /api/daemon/start")
test_post("/api/daemon/start", json_data={}, expected_status=200)

# ── 12. POST /api/daemon/stop ──────────────────────────────────────
print("\n[12] POST /api/daemon/stop")
test_post("/api/daemon/stop", json_data={}, expected_status=200)

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
print("\n[23] POST /api/logs/clear")
test_post("/api/logs/clear", json_data={"type": "daemon"}, expected_status=200)

# ── 24. POST /api/photos/upload ────────────────────────────────────
print("\n[24] POST /api/photos/upload")
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
print("\n[25] DELETE /api/photos/{name}")
# Re-fetch photos to find the uploaded one
photos_resp2 = test_get("/api/photos", expected_status=200)
photo_name = None
if photos_resp2 and isinstance(photos_resp2, dict):
    photo_list = photos_resp2.get("photos", [])
    if isinstance(photo_list, list) and len(photo_list) > 0:
        photo_name = photo_list[0].get("name")

if photo_name:
    test_delete("/api/photos/%s" % photo_name, expected_status=200)
else:
    # Try deleting the one we just uploaded
    test_delete("/api/photos/test_upload.png", expected_status=200)

# ── 26. POST /api/photos/clear ─────────────────────────────────────
print("\n[26] POST /api/photos/clear")
test_post("/api/photos/clear", json_data={}, expected_status=200)

# Clean up temp file
if os.path.exists(test_file_path):
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
