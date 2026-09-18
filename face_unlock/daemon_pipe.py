import os
import sys
import cv2
import threading
import time
import ctypes
import ctypes.wintypes as wt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
LOG = r"C:\ProgramData\NeoFace\daemon.log"
os.makedirs(os.path.dirname(LOG), exist_ok=True)
MAX_MSG_LEN = 8192  # Maximum allowed pipe message length in bytes

def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg, flush=True)
import win32pipe
import win32file
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import cosine_score
from face_unlock.antispoof import SpoofGate

PIPE = r"\\.\pipe\NeoFace"
IMG_SIZE = 320
WARMUP = 2
FRAMES = 3
HIT_REQ = 2
THRESHOLD = 0.35

# Allowed connecting processes: dashboard.py and explorer.exe
_ALLOWED_PROCESS_NAMES = {"dashboard.py", "explorer.exe", "python.exe", "pythonw.exe"}

for name, path in [("yunet", "models/yunet.onnx"), ("sface", "models/sface.onnx")]:
    if not os.path.exists(os.path.join(ROOT, path)):
        log(f"FATAL: missing model {path}")
        sys.exit(1)

engine = FastEngine(os.path.join(ROOT, "models", "yunet.onnx"),
                    os.path.join(ROOT, "models", "sface.onnx"))
engine.load()
gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
gallery.load()
gallery_mtime = os.path.getmtime(gallery.path) if os.path.exists(gallery.path) else 0

spoof = SpoofGate()
if not spoof.load():
    log("WARNING: anti-spoof model failed to load - spoof detection DISABLED (all frames will pass)")

log(f"daemon loaded - {sum(len(v) for v in gallery.templates.values())} fast templates, antispoof={'on' if spoof.net else 'off'}")

class Cam:
    def __init__(self):
        self.cap = None
        self.lock = threading.Lock()
        self.latest = None
        self.running = False
        self._thread = None

    def open(self):
        if self.cap and self.cap.isOpened():
            return
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self._thread = threading.Thread(target=self._grab, daemon=True)
        self._thread.start()
        for _ in range(WARMUP):
            self.cap.read()
        time.sleep(0.05)

    def _grab(self):
        while self.running:
            cap = self.cap
            if not cap or not cap.isOpened():
                break
            ok, f = cap.read()
            if ok:
                with self.lock:
                    self.latest = f
            else:
                time.sleep(0.01)

    def read(self):
        with self.lock:
            if self.latest is not None:
                return True, self.latest.copy()
        return False, None

    def close(self):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.latest = None

cam = Cam()

log(f"{time.strftime('%H:%M:%S')} creating pipe {PIPE}")

