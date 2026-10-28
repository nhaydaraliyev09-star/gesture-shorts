"""Thin backward-compatibility shim for gesture_control.py."""

from __future__ import annotations

import os

# Mitigate Windows OpenBLAS thread allocation exhaustion with OpenCV
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from gesture_shorts.__main__ import main
from gesture_shorts.adapters import PlatformAdapter
from gesture_shorts.camera import CameraWorker
from gesture_shorts.recognizer import GestureEvent, GestureRecognizer
from gesture_shorts.settings import Settings
from gesture_shorts.ui import PiPApp

__all__ = [
    "CameraWorker",
    "GestureEvent",
    "GestureRecognizer",
    "PiPApp",
    "PlatformAdapter",
    "Settings",
    "main",
]

if __name__ == "__main__":
    main()
