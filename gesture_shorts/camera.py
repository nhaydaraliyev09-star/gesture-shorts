"""Camera capture worker, MediaPipe pipeline, and model management."""

from __future__ import annotations

import hashlib
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gesture_shorts.recognizer import GestureEvent, GestureRecognizer
from gesture_shorts.settings import Settings

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import mediapipe as mp
except ImportError:
    mp = None

APP_DIR = Path(__file__).resolve().parent.parent


def detect_available_cameras(max_test: int = 4) -> list[int]:
    """Test video capture indices and return list of working camera IDs."""
    if cv2 is None:
        return [0]
    available: list[int] = []
    for idx in range(max_test):
        cap = None
        try:
            if sys.platform.startswith("win"):
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap is None or not cap.isOpened():
                if cap is not None:
                    cap.release()
                cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                available.append(idx)
                cap.release()
        except Exception:
            if cap is not None:
                cap.release()
    return available or [0]


class CameraWorker(threading.Thread):
    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
    MODEL_SOURCE_PATH = APP_DIR / "hand_landmarker.task"
    MODEL_PATH = Path(tempfile.gettempdir()) / "gesture_shorts" / "hand_landmarker.task"
    MODEL_HASH = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"

    FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    FACE_MODEL_SOURCE_PATH = APP_DIR / "face_landmarker.task"
    FACE_MODEL_PATH = Path(tempfile.gettempdir()) / "gesture_shorts" / "face_landmarker.task"
    FACE_MODEL_HASH = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

    def __init__(
        self,
        settings: Settings,
        events: queue.Queue[GestureEvent],
        status: Callable[[str], None],
        on_frame: Callable[[Any, list[Any] | None, tuple[float, float] | None], None] | None = None,
        recognizer: GestureRecognizer | None = None,
    ) -> None:
        super().__init__(daemon=True)
        self.settings = settings
        self.events = events
        self.status = status
        self.on_frame = on_frame
        self.stop_requested = threading.Event()
        self.recognizer = recognizer or GestureRecognizer(self.settings, self.events.put)

        # Mouth caching optimization (Phase 3.4)
        self._cached_mouth: tuple[float, float] | None = None
        self._mouth_cache_ttl: int = 0

    def stop(self) -> None:
        self.stop_requested.set()

    def run(self) -> None:
        missing = []
        if cv2 is None:
            missing.append("opencv-python")
        if mp is None:
            missing.append("mediapipe")
        if missing:
            self.status(
                f"Missing dependency: {', '.join(missing)}. Run: pip install -r requirements.txt"
            )
            return

        camera = None
        # On Windows, try DirectShow backend first for fast, reliable hardware initialization
        if sys.platform.startswith("win"):
            try:
                camera = cv2.VideoCapture(self.settings.camera_index, cv2.CAP_DSHOW)
                if not camera.isOpened():
                    camera.release()
                    camera = None
            except Exception:
                camera = None

        if camera is None or not camera.isOpened():
            camera = cv2.VideoCapture(self.settings.camera_index)

        if not camera.isOpened():
            self.status("Could not open webcam")
            return

        error_message: str | None = None
        try:
            if hasattr(mp, "tasks"):
                self._run_tasks(camera)
            elif hasattr(mp, "solutions"):
                self.status("Using legacy MediaPipe: finger-on-lips mute is unavailable")
                self._run_legacy(camera)
            else:
                self.status("MediaPipe vision tasks not found")
        except Exception as error:
            error_message = f"Camera gesture error: {error}"
        finally:
            camera.release()
        self.status(error_message or "Camera gestures stopped")

    def _run_legacy(self, camera: Any) -> None:
        hands_api = mp.solutions.hands
        with hands_api.Hands(
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        ) as hands:
            self._capture_loop(
                camera,
                lambda frame: (self._detect_legacy(hands, frame), None),
            )

    @staticmethod
    def _detect_legacy(hands: Any, frame: Any) -> list[Any] | None:
        result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return result.multi_hand_landmarks[0].landmark if result.multi_hand_landmarks else None

    def _run_tasks(self, camera: Any) -> None:
        hand_path = self._ensure_model(
            self.MODEL_PATH, self.MODEL_SOURCE_PATH, self.MODEL_URL, "hand", self.MODEL_HASH
        )
        face_path = self._ensure_model(
            self.FACE_MODEL_PATH,
            self.FACE_MODEL_SOURCE_PATH,
            self.FACE_MODEL_URL,
            "face",
            self.FACE_MODEL_HASH,
        )
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
        with (
            vision.HandLandmarker.create_from_options(hand_options) as hands,
            vision.FaceLandmarker.create_from_options(face_options) as face,
        ):
            self._capture_loop(
                camera,
                lambda frame: self._detect_tasks_optimized(hands, face, frame),
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

        if (
            source_path.exists()
            and source_is_ascii
            and self._verify_model(source_path, expected_hash)
        ):
            return source_path.resolve()

        if self._verify_model(dest_path, expected_hash):
            return dest_path

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
            with (
                urllib.request.urlopen(url, timeout=30.0) as response,
                open(part_path, "wb") as out_file,
            ):
                shutil.copyfileobj(response, out_file)

        if not self._verify_model(part_path, expected_hash):
            if part_path.exists():
                part_path.unlink()
            raise RuntimeError(f"Downloaded/copied {label} model failed integrity verification")

        os.replace(part_path, dest_path)
        return dest_path

    def _detect_tasks_optimized(
        self,
        hands: Any,
        face: Any,
        frame: Any,
    ) -> tuple[list[Any] | None, tuple[float, float] | None]:
        """Detect hands and conditionally detect face/mouth only when needed (Phase 3.4)."""
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        hand_result = hands.detect(image)
        landmarks = hand_result.hand_landmarks[0] if hand_result.hand_landmarks else None

        mouth_position = None
        # Phase 3.4: Only run face landmarker if hand is in index pose with fingertip in upper ~60%
        needs_mouth = False
        if landmarks and len(landmarks) >= 21:
            index_tip = landmarks[8]
            is_index = GestureRecognizer._is_index_only(landmarks, self.recognizer.aspect_ratio)
            if is_index and float(index_tip.y) <= 0.65:
                needs_mouth = True

        if needs_mouth:
            face_result = face.detect(image)
            if face_result.face_landmarks:
                mouth = face_result.face_landmarks[0]
                mouth_position = (
                    (mouth[13].x + mouth[14].x) / 2,
                    (mouth[13].y + mouth[14].y) / 2,
                )
                self._cached_mouth = mouth_position
                self._mouth_cache_ttl = 5
            elif self._mouth_cache_ttl > 0:
                self._mouth_cache_ttl -= 1
                mouth_position = self._cached_mouth
        elif self._mouth_cache_ttl > 0:
            self._mouth_cache_ttl -= 1
            mouth_position = self._cached_mouth

        return landmarks, mouth_position

    def _capture_loop(
        self,
        camera: Any,
        detect: Callable[[Any], tuple[list[Any] | None, tuple[float, float] | None]],
    ) -> None:
        interval = 1 / max(1, self.settings.camera_fps)
        self.status("Camera gestures active")
        while not self.stop_requested.is_set():
            started = time.monotonic()
            ok, frame = camera.read()
            if ok:
                h, w = frame.shape[:2]
                self.recognizer.set_aspect_ratio(float(w) / float(max(1, h)))
                flipped = cv2.flip(frame, 1)
                landmarks, mouth_position = detect(flipped)
                if landmarks:
                    self.recognizer.update(landmarks, mouth_position)
                else:
                    self.recognizer.flush()

                if on_frame := self.on_frame:
                    on_frame(flipped, landmarks, mouth_position)

            delay = interval - (time.monotonic() - started)
            if delay > 0:
                self.stop_requested.wait(delay)
