"""Verify gesture_shorts.recognizer can be imported without cv2/mediapipe/tkinter."""

from __future__ import annotations

import sys


def test_recognizer_has_no_heavy_gui_or_cv_dependencies() -> None:
    # Unload gesture_shorts if loaded
    for mod in list(sys.modules.keys()):
        if mod.startswith("gesture_shorts"):
            del sys.modules[mod]

    # Mask heavy modules
    orig_modules = {}
    blocked = ["cv2", "mediapipe", "tkinter", "_tkinter"]
    for b in blocked:
        orig_modules[b] = sys.modules.get(b)
        sys.modules[b] = None  # Causes ImportError on attempt to import

    try:
        from gesture_shorts.recognizer import GestureEvent, GestureRecognizer
        from gesture_shorts.settings import Settings

        s = Settings()
        r = GestureRecognizer(s, lambda _: None)
        assert r is not None
        assert GestureEvent("test").name == "test"
    finally:
        for b, orig in orig_modules.items():
            if orig is None:
                sys.modules.pop(b, None)
            else:
                sys.modules[b] = orig
