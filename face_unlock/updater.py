"""NeoFace updater library.

Shared by the dashboard (Flask endpoints), tools/update_notifier.py
(scheduled task) and tools/apply_update.ps1 (elevated apply). Two install
modes are supported:

  git       - a developer clone: .git exists, git.exe is installed and the
              origin URL is on the allow-list. Updates apply via
              ``git pull --ff-only``.
  installed - a setup.exe install (no .git): updates are the signed
              ``NeoFace-Setup-<v>.exe`` GitHub Release assets, verified
              against the SHA256 published in the release notes, applied by
              the elevated ``NeoFace-UpdateApply`` scheduled task.

Import is 100% side-effect free (no network, no window, no task/state IO),
same discipline as tools/update_notifier.py, so tests can import directly.
Everything that can fail raises UpdaterError with a stable ``code``; callers
translate that into their own fail-soft contract.

Security invariants (docs/SECURITY.md):
  * the release slug is a constant - never taken from user input;
  * the asset URL is only ever read from the GitHub API response and its
    host must be on ALLOWED_DOWNLOAD_HOSTS;
  * an installer is executed only after its bytes hash-match the SHA256
    published in the TLS-delivered release notes, re-checked inside the
    elevated context (see tools/apply_update.ps1).
"""

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_SLUG = "Jaskaran9880/NeoFace"
GITHUB_API = "https://api.github.com/repos/Jaskaran9880/NeoFace"
GITHUB_USER_AGENT = "NeoFace-Dashboard"
ALLOWED_DOWNLOAD_HOSTS = ("github.com", "objects.githubusercontent.com",
                          "api.github.com")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
VERSION_FILE = os.path.join(ROOT, "VERSION")
FALLBACK_VERSION = "0.5.0"

# ProgramData is preserved by the installer across updates and uninstalls
# (installer.iss UninstallDelete) and is user-writable, so it is the right
# home for state that must survive a self-update.
DATA_DIR = os.path.expandvars(r"C:\ProgramData\NeoFace")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")
PREFS_MIRROR = os.path.join(DATA_DIR, "update_prefs.json")
APPLY_STATE_FILE = os.path.join(UPDATES_DIR, "apply_state.json")
PENDING_FILE = os.path.join(UPDATES_DIR, "pending.json")
RELEASE_CACHE_FILE = os.path.join(ROOT, ".release_cache.json")

# Origin allow-list (compared after _normalize_origin). Kept in sync with
# dashboard.ALLOWED_ORIGINS; duplicated rather than imported because
# dashboard imports this module and the import must stay acyclic.
ALLOWED_ORIGINS = (
    "https://github.com/jaskaran9880/neoface",
    "git@github.com:jaskaran9880/neoface",
    "ssh://git@github.com:jaskaran9880/neoface",
)


class UpdaterError(Exception):
    """Updater failure with a stable code and a user-facing message.

    cacheable=True marks network failures so the caller can cache them and
    stop every check from re-hitting a dead network.
    """

    def __init__(self, code, message=None, cacheable=False):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.cacheable = cacheable


