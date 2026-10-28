"""Gesture Shorts - Hands-free video navigation via webcam gestures."""

from __future__ import annotations

import os

# Mitigate Windows OpenBLAS thread allocation exhaustion with OpenCV
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

__version__ = "0.2.0"
