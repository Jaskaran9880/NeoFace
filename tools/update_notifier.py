"""NeoFace logon update notifier.

Scheduled task: NeoFace-UpdateCheck (AtLogOn + 1 min delay, pythonw).
Flow: wait for network -> reuse dashboard's update check -> Yes/No prompt
only when a fresh result shows behind_count > 0 -> git pull --ff-only
(origin allow-list re-verified) or open GitHub for non-git installs.

Dedupe: .update_notify.json keeps declined_sha / last_notified(_sha) so a
declined version never re-prompts and at most one prompt appears per 24h.

Fail-soft: every failure appends one line to update_notifier.log and exits 0.

Import is 100% side-effect free (no network, no window, no task/state IO) so
test_dashboard_api.py [41] can import this module directly. Public API below
is the frozen contract used by test_dashboard_api.py [41].
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(REPO_ROOT, ".update_notify.json")
LOG_FILE = os.path.join(REPO_ROOT, "update_notifier.log")
NOTIFY_MIN_INTERVAL_S = 86400

_STATE_DEFAULTS = {
    "declined_sha": None,
    "last_notified": 0,
    "last_notified_sha": None,
}


def load_state():
    """Read .update_notify.json -> dict; missing/corrupt -> defaults."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            state = dict(_STATE_DEFAULTS)
            state.update({k: data.get(k) for k in _STATE_DEFAULTS})
            return state
    except Exception:
        pass
    return dict(_STATE_DEFAULTS)


def save_state(state):
    """Atomic state write: tmp in REPO_ROOT, then os.replace()."""
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_FILE)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def should_notify(payload, state, now=None):
    """True only for a fresh, solid result with a not-yet-declined update."""
    if not isinstance(payload, dict):
        return False
    if not payload.get("ok") or payload.get("stale") or payload.get("error"):
        return False
    behind = payload.get("behind_count")
    if not isinstance(behind, int) or isinstance(behind, bool) or behind <= 0:
        return False
    remote_sha = payload.get("remote_sha")
    if not remote_sha:
        return False
    if remote_sha == state.get("declined_sha"):
        return False
    now = time.time() if now is None else now
    if (state.get("last_notified_sha") == remote_sha
            and now - (state.get("last_notified") or 0) < NOTIFY_MIN_INTERVAL_S):
        return False
    return True


def _log(line):
    """Append one timestamped line to LOG_FILE (self-truncating at 100KB)."""
    try:
        # Keep the file bounded: >100KB -> keep only the last 20 lines.
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 100 * 1024:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-20:]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(tail)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (stamp, line))
    except Exception:
        pass    # logging must never be able to break the notifier


def _parse_flags(flags):
    """--test / --check-only / --answer yes|no -> dict. Raises ValueError."""
    parsed = {"test": False, "check_only": False, "answer": None}
    args = list(flags or [])
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--test":
            parsed["test"] = True
        elif arg == "--check-only":
            parsed["check_only"] = True
        elif arg == "--answer" or str(arg).startswith("--answer="):
            if arg == "--answer":
                i += 1
                if i >= len(args):
                    raise ValueError("--answer needs a value of yes or no")
                value = args[i]
            else:
                value = arg.split("=", 1)[1]
            value = str(value or "").strip().lower()
            if value not in ("yes", "no"):
                raise ValueError("--answer must be yes or no, got %r" % value)
            parsed["answer"] = value
        else:
            raise ValueError("unknown flag: %r" % (arg,))
        i += 1
    return parsed


def _wait_for_network(host="api.github.com", port=443,
                      timeout_s=300, interval_s=15, probe_s=3):
    """True once a TCP probe connects; False after timeout_s (caller: exit 0)."""
    deadline = time.time() + timeout_s
    while True:
        try:
            conn = socket.create_connection((host, port), probe_s)
            conn.close()
            return True
        except OSError:
            if time.time() + probe_s >= deadline:
                return False    # still offline: silent no-op, never an error
            time.sleep(interval_s)


def _import_dashboard(name):
    """Import one helper from dashboard.py; failure -> None (already logged).

    Importing dashboard is safe: Flask app creation only, app.run() is
    __main__-guarded, so no server, port bind or window appears here.
    """
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    try:
        module = __import__("dashboard", fromlist=[name])
        return getattr(module, name)
    except Exception as exc:
        _log("dashboard import failed (%s): %r" % (name, exc))
        return None


def show_prompt(text, title="NeoFace Update", buttons="yesno"):
    """Blocking Yes/No MessageBox; True = Yes, False = No / no UI available."""
    try:
        import ctypes   # Windows-only: imported lazily, import stays pure
        flags = 0x4 | 0x40 | 0x10000   # MB_YESNO | MB_ICONINFORMATION | MB_SETFOREGROUND
        answer = ctypes.windll.user32.MessageBoxW(None, text or "", title, flags)
        return answer == 6             # IDYES
    except Exception:
        return False                   # no UI -> treat as No (fail soft)