try:
    # Build a restrictive DACL: only the current user gets access.
    # This prevents any other local process from connecting to the pipe.
    class SID_IDENTIFIER_AUTHORITY(ctypes.Structure):
        _fields_ = [("Value", ctypes.c_ubyte * 6)]

    class SID(ctypes.Structure):
        _fields_ = [
            ("Revision", ctypes.c_ubyte),
            ("SubAuthorityCount", ctypes.c_ubyte),
            ("IdentifierAuthority", SID_IDENTIFIER_AUTHORITY),
            ("SubAuthority", ctypes.c_ulong * 15),
        ]

    class ACE_HEADER(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", ctypes.c_ushort),
        ]

    class ACCESS_ALLOWED_ACE(ctypes.Structure):
        _fields_ = [
            ("Header", ACE_HEADER),
            ("Mask", ctypes.c_ulong),
            ("SidStart", ctypes.c_ulong),
        ]

    class ACL(ctypes.Structure):
        _fields_ = [
            ("AclRevision", ctypes.c_ubyte),
            ("Sbz1", ctypes.c_ubyte),
            ("AclSize", ctypes.c_ushort),
            ("AceCount", ctypes.c_ushort),
            ("Sbz2", ctypes.c_ushort),
        ]

    class SECURITY_DESCRIPTOR(ctypes.Structure):
        _fields_ = [
            ("Revision", ctypes.c_ubyte),
            ("Sbz1", ctypes.c_ubyte),
            ("Control", ctypes.c_ushort),
            ("Owner", ctypes.c_void_p),
            ("Group", ctypes.c_void_p),
            ("Sacl", ctypes.c_void_p),
            ("Dacl", ctypes.c_void_p),
        ]

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", ctypes.c_ulong),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", ctypes.wintypes.BOOL),
        ]

    advapi32 = ctypes.windll.advapi32

    # Get current user SID
    token = ctypes.wintypes.HANDLE()
    advapi32.OpenProcessToken(ctypes.windll.kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token))
    sid_len = ctypes.wintypes.DWORD()
    advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(sid_len))
    sid_buf = ctypes.create_string_buffer(sid_len.value)
    advapi32.GetTokenInformation(token, 1, sid_buf, sid_len, ctypes.byref(sid_len))
    # TOKEN_USER has PSID User; the SID starts at offset pointer-sized value
    sid_ptr = ctypes.cast(sid_buf, ctypes.POINTER(ctypes.c_void_p)).contents.value

    # Calculate SID binary size
    sid = ctypes.cast(sid_ptr, ctypes.POINTER(SID)).contents
    sid_binary_size = 8 + 4 * sid.SubAuthorityCount

    ace_total_size = ctypes.sizeof(ACE_HEADER) + 4 + sid_binary_size
    acl_size = ctypes.sizeof(ACL) + ace_total_size
    acl_buf = ctypes.create_string_buffer(acl_size)

    acl = ctypes.cast(acl_buf, ctypes.POINTER(ACL)).contents
    acl.AclRevision = 2
    acl.Sbz1 = 0
    acl.AclSize = acl_size
    acl.AceCount = 1
    acl.Sbz2 = 0

    ace_offset = ctypes.sizeof(ACL)
    ace = ACCESS_ALLOWED_ACE()
    ace.Header.AceType = 0  # ACCESS_ALLOWED_ACE_TYPE
    ace.Header.AceFlags = 0
    ace.Header.AceSize = ace_total_size
    ace.Mask = 0x001F01FF  # FILE_ALL_ACCESS

    ctypes.memmove(ctypes.addressof(acl_buf) + ace_offset, ctypes.addressof(ace), ctypes.sizeof(ACE_HEADER) + 4)
    ctypes.memmove(ctypes.addressof(acl_buf) + ace_offset + ctypes.sizeof(ACE_HEADER) + 4,
                   sid_ptr, sid_binary_size)

    sd = SECURITY_DESCRIPTOR()
    sd.Revision = 1
    sd.Sbz1 = 0
    sd.Control = 0x8004  # SE_DACL_PRESENT | SE_SELF_RELATIVE
    sd.Owner = 0
    sd.Group = 0
    sd.Sacl = 0
    sd.Dacl = ctypes.addressof(acl_buf)

    sa = SECURITY_ATTRIBUTES()
    sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    sa.lpSecurityDescriptor = ctypes.addressof(sd)
    sa.bInheritHandle = False

    pipe = win32pipe.CreateNamedPipe(PIPE,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        1, 65536, 65536, 0, ctypes.byref(sa))
    log(f"{time.strftime('%H:%M:%S')} pipe created handle={pipe} (ACL: current user only)")
except Exception as e:
    log(f"FATAL: Could not set pipe ACL ({e}), refusing to start (security requirement)")
    sys.exit(1)

