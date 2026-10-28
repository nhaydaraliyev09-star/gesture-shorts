# Changelog

All notable changes to the `gesture-shorts` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Model Asset Management
- **Untracked `*.task` Binaries from Git**: Removed large `*.task` MediaPipe model binaries (~11.5 MB) from git tracking in favor of verified on-demand download and local caching, keeping the git repository lightweight and fast to clone. Existing files on disk remain functional, and `.gitignore` prevents accidental commits of binary model assets.

### Phase 4: Optional Browser Bridge
- **Local WebSocket Bridge Server**: Built a lightweight, secure RFC 6455 WebSocket server (`gesture_shorts/bridge.py`) running strictly on `127.0.0.1` using Python's standard library (no extra pip dependencies). Enforces random per-session token authentication and origin checks.
- **Manifest V3 Browser Extension**: Created a minimal Chrome/Edge/Brave extension (`extension/`) that directly manipulates active `<video>` elements (play, pause, mute, scroll navigation) and streams actual playback and volume states back to the application.
- **Dual Dispatch Mode**: Updated `PlatformAdapter` to route gestures directly to the connected extension and automatically fall back to OS-level `pynput` keystrokes when disconnected. Both paths are fully tested.

### Phase 3: New Features
- **3.1 Window Focus Safety Guard**: Before injecting any keyboard shortcut, `WindowFocusChecker` inspects the active foreground window title (using `ctypes` on Windows, `osascript` on macOS, and `xdotool` on Linux X11). Gestures are suppressed with a status message ("Gesture ignored: browser not focused") unless the target platform (YouTube / TikTok / Instagram) is active. Configurable via `require_browser_focus` (default `true`).
- **3.2 Activation Pose (Arm/Disarm)**: Added deliberate open-palm activation pose (held ~1.0 s) to toggle armed/disarmed states. When disarmed, all navigation gestures are safely disabled to prevent accidental triggers while talking or moving. Includes auto-disarm timer (`auto_disarm_seconds`, default 20 s) and mode selection (`activation_mode`: `"pose"` vs `"always"`).
- **3.3 Camera Preview & Feedback Overlay**: Integrated mirrored live camera preview in the PiP canvas with landmark tracking circles, mouth proximity target, armed/disarmed badge, still-hold progress bar, and 1-second recognized action flash overlay. Added a privacy toggle ("Hide preview") and frame rate capping to keep CPU usage low.
- **3.4 Conditional Face Landmarker Optimization**: Optimized face tracking by executing the face landmarker only when an index finger is detected in the upper 65% of the frame, with mouth position caching (5-frame TTL). Reduces face model invocations by up to 80% during normal playback navigation.
- **3.5 Play/Mute State Tracking**: Removed guessing; next/previous operations set `is_playing = True`, status header displays `▶ Playing / ⏸ Paused` and `🔊 Unmuted / 🔇 Muted`, and events are reported transparently as "Toggled play/pause".
- **3.6 Live Settings Dialog**: Added a comprehensive Tkinter configuration dialog with interactive sliders/entries for camera index, FPS, swipe threshold, hold time, cooldown, mouth distance, focus guard, activation mode, and a "Detect Cameras" helper. Supports live updates, saving to disk, and factory default reset.
- **3.7 Platform Selection UI**: Platform selector buttons highlight the active feed and remember last selected platform across sessions.
- **3.8 Platform Diagnostics & Permissions**: Added environment checks in `gesture_shorts.permissions` to detect Linux Wayland restrictions and explain macOS Accessibility/Input Monitoring requirements.

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