def _prompt_text(payload):
    """Human-readable MessageBox body from the update-check payload."""
    local_version = payload.get("local_version") or "unknown version"
    local_sha = payload.get("local_sha") or "unknown"
    remote_sha = payload.get("remote_sha") or "unknown"
    behind = payload.get("behind_count")
    lines = []
    if isinstance(behind, int) and not isinstance(behind, bool) and behind > 0:
        lines.append("A NeoFace update is available.")
    else:
        lines.append("NeoFace update check.")   # --test run with behind_count 0
    lines.append("")
    lines.append("Installed: %s (%s)" % (local_version, local_sha))
    lines.append("Available: %s" % remote_sha)
    if isinstance(behind, int) and not isinstance(behind, bool):
        if behind > 0:
            lines.append("%d commit%s behind." % (behind, "" if behind == 1 else "s"))
        else:
            lines.append("0 commits behind (prompt shown for testing).")
    commits = payload.get("commits") or []
    subjects = [c.get("subject") for c in commits
                if isinstance(c, dict) and c.get("subject")][:3]
    if subjects:
        lines.append("")
        lines.append("Latest changes:")
        for subject in subjects:
            lines.append("  - %s" % subject)
    lines.append("")
    lines.append("Update now? Yes = pull the update, No = skip this version.")
    return "\n".join(lines)


def _git_exe():
    """Locate git.exe: PATH first, then the usual Windows install paths."""
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


def _run_git(args, timeout=15):
    """Run git in REPO_ROOT -> (ok, stdout, stderr). Never raises."""
    exe = _git_exe()
    if not exe:
        return False, "", "git executable not found"
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"     # never hang on a credential prompt
    env["GCM_INTERACTIVE"] = "never"
    try:
        result = subprocess.run(
            [exe] + list(args), cwd=REPO_ROOT, env=env,
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0, result.stdout or "", result.stderr or ""
    except Exception as exc:
        return False, "", str(exc)


def _open_github(reason):
    """Fallback path: open the repo page in the browser (no safe git update)."""
    url = "https://github.com/Jaskaran9880/NeoFace"
    try:
        os.startfile(url)
        _log("apply: %s -> opened %s" % (reason, url))
        return {"ok": True, "message": "Not a git clone - opened GitHub instead"}
    except Exception as exc:
        _log("apply: %s -> startfile failed: %r" % (reason, exc))
        return {"ok": False,
                "message": "Not a git clone and GitHub could not be opened: %s" % exc}


def apply_update(payload):
    """Origin allow-list + git pull --ff-only, or browser for non-git."""
    if not isinstance(payload, dict):
        return {"ok": False, "message": "No update payload - nothing to apply."}
    if payload.get("mode") != "git":
        return _open_github("mode %r is not a git install" % payload.get("mode"))

    # Re-verify the origin allow-list before touching the network.
    check_origin = _import_dashboard("_git_check_origin")
    if check_origin is None:
        return _open_github("origin allow-list check unavailable")
    try:
        check_origin()
    except Exception as exc:
        return _open_github("origin rejected (%s)" % (exc,))

    if _git_exe() is None:
        return _open_github("git is not installed")
    ok, out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], 10)
    branch = (out or "").strip() if ok else ""
    if not branch or branch == "HEAD":    # detached HEAD -> default branch
        branch = "main"

    ok, out, err = _run_git(["pull", "--ff-only", "origin", branch], 120)
    if ok:
        _, version, _ = _run_git(["describe", "--tags", "--always"], 10)
        version = (version or "").strip() or "the latest commit"
        _log("apply: pulled %s (branch %s)" % (version, branch))
        return {"ok": True,
                "message": ("Updated to %s. Restart the NeoFace "
                            "daemon/dashboard to use it." % version)}

    detail = ((err or out or "").strip())[-300:]
    message = "git pull --ff-only on %s failed: %s" % (branch, detail or "unknown error")
    if any(word in ((err or "") + (out or "")).lower()
           for word in ("local changes", "stash", "overwritten")):
        message += " - commit/stash your local changes, or re-run the installer"
    _log("apply: %s" % message)
    return {"ok": False, "message": message}


def _run_once(flags):
    """One check cycle (assumes no unexpected exception escapes)."""
    opts = _parse_flags(flags)

    # Real runs wait for the network first; --test / --check-only skip the wait.
    if not opts["test"] and not opts["check_only"]:
        if not _wait_for_network():
            return 0

    perform_check = _import_dashboard("_perform_update_check")
    if perform_check is None:
        return 0                       # import failure: logged, fail soft
    payload = perform_check()
    if not isinstance(payload, dict):
        _log("update check returned %r - nothing to do" % (type(payload).__name__,))
        return 0

    if opts["check_only"]:
        try:
            print(json.dumps(payload))
        except Exception:
            _log("check-only: payload could not be written to stdout")
        return 0                       # no wait, no UI, no state change

    state = load_state()
    if not opts["test"] and not should_notify(payload, state):
        return 0                       # up to date / declined / prompted recently

    answer = opts["answer"]
    if answer is None:
        answer = "yes" if show_prompt(_prompt_text(payload)) else "no"

    # Bookkeeping happens whenever a prompt was shown (also for --answer).
    remote_sha = payload.get("remote_sha")
    state["last_notified"] = time.time()
    state["last_notified_sha"] = remote_sha
    if answer == "no":
        state["declined_sha"] = remote_sha
    save_state(state)
    _log("prompt: remote=%s behind=%s answer=%s"
         % (remote_sha, payload.get("behind_count"), answer))

    if answer == "yes":
        result = apply_update(payload)
        _log("apply: ok=%s - %s" % (result.get("ok"), result.get("message")))
    return 0


def run_once(flags=None):
    """One full check cycle; returns process exit code (always 0 in prod)."""
    try:
        return _run_once(flags)
    except Exception as exc:
        try:
            _log("run_once aborted: %r" % (exc,))
        except Exception:
            pass
        return 0                       # NEVER raise to the OS


def main(argv=None):
    return run_once(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
