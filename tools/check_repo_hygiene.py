"""Fail if secrets/debug artifacts are tracked or ignore rules go missing.

Checks:
  - no tracked file matches secret/artifact patterns (.dashboard_key,
    cred.bin, faces*.dat, daemon.log, debug_*.jpg)
  - .dashboard_key, debug images, and logs are ignored by .gitignore
  - .dashboard_key never appears in git status output

Run from the repo root:  python tools\\check_repo_hygiene.py
"""
import re
import subprocess
import sys

FORBIDDEN_TRACKED = re.compile(
    r"(^|/)(\.dashboard_key|cred\.bin|faces(_fast|_acc)?\.dat|daemon\.log)$"
    r"|(^|/)debug_[^/]*\.jpg$"
)
MUST_IGNORE = (".dashboard_key", "debug_frame.jpg", "scratch.log")


def git(*args):
    return subprocess.check_output(["git"] + list(args), text=True)


def main():
    problems = []

    for path in git("ls-files").splitlines():
        if path and FORBIDDEN_TRACKED.search(path):
            problems.append("tracked file must not be committed: " + path)

    for path in MUST_IGNORE:
        if subprocess.run(["git", "check-ignore", "-q", path]).returncode != 0:
            problems.append("not covered by .gitignore: " + path)

    for line in git("status", "--porcelain").splitlines():
        if ".dashboard_key" in line:
            problems.append(".dashboard_key visible in git status")

    for p in problems:
        print("FAIL " + p)
    print("repo hygiene: %s" % ("FAIL" if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
