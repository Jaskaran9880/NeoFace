import os
import sys
import cv2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap

from face_unlock.camera import Camera
from face_unlock.engine import FaceEngine
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


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeoFace - Predator Neo 16")
        self.setMinimumSize(720, 560)
        root = QWidget()
        lay = QVBoxLayout(root)
        self.view = QLabel("starting camera...")
        self.view.setMinimumSize(640, 360)
        self.view.setStyleSheet("background: #111; color: #888; font-size: 14px;")
        lay.addWidget(self.view)
        self.status = QLabel("Gallery + camera warming...")
        self.status.setStyleSheet("font-size: 14px; padding: 10px;")
        lay.addWidget(self.status)
        self.test_btn = QPushButton("Test unlock - capture 5 frames")
        self.test_btn.clicked.connect(self.test)
        lay.addWidget(self.test_btn)
        self.setCentralWidget(root)

        self.engine = FaceEngine("models")
        self.engine.load()
        self.gallery = Gallery(r"C:\ProgramData\NeoFace\faces.dat")
        self.gallery.load()
        users = list(self.gallery.templates.keys())
        self.user = users[0] if users else os.getlogin()
        n = sum(len(v) for v in self.gallery.templates.values())
        self.status.setText(f"Ready - {n} templates ({self.user}). Hold straight, press Test.")

        self.thread = CamThread()
        self.thread.frame.connect(self.on_frame)
        self.thread.start()
        self.last = None

    @Slot(object)
    def on_frame(self, f):
        self.last = f
        h, w = f.shape[:2]
        sw = 640
        sh = int(h * sw / w)
        small = cv2.resize(f, (sw, sh))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        q = QImage(rgb.data, sw, sh, sw * 3, QImage.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(q))

    def test(self):
        if self.last is None:
            self.status.setText("No camera frame yet")
            return
        import numpy as np
        scores = []
        frames = [self.last]
        for _ in range(4):
            _, f = self.thread.cam.read()
            if f is not None:
                frames.append(f)
        for f in frames:
            h, w = f.shape[:2]
            if w > 640:
                f = cv2.resize(f, (640, int(h * 640 / w)))
            emb, face = self.engine.embed(f)
            if emb is None:
                continue
            scores.append(self.gallery.best(self.user, emb))
        if not scores:
            self.status.setText("No face found - look straight, closer, more light")
            return
        passed = vote(scores, 0.42, 2)
        best = max(scores)
        mark = "UNLOCK" if passed else "NO MATCH"
        self.status.setText(f"{mark} - best {best:.2f} over {len(scores)} frames {['%.2f' % s for s in scores]}")

    def closeEvent(self, e):
        self.thread.stop()
        super().closeEvent(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())
