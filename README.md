# Gesture Shorts 🎥✋

> **Hands-free, gesture-controlled navigation for YouTube Shorts, TikTok, and Instagram Reels.**

Gesture Shorts is an always-on-top desktop control panel with a live camera preview and landmark overlay. It lets you browse and control short-form vertical videos playing in your regular web browser using intuitive webcam hand gestures—no keyboard or mouse required.

---

## ✨ Features

- ✋ **Deliberate Arm/Disarm Pose:** Hold an open palm for ~1.0 s to arm or disarm gestures. When disarmed, gestures are ignored so you can type or talk without false triggers. Auto-disarms after 20 s of inactivity.
- ☝️ **Touch-Free Navigation:**
  - **Swipe Up:** Next video (`↓` arrow key on YouTube Shorts / TikTok / Reels)
  - **Swipe Down:** Previous video (`↑` arrow key on YouTube Shorts / TikTok / Reels)
  - **Hold Still in Mid-Air (~0.8 s):** Play / Pause (`k` / `Space`)
  - **Finger on Lips ("Shh" pose):** Mute / Unmute (`m` key)
- 🛡️ **Browser Focus Guard:** Inspects the active window title before sending keys. Keystrokes are only dispatched if your browser displaying the selected platform is in focus, preventing accidental keystrokes in other applications.
- 🎥 **Real-Time Camera Feedback:** Canvas displays a mirrored camera preview with landmark tracking, fingertip indicator, mouth proximity circle, still-hold timer progress bar, and 1-second recognized action flash. Includes a "Hide preview" privacy toggle.
- ⚡ **Optimized Performance:** Face landmarker runs only when an index finger is detected in the upper 65% of the frame with mouth position caching, reducing CPU overhead by up to 80%.
- 📐 **Aspect-Ratio-Normalized Math:** Distances and thresholds are normalized by camera aspect ratio (`frame_width / frame_height`), ensuring circular Euclidean detection on 16:9, 4:3, and vertical cameras.
- 🔒 **100% Local & Private:** All computer vision processing runs strictly in-memory on your device using MediaPipe and OpenCV. No frames or images are ever stored on disk or transmitted across the network.

---

## 🖐️ Gesture Control Guide

