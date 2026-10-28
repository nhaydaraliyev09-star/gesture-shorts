"""Tkinter User Interface with camera preview overlay and settings dialog."""

from __future__ import annotations

import queue
import threading
import time
from tkinter import (
    BOTH,
    BOTTOM,
    LEFT,
    RIGHT,
    BooleanVar,
    Button,
    Canvas,
    Checkbutton,
    DoubleVar,
    Entry,
    Frame,
    IntVar,
    Label,
    Radiobutton,
    Scale,
    StringVar,
    Toplevel,
    X,
)
from typing import Any

from gesture_shorts.adapters import PlatformAdapter
from gesture_shorts.camera import CameraWorker, detect_available_cameras
from gesture_shorts.recognizer import GestureEvent, GestureRecognizer
from gesture_shorts.settings import Settings

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


class SettingsDialog(Toplevel):
    """Configuration dialog for gesture thresholds, camera settings, and modes."""

    def __init__(self, parent: PiPApp) -> None:
        super().__init__(parent.root)
        self.parent = parent
        self.settings = parent.settings
        self.title("Gesture Shorts - Settings")
        self.geometry("380x620")
        self.configure(bg="#181a20")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        self._build_widgets()

    def _build_widgets(self) -> None:
        container = Frame(self, bg="#181a20", padx=16, pady=12)
        container.pack(fill=BOTH, expand=True)

        Label(
            container,
            text="SETTINGS & THRESHOLDS",
            fg="#60a5fa",
            bg="#181a20",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        # Camera Index & Detect
        cam_frame = Frame(container, bg="#181a20")
        cam_frame.pack(fill=X, pady=4)
        Label(
            cam_frame, text="Camera Index:", fg="#d1d5db", bg="#181a20", font=("Segoe UI", 9)
        ).pack(side=LEFT)
        self.cam_idx_var = IntVar(value=self.settings.camera_index)
        Entry(cam_frame, textvariable=self.cam_idx_var, width=5).pack(side=LEFT, padx=8)
        Button(
            cam_frame,
            text="Detect Cameras",
            command=self._detect_cameras,
            bg="#2b303a",
            fg="#f3f4f6",
            font=("Segoe UI", 8),
            relief="flat",
        ).pack(side=RIGHT)

        # Camera FPS
        fps_frame = Frame(container, bg="#181a20")
        fps_frame.pack(fill=X, pady=4)
        Label(
            fps_frame, text="Camera FPS (1-60):", fg="#d1d5db", bg="#181a20", font=("Segoe UI", 9)
        ).pack(side=LEFT)
        self.fps_var = IntVar(value=self.settings.camera_fps)
        Scale(
            fps_frame,
            from_=5,
            to=30,
            orient="horizontal",
            variable=self.fps_var,
            bg="#181a20",
            fg="#d1d5db",
            highlightthickness=0,
            command=self._live_apply,
        ).pack(side=RIGHT, fill=X, expand=True, padx=6)

        # Swipe Threshold
        self.swipe_var = DoubleVar(value=round(self.settings.swipe_threshold, 2))
        self._add_slider(container, "Swipe Threshold:", self.swipe_var, 0.03, 0.40, 0.01)

        # Hold Duration
        self.hold_var = DoubleVar(value=round(self.settings.stationary_hold_seconds, 2))
        self._add_slider(container, "Stationary Hold (sec):", self.hold_var, 0.2, 2.0, 0.1)

        # Cooldown
        self.cooldown_var = DoubleVar(value=round(self.settings.cooldown_seconds, 2))
        self._add_slider(container, "Cooldown (sec):", self.cooldown_var, 0.1, 1.5, 0.05)

        # Mouth Distance
        self.mouth_var = DoubleVar(value=round(self.settings.mouth_distance, 2))
        self._add_slider(container, "Mouth Distance (mute):", self.mouth_var, 0.04, 0.30, 0.01)

        # Require Browser Focus Checkbox
        self.focus_var = BooleanVar(value=self.settings.require_browser_focus)
        Checkbutton(
            container,
            text="Only trigger when browser is focused",
            variable=self.focus_var,
            bg="#181a20",
            fg="#d1d5db",
            selectcolor="#2b303a",
            activebackground="#181a20",
            activeforeground="#f3f4f6",
            command=self._live_apply,
        ).pack(anchor="w", pady=6)

        # Activation Mode (Pose vs Always)
        mode_frame = Frame(container, bg="#181a20")
        mode_frame.pack(fill=X, pady=4)
        Label(
            mode_frame,
            text="Activation Mode:",
            fg="#d1d5db",
            bg="#181a20",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        self.mode_var = StringVar(value=self.settings.activation_mode)
        Radiobutton(
            mode_frame,
            text="Open-palm arm/disarm pose (Recommended)",
            variable=self.mode_var,
            value="pose",
            bg="#181a20",
            fg="#d1d5db",
            selectcolor="#2b303a",
            activebackground="#181a20",
            command=self._live_apply,
        ).pack(anchor="w")
        Radiobutton(
            mode_frame,
            text="Always active (classic)",
            variable=self.mode_var,
            value="always",
            bg="#181a20",
            fg="#d1d5db",
            selectcolor="#2b303a",
            activebackground="#181a20",
            command=self._live_apply,
        ).pack(anchor="w")

        # Buttons at bottom
        btn_frame = Frame(container, bg="#181a20")
        btn_frame.pack(fill=X, side=BOTTOM, pady=10)
        Button(
            btn_frame,
            text="Reset to Defaults",
            command=self._reset_defaults,
            bg="#374151",
            fg="#f3f4f6",
            relief="flat",
        ).pack(side=LEFT)
        Button(
            btn_frame,
            text="Save Settings",
            command=self._save_and_close,
            bg="#2563eb",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        ).pack(side=RIGHT)

    def _add_slider(
        self,
        parent: Frame,
        label: str,
        var: DoubleVar,
        from_: float,
        to: float,
        res: float,
    ) -> None:
        row = Frame(parent, bg="#181a20")
        row.pack(fill=X, pady=2)
        Label(row, text=label, fg="#d1d5db", bg="#181a20", font=("Segoe UI", 9)).pack(side=LEFT)
        Scale(
            row,
            from_=from_,
            to=to,
            resolution=res,
            orient="horizontal",
            variable=var,
            bg="#181a20",
            fg="#d1d5db",
            highlightthickness=0,
            command=self._live_apply,
        ).pack(side=RIGHT, fill=X, expand=True, padx=6)

    def _detect_cameras(self) -> None:
        available = detect_available_cameras()
        self.cam_idx_var.set(available[0])
        self.parent.show_status(f"Detected camera indices: {available}")

    def _live_apply(self, _event: Any = None) -> None:
        self.settings.camera_index = self.cam_idx_var.get()
        self.settings.camera_fps = self.fps_var.get()
        self.settings.swipe_threshold = self.swipe_var.get()
        self.settings.stationary_hold_seconds = self.hold_var.get()
        self.settings.cooldown_seconds = self.cooldown_var.get()
        self.settings.mouth_distance = self.mouth_var.get()
        self.settings.require_browser_focus = self.focus_var.get()
        self.settings.activation_mode = self.mode_var.get()
        if self.settings.activation_mode == "always":
            self.parent.recognizer.set_armed(True)
        self.parent.update_header_status()

    def _reset_defaults(self) -> None:
        defaults = Settings()
        self.cam_idx_var.set(defaults.camera_index)
        self.fps_var.set(defaults.camera_fps)
        self.swipe_var.set(defaults.swipe_threshold)
        self.hold_var.set(defaults.stationary_hold_seconds)
        self.cooldown_var.set(defaults.cooldown_seconds)
        self.mouth_var.set(defaults.mouth_distance)
        self.focus_var.set(defaults.require_browser_focus)
        self.mode_var.set(defaults.activation_mode)
        self._live_apply()

    def _save_and_close(self) -> None:
        self._live_apply()
        self.settings.save()
        self.parent.show_status("Settings saved successfully")
        self.destroy()


class PiPApp:
    """Main application window for Gesture Shorts."""

    def __init__(self, root: Any) -> None:
        self.root = root
        self.settings = Settings.load()
        self.events: queue.Queue[GestureEvent] = queue.Queue()
        self.status_queue: queue.Queue[str] = queue.Queue()
        self.frame_queue: queue.Queue[tuple[Any, list[Any] | None, tuple[float, float] | None]] = (
            queue.Queue(maxsize=2)
        )

        self.recognizer = GestureRecognizer(
            self.settings, self.events.put, on_arm_change=self._on_arm_change
        )
        self.platform = self.settings.platform
        self.adapter = PlatformAdapter(self.platform, self.show_status)
        self.camera: CameraWorker | None = None

        self.status_var = StringVar(value="Ready")
        self.state_var = StringVar(value="")
        self.last_action_text: str = ""
        self.last_action_until: float = 0.0

        # Preview rendering state
        self.preview_image: Any = None
        self.platform_buttons: dict[str, Button] = {}

        self.build_ui()
        self.update_header_status()
        self.root.after(80, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self) -> None:
        self.root.title("Gesture Shorts")
        self.root.geometry(f"{self.settings.pip_width}x{self.settings.pip_height}")
        self.root.minsize(320, 520)
        self.root.configure(bg="#111318")
        self.root.attributes("-topmost", True)

        # Toolbar
        toolbar = Frame(self.root, bg="#1d2028")
        toolbar.pack(fill=X)
        Label(
            toolbar,
            text="GESTURE SHORTS",
            fg="#f3f4f6",
            bg="#1d2028",
            font=("Segoe UI", 10, "bold"),
        ).pack(side=LEFT, padx=10, pady=8)

        Button(
            toolbar,
            text="Settings",
            command=self.open_settings,
            bg="#2b303a",
            fg="#93c5fd",
            font=("Segoe UI", 8),
            relief="flat",
        ).pack(side=RIGHT, padx=6, pady=6)

        Button(
            toolbar,
            text="Open feed",
            command=lambda: self.adapter.open_feed(),
            bg="#2b303a",
            fg="#f3f4f6",
            font=("Segoe UI", 8),
            relief="flat",
        ).pack(side=RIGHT, padx=4, pady=6)

        # Playback & Armed status sub-header
        self.header_frame = Frame(self.root, bg="#181a20", padx=10, pady=4)
        self.header_frame.pack(fill=X)
        self.header_label = Label(
            self.header_frame,
            textvariable=self.state_var,
            fg="#9ca3af",
            bg="#181a20",
            font=("Segoe UI", 8),
        )
        self.header_label.pack(side=LEFT)

        self.arm_toggle_btn = Button(
            self.header_frame,
            text="ARMED",
            command=self.toggle_arm,
            bg="#15803d",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=6,
        )
        self.arm_toggle_btn.pack(side=RIGHT)

        # Canvas for camera preview & feedback
        self.canvas = Canvas(self.root, bg="#08090c", highlightthickness=0)
        self.canvas.pack(fill=BOTH, expand=True)
        self._draw_placeholder()

        # Platform selector bar
        controls = Frame(self.root, bg="#1d2028")
        controls.pack(fill=X)

        for name in PlatformAdapter.URLS:
            btn = Button(
                controls,
                text=name,
                command=lambda selected=name: self.select_platform(selected),
                bg="#3b82f6" if name == self.platform else "#2b303a",
                fg="#f3f4f6",
                font=("Segoe UI", 8, "bold" if name == self.platform else "normal"),
                relief="flat",
            )
            btn.pack(side=LEFT, padx=(6 if name == "YouTube" else 2, 2), pady=6)
            self.platform_buttons[name] = btn

        self.preview_btn = Button(
            controls,
            text="Hide preview" if self.settings.preview_enabled else "Show preview",
            command=self.toggle_preview,
            bg="#2b303a",
            fg="#d1d5db",
            font=("Segoe UI", 8),
            relief="flat",
        )
        self.preview_btn.pack(side=LEFT, padx=4, pady=6)

        self.camera_btn = Button(
            controls,
            text="Start camera",
            command=self.toggle_camera,
            bg="#2f6f5e",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
        )
        self.camera_btn.pack(side=RIGHT, padx=8, pady=6)

        # Status footer
        status_bar = Frame(self.root, bg="#111318")
        status_bar.pack(fill=X, padx=8, pady=5)
        Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            bg="#111318",
            fg="#a9b0bd",
            font=("Segoe UI", 9),
        ).pack(side=LEFT, fill=X, expand=True)

    def _draw_placeholder(self) -> None:
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or self.settings.pip_width
        h = self.canvas.winfo_height() or (self.settings.pip_height - 120)
        self.canvas.create_text(
            w // 2,
            h // 2 - 30,
            text="Choose a platform,\nthen open its feed",
            fill="#a9b0bd",
            font=("Segoe UI", 14),
            justify="center",
            tags="placeholder",
        )
        self.canvas.create_text(
            w // 2,
            h // 2 + 35,
            text="☝️ Up/Down: Next/Prev  |  Hold: Pause\n🤫 Finger on Lips: Mute  |  ✋ Palm: Arm",
            fill="#606875",
            font=("Segoe UI", 8),
            justify="center",
            tags="placeholder",
        )

    def update_header_status(self) -> None:
        play_str = "▶ Playing" if self.adapter.is_playing else "⏸ Paused"
        mute_str = "🔇 Muted" if self.adapter.is_muted else "🔊 Unmuted"
        focus_str = "Focus Guard: ON" if self.settings.require_browser_focus else "Focus Guard: OFF"
        self.state_var.set(f"{play_str}  |  {mute_str}  |  {focus_str}")

        if self.recognizer.is_armed:
            self.arm_toggle_btn.config(text="ARMED 🟢", bg="#15803d")
        else:
            self.arm_toggle_btn.config(text="DISARMED ⚪", bg="#4b5563")

    def toggle_arm(self) -> None:
        self.recognizer.set_armed(not self.recognizer.is_armed)
        self.update_header_status()

    def _on_arm_change(self, armed: bool) -> None:
        self.show_status("Gestures ARMED" if armed else "Gestures DISARMED")
        self.update_header_status()

    def toggle_preview(self) -> None:
        self.settings.preview_enabled = not self.settings.preview_enabled
        self.preview_btn.config(
            text="Hide preview" if self.settings.preview_enabled else "Show preview"
        )
        if not self.settings.preview_enabled:
            self._draw_placeholder()

    def select_platform(self, platform: str) -> None:
        self.platform = platform
        self.settings.platform = platform
        self.adapter = PlatformAdapter(platform, self.show_status)
        for name, btn in self.platform_buttons.items():
            if name == platform:
                btn.config(bg="#3b82f6", font=("Segoe UI", 8, "bold"))
            else:
                btn.config(bg="#2b303a", font=("Segoe UI", 8, "normal"))
        self.show_status(f"Selected {platform}")

    def open_settings(self) -> None:
        SettingsDialog(self)

    def toggle_camera(self) -> None:
        if self.camera and self.camera.is_alive():
            self.camera_btn.config(state="disabled", text="Stopping...")
            cam_to_stop = self.camera

            def _stop_worker() -> None:
                cam_to_stop.stop()
                cam_to_stop.join(timeout=2.0)
                self.camera = None
                self.show_status("Camera stopped")
                self.status_queue.put("__CAMERA_STOPPED__")

            threading.Thread(target=_stop_worker, daemon=True).start()
            return

        def _on_camera_frame(
            frame: Any, landmarks: list[Any] | None, mouth_pos: tuple[float, float] | None
        ) -> None:
            if not self.settings.preview_enabled:
                return
            try:
                self.frame_queue.put_nowait((frame, landmarks, mouth_pos))
            except queue.Full:
                pass

        self.camera = CameraWorker(
            self.settings,
            self.events,
            self.show_status,
            on_frame=_on_camera_frame,
            recognizer=self.recognizer,
        )
        self.camera.start()
        self.camera_btn.config(text="Stop camera", bg="#8a3030")

    def _render_camera_frame(
        self,
        frame: Any,
        landmarks: list[Any] | None,
        mouth_pos: tuple[float, float] | None,
    ) -> None:
        if not self.settings.preview_enabled or Image is None or ImageTk is None:
            return

        canvas_w = max(10, self.canvas.winfo_width())
        canvas_h = max(10, self.canvas.winfo_height())

        # Resize frame to preview dimensions maintaining aspect ratio
        try:
            h, w = frame.shape[:2]
            scale = min(canvas_w / w, canvas_h / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))

            import cv2
            resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            self.preview_image = ImageTk.PhotoImage(image=pil_img)

            self.canvas.delete("all")
            offset_x = (canvas_w - new_w) // 2
            offset_y = (canvas_h - new_h) // 2
            self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self.preview_image)

            # Draw landmarks overlay
            if landmarks and len(landmarks) >= 21:
                # Draw index tip
                tip = landmarks[8]
                tx = offset_x + int(tip.x * new_w)
                ty = offset_y + int(tip.y * new_h)
                self.canvas.create_oval(
                    tx - 6, ty - 6, tx + 6, ty + 6, fill="#22c55e", outline="#ffffff", width=2
                )

                # Draw wrist
                wrist = landmarks[0]
                wx = offset_x + int(wrist.x * new_w)
                wy = offset_y + int(wrist.y * new_h)
                self.canvas.create_oval(
                    wx - 4, wy - 4, wx + 4, wy + 4, fill="#3b82f6", outline="#ffffff"
                )

            if mouth_pos is not None:
                mx = offset_x + int(mouth_pos[0] * new_w)
                my = offset_y + int(mouth_pos[1] * new_h)
                self.canvas.create_oval(
                    mx - 5, my - 5, mx + 5, my + 5, fill="#06b6d4", outline="#ffffff"
                )

            # Draw status / pose badge
            pose_text = f"Pose: {self.recognizer.current_pose_name.upper()}"
            arm_text = "ARMED" if self.recognizer.is_armed else "DISARMED"
            badge_color = "#15803d" if self.recognizer.is_armed else "#6b7280"

            self.canvas.create_rectangle(
                10, 10, 180, 42, fill="#111827", outline=badge_color, width=2
            )
            self.canvas.create_text(
                16,
                26,
                anchor="w",
                text=f"{arm_text} | {pose_text}",
                fill="#f3f4f6",
                font=("Segoe UI", 8, "bold"),
            )

            # Draw stationary hold progress bar if holding
            progress = self.recognizer.get_hold_progress()
            if progress > 0.05:
                bar_w = 120
                self.canvas.create_rectangle(10, 50, 10 + bar_w, 58, fill="#1f2937", outline="")
                self.canvas.create_rectangle(
                    10, 50, 10 + int(bar_w * progress), 58, fill="#3b82f6", outline=""
                )

            # Flash recognized action text
            now = time.monotonic()
            if self.last_action_text and now < self.last_action_until:
                self.canvas.create_rectangle(
                    canvas_w // 2 - 80,
                    canvas_h // 2 - 25,
                    canvas_w // 2 + 80,
                    canvas_h // 2 + 25,
                    fill="#111827",
                    outline="#3b82f6",
                    width=2,
                )
                self.canvas.create_text(
                    canvas_w // 2,
                    canvas_h // 2,
                    text=self.last_action_text,
                    fill="#60a5fa",
                    font=("Segoe UI", 12, "bold"),
                )
        except Exception:
            pass

    def process_events(self) -> None:
        try:
            # Drain status queue
            while True:
                try:
                    msg = self.status_queue.get_nowait()
                    if msg == "__CAMERA_STOPPED__":
                        self.camera_btn.config(state="normal", text="Start camera", bg="#2f6f5e")
                        self._draw_placeholder()
                    else:
                        self.status_var.set(msg)
                except queue.Empty:
                    break

            # Render newest video preview frame
            latest_frame = None
            while True:
                try:
                    latest_frame = self.frame_queue.get_nowait()
                except queue.Empty:
                    break
            if latest_frame is not None:
                frame, landmarks, mouth_pos = latest_frame
                self._render_camera_frame(frame, landmarks, mouth_pos)

            # Process gesture events
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                action = self.settings.gesture_actions.get(event.name)
                if action is None:
                    continue
                try:
                    success = self.adapter.perform(
                        action, require_browser_focus=self.settings.require_browser_focus
                    )
                    if success:
                        self.last_action_text = action.replace("_", " ").title()
                        self.last_action_until = time.monotonic() + 1.0
                        self.update_header_status()
                except Exception as exc:
                    self.show_status(f"Action error: {exc}")
        finally:
            self.root.after(80, self.process_events)

    def show_status(self, text: str) -> None:
        self.status_queue.put(text)

    def close(self) -> None:
        if self.camera:
            self.camera.stop()
        try:
            if self.settings.is_modified():
                self.settings.save()
        except OSError:
            pass
        finally:
            self.root.destroy()
