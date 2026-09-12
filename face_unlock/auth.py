from dataclasses import dataclass


@dataclass
class Guide:
    state: str
    text: str


def guide_for(yaw=0, pitch=0, brightness=120, faces=1, dist=0.5):
    if faces == 0:
        return Guide("waiting", "Press F and look here")
    if faces > 1:
        return Guide("reject", "Only you - ask others to move")
    if brightness < 60:
        return Guide("dark", "Too dark - turn on a light")
    if abs(yaw) > 25:
        return Guide("yaw", "Look straight into the camera")
    if abs(pitch) > 20:
        return Guide("pitch", "Keep head level")
    if dist < 0.3 or dist > 1.0:
        return Guide("dist", "Move a bit - arm's length is best")
    return Guide("ready", "Hold still - scanning")
