import os
import struct
import numpy as np

try:
    import win32crypt
    _HAS_DPAPI = True
except ImportError:
    _HAS_DPAPI = False

MAGIC = b"NF02"


class Gallery:
    def __init__(self, path):
        self.path = os.path.expandvars(path)
        self.templates = {}

    def add(self, user, embedding):
        self.templates.setdefault(user, []).append(np.array(embedding, dtype=np.float32))

    def best(self, user, embedding):
        from .matcher import cosine_score
        cands = [c for c in self.templates.get(user, []) if len(c) == len(embedding)]
        if not cands:
            return 0.0
        return max(cosine_score(embedding, c) for c in cands)

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        blob = MAGIC + struct.pack("<I", len(self.templates))
        for user, embs in self.templates.items():
            ub = user.encode("utf-8")
            blob += struct.pack("<I", len(ub)) + ub
            blob += struct.pack("<I", len(embs))
            for e in embs:
                e = np.array(e, dtype=np.float32)
                blob += struct.pack("<I", len(e)) + e.tobytes()
        if _HAS_DPAPI:
            blob = win32crypt.CryptProtectData(blob, None, None, None, None, 0x04)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.path)

    def load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "rb") as f:
            blob = f.read()
        if _HAS_DPAPI:
            try:
                _, blob = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
            except Exception as e:
                raise ValueError(f"Failed to decrypt gallery: {e}")
        try:
            self._parse(blob)
        except (struct.error, IndexError, ValueError) as e:
            raise ValueError(f"Corrupted gallery file ({self.path}): {e}")

    def _parse(self, blob):
        if blob[:4] == b"NF01":
            off = 4
            nusers = struct.unpack_from("<I", blob, off)[0]
            off += 4
            self.templates = {}
            for _ in range(nusers):
                ulen = struct.unpack_from("<I", blob, off)[0]
                off += 4
                user = blob[off:off+ulen].decode("utf-8")
                off += ulen
                nemb = struct.unpack_from("<I", blob, off)[0]
                off += 4
                embs = []
                for _ in range(nemb):
                    e = np.frombuffer(blob[off:off+2048], dtype=np.float32).copy()
                    off += 2048
                    embs.append(e)
                self.templates[user] = embs
            return
        if blob[:4] != MAGIC:
            raise ValueError(f"Invalid gallery format: expected {MAGIC!r}, got {blob[:4]!r}")
        off = 4
        nusers = struct.unpack_from("<I", blob, off)[0]
        off += 4
        self.templates = {}
        for _ in range(nusers):
            ulen = struct.unpack_from("<I", blob, off)[0]
            off += 4
            user = blob[off:off+ulen].decode("utf-8")
            off += ulen
            nemb = struct.unpack_from("<I", blob, off)[0]
            off += 4
            embs = []
            for _ in range(nemb):
                dim = struct.unpack_from("<I", blob, off)[0]
                off += 4
                e = np.frombuffer(blob[off:off+dim*4], dtype=np.float32).copy()
                off += dim * 4
                embs.append(e)
            self.templates[user] = embs
