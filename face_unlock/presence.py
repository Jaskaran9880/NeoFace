import time
import ctypes


def idle_seconds():
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0


class Presence:
    def __init__(self, interval_s=45, strikes=2):
        self.interval_s = interval_s
        self.strikes = strikes
        self.misses = 0

    def tick(self, faces_found):
        if faces_found:
            self.misses = 0
            return False
        self.misses += 1
        if self.misses >= self.strikes and idle_seconds() > 60:
            self.misses = 0
            ctypes.windll.user32.LockWorkStation()
            return True
        return False