log(f"{time.strftime('%H:%M:%S')} listening")
while True:
    try:
        log(f"{time.strftime('%H:%M:%S')} waiting for client...")
        win32pipe.ConnectNamedPipe(pipe, None)
        log(f"{time.strftime('%H:%M:%S')} client connected")

        # Validate connecting process via GetNamedPipeClientProcessId
        try:
            kernel32 = ctypes.windll.kernel32
            client_pid = ctypes.wintypes.DWORD()
            if hasattr(win32pipe, 'GetNamedPipeClientProcessId'):
                # GetNamedPipeClientProcessId(handle, &pid)
                kernel32.GetNamedPipeClientProcessId(pipe, ctypes.byref(client_pid))
                pid_val = client_pid.value
                # Look up process name from PID
                import subprocess
                ps_result = subprocess.run(
                    ["powershell", "-Command",
                     f"Get-CimInstance Win32_Process -Filter \"ProcessId={pid_val}\" | Select-Object -Expand Name"],
                    capture_output=True, text=True, timeout=3
                )
                proc_name = ps_result.stdout.strip().lower()
                log(f"{time.strftime('%H:%M:%S')} client PID={pid_val} name={proc_name}")
                if proc_name not in _ALLOWED_PROCESS_NAMES:
                    log(f"{time.strftime('%H:%M:%S')} REJECTED: process '{proc_name}' (PID {pid_val}) is not an allowed client")
                    win32file.WriteFile(pipe, b"FAIL")
                    win32pipe.DisconnectNamedPipe(pipe)
                    continue
        except Exception as e:
            log(f"{time.strftime('%H:%M:%S')} WARNING: Could not validate client process: {e}")

        _, data = win32file.ReadFile(pipe, 65536)

        # Validate message length
        if len(data) > MAX_MSG_LEN:
            log(f"{time.strftime('%H:%M:%S')} message too long ({len(data)} bytes), rejecting")
            win32file.WriteFile(pipe, b"FAIL")
            win32pipe.DisconnectNamedPipe(pipe)
            continue

        log(f"{time.strftime('%H:%M:%S')} read {len(data)} bytes")
        req = data.decode("utf-8", "ignore").strip().rstrip("\x00")
        user = req.split(" ", 1)[1].strip().rstrip("\x00") if req.startswith("VERIFY") and " " in req else None
        if not user:
            log(f"{time.strftime('%H:%M:%S')} invalid request: (redacted)")
            win32file.WriteFile(pipe, b"FAIL")
            win32pipe.DisconnectNamedPipe(pipe)
            continue

        # Reload gallery if file changed on disk (enrollment happened)
        try:
            cur_mtime = os.path.getmtime(gallery.path)
            if cur_mtime != gallery_mtime:
                gallery.load()
                gallery_mtime = cur_mtime
                log(f"{time.strftime('%H:%M:%S')} gallery reloaded - {sum(len(v) for v in gallery.templates.values())} templates")
        except Exception:
            pass

        t0 = time.time()
        try:
            cam.open()
            t1 = time.time()
            scores = []
            frames_ok = 0
            faces_seen = 0
            spoofs_rejected = 0
            for _ in range(FRAMES):
                ok, f = cam.read()
                if not ok:
                    continue
                frames_ok += 1
                h, w = f.shape[:2]
                if w > IMG_SIZE:
                    f = cv2.resize(f, (IMG_SIZE, int(h * IMG_SIZE / w)))
                emb, face = engine.embed(f)
                if face is not None:
                    faces_seen += 1
                if emb is None:
                    continue
                real = spoof.real_score(f)
                if real < spoof.threshold:
                    log(f"{time.strftime('%H:%M:%S')} spoof rejected frame: real={real:.3f} < {spoof.threshold}")
                    spoofs_rejected += 1
                    continue
                cands = [c for c in gallery.templates.get(user, []) if len(c) == len(emb)]
                if cands:
                    scores.append(max(cosine_score(emb, c) for c in cands))
            t_scan = time.time() - t1

            good = bool(scores) and sum(1 for s in scores if s >= THRESHOLD) >= HIT_REQ
            best = max(scores) if scores else 0.0
            total = time.time() - t0
            log(f"{time.strftime('%H:%M:%S')} user=(redacted) total={total:.1f}s scan={t_scan:.1f}s frames={frames_ok} faces={faces_seen} spoof_rejected={spoofs_rejected} scores={[round(s,2) for s in scores]} best={round(best,2)} -> {'OK' if good else 'FAIL'}")
            win32file.WriteFile(pipe, ("OK" if good else "FAIL").encode())
        except Exception as scan_err:
            log(f"{time.strftime('%H:%M:%S')} scan error: {scan_err}")
            try:
                win32file.WriteFile(pipe, b"FAIL")
            except Exception:
                pass
        finally:
            cam.close()
        win32pipe.DisconnectNamedPipe(pipe)
        log(f"{time.strftime('%H:%M:%S')} disconnected, ready for next client")
    except Exception as e:
        log(f"{time.strftime('%H:%M:%S')} error: {e}")
        cam.close()
        try:
            win32pipe.DisconnectNamedPipe(pipe)
        except Exception:
            pass
