"""Cross-check provider.cpp field schema against credential.cpp handlers.

Verifies:
  - GetFieldDescriptorCount value parses
  - GetFieldDescriptorAt bounds guard matches count - 1
  - GetFieldState handles exactly fields 0..count-1
  - GetSubmitButtonValue targets an existing field
  - GetBitmapValue is implemented (not stubbed)

Run from the repo root:  python tools\\check_cp_fields.py
"""
import re
import sys


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def func_body(src, header_re):
    m = re.search(header_re + r"[^{]*\{(.*?)\n\}", src, re.S)
    return m.group(1) if m else None


def main():
    prov = read("cp/provider.cpp")
    cred = read("cp/credential.cpp")
    problems = []

    m = re.search(r"GetFieldDescriptorCount\(DWORD \*n\)\s*\{\s*\*n = (\d+);", prov)
    count = int(m.group(1)) if m else None
    if count is None:
        problems.append("provider.cpp: cannot parse GetFieldDescriptorCount")

    m = re.search(r"if \(i > (\d+)\) return E_INVALIDARG;", prov)
    if m and count is not None:
        if int(m.group(1)) != count - 1:
            problems.append(
                "provider.cpp: bounds guard i > %s does not match field count %d"
                % (m.group(1), count)
            )
    else:
        problems.append("provider.cpp: cannot parse GetFieldDescriptorAt guard")

    state = func_body(cred, r"HRESULT NeoFaceCredential::GetFieldState")
    if state is None:
        problems.append("credential.cpp: cannot parse GetFieldState")
    elif count is not None:
        ids = set(int(x) for x in re.findall(r"if \(id == (\d+)\)", state))
        expected = set(range(count))
        if ids != expected:
            problems.append(
                "credential.cpp: GetFieldState handles %s, provider declares %d fields (expected %s)"
                % (sorted(ids), count, sorted(expected))
            )

    submit = func_body(cred, r"HRESULT NeoFaceCredential::GetSubmitButtonValue")
    if submit is None:
        problems.append("credential.cpp: cannot parse GetSubmitButtonValue")
    else:
        m = re.search(r"id != (\d+)", submit)
        if not m:
            problems.append("credential.cpp: cannot parse submit button target id")
        elif count is not None and int(m.group(1)) >= count:
            problems.append(
                "credential.cpp: submit button id %s out of range for %d fields"
                % (m.group(1), count)
            )

    if func_body(cred, r"HRESULT NeoFaceCredential::GetBitmapValue") is None:
        problems.append("credential.cpp: GetBitmapValue implementation missing")

    for p in problems:
        print("FAIL " + p)
    print("cp field check: %s" % ("FAIL" if problems else "OK"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
