# Gesture Shorts 🎥✋

> **Hands-free, gesture-controlled short-video player for YouTube Shorts, TikTok, and Instagram Reels.**

Gesture Shorts lets you watch and navigate short-form vertical videos on your desktop in an always-on-top Picture-in-Picture (PiP) window, controlled entirely by intuitive hand gestures through your webcam—no keyboard or mouse required.

---

## ✨ Features

- ☝️ **Index-Finger Gestures:** Designed to feel like mobile touch controls:
  - **Move Up:** Next video (`↓` key on YouTube Shorts / TikTok / Instagram Reels)
  - **Move Down:** Previous video (`↑` key on YouTube Shorts / TikTok / Instagram Reels)
  - **Hold Still in Mid-Air (~0.8s):** Play / Pause (`k` / `Space`)
  - **Finger on Lips ("Shh" pose):** Mute / Unmute (`m` key)
- 🛡️ **Return Motion Suppression:** Returning your hand back to neutral after swiping will **never** trigger a reverse action.
- 📐 **Scale- & Angle-Invariant Tracking:** Natural index-finger pose detection adapts to hand distance and pointing angles.
- 🎯 **Accurate Lips / Mute Isolation:** When touching your finger to your lips, the stationary hold is automatically suppressed so mute never accidentally pauses or resumes playback.
- 📌 **Always-on-Top PiP Window:** Compact vertical 9:16 layout designed to float alongside your work or study setup.
- 🔒 **100% Private & Local:** All computer vision and landmark tracking runs on-device using MediaPipe and OpenCV. No video, images, or telemetry are ever recorded or transmitted to the cloud.

---

## 🖐️ Gesture Control Guide

| Gesture | Action | Shortcut (YouTube) | Shortcut (TikTok) | Shortcut (Instagram) |
| :--- | :--- | :---: | :---: | :---: |
| ☝️ **Index Finger Up** | Next Video | `Down Arrow` | `Down Arrow` | `Down Arrow` |
| 👇 **Index Finger Down** | Previous Video | `Up Arrow` | `Up Arrow` | `Up Arrow` |
| ⏸️ **Index Held Still (~0.8s)** | Play / Pause | `K` | `Space` | `Space` |
| 🤫 **Finger on Lips** | Mute / Unmute | `M` | `M` | `M` |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A working webcam
- Windows, macOS, or Linux

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nhaydaraliyev09-star/gesture-shorts.git
   cd gesture-shorts
   ```

2. **Set up a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv venv
     .\venv\Scripts\Activate.ps1
     ```
   - **macOS / Linux:**
     ```bash
     python3 -m venv venv
     source venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Launch the application:**
   - **Windows:**
     ```powershell
     .\venv\Scripts\python.exe gesture_control.py
     ```
   - **macOS / Linux:**
     ```bash
     python gesture_control.py
     ```

---

## 🎮 How to Use

1. Launch **Gesture Shorts**.
2. Select your platform: **YouTube**, **TikTok**, or **Instagram**.
3. Click **Open feed** to open your favorite feed in your browser.
4. Click **Start camera** in the PiP toolbar.
5. Focus your browser window and control playback using index-finger gestures!

---

## ⚙️ Configuration (`gesture_settings.json`)

All thresholds and controls are customizable in `gesture_settings.json`:

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
  }
}
```

- **`camera_fps`**: Camera capture rate (12 FPS is optimized for low CPU usage while maintaining responsive tracking).
- **`swipe_threshold`**: Vertical distance needed to register a swipe (normalized 0.0 to 1.0).
- **`stationary_radius`**: Mid-air tremor tolerance for stationary hold.
- **`stationary_hold_seconds`**: Duration to hold finger still before play/pause toggles.
- **`mouth_distance`**: Proximity between index fingertip and lips to trigger mute.

---

## 🏗️ Architecture & Tech Stack

- **GUI & PiP Window:** Python `tkinter` (Always-on-top, responsive, lightweight).
- **Computer Vision:** `mediapipe` (HandLandmarker & FaceLandmarker tasks), `opencv-python`.
- **Input Automation:** `pynput` (Simulated cross-platform keyboard events sent to browser player).
- **Persistence:** Local JSON settings store.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