# --- git helpers (self-contained: updater.py never imports dashboard) -----
def _git_exe():
    """Locate git.exe once: PATH first, then the usual Windows install paths."""
    found = shutil.which("git")
    if found:
        return found
    for candidate in (r"C:\Program Files\Git\cmd\git.exe",
                      r"C:\Program Files (x86)\Git\cmd\git.exe",
                      r"C:\Program Files\Git\bin\git.exe",
                      os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
        if os.path.isfile(candidate):
            return candidate
    return None


def _git(args, cwd=ROOT, timeout=10):
    """Run a git command; returns (ok, stdout, stderr). Never raises."""
    exe = _git_exe()
    if not exe:
        return False, "", "git executable not found"
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    try:
        result = subprocess.run(
            [exe] + list(args),
            cwd=cwd,
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


def check_origin(root=ROOT):
    """Raise UpdaterError('origin_mismatch') unless every origin URL is allowed.

    Runs BEFORE any network call so a tampered/foreign remote never causes a
    fetch. Public: apply paths re-verify the allow-list right before pulling.
    """
    ok, out, _ = _git(["remote", "get-url", "origin", "--all"], cwd=root, timeout=10)
    urls = [u for u in (out or "").splitlines() if u.strip()] if ok else []
    # Every configured URL must be allow-listed: git fetch fails over through
    # the remote's URL list, so one foreign URL among allowed ones is enough.
    if not urls or any(_normalize_origin(u) not in ALLOWED_ORIGINS for u in urls):
        raise UpdaterError("origin_mismatch", "origin_mismatch")


# --- install mode + local version -----------------------------------------
def detect_install_mode(root=ROOT):
    """"git" iff <root>\\.git exists, git.exe works and origin is allowed.

    Keying on the .git *directory* (not git.exe presence) keeps an installed
    build that happens to have git on PATH classified as "installed".
    """
    if not os.path.isdir(os.path.join(root, ".git")):
        return "installed"
    if not _git_exe():
        return "installed"
    try:
        check_origin(root)
    except UpdaterError:
        return "installed"
    return "git"


def local_version(root=ROOT):
    """{"version", "sha", "source"} - git describe -> VERSION file -> fallback.

    source is one of "git" | "version_file" | "fallback". Installed builds
    get their VERSION file stamped by installer/post_install.ps1, which is
    what lets a no-git install report a real version instead of the fallback
    forever.
    """
    if os.path.isdir(os.path.join(root, ".git")) and _git_exe():
        ok, out, _ = _git(["describe", "--tags", "--always"], cwd=root, timeout=5)
        version = out.strip() if ok and out.strip() else None
        ok, out, _ = _git(["rev-parse", "--short=7", "HEAD"], cwd=root, timeout=5)
        sha = out.strip() if ok and out.strip() else None
        if version:
            return {"version": version, "sha": sha, "source": "git"}
    try:
        with open(VERSION_FILE if root == ROOT else os.path.join(root, "VERSION"),
                  "r", encoding="utf-8") as f:
            version = f.read().strip()
        if version:
            return {"version": version, "sha": None, "source": "version_file"}
    except OSError:
        pass
    return {"version": FALLBACK_VERSION, "sha": None, "source": "fallback"}


# --- semver ----------------------------------------------------------------
_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def parse_semver(text):
    """(major, minor, patch) from "v0.6.0" / "0.6.0" / "v0.5.0-12-gabc1234".

    Prerelease/build suffixes are ignored; None when unparseable. A
    git-describe value therefore compares as its nearest tag.
    """
    match = _SEMVER_RE.match((text or "").strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_newer(remote_tag, local_version):
    """True only when the remote version is strictly greater than the local one.

    Either side unparseable -> False (never apply an update we cannot
    compare; the caller keeps the "check failed" copy instead).
    """
    remote = parse_semver(remote_tag)
    local = parse_semver(local_version)
    if remote is None or local is None:
        return False
    return remote > local


# --- release metadata (ETag cache, 304 = free, stale-serve on 403) --------
RELEASE_CACHE_TTL = 3600          # serve cache under an hour old without a request
RELEASE_STALE_MAX_AGE = 7 * 24 * 3600   # same 7d bound as the dashboard cache


def _release_cache_read():
    """Read .release_cache.json -> dict or {} on any problem."""
    try:
        with open(RELEASE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _release_cache_write(data):
    """Atomic cache write: temp file next to it, then os.replace()."""
    tmp = RELEASE_CACHE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, RELEASE_CACHE_FILE)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _github_get_release(path, etag=None, timeout=10):
    """GET a GitHub API path -> (status, json_or_None, response_etag).

    304 (ETag hit) returns the marker without a body - GitHub does not count
    304s against the unauthenticated rate limit, which is what makes an
    hourly poll safe. 403 with an exhausted rate-limit budget raises
    UpdaterError('rate_limited'); every other failure raises with the
    cacheable flag so the caller can back off instead of hammering.
    """
    headers = {"User-Agent": GITHUB_USER_AGENT, "Accept": "application/vnd.github+json"}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(GITHUB_API + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            data = json.loads(body.decode("utf-8", "replace"))
            return response.status, data, response.headers.get("ETag")
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, None, exc.headers.get("ETag")
        if exc.code == 403 and (exc.headers.get("X-RateLimit-Remaining") or "1") == "0":
            reset = int(exc.headers.get("X-RateLimit-Reset") or 0)
            raise UpdaterError("rate_limited",
                               "GitHub API rate limit exhausted (resets at %s)." % reset,
                               cacheable=True)
        raise UpdaterError("api_unreachable",
                           "GitHub API returned HTTP %s." % exc.code,
                           cacheable=True)
    except urllib.error.URLError as exc:
        raise UpdaterError("offline",
                           "Network unavailable - GitHub API unreachable (%s)" % exc,
                           cacheable=True)
    except UpdaterError:
        raise
    except Exception as exc:   # JSON decode and friends
        raise UpdaterError("api_unreachable",
                           "Bad response from GitHub API: %s" % exc,
                           cacheable=True)


_SHA256_HEADING_RE = re.compile(r"(?is)sha256\b[^\n]*\n+`*\s*([0-9a-f]{64})")
_SHA256_BARE_RE = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


def parse_sha256_from_body(body):
    """The installer hash release.yml publishes under the '### SHA256' heading.

    Falls back to the first standalone 64-hex run in the body; None when the
    release carries no hash (an update can then never be auto-applied - the
    apply path refuses to run anything it cannot verify).
    """
    if not body:
        return None
    match = _SHA256_HEADING_RE.search(body)
    if match:
        return match.group(1).lower()
    match = _SHA256_BARE_RE.search(body)
    return match.group(0).lower() if match else None


def find_setup_asset(release, version):
    """The NeoFace-Setup-<version>.exe asset, but only from an allowed host.

    The URL is never constructed - it is read from the API response and its
    host checked against ALLOWED_DOWNLOAD_HOSTS (release assets redirect to
    objects.githubusercontent.com). None when missing or on a foreign host.
    """
    if not isinstance(release, dict):
        return None
    want = re.compile(r"^NeoFace-Setup-%s\.exe$" % re.escape(str(version or "").strip()),
                      re.IGNORECASE)
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("url") or "")
        if not want.match(name):
            continue
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        if host not in ALLOWED_DOWNLOAD_HOSTS:
            continue
        return {"name": name, "url": url, "size": asset.get("size")}
    return None


def _release_payload(data, response_etag, now):
    """Contract dict for one release; raises UpdaterError('not_found')."""
    tag = str((data or {}).get("tag_name") or "")
    if not tag:
        raise UpdaterError("not_found", "GitHub returned no latest release.",
                           cacheable=True)
    body = str((data or {}).get("body") or "")
    assets = []
    for raw in (data or {}).get("assets") or []:
        if isinstance(raw, dict):
            assets.append({
                "name": str(raw.get("name") or ""),
                "url": str(raw.get("browser_download_url") or ""),
                "size": raw.get("size"),
            })
    return {
        "tag": tag,
        "version": tag.lstrip("v"),
        "body": body,
        "published_at": str((data or {}).get("published_at") or ""),
        "assets": assets,
        "sha256": parse_sha256_from_body(body),
        "etag": response_etag,
        "fetched_at": int(now),
        "cached": False,
        "cache_age_s": 0,
    }


def _stale_release_payload(cache, now):
    """Last good release payload if <= 7d old, marked stale; else None."""
    entry = cache.get("entry") if isinstance(cache, dict) else None
    payload = entry.get("payload") if isinstance(entry, dict) else None
    if isinstance(payload, dict) and payload.get("tag"):
        age = now - (entry.get("fetched_at") or 0)
        if 0 <= age <= RELEASE_STALE_MAX_AGE:
            out = dict(payload)
            out["cached"] = True
            out["stale"] = True
            out["cache_age_s"] = int(age)
            return out
    return None


def fetch_latest_release(force=False, timeout=10):
    """Latest GitHub Release -> contract dict, honouring ETag and the cache.

    Contract keys: tag, version, body, published_at, assets, sha256, etag,
    fetched_at, cached, cache_age_s (+ stale on degraded serves). Offline or
    rate-limited results serve the last good payload up to 7 days; older
    than that (or never fetched) raises the UpdaterError for the caller's
    fail-soft contract.
    """
    now = time.time()
    cache = _release_cache_read()
    entry = cache.get("entry") if isinstance(cache, dict) else None
    if (not force and isinstance(entry, dict)
            and isinstance(entry.get("payload"), dict)
            and now - (entry.get("fetched_at") or 0) < RELEASE_CACHE_TTL):
        out = dict(entry["payload"])
        out["cached"] = True
        out["cache_age_s"] = int(now - (entry.get("fetched_at") or 0))
        return out

    etag = entry.get("etag") if isinstance(entry, dict) else None
    try:
        status, data, response_etag = _github_get_release("/releases/latest",
                                                          etag=etag, timeout=timeout)
    except UpdaterError as exc:
        stale = _stale_release_payload(cache, now)
        if stale is not None:
            return stale
        raise exc

    if status == 304 and isinstance(entry, dict) and entry.get("payload"):
        # Free (304s do not count against the rate limit): refresh the clock
        # so the hourly cadence keeps serving cache without re-downloading.
        fetched_at = int(now)
        payload = dict(entry["payload"])
        payload["fetched_at"] = fetched_at
        payload["cached"] = True
        payload["cache_age_s"] = 0
        _release_cache_write({"etag": etag, "entry": {"fetched_at": fetched_at,
                                                      "etag": etag,
                                                      "payload": payload}})
        return payload

    payload = _release_payload(data, response_etag, now)
    _release_cache_write({"etag": response_etag,
                          "entry": {"fetched_at": payload["fetched_at"],
                                    "etag": response_etag,
                                    "payload": payload}})
    return payload


# --- download + verify -----------------------------------------------------
_DOWNLOAD_CHUNK = 256 * 1024
# In-process progress for the dashboard's 1s poll (survives nothing - the
# authoritative cross-process state is apply_state.json written by the apply
# script; this dict only fills in pct while the download runs in-process).
_PROGRESS = {"phase": None, "done": 0, "total": None, "pct": None, "message": ""}


def set_progress(phase=None, done=None, total=None, pct=None, message=None):
    """Update the in-process download progress snapshot (thread-safe enough:
    each field is a single atomic assignment; the reader tolerates tearing)."""
    if phase is not None:
        _PROGRESS["phase"] = phase
    if done is not None:
        _PROGRESS["done"] = done
    if total is not None:
        _PROGRESS["total"] = total
    if pct is not None:
        _PROGRESS["pct"] = pct
    if message is not None:
        _PROGRESS["message"] = message


def get_progress():
    """Copy of the in-process progress snapshot (never the live dict)."""
    return dict(_PROGRESS)


def verify_sha256(path, expected_hex):
    """Streaming SHA256 of <path> compared in constant time with expected_hex."""
    if not expected_hex:
        return False
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(_DOWNLOAD_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return False
    return hmac.compare_digest(digest.hexdigest().lower(),
                               str(expected_hex).strip().lower())


def _download_with_curl(url, dest, timeout):
    """Fallback downloader (Win10 1803+ ships curl.exe). Raises on failure."""
    exe = shutil.which("curl.exe") or "curl.exe"
    try:
        result = subprocess.run(
            [exe, "-fsSL", "--retry", "3", "--connect-timeout", "10",
             "-o", dest, url],
            capture_output=True, timeout=timeout, encoding="utf-8",
            errors="replace", shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise UpdaterError("download_failed", "curl download failed: %s" % exc,
                           cacheable=True)
    if result.returncode != 0:
        detail = ((result.stderr or result.stdout or "").strip())[-200:]
        raise UpdaterError("download_failed",
                           "curl download failed: %s" % (detail or "unknown error"),
                           cacheable=True)


def download_latest(release=None, dest_dir=UPDATES_DIR, progress_cb=None,
                    timeout=300):
    """Download the release's setup exe, verify it, atomically finalize.

    The URL comes from the API response (find_setup_asset already checked the
    host allow-list). The bytes stream to <name>.part, are hashed, and are
    only os.replace()d to the final name AFTER the hash matches the SHA256
    published in the release notes. A mismatch deletes the .part file and
    raises UpdaterError('hash_mismatch') - the file never exists as an
    executable name unverified.
    """
    release = release if release is not None else fetch_latest_release()
    version = release.get("version")
    asset = find_setup_asset(release, version)
    if asset is None:
        raise UpdaterError("no_asset",
                           "Release %s has no NeoFace-Setup exe on an allowed host."
                           % release.get("tag"))
    expected = release.get("sha256")
    if not expected:
        raise UpdaterError("no_hash",
                           "Release %s publishes no SHA256 - automatic apply is refused."
                           % release.get("tag"))

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as exc:
        raise UpdaterError("download_failed", "Cannot create %s: %s" % (dest_dir, exc))

    final_path = os.path.join(dest_dir, asset["name"])
    if os.path.isfile(final_path) and verify_sha256(final_path, expected):
        set_progress(phase="verifying", pct=100,
                     message="Installer already downloaded and verified.")
        if progress_cb:
            progress_cb(1, 1)
        return {"path": final_path, "sha256": expected,
                "size": os.path.getsize(final_path), "tag": release.get("tag"),
                "reused": True}

    part_path = final_path + ".part"
    set_progress(phase="downloading", done=0, total=asset.get("size"), pct=0,
                 message="Downloading %s..." % asset["name"])
    try:
        try:
            request = urllib.request.Request(
                asset["url"],
                headers={"User-Agent": GITHUB_USER_AGENT,
                         "Accept": "application/octet-stream"})
            done = 0
            total = asset.get("size") if isinstance(asset.get("size"), int) else None
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.headers.get("Content-Length"):
                    try:
                        total = int(response.headers["Content-Length"])
                    except (TypeError, ValueError):
                        pass
                with open(part_path, "wb") as out:
                    while True:
                        chunk = response.read(_DOWNLOAD_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        pct = int(done * 100 / total) if total else None
                        set_progress(done=done, total=total, pct=pct)
                        if progress_cb:
                            progress_cb(done, total or 0)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # urllib failed -> native curl fallback (same posture as
            # post_install.ps1's curl-first model, mirrored for downloads).
            set_progress(message="urllib failed (%s) - retrying with curl..." % str(exc)[:80])
            try:
                if os.path.exists(part_path):
                    os.remove(part_path)
            except OSError:
                pass
            _download_with_curl(asset["url"], part_path, timeout)

        set_progress(phase="verifying", pct=None,
                     message="Verifying download integrity...")
        if not verify_sha256(part_path, expected):
            try:
                os.remove(part_path)
            except OSError:
                pass
            set_progress(phase="failed", pct=None,
                         message="Download corrupted (SHA256 mismatch) - deleted.")
            raise UpdaterError("hash_mismatch",
                               "SHA256 mismatch for %s - the download was deleted; "
                               "the update was NOT applied." % asset["name"])
        os.replace(part_path, final_path)
    except UpdaterError:
        raise
    except Exception as exc:
        try:
            if os.path.exists(part_path):
                os.remove(part_path)
        except OSError:
            pass
        set_progress(phase="failed", message="Download failed.")
        raise UpdaterError("download_failed", "Download failed: %s" % exc,
                           cacheable=True)

    set_progress(phase="downloaded", pct=100, message="Installer verified.")
    return {"path": final_path, "sha256": expected,
            "size": os.path.getsize(final_path), "tag": release.get("tag"),
            "reused": False}