| Gesture | Action | Shortcut (YouTube) | Shortcut (TikTok) | Shortcut (Instagram) |
| :--- | :--- | :---: | :---: | :---: |
| ✋ **Open Palm (Hold ~1.0s)** | **Arm / Disarm** | *(App state toggle)* | *(App state toggle)* | *(App state toggle)* |
| ☝️ **Index Swipe Up** | Next Video | `Down Arrow` | `Down Arrow` | `Down Arrow` |
| 👇 **Index Swipe Down** | Previous Video | `Up Arrow` | `Up Arrow` | `Up Arrow` |
| ⏸️ **Index Held Still (~0.8s)** | Play / Pause | `K` | `Space` | `Space` |
| 🤫 **Finger on Lips** | Mute / Unmute | `M` | `M` | `M` |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A working webcam
- Windows, macOS, or Linux (X11)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nhaydaraliyev09-star/gesture-shorts.git
   cd gesture-shorts
   ```

2. **Set up a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(Note: `opencv-contrib-python` is used to provide complete OpenCV functionality compatible with MediaPipe without symbol collisions).*

4. **Launch the application:**
   - As a Python module:
     ```bash
     python -m gesture_shorts
     ```
   - Or using the legacy script:
     ```bash
     python gesture_control.py
     ```
   - Or after installing with `pip install -e .`:
     ```bash
     gesture-shorts
     ```

---

## 🎮 How to Use

1. Launch **Gesture Shorts**. The compact control window will stay floating on top of your desktop.
2. Choose your platform: **YouTube**, **TikTok**, or **Instagram**.
3. Click **Open feed** to open your platform in your standard browser.
4. Click **Start camera** in the control toolbar.
5. Focus your browser window containing the video player.
6. Raise an **open palm** for ~1 second until the badge shows `ARMED 🟢`.
7. Navigate with index finger swipes and gestures!

---

## ⚙️ Configuration & Units

Settings can be customized directly in the graphical **Settings Dialog** (click "Settings" in the toolbar) or by editing `gesture_settings.json`:

```json
{
  "camera_index": 0,
  "camera_fps": 12,
  "swipe_threshold": 0.13,
  "swipe_window_seconds": 0.60,
  "cooldown_seconds": 0.50,
  "stationary_radius": 0.05,
  "stationary_hold_seconds": 0.80,
  "mouth_distance": 0.13,
  "pip_width": 360,
  "pip_height": 640,
  "gesture_actions": {
    "swipe_up": "next",
    "swipe_down": "previous",
    "stationary_hold": "toggle_play",
    "finger_on_lips": "mute"
  },
  "platform": "YouTube",
  "require_browser_focus": true,
  "activation_mode": "pose",
  "auto_disarm_seconds": 20.0,
  "preview_enabled": true
}
```

### Coordinate & Unit System (Phase 1.9 Note)
Coordinates are normalized using the camera's aspect ratio:
- Horizontal distances are multiplied by `aspect_ratio = frame_width / frame_height`.
- Both horizontal and vertical movements are measured in **units of frame height**.
- This ensures thresholds (`swipe_threshold`, `stationary_radius`, `mouth_distance`) define true isotropic Euclidean circles rather than distorted ellipses across different camera resolutions (e.g. 16:9, 4:3, or 9:16).

---

## 🌐 Optional: Browser Bridge Extension (Direct Video Control)

By default, Gesture Shorts controls playback by simulating OS-level keyboard shortcuts (`pynput`) directed at the active browser window. For more precise control and real-time state feedback, you can optionally install the bundled Manifest V3 browser extension.

### Why Use the Extension?
- Directly accesses HTML5 `<video>` elements (`video.play()`, `video.pause()`, `video.muted`).
- Reports true, un-guessed playback and mute status back to the desktop application.
- Does not rely on keyboard focus.

### Installation Instructions:
1. Open Google Chrome, Microsoft Edge, or Brave and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `extension/` directory from this repository.
4. Click the **Gesture Shorts Bridge** extension icon in your browser toolbar to confirm connection to `127.0.0.1:8765`.
5. When connected, the app automatically routes gestures through the extension, falling back to keystroke simulation if disconnected.

### Security:
- Bound strictly to `127.0.0.1` (never exposed externally).
- Authenticated with a random per-session token.
- Non-extension and non-localhost origins are rejected.

---

## 🏗️ Architecture & Package Structure

```
gesture_shorts/
├── __init__.py       # Package definition & Windows OpenBLAS mitigation
├── __main__.py       # CLI entry point (python -m gesture_shorts)
├── settings.py       # Dataclass settings, clamping, and validation
├── recognizer.py     # Pure gesture state machine (zero GUI/CV dependencies)
├── adapters.py       # Platform shortcuts, key dispatch, and window focus check
├── camera.py         # OpenCV capture worker and MediaPipe task pipeline
├── permissions.py    # Cross-platform environment and permission diagnostics
└── ui.py             # Tkinter GUI, preview overlay, and settings dialog
gesture_control.py    # Backward-compatible thin shim
tests/                # Pytest test suite with synthetic landmark generators
docs/                 # Screenshot and asset documentation
```

---

## 🔧 Permissions & Troubleshooting

### Windows
- Webcam backend defaults to DirectShow (`cv2.CAP_DSHOW`) for low-latency initialization, falling back to the default backend if needed.
- If OpenBLAS thread allocation issues occur on certain multicore systems, `OPENBLAS_NUM_THREADS=1` is automatically configured on startup.

### macOS
- **Accessibility & Input Monitoring:** `pynput` requires Accessibility permissions to simulate keyboard strokes. If keystrokes are ignored, navigate to:
  `System Settings` → `Privacy & Security` → `Accessibility` (and `Input Monitoring`), then grant permission to your Terminal or Python interpreter.
- **Camera Permission:** Ensure Terminal/Python has permission to access the camera under `System Settings` → `Privacy & Security` → `Camera`.

### Linux
- **X11 vs Wayland:** `pynput` keystroke simulation and `xdotool` active window title detection are restricted by Wayland security architecture. Under Wayland, switch to an **X11 / X.Org session** or ensure XWayland is enabled.
- Make sure `xdotool` is installed for browser focus detection:
  ```bash
  sudo apt install xdotool
  ```

---

## 🔒 Privacy & Network Notice

- **Frames:** Camera frames are strictly processed in volatile memory. No video or frames are saved to disk or transmitted anywhere.
- **Models:** The computer vision models (`hand_landmarker.task` and `face_landmarker.task`) are bundled locally. On the first run, if these files are missing or corrupted, the app will download them once from Google's official MediaPipe storage and verify their SHA-256 hash. Once present, the app operates 100% offline.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
