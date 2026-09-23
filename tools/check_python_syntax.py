"""Parse every tracked Python file with ast; exit 1 on any syntax error.

Run from the repo root:  python tools\\check_python_syntax.py
"""
import ast
import subprocess
import sys


def main():
    files = subprocess.check_output(["git", "ls-files", "*.py"], text=True).split()
    if not files:
        print("no Python files tracked")
        return 1
    bad = []
    for path in files:
        try:
            with open(path, encoding="utf-8-sig") as f:
                ast.parse(f.read(), filename=path)
        except SyntaxError as e:
            bad.append("%s:%s: %s" % (path, e.lineno, e.msg))
        except OSError as e:
            bad.append("%s: %s" % (path, e))
    for line in bad:
        print("FAIL " + line)
    print("checked %d Python files, %d bad" % (len(files), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
