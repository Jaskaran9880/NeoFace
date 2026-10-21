# Contributing to NeoFace

## Development setup

```powershell
git clone https://github.com/Jaskaran9880/NeoFace.git
cd NeoFace
pip install -r requirements.txt
python tools\fetch_fast.py
```

## Project structure

```
face_unlock/       - Core Python modules (engine, camera, gallery, daemon)
cp/                - C++ Credential Provider DLL (lock screen tile)
tools/             - Enrollment, testing, deployment scripts
tools/dev/         - Diagnostics and sanity-check scripts
installer/         - Install/uninstall scripts and setup wizard
tests/             - Test scripts (dashboard API, camera)
dashboard.py       - Flask dashboard (status, photos, troubleshoot)
templates/         - Dashboard HTML (Tailwind dark UI)
static/            - Dashboard static assets (logo.png)
docs/              - Architecture and security documentation (docs/dev/ = analysis notes)
photos/            - Face photos for enrollment (gitignored)
models/            - AI models (gitignored, downloaded by fetch_fast.py)
```

## Code style

- Python: PEP 8, no type hints (codebase uses dynamic typing)
- C++: MSVC conventions, `/std:c++17`, `/EHsc`
- Commit messages: conventional commits format
- No emojis in code or commit messages

## Testing

```powershell
python tools\test_unlock.py          # Test face scan
python tools\probe_system.py         # Test pipe connection
python tools\dev\check_python_syntax.py  # AST-parse all tracked .py
powershell -File tools\dev\check_ps1_syntax.ps1  # Parse all tracked .ps1
python tools\dev\check_cp_fields.py      # CP field schema consistency
python tools\dev\check_repo_hygiene.py   # Secrets/artifacts must stay untracked
```

## Building the DLL

```powershell
cd cp
.\build_cp.ps1                      # Requires VS2022 Build Tools
```

## License

MIT
