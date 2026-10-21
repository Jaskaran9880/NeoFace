"""NeoFace setup wizard: password vault, face enrollment, test scan.

Runs after the installer (or any time from the Start Menu). Safe to re-run:
an existing vault/gallery is kept unless you choose to redo it.

Steps:
  1. Password vault   - stores your Windows password (DPAPI machine-scope)
  2. Face enrollment  - live camera (recommended) or photos folder
  3. Test scan        - one live scan against the new gallery
"""

import getpass
import os
import socket
import subprocess
import sys
import time

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_ROOT)
os.chdir(APP_ROOT)

DATA_DIR = r"C:\ProgramData\NeoFace"
CRED_PATH = os.path.join(DATA_DIR, "cred.bin")
GALLERY_PATH = os.path.join(DATA_DIR, "faces_fast.dat")
PHOTOS_DIR = os.path.join(APP_ROOT, "photos")

MIN_FACE_PX = 80
TARGET_EMBEDS = 10
MIN_EMBEDS = 5
CAPTURE_TIMEOUT_S = 60.0
EMBED_INTERVAL_S = 0.25


def banner():
    print("=" * 58)
    print("  NeoFace Unlock - Setup Wizard")
    print("=" * 58)
    print()
    print("This wizard sets up face unlock for THIS Windows account.")
    print("Your face data and password stay on this PC only.")
    print()


def load_camera_cfg():
    idx, w, h = 0, 640, 480
    try:
        import tomllib
        with open(os.path.join(APP_ROOT, "config.toml"), "rb") as f:
            cam = tomllib.load(f).get("camera", {})
        idx = int(cam.get("index", idx))
        w = int(cam.get("width", w))
        h = int(cam.get("height", h))
    except Exception:
        pass
    return idx, w, h


def current_user():
    try:
        return os.getlogin()
    except OSError:
        return os.environ.get("USERNAME", "default")


# ---------------------------------------------------------------- vault

def step_vault():
    print("-" * 58)
    print("[1/3] Password vault")
    print("-" * 58)
    if os.path.exists(CRED_PATH):
        print("  Vault already exists (%s)." % CRED_PATH)
        ans = input("  Set it again? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Kept.\n")
            return True
    print()
    print("  Enter your WINDOWS password (not the PIN).")
    print("  It is encrypted with Windows DPAPI and stored locally;")
    print("  the lock screen tile uses it to sign you in after a face match.")
    print()
    pw = getpass.getpass("  Password: ")
    pw2 = getpass.getpass("  Repeat:   ")
    if not pw or pw != pw2:
        print("  Mismatch or empty - vault not changed.\n")
        return os.path.exists(CRED_PATH)
    try:
        import win32crypt
        domain = os.environ.get("USERDOMAIN", socket.gethostname())
        user = current_user()
        raw = "%s\n%s\n%s" % (domain, user, pw)
        blob = win32crypt.CryptProtectData(
            raw.encode("utf-8"), None, None, None, None, 0x04)
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CRED_PATH, "wb") as f:
            f.write(blob)
        print("  Vault saved.\n")
        return True
    except Exception as e:
        print("  Vault FAILED: %s\n" % e)
        return False


# ------------------------------------------------------------- enroll

def _capture_embeddings(engine, cap, want, on_progress=None):
    """Grab `want` face embeddings from the camera with quality gates."""
    import numpy as np
    embs = []
    started = time.time()
    last_at = 0.0
    while len(embs) < want:
        if time.time() - started > CAPTURE_TIMEOUT_S:
            break
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.05)
            continue
        h, w = frame.shape[:2]
        engine.det.setInputSize((w, h))
        _, faces = engine.det.detect(frame)
        now = time.time()
        if faces is not None and len(faces) and (now - last_at) >= EMBED_INTERVAL_S:
            f = max(faces, key=lambda x: x[2] * x[3])
            if f[2] >= MIN_FACE_PX and f[3] >= MIN_FACE_PX:
                aligned = engine.rec.alignCrop(frame, f)
                feat = engine.rec.feature(aligned)
                if feat is not None:
                    emb = np.array(feat, dtype=np.float32).flatten()
                    if embs:
                        from face_unlock.matcher import cosine_score
                        if max(cosine_score(emb, e) for e in embs) > 0.98:
                            pass  # near-duplicate of an already captured frame
                        else:
                            embs.append(emb)
                            last_at = now
                    else:
                        embs.append(emb)
                        last_at = now
        if on_progress:
            on_progress(len(embs), want)
    return embs


