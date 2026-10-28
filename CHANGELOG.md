# Changelog

All notable changes to the `gesture-shorts` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Phase 2: Architecture, Tests & Tooling
- **2.1 Package Modularization**: Split monolithic script into modular `gesture_shorts` package (`settings`, `recognizer`, `adapters`, `camera`, `ui`, `__main__`). Retained `gesture_control.py` as a backward-compatible thin shim. `gesture_shorts.recognizer` has zero dependencies on Tkinter, OpenCV, or MediaPipe.
- **Indentation Refactor**: Converted repository from tab indentation to 4 spaces across all files.
- **2.2 Robust Settings Validation**: Added per-key fallback, numeric clamping (FPS 1–60, thresholds 0.01–1.0, etc.), type verification, and action whitelist validation. Missing or corrupted keys no longer discard valid configurations.
- **2.3 Test Suite**: Added 29 comprehensive tests using synthetic hand landmark generators covering swipe directions, return motion suppression, stationary hold single-triggering, finger-on-lips isolation, dropout handling, cooldown enforcement, and corrupted file resilience.
- **2.4 Tooling & Packaging**:
  - Configured `pyproject.toml` with project metadata, dependencies, `gesture-shorts` CLI console script entry point, `ruff`, and `pytest` configurations.
  - Resolved MediaPipe OpenCV conflict by standardizing on `opencv-contrib-python>=4.8.0,<5.1.0` in `requirements.txt` to prevent duplicate symbols and OpenBLAS thread exhaustion.
  - Added GitHub Actions CI matrix workflow (`.github/workflows/ci.yml`) running `ruff` and `pytest` on Python 3.10, 3.11, and 3.12.

### Phase 1: Bug Fixes
- **1.1 Hand Dropout Swipe Fix**: Updated `GestureRecognizer.flush()` to track lost frames and trigger state reset after a 2-frame grace period. Also reset `_suppress_swipe` and `mute_fired` on state reset, preventing false swipes when hands drop out and reappear.
- **1.2 Safe Window Closure & Dirty-Only Save**: Wrapped `PiPApp.close()` in `try/except OSError` with a `finally: root.destroy()` guarantee. Only write `gesture_settings.json` if values have been modified.
- **1.3 Thread-Safe Status Queue**: Camera worker now publishes status strings to a thread-safe `queue.Queue`, drained by the main Tkinter thread inside `process_events()`.
- **1.4 Event Processing Rescheduling**: Guarded `process_events()` with `try/finally` to guarantee UI event loop rescheduling even if key sending or adapter actions raise exceptions.
- **1.5 Safe Camera Start/Stop**: Added dynamic "Start camera" / "Stop camera" button states with stopping state locking; worker thread is joined with a 2-second timeout before release. On Windows, `cv2.VideoCapture` prioritizes `cv2.CAP_DSHOW` before falling back to default.
- **1.6 Prioritize Tasks API & Warn on Legacy**: Camera worker now prioritizes MediaPipe Tasks API when available (`mp.tasks`) and displays an informative warning if falling back to legacy solutions where mute is unavailable.
- **1.7 Model Integrity & Safe Download**: Added SHA-256 and size verification for MediaPipe models. Models are downloaded with timeouts into temporary `.part` files before atomic replacement. Staged in temp directories on Windows to prevent C++ path issues with non-ASCII directory names.
- **1.8 Cross-Platform Missing Dependency Message**: Replaced Windows-only error message with a dynamic cross-platform prompt reporting missing dependencies (`opencv-python`, `mediapipe`) and exact `pip install -r requirements.txt` command.
- **1.9 Aspect-Ratio-Aware Distance Math**: Scaled horizontal coordinates by `aspect_ratio = width / height` across swipe, stationary radius, and mouth distance calculations, normalizing Euclidean math across 16:9, 4:3, and vertical cameras.
