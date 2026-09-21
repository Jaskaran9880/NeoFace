"""Temporal liveness detection — catches photo / video-replay attacks.

A real person in front of a camera produces moderate, natural frame-to-frame
motion.  A printed photo or a still image held up to the camera produces
near-zero motion.  A video replay can produce *too consistent* motion.

The checker maintains a rolling buffer of grayscale frames and computes
the mean absolute pixel difference between consecutive pairs.
"""

import logging

import cv2
import numpy as np

logger = logging.getLogger("neoface.liveness")


class LivenessChecker:
    """Lightweight liveness checks that run alongside the anti-spoof model."""

    def __init__(self):
        self.prev_gray = None
        self.frame_buffer: list = []
        self.max_buffer = 10

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_temporal_consistency(self, frame_gray):
        """Detect if the scene is static (photo held up) vs. dynamic (real person).

        Parameters
        ----------
        frame_gray : numpy.ndarray
            Single-channel (grayscale) frame from the camera.

        Returns
        -------
        float
            Score in [0.0, 1.0]:
            * 1.0 — likely a real person (natural motion detected)
            * 0.0 — likely a photo / screen replay (no motion)
        """
        # Add frame to buffer
        self.frame_buffer.append(frame_gray)
        if len(self.frame_buffer) > self.max_buffer:
            self.frame_buffer.pop(0)

        # Need at least 3 frames to detect motion
        if len(self.frame_buffer) < 3:
            return 1.0  # Not enough data, allow

        # Compute frame differences using absolute difference
        diffs = []
        for i in range(1, len(self.frame_buffer)):
            diff = cv2.absdiff(self.frame_buffer[i - 1], self.frame_buffer[i])
            mean_diff = np.mean(diff)
            diffs.append(mean_diff)

        avg_motion = np.mean(diffs)

        # A real person has moderate motion (0.5-5.0 pixels avg difference)
        # A photo has near-zero motion (< 0.3)
        # A video playing has very consistent motion (> 8.0)
        if avg_motion < 0.3:
            return 0.1  # Very low motion — likely a photo
        elif avg_motion < 0.5:
            return 0.5  # Low motion — suspicious
        elif avg_motion > 8.0:
            return 0.3  # Too much motion — suspicious (video playing?)
        else:
            return 1.0  # Natural motion — likely real person

    def reset(self):
        """Reset state for new verification session."""
        self.prev_gray = None
        self.frame_buffer = []
