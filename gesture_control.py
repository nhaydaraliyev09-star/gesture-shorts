"""Gesture-controlled short-video viewer.

The app stays local: camera frames are processed in memory and platform feeds
are opened in the user's normal browser session. Install the optional vision
dependencies from requirements.txt to enable camera control.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import BOTH, LEFT, RIGHT, Button, Canvas, Frame, Label, StringVar, Tk, X
from typing import ClassVar

try:
	from pynput.keyboard import Controller as KeyboardController
	from pynput.keyboard import Key
	_keyboard = KeyboardController()
except ImportError:
	_keyboard = None

try:
	import cv2
except ImportError:
	cv2 = None

try:
	import mediapipe as mp
except ImportError:
	mp = None


APP_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = APP_DIR / "gesture_settings.json"


@dataclass
class Settings:
	camera_index: int = 0
	camera_fps: int = 12
	swipe_threshold: float = 0.13
	swipe_window_seconds: float = 0.60
	cooldown_seconds: float = 0.50
	stationary_radius: float = 0.05
	stationary_hold_seconds: float = 0.80
	mouth_distance: float = 0.13
	pip_width: int = 360
	pip_height: int = 640
	gesture_actions: dict[str, str] = field(default_factory=lambda: {
		"swipe_up": "next",
		"swipe_down": "previous",
		"stationary_hold": "toggle_play",
		"finger_on_lips": "mute",
	})
	_loaded_snapshot: str = field(default="", init=False, repr=False)

	def to_dict(self) -> dict[str, object]:
		return {
			"camera_index": self.camera_index,
			"camera_fps": self.camera_fps,
			"swipe_threshold": self.swipe_threshold,
			"swipe_window_seconds": self.swipe_window_seconds,
			"cooldown_seconds": self.cooldown_seconds,
			"stationary_radius": self.stationary_radius,
			"stationary_hold_seconds": self.stationary_hold_seconds,
			"mouth_distance": self.mouth_distance,
			"pip_width": self.pip_width,
			"pip_height": self.pip_height,
			"gesture_actions": dict(self.gesture_actions),
		}

	@classmethod
	def load(cls) -> Settings:
		if not SETTINGS_PATH.exists():
			instance = cls()
			instance._loaded_snapshot = json.dumps(instance.to_dict(), sort_keys=True)
			return instance
		try:
			raw = SETTINGS_PATH.read_text(encoding="utf-8")
			values = json.loads(raw)
			valid_values = {key: value for key, value in values.items() if key in cls.__dataclass_fields__}
			instance = cls(**valid_values)
			instance._loaded_snapshot = json.dumps(instance.to_dict(), sort_keys=True)
			return instance
		except (OSError, TypeError, ValueError):
			instance = cls()
			instance._loaded_snapshot = json.dumps(instance.to_dict(), sort_keys=True)
			return instance

	def save(self) -> None:
		serialized = json.dumps(self.to_dict(), indent=2)
		SETTINGS_PATH.write_text(serialized, encoding="utf-8")
		self._loaded_snapshot = json.dumps(self.to_dict(), sort_keys=True)

	def is_modified(self) -> bool:
		current = json.dumps(self.to_dict(), sort_keys=True)
		return current != self._loaded_snapshot


@dataclass(frozen=True)
class GestureEvent:
	name: str
	confidence: float = 1.0


class GestureRecognizer:
	"""Index-finger state machine for navigation, hold, and mute gestures."""

	def __init__(self, settings: Settings, emit: Callable[[GestureEvent], None]) -> None:
		self.settings = settings
		self.emit = emit
		self.aspect_ratio: float = 1.0
		self.last_position: tuple[float, float] | None = None
		self.start_position: tuple[float, float] | None = None
		self.started_at: float = 0.0

		# Stationary hold tracking (holding index finger still in mid-air)
		self.stationary_anchor: tuple[float, float] | None = None
		self.stationary_since: float | None = None
		self.stationary_fired: bool = False

		# Mute tracking (finger on lips)
		self.mute_fired: bool = False

		# Swipe return suppression: after a swipe, suppress the opposite return motion
		self._suppress_swipe: str | None = None
		self._suppress_until: float = 0.0

		self.cooldown_until: float = 0.0
		self._lost_frames: int = 0

	def set_aspect_ratio(self, ratio: float) -> None:
		self.aspect_ratio = max(0.1, ratio)

	def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
		dx = (p1[0] - p2[0]) * self.aspect_ratio
		dy = p1[1] - p2[1]
		return math.hypot(dx, dy)

	def update(
		self,
		landmarks: list[object],
		mouth_position: tuple[float, float] | None = None,
		now: float | None = None,
	) -> None:
		now = time.monotonic() if now is None else now

		if not self._is_index_only(landmarks, self.aspect_ratio):
			self._lost_frames += 1
			# Allow a small 2-frame grace period for tracking flickers during fast motion
			if self._lost_frames > 2:
				self._reset_finger_state()
			return

		self._lost_frames = 0
		index_tip = landmarks[8]
		position = (float(index_tip.x), float(index_tip.y))

		if self.last_position is None:
			self.last_position = position
			self.start_position = position
			self.started_at = now
			self.stationary_anchor = position
			self.stationary_since = now
			self.stationary_fired = False
			return

		assert self.start_position is not None

		# Clear opposite swipe suppression if timeout passed
		if self._suppress_swipe and now > self._suppress_until:
			self._suppress_swipe = None

		# --- 1. MOUTH / MUTE CHECK ---
		is_near_mouth = False
		if mouth_position is not None:
			dist_to_mouth = self._distance(position, mouth_position)
			if dist_to_mouth <= self.settings.mouth_distance:
				is_near_mouth = True
				if not self.mute_fired and now >= self.cooldown_until:
					self._fire("finger_on_lips", now)
					self.mute_fired = True
			elif dist_to_mouth > self.settings.mouth_distance * 1.35:
				self.mute_fired = False

		# --- 2. SWIPE DETECTION (Moving UP or DOWN) ---
		# Don't trigger swipes when hand is resting near mouth
		if not is_near_mouth:
			elapsed = now - self.started_at
			dx = (position[0] - self.start_position[0]) * self.aspect_ratio
			dy = position[1] - self.start_position[1]

			if elapsed <= self.settings.swipe_window_seconds and abs(dy) >= self.settings.swipe_threshold:
				if now >= self.cooldown_until and abs(dy) > abs(dx) * 1.1:
					swipe_dir = "swipe_up" if dy < 0 else "swipe_down"
					opposite_dir = "swipe_down" if dy < 0 else "swipe_up"

					if self._suppress_swipe != swipe_dir:
						self._fire(swipe_dir, now)
						# Suppress return motion so moving hand back doesn't trigger reverse swipe
						self._suppress_swipe = opposite_dir
						self._suppress_until = now + 0.85
						# Reset motion anchor to current position
						self.start_position = position
						self.started_at = now
						# Reset stationary tracking
						self.stationary_anchor = position
						self.stationary_since = now
						self.stationary_fired = True  # don't fire pause immediately after a swipe
						self.last_position = position
						return
			elif elapsed > self.settings.swipe_window_seconds:
				self.start_position = position
				self.started_at = now

		# --- 3. STATIONARY HOLD (Not moving in mid-air -> Pause / Resume) ---
		if is_near_mouth:
			# Finger on lips is exclusively for mute, never trigger pause/resume!
			self.stationary_anchor = None
			self.stationary_since = None
			self.stationary_fired = False
		else:
			if self.stationary_anchor is None:
				self.stationary_anchor = position
				self.stationary_since = now
				self.stationary_fired = False
			else:
				drift = self._distance(position, self.stationary_anchor)
				if drift <= self.settings.stationary_radius:
					# Hand is still in mid-air
					if (
						not self.stationary_fired
						and (now - self.stationary_since) >= self.settings.stationary_hold_seconds
						and now >= self.cooldown_until
					):
						self._fire("stationary_hold", now)
						self.stationary_fired = True
						self._suppress_swipe = None  # Hand came to rest, clear return suppression
				else:
					# Hand moved beyond stationary jitter radius
					self.stationary_anchor = position
					self.stationary_since = now
					self.stationary_fired = False

		self.last_position = position

	def flush(self, now: float | None = None) -> None:
		_ = time.monotonic() if now is None else now
		self._lost_frames += 1
		if self._lost_frames > 2:
			self._reset_finger_state()

	def _fire(self, name: str, now: float) -> None:
		self.emit(GestureEvent(name))
		self.cooldown_until = now + self.settings.cooldown_seconds

	def _reset_finger_state(self) -> None:
		self.last_position = None
		self.start_position = None
		self.stationary_anchor = None
		self.stationary_since = None
		self.stationary_fired = False
		self.mute_fired = False
		self._suppress_swipe = None
		self._suppress_until = 0.0

	@staticmethod
	def _is_index_only(landmarks: list[object], aspect_ratio: float = 1.0) -> bool:
		wrist = landmarks[0]

		def dist(p1: object, p2: object) -> float:
			dx = (p1.x - p2.x) * aspect_ratio
			dy = p1.y - p2.y
			return math.hypot(dx, dy)

		palm_len = dist(landmarks[9], wrist)
		palm_len = max(palm_len, 0.04)

		# Index finger extension (scale-invariant and angle-invariant)
		index_tip = landmarks[8]
		index_pip = landmarks[6]
		dist_index_wrist = dist(index_tip, wrist)
		dist_index_pip = dist(index_pip, wrist)
		index_extended = dist_index_wrist > dist_index_pip * 1.15 and dist_index_wrist > palm_len * 0.9

		# Middle finger: must be folded compared to index
		dist_mid_wrist = dist(landmarks[12], wrist)
		middle_folded = dist_index_wrist > dist_mid_wrist * 1.15

		# Ring and pinky: folded
		ring_folded = dist(landmarks[16], wrist) < dist_index_wrist * 0.9
		pinky_folded = dist(landmarks[20], wrist) < dist_index_wrist * 0.9

		return index_extended and middle_folded and ring_folded and pinky_folded


class PlatformAdapter:
	URLS: ClassVar[dict[str, str]] = {
		"YouTube": "https://www.youtube.com/shorts",
		"TikTok": "https://www.tiktok.com/foryou",
		"Instagram": "https://www.instagram.com/reels/",
	}

	# Per-platform keyboard shortcuts for each action.
	KEY_MAP: ClassVar[dict[str, dict[str, object]]] = {
		"YouTube": {
			"next": Key.down if _keyboard else None,
			"previous": Key.up if _keyboard else None,
			"toggle_play": "k",
			"mute": "m",
		},
		"TikTok": {
			"next": Key.down if _keyboard else None,
			"previous": Key.up if _keyboard else None,
			"toggle_play": Key.space if _keyboard else None,
			"mute": "m",
		},
		"Instagram": {
			"next": Key.down if _keyboard else None,
			"previous": Key.up if _keyboard else None,
			"toggle_play": Key.space if _keyboard else None,
			"mute": "m",
		},
	}

	def __init__(self, platform: str, notify: Callable[[str], None]) -> None:
		self.platform = platform
		self.notify = notify
		self.is_playing = True

	def open_feed(self) -> None:
		webbrowser.open(self.URLS[self.platform])
		self.notify(f"{self.platform} opened in your browser")

	def _send_key(self, key: object) -> bool:
		"""Press and release a key via pynput. Returns True on success."""
		if _keyboard is None:
			self.notify("pynput not installed – keyboard control unavailable")
			return False
		try:
			_keyboard.press(key)
			_keyboard.release(key)
			return True
		except Exception as exc:  # noqa: BLE001
			self.notify(f"Key send error: {exc}")
			return False

	def perform(self, action: str) -> None:
		keys = self.KEY_MAP.get(self.platform, {})
		key = keys.get(action)
		if key is None:
			self.notify(f"No key mapping for '{action}' on {self.platform}")
			return

		if action == "toggle_play":
			self.is_playing = not self.is_playing
			label = "Paused" if not self.is_playing else "Resumed"
		else:
			label = action.replace("_", " ").title()

		if self._send_key(key):
			self.notify(label)


class CameraWorker(threading.Thread):
	MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
	MODEL_SOURCE_PATH = APP_DIR / "hand_landmarker.task"
	MODEL_PATH = Path(tempfile.gettempdir()) / "gesture_shorts" / "hand_landmarker.task"
	MODEL_HASH = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"

	FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
	FACE_MODEL_SOURCE_PATH = APP_DIR / "face_landmarker.task"
	FACE_MODEL_PATH = Path(tempfile.gettempdir()) / "gesture_shorts" / "face_landmarker.task"
	FACE_MODEL_HASH = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

	def __init__(self, settings: Settings, events: queue.Queue[GestureEvent], status: Callable[[str], None]) -> None:
		super().__init__(daemon=True)
		self.settings = settings
		self.events = events
		self.status = status
		self.stop_requested = threading.Event()

	def stop(self) -> None:
		self.stop_requested.set()

	def run(self) -> None:
		missing = []
		if cv2 is None:
			missing.append("opencv-python")
		if mp is None:
			missing.append("mediapipe")
		if missing:
			self.status(f"Missing dependency: {', '.join(missing)}. Run: pip install -r requirements.txt")
			return

		camera = None
		# On Windows, DirectShow backend initializes webcams significantly faster and more reliably
		if sys.platform.startswith("win"):
			try:
				camera = cv2.VideoCapture(self.settings.camera_index, cv2.CAP_DSHOW)
				if not camera.isOpened():
					camera.release()
					camera = None
			except Exception:  # noqa: BLE001
				camera = None

		if camera is None or not camera.isOpened():
			camera = cv2.VideoCapture(self.settings.camera_index)

		if not camera.isOpened():
			self.status("Could not open webcam")
			return

		recognizer = GestureRecognizer(self.settings, self.events.put)
		error_message: str | None = None
		try:
			# Prefer Tasks API over legacy solutions API
			if hasattr(mp, "tasks"):
				self._run_tasks(camera, recognizer)
			elif hasattr(mp, "solutions"):
				self.status("Using legacy MediaPipe: finger-on-lips mute is unavailable")
				self._run_legacy(camera, recognizer)
			else:
				self.status("MediaPipe vision tasks not found")
		except Exception as error:  # noqa: BLE001
			error_message = f"Camera gesture error: {error}"
		finally:
			camera.release()
		self.status(error_message or "Camera gestures stopped")

	def _run_legacy(self, camera: object, recognizer: GestureRecognizer) -> None:
		hands_api = mp.solutions.hands
		with hands_api.Hands(max_num_hands=1, model_complexity=0, min_detection_confidence=0.6, min_tracking_confidence=0.6) as hands:
			self._capture_loop(camera, recognizer, lambda frame: (self._detect_legacy(hands, frame), None))

	@staticmethod
	def _detect_legacy(hands: object, frame: object) -> list[object] | None:
		result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
		return result.multi_hand_landmarks[0].landmark if result.multi_hand_landmarks else None

	def _run_tasks(self, camera: object, recognizer: GestureRecognizer) -> None:
		hand_path = self._ensure_model(self.MODEL_PATH, self.MODEL_SOURCE_PATH, self.MODEL_URL, "hand", self.MODEL_HASH)
		face_path = self._ensure_model(self.FACE_MODEL_PATH, self.FACE_MODEL_SOURCE_PATH, self.FACE_MODEL_URL, "face", self.FACE_MODEL_HASH)
		vision = mp.tasks.vision
		hand_options = vision.HandLandmarkerOptions(
			base_options=mp.tasks.BaseOptions(model_asset_path=str(hand_path)),
			running_mode=vision.RunningMode.IMAGE,
			num_hands=1,
			min_hand_detection_confidence=0.6,
			min_hand_presence_confidence=0.6,
			min_tracking_confidence=0.6,
		)
		face_options = vision.FaceLandmarkerOptions(
			base_options=mp.tasks.BaseOptions(model_asset_path=str(face_path)),
			running_mode=vision.RunningMode.IMAGE,
			num_faces=1,
			min_face_detection_confidence=0.6,
			min_face_presence_confidence=0.6,
			min_tracking_confidence=0.6,
		)
		with vision.HandLandmarker.create_from_options(hand_options) as hands, vision.FaceLandmarker.create_from_options(face_options) as face:
			self._capture_loop(
				camera,
				recognizer,
				lambda frame: self._detect_tasks(hands, face, frame),
			)

	@staticmethod
	def _verify_model(path: Path, expected_hash: str | None) -> bool:
		if not path.is_file():
			return False
		try:
			if path.stat().st_size == 0:
				return False
			if expected_hash:
				hasher = hashlib.sha256()
				with open(path, "rb") as f:
					for chunk in iter(lambda: f.read(65536), b""):
						hasher.update(chunk)
				return hasher.hexdigest().lower() == expected_hash.lower()
			return True
		except OSError:
			return False

	def _ensure_model(
		self,
		dest_path: Path,
		source_path: Path,
		url: str,
		label: str,
		expected_hash: str | None = None,
	) -> Path:
		# MediaPipe C++ core on Windows cannot read file paths containing non-ASCII
		# characters (e.g. Cyrillic directory names like OneDrive/Документы).
		# If the source path is valid and purely ASCII, we can load it directly.
		# Otherwise, we stage/cache the model in the system temp directory.
		source_is_ascii = False
		try:
			str(source_path.resolve()).encode("ascii")
			source_is_ascii = True
		except (UnicodeEncodeError, OSError):
			source_is_ascii = False

		if source_path.exists() and source_is_ascii and self._verify_model(source_path, expected_hash):
			return source_path.resolve()

		# Check existing cached model
		if self._verify_model(dest_path, expected_hash):
			return dest_path

		# Clean invalid cached file if any
		if dest_path.exists():
			try:
				dest_path.unlink()
			except OSError:
				pass

		dest_path.parent.mkdir(parents=True, exist_ok=True)
		part_path = dest_path.with_suffix(dest_path.suffix + ".part")
		if part_path.exists():
			try:
				part_path.unlink()
			except OSError:
				pass

		self.status(f"Preparing {label} model...")
		if source_path.exists() and self._verify_model(source_path, expected_hash):
			shutil.copyfile(source_path, part_path)
		else:
			# Download with timeout and integrity check
			with urllib.request.urlopen(url, timeout=30.0) as response, open(part_path, "wb") as out_file:
				shutil.copyfileobj(response, out_file)

		if not self._verify_model(part_path, expected_hash):
			if part_path.exists():
				part_path.unlink()
			raise RuntimeError(f"Downloaded/copied {label} model failed integrity verification")

		os.replace(part_path, dest_path)
		return dest_path

	@staticmethod
	def _detect_tasks(
		hands: object,
		face: object,
		frame: object,
	) -> tuple[list[object] | None, tuple[float, float] | None]:
		image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
		hand_result = hands.detect(image)
		face_result = face.detect(image)
		mouth_position = None
		if face_result.face_landmarks:
			mouth = face_result.face_landmarks[0]
			mouth_position = ((mouth[13].x + mouth[14].x) / 2, (mouth[13].y + mouth[14].y) / 2)
		return (hand_result.hand_landmarks[0] if hand_result.hand_landmarks else None, mouth_position)

	def _capture_loop(
		self,
		camera: object,
		recognizer: GestureRecognizer,
		detect: Callable[[object], tuple[list[object] | None, tuple[float, float] | None]],
	) -> None:
		interval = 1 / max(1, self.settings.camera_fps)
		self.status("Camera gestures active")
		while not self.stop_requested.is_set():
			started = time.monotonic()
			ok, frame = camera.read()
			if ok:
				h, w = frame.shape[:2]
				recognizer.set_aspect_ratio(float(w) / float(max(1, h)))
				landmarks, mouth_position = detect(cv2.flip(frame, 1))
				if landmarks:
					recognizer.update(landmarks, mouth_position)
				else:
					recognizer.flush()
			delay = interval - (time.monotonic() - started)
			if delay > 0:
				self.stop_requested.wait(delay)


class PiPApp:
	def __init__(self, root: Tk) -> None:
		self.root = root
		self.settings = Settings.load()
		self.events: queue.Queue[GestureEvent] = queue.Queue()
		self.status_queue: queue.Queue[str] = queue.Queue()
		self.platform = "YouTube"
		self.adapter = PlatformAdapter(self.platform, self.show_status)
		self.camera: CameraWorker | None = None
		self.status_var = StringVar(value="Ready")
		self.build_ui()
		self.root.after(80, self.process_events)
		self.root.protocol("WM_DELETE_WINDOW", self.close)

	def build_ui(self) -> None:
		self.root.title("Gesture Shorts")
		self.root.geometry(f"{self.settings.pip_width}x{self.settings.pip_height}")
		self.root.minsize(300, 480)
		self.root.configure(bg="#111318")
		self.root.attributes("-topmost", True)

		toolbar = Frame(self.root, bg="#1d2028")
		toolbar.pack(fill=X)
		Label(toolbar, text="GESTURE SHORTS", fg="#f3f4f6", bg="#1d2028", font=("Segoe UI", 10, "bold")).pack(side=LEFT, padx=12, pady=10)
		Button(toolbar, text="Open feed", command=lambda: self.adapter.open_feed(), bg="#2b303a", fg="#f3f4f6", relief="flat").pack(side=RIGHT, padx=8, pady=7)

		self.canvas = Canvas(self.root, bg="#08090c", highlightthickness=0)
		self.canvas.pack(fill=BOTH, expand=True)
		self.canvas.create_text(180, 230, text="Choose a platform,\nthen open its feed", fill="#a9b0bd", font=("Segoe UI", 15), justify="center")
		self.canvas.create_text(180, 285, text="Camera gestures control this window", fill="#606875", font=("Segoe UI", 9))

		controls = Frame(self.root, bg="#1d2028")
		controls.pack(fill=X)
		for name in PlatformAdapter.URLS:
			Button(controls, text=name, command=lambda selected=name: self.select_platform(selected), bg="#2b303a", fg="#f3f4f6", relief="flat").pack(side=LEFT, padx=(8 if name == "YouTube" else 2, 2), pady=8)
		self.camera_btn = Button(controls, text="Start camera", command=self.toggle_camera, bg="#2f6f5e", fg="white", relief="flat")
		self.camera_btn.pack(side=RIGHT, padx=8, pady=8)
		Label(self.root, textvariable=self.status_var, anchor="w", bg="#111318", fg="#a9b0bd", font=("Segoe UI", 9)).pack(fill=X, padx=10, pady=7)

	def select_platform(self, platform: str) -> None:
		self.platform = platform
		self.adapter = PlatformAdapter(platform, self.show_status)
		self.show_status(f"Selected {platform}")

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

		self.camera = CameraWorker(self.settings, self.events, self.show_status)
		self.camera.start()
		self.camera_btn.config(text="Stop camera", bg="#8a3030")

	def process_events(self) -> None:
		try:
			# Drain thread-safe status updates
			while True:
				try:
					msg = self.status_queue.get_nowait()
					if msg == "__CAMERA_STOPPED__":
						self.camera_btn.config(state="normal", text="Start camera", bg="#2f6f5e")
					else:
						self.status_var.set(msg)
				except queue.Empty:
					break

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
					self.adapter.perform(action)
				except Exception as exc:  # noqa: BLE001
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


def main() -> None:
	root = Tk()
	PiPApp(root)
	root.mainloop()


if __name__ == "__main__":
	main()
