"""Camera settle/warmup helpers.

Import-safe: no camera, no I/O, no side effects at import (the module only
imports :mod:`time`; frames are duck-typed via ``.mean()``, so ``cv2`` / numpy
are deliberately NOT imported here).

Why this exists
---------------
Frames captured in the first ~1-3 minutes after wake from sleep/hibernate are
unsettled (auto-exposure / auto-white-balance still converging, often
black-ish).  The anti-spoof model then scores them ``real_score < 0.3`` and
every frame is rejected.  :func:`settle` drains the stream until brightness is
stable (or the budget runs out) *before* the grab thread starts, so the scan
never samples the coldest instant of the stream.

Module constants (frozen contract)
----------------------------------
``STABLE_DELTA = 3.0``   mean-brightness change (0-255) considered stable
``STABLE_FRAMES = 3``    consecutive stable frame-to-frame transitions required
``MIN_SETTLE_S = 1.0``   never settle faster than this
``MAX_SETTLE_S = 2.5``   give up (``stable=False``) after this
``BLACK_MEAN = 5.0``     frames darker than this are "black" and never stable

Frame / streak / black semantics (tests and production code must agree on this)
-------------------------------------------------------------------------------
* ``frame_mean(frame)`` -> ``float(frame.mean())``; **any** exception -> ``0.0``.
* ``is_stable(prev_mean, mean, delta=STABLE_DELTA)`` -> ``False`` when either
  argument is ``None``, or when either argument is ``< BLACK_MEAN`` (a black
  frame is never stable); otherwise ``abs(prev_mean - mean) <= delta``.
* The streak counts consecutive **stable transitions**, not stable frames.
  After every frame that was actually read the rule is::

      streak = streak + 1 if is_stable(prev_mean, mean) else 0

  ``prev_mean`` starts as ``None``, so the very first read frame can never be
  stable and ``STABLE_FRAMES = 3`` therefore needs at least 4 read frames.
* Black tracking: a read frame with ``mean < BLACK_MEAN`` still increments
  ``frames`` AND ``black``, still becomes ``last_mean`` / ``prev_mean``, but
  it always fails ``is_stable`` -- it resets the streak to 0, and because the
  next transition has a black partner that next frame cannot extend a streak
  either (streak stays 0 until two consecutive non-black frames whose means
  differ by at most ``STABLE_DELTA``).
* Failed reads (``read_fn()`` raising an exception, or returning a falsy
  frame) are NOT frames: ``frames``/``black`` do not change, ``last_mean`` /
  ``prev_mean`` keep their previous values, and the streak is untouched -- the
  loop simply keeps trying until ``max_s``.  Truthiness is evaluated safely:
  real camera frames are multi-element numpy arrays whose truth value is
  ambiguous (``bool(ndarray)`` raises), so a frame that cannot be truth-tested
  is treated as a REAL frame, never as a failed read.

``settle`` call protocol
------------------------
``time_fn`` defaults to :func:`time.monotonic` and is injectable for tests.
It is called exactly once before the loop and once per loop iteration
(immediately after the read).  Each iteration:

1. ``frame = read_fn()`` -- an exception raised by ``read_fn`` is treated as a
   failed read.
2. ``elapsed = time_fn() - t_start`` (stored into the result).
3. Failed read -> stop if ``elapsed >= max_s``, else continue.  A read is a
   failure only when ``read_fn`` raised or the returned object is falsy;
   if its truth value cannot be evaluated (numpy array), it is a real frame.
4. Account for the frame (``frames``, ``last_mean``, ``black``, streak).
5. If ``streak >= stable_frames and elapsed >= min_s`` -> stop, ``stable=True``
   (this check runs FIRST, so a frame that completes the streak at/after
   ``min_s`` settles even if it also crossed ``max_s`` by a frame).
6. Else if ``elapsed >= max_s`` -> stop, ``stable=False``.  A stop caused by
   ``max_s`` always reports ``stable=False``.

The loop is additionally capped at 150 read attempts as a fail-soft guard
against a ``time_fn`` that never advances.  The result dict is **ALWAYS**
returned and NEVER raises::

    {"stable": bool, "frames": int, "elapsed": float,
     "last_mean": float | None, "black": int}

``should_retry_scan(good, frames_ok, spoofs_rejected)``
    -> ``bool(not good and frames_ok > 0 and spoofs_rejected > 0)``:
    retry the scan once when the round failed, at least one frame was captured
    and the anti-spoof gate is what threw frames away.
"""