def step_enroll(user):
    print("-" * 58)
    print("[2/3] Face enrollment")
    print("-" * 58)
    if os.path.exists(GALLERY_PATH):
        print("  A face gallery already exists.")
        ans = input("  Enroll AGAIN (adds more templates)? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Kept.\n")
            return True

    has_photos = False
    if os.path.isdir(PHOTOS_DIR):
        exts = (".jpg", ".jpeg", ".png", ".bmp", ".heic", ".heif", ".webp")
        has_photos = any(n.lower().endswith(exts) for n in os.listdir(PHOTOS_DIR))

    mode = "1"
    if has_photos:
        print("  Photos found in %s" % PHOTOS_DIR)
        print("  [1] Live camera (recommended - better angles, 1 minute)")
        print("  [2] Enroll from photos folder")
        mode = input("  Choice [1]: ").strip() or "1"

    if mode == "2":
        print("  Running photo enrollment...")
        rc = subprocess.call([sys.executable,
                              os.path.join(APP_ROOT, "tools", "enroll_fast.py")])
        print()
        return rc == 0 and os.path.exists(GALLERY_PATH)

    print()
    print("  Camera enrollment: sit facing the camera, good lighting.")
    print("  Slowly turn your head a little between captures.")
    print("  Press Ctrl+C to cancel.\n")
    from face_unlock.fast import FastEngine
    from face_unlock.store import Gallery
    engine = FastEngine()
    if not engine.load():
        print("  Could not load face models.\n")
        return False
    idx, w, h = load_camera_cfg()
    cap = None
    for ci in (idx, 0, 1):
        import cv2
        cap = cv2.VideoCapture(ci)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            break
        cap.release()
        cap = None
    if cap is None or not cap.isOpened():
        print("  No camera available. Plug in / allow camera access,\n"
              "  then re-run this wizard from the Start Menu.\n")
        return False
    try:
        shown = [0]

        def progress(got, want):
            if got != shown[0]:
                shown[0] = got
                print("  captured %d/%d ..." % (got, want), flush=True)

        try:
            embs = _capture_embeddings(engine, cap, TARGET_EMBEDS, progress)
        except KeyboardInterrupt:
            print("\n  Cancelled.")
            cap.release()
            return os.path.exists(GALLERY_PATH)
    finally:
        cap.release()
    if len(embs) < MIN_EMBEDS:
        print("  Only %d usable captures (need %d). Retry with better"
              " lighting / closer to the camera." % (len(embs), MIN_EMBEDS))
        print()
        return False
    gallery = Gallery(GALLERY_PATH)
    gallery.load()
    for emb in embs:
        gallery.add(user, emb)
    gallery.save()
    print("  Saved %d face templates for %s." % (len(embs), user))
    print()
    return True


# -------------------------------------------------------------- test

def step_test(user):
    print("-" * 58)
    print("[3/3] Test scan")
    print("-" * 58)
    if not os.path.exists(GALLERY_PATH):
        print("  No gallery to test against.\n")
        return False
    from face_unlock.fast import FastEngine
    from face_unlock.store import Gallery
    from face_unlock.matcher import cosine_score
    engine = FastEngine()
    if not engine.load():
        print("  Could not load face models.\n")
        return False
    gallery = Gallery(GALLERY_PATH)
    try:
        gallery.load()
    except Exception as e:
        print("  Gallery unreadable: %s\n" % e)
        return False
    idx, w, h = load_camera_cfg()
    import cv2
    cap = None
    for ci in (idx, 0, 1):
        cap = cv2.VideoCapture(ci)
        if cap.isOpened():
            break
        cap.release()
        cap = None
    if cap is None or not cap.isOpened():
        print("  No camera - skipping test. Run again later from Start Menu.\n")
        return True
    print("  Looking for your face (10s)...")
    best = 0.0
    deadline = time.time() + 10.0
    try:
        while time.time() < deadline:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            emb, _ = engine.embed(frame)
            if emb is not None:
                best = gallery.best(user, emb)
                if best >= 0.45:
                    break
    finally:
        cap.release()
    print("  best match score: %.2f (need 0.45)" % best)
    print()
    if best >= 0.45:
        print("  TEST PASSED - face unlock is ready.")
        return True
    print("  TEST WEAK/FAILED - enroll again (better lighting, closer),")
    print("  or lower cosine_threshold in the dashboard settings.")
    print()
    return False


# -------------------------------------------------------------- main

def main():
    banner()
    user = current_user()
    print("Account: %s\\%s\n" % (os.environ.get("USERDOMAIN", socket.gethostname()), user))
    try:
        vault_ok = step_vault()
        enroll_ok = step_enroll(user) if vault_ok else False
        test_ok = step_test(user) if enroll_ok else False
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1
    print("=" * 58)
    if vault_ok and enroll_ok and test_ok:
        print("  Setup complete.")
        print()
        print("  How to unlock with your face:")
        print("    1. Sign in with PIN once (starts the face service)")
        print("    2. Press Win+L to lock the screen")
        print("    3. Click the NeoFace tile and look at the camera")
        print()
        print("  Re-run anytime: Start Menu > NeoFace > Setup Wizard")
        print("  Dashboard:      Start Menu > NeoFace > Dashboard")
        return 0
    if vault_ok and enroll_ok:
        print("  Setup mostly complete (test skipped/weak).")
        print("  Press Win+L and try the NeoFace tile; re-run the wizard")
        print("  from the Start Menu anytime to re-enroll or re-test.")
        return 0
    print("  Setup incomplete - re-run the wizard from the Start Menu.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
