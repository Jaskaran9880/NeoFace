import os
import sys
import time
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QThread, Signal, Slot, Qt
from PySide6.QtGui import QImage, QPixmap, QShortcut, QKeySequence

from face_unlock.camera import Camera
from face_unlock.fast import FastEngine
from face_unlock.store import Gallery
from face_unlock.matcher import vote


class CamThread(QThread):
    frame = Signal(object)

    def __init__(self):
        super().__init__()
        self.running = True
        self.cam = Camera(0, 640, 480)

    def run(self):
        self.cam.open()
        for _ in range(5):
            self.cam.read()
        while self.running:
            ok, f = self.cam.read()
            if ok:
                self.frame.emit(f)
            self.msleep(33)

    def stop(self):
        self.running = False
        self.wait(1000)
        self.cam.close()


class LockScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeoFace Locked - press F and look here")
        self.setWindowState(Qt.WindowFullScreen)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setStyleSheet("background: #05070d; color: white;")
        lay = QVBoxLayout(self)
        self.ring = QLabel("◯  Press F and look here")
        self.ring.setAlignment(Qt.AlignCenter)
        self.ring.setStyleSheet("font-size: 34px; padding: 30px; color: #7dd3fc;")
        lay.addWidget(self.ring)
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setMinimumSize(480, 270)
        lay.addWidget(self.view)
        self.status = QLabel("Locked - camera warming...")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("font-size: 16px; color: #cbd5e1;")
        lay.addWidget(self.status)
        self.unlock_btn = QPushButton("Unlock with PIN instead (fallback)")
        self.unlock_btn.setStyleSheet("padding: 12px; font-size: 14px;")
        self.unlock_btn.clicked.connect(self.pin_fallback)
        lay.addWidget(self.unlock_btn)

        QShortcut(QKeySequence("F"), self).activated.connect(self.scan)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self.pin_fallback)

        self.engine = FastEngine()
        self.engine.load()
        self.gallery = Gallery(r"C:\ProgramData\NeoFace\faces_fast.dat")
        self.gallery.load()
        self.user = os.getlogin()
        self.tries = 0
        self.last = None

        self.thread = CamThread()
        self.thread.frame.connect(self.on_frame)
        self.thread.start()
        self.status.setText(f"Locked - press F, {sum(len(v) for v in self.gallery.templates.values())} templates ready")

    @Slot(object)
    def on_frame(self, f):
        self.last = f
        if f.mean() < 5:
            self.view.setText("CAMERA BLOCKED - open shutter / allow privacy / close Teams-Chrome-Camera app")
            self.view.setStyleSheet("color:#f87171; font-size:15px;")
            return
        h, w = f.shape[:2]
        sw = 480
        sh = int(h * sw / w)
        small = cv2.resize(f, (sw, sh))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        q = QImage(rgb.data, sw, sh, sw * 3, QImage.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(q))

    def scan(self):
        if self.last is None:
            self.ring.setText("◯  Camera not ready - wait 2s")
            return
        if self.last.mean() < 5:
            self.ring.setText("◯  Camera blocked - check shutter + privacy")
            self.status.setText("1) Open Camera app - if black there, it's hardware. 2) Settings>Privacy>Camera ON. 3) Slide bezel shutter open. 4) Close Teams/Discord/Chrome.")
            return
        self.ring.setText("◉  Scanning - hold still...")
        self.ring.setStyleSheet("font-size: 34px; padding: 30px; color: #22d3ee;")
        QApplication.processEvents()
        scores = []
        for _ in range(5):
            _, f = self.thread.cam.read()
            if f is None:
                continue
            h, w = f.shape[:2]
            if w > 640:
                f = cv2.resize(f, (640, int(h * 640 / w)))
            emb, face = self.engine.embed(f)
            if emb is None:
                continue
            scores.append(self.gallery.best(self.user, emb))
            time.sleep(0.1)
        if not scores:
            self.ring.setText("◯  No face - look straight")
            return
        if vote(scores, 0.35, 2):
            self.ring.setText("✓  Welcome")
            self.ring.setStyleSheet("font-size: 38px; padding: 30px; color: #4ade80;")
            self.status.setText(f"UNLOCK best {max(scores):.2f}")
            QApplication.processEvents()
            time.sleep(0.8)
            self.close()
        else:
            self.tries += 1
            left = 3 - self.tries
            self.ring.setText("✕  No match - try again" if left > 0 else "Use PIN below")
            self.ring.setStyleSheet("font-size: 34px; padding: 30px; color: #f87171;")
            self.status.setText(f"best {max(scores):.2f}, {left} tries left")
            if left <= 0:
                self.pin_fallback()

    def pin_fallback(self):
        self.thread.stop()
        self.close()

    def closeEvent(self, e):
        try:
            self.thread.stop()
        except Exception:
            pass
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = LockScreen()
    w.showFullScreen()
    sys.exit(app.exec())