__all__ = [
    "STABLE_DELTA",
    "STABLE_FRAMES",
    "MIN_SETTLE_S",
    "MAX_SETTLE_S",
    "BLACK_MEAN",
    "frame_mean",
    "is_stable",
    "settle",
    "should_retry_scan",
]

import time

STABLE_DELTA = 3.0      # mean-brightness change (0-255) considered stable
STABLE_FRAMES = 3       # consecutive stable frames required
MIN_SETTLE_S = 1.0      # never settle faster than this
MAX_SETTLE_S = 2.5      # give up (stable=False) after this
BLACK_MEAN = 5.0        # frames darker than this are "black" and never stable

_MAX_READS = 150       # fail-soft guard against a non-advancing time_fn


def frame_mean(frame):
    """Mean brightness (0-255) of *frame*; any exception -> 0.0."""
    try:
        return float(frame.mean())
    except Exception:
        return 0.0


def is_stable(prev_mean, mean, delta=STABLE_DELTA):
    """True when the frame-to-frame brightness step is stable.

    False if either mean is None or either mean is < BLACK_MEAN (black frames
    are never stable); else ``abs(prev_mean - mean) <= delta``.
    """
    if prev_mean is None or mean is None:
        return False
    if prev_mean < BLACK_MEAN or mean < BLACK_MEAN:
        return False
    return abs(prev_mean - mean) <= delta


def _is_failed_read(frame):
    """True when *frame* counts as a failed read (falsy object).

    Multi-element numpy arrays raise on truth testing (``bool(ndarray)`` is
    ambiguous); a frame that cannot be truth-tested is a REAL frame, so the
    exception is swallowed and this returns False.  ``None``/``False``/other
    falsy sentinels return True.
    """
    try:
        return not frame
    except Exception:
        return False


def settle(read_fn, time_fn=None, max_s=MAX_SETTLE_S, min_s=MIN_SETTLE_S,
           stable_frames=STABLE_FRAMES):
    """Drain *read_fn* until the brightness stream settles or the budget runs out.

    Semantics are documented in detail in the module docstring (streak counts
    consecutive stable transitions, black frames are counted but never stable,
    failed reads are not frames).  ``time_fn`` defaults to ``time.monotonic``.

    Always returns -- never raises::

        {"stable": bool, "frames": int, "elapsed": float,
         "last_mean": float | None, "black": int}
    """
    if time_fn is None:
        time_fn = time.monotonic

    stats = {"stable": False, "frames": 0, "elapsed": 0.0,
             "last_mean": None, "black": 0}
    t_start = time_fn()
    prev_mean = None
    streak = 0
    reads = 0

    while reads < _MAX_READS:
        reads += 1
        try:
            frame = read_fn()
        except Exception:
            frame = None

        elapsed = time_fn() - t_start
        stats["elapsed"] = elapsed

        if _is_failed_read(frame):
            # Failed read: not a frame, keep trying (unless out of budget).
            if elapsed >= max_s:
                break
            continue

        mean = frame_mean(frame)
        stats["frames"] += 1
        stats["last_mean"] = mean
        if mean < BLACK_MEAN:
            stats["black"] += 1

        if is_stable(prev_mean, mean):
            streak += 1
        else:
            streak = 0
        prev_mean = mean

        if streak >= stable_frames and elapsed >= min_s:
            stats["stable"] = True
            break
        if elapsed >= max_s:
            break

    return stats


def should_retry_scan(good, frames_ok, spoofs_rejected):
    """True when a failed round deserves exactly one anti-spoof retry."""
    return bool(not good and frames_ok > 0 and spoofs_rejected > 0)
