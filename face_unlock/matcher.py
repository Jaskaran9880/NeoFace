import numpy as np


def cosine_score(a: np.ndarray, b: np.ndarray) -> float:
    a = a / (np.linalg.norm(a) + 1e-9)
    b = b / (np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b))


def vote(scores, threshold=0.42, required=3):
    hits = sum(1 for s in scores if s >= threshold)
    return hits >= required
