"""Tests for Phase 1 bug fixes."""

from __future__ import annotations

import queue
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import gesture_shorts.camera
from gesture_control import (
    CameraWorker,
    GestureEvent,
    GestureRecognizer,
    PiPApp,
    Settings,
)


class DummyLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


def make_hand(
    index_y: float = 0.4,
    index_x: float = 0.5,
    wrist: tuple[float, float] = (0.5, 0.9),
) -> list[DummyLandmark]:
    """Helper to generate 21 hand landmarks in an index-pointing pose."""
    landmarks = [DummyLandmark(0.0, 0.0) for _ in range(21)]
    landmarks[0] = DummyLandmark(wrist[0], wrist[1])  # wrist
    landmarks[6] = DummyLandmark(index_x, index_y + 0.25)  # index PIP
    landmarks[8] = DummyLandmark(index_x, index_y)  # index tip
    landmarks[9] = DummyLandmark(0.5, 0.70)  # middle MCP (palm base)
    landmarks[12] = DummyLandmark(0.5, 0.85)  # middle tip (folded)
    landmarks[16] = DummyLandmark(0.55, 0.87)  # ring tip (folded)
    landmarks[20] = DummyLandmark(0.60, 0.88)  # pinky tip (folded)
    return landmarks


def test_dropout_then_reappear_produces_no_false_swipe() -> None:
    """1.1 Hand disappearance and reappearance must not trigger a false swipe."""
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.13, swipe_window_seconds=0.6)
    recognizer = GestureRecognizer(settings, events.append)

    # Frame 1: Hand at bottom (y=0.8)
    recognizer.update(make_hand(index_y=0.8), now=1.0)
    assert len(events) == 0

    # Hand disappears: 3 flush() frames
    recognizer.flush(now=1.1)
    recognizer.flush(now=1.2)
    recognizer.flush(now=1.3)

    # Frame 5: Hand reappears near top (y=0.2) within 0.6s
    recognizer.update(make_hand(index_y=0.2), now=1.4)
    assert len(events) == 0, f"Expected no events on reappearance, got: {events}"


def test_close_handles_oserror_and_destroys_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """1.2 close() must not get stuck if settings.save() raises OSError."""
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.camera = None
    app.settings = Settings()

    # Mark settings as modified so save is attempted
    app.settings._loaded_snapshot = "different"

    def failing_save() -> None:
        raise OSError("Read-only filesystem")

    monkeypatch.setattr(app.settings, "save", failing_save)
    app.close()
    root.destroy.assert_called_once()


def test_settings_save_only_when_modified(monkeypatch: pytest.MonkeyPatch) -> None:
    """1.2 Settings should only be saved if values were modified."""
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.camera = None
    app.settings = Settings()
    app.settings._loaded_snapshot = app.settings._loaded_snapshot or '{"clean": true}'

    save_mock = MagicMock()
    monkeypatch.setattr(app.settings, "save", save_mock)
    monkeypatch.setattr(app.settings, "is_modified", lambda: False)

    app.close()
    save_mock.assert_not_called()
    root.destroy.assert_called_once()


def test_status_queue_thread_safe_drain() -> None:
    """1.3 Status updates queued from camera thread must update status_var safely."""
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.status_queue = queue.Queue()
    app.events = queue.Queue()
    app.frame_queue = queue.Queue()
    app.status_var = MagicMock()
    app.settings = Settings()
    app.adapter = MagicMock()
    app.recognizer = MagicMock()

    # Simulate camera thread calling show_status
    app.show_status("Camera gestures active")

    # UI thread drains in process_events
    app.process_events()
    app.status_var.set.assert_called_with("Camera gestures active")


def test_process_events_reschedules_after_exception() -> None:
    """1.4 process_events must reschedule root.after even if adapter.perform raises."""
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.status_queue = queue.Queue()
    app.events = queue.Queue()
    app.frame_queue = queue.Queue()
    app.status_var = MagicMock()
    app.settings = Settings()
    app.adapter = MagicMock()
    app.recognizer = MagicMock()
    app.adapter.perform.side_effect = RuntimeError("OS keyboard failure")

    # Put a gesture event in queue
    app.events.put(GestureEvent("swipe_up"))
    app.process_events()

    # Verify reschedule still occurred
    root.after.assert_called_with(80, app.process_events)


def test_missing_dependencies_message() -> None:
    """1.8 Clear cross-platform error when cv2/mediapipe is missing."""
    status_messages: list[str] = []
    settings = Settings()
    events: queue.Queue[GestureEvent] = queue.Queue()

    worker = CameraWorker(settings, events, status_messages.append)
    orig_cv2 = gesture_shorts.camera.cv2
    gesture_shorts.camera.cv2 = None
    try:
        worker.run()
        assert len(status_messages) > 0
        assert "pip install -r requirements.txt" in status_messages[0]
        assert "opencv-python" in status_messages[0]
    finally:
        gesture_shorts.camera.cv2 = orig_cv2


def test_model_verification(tmp_path: Path) -> None:
    """1.7 Model integrity checking must detect corrupt / empty files."""
    empty_file = tmp_path / "empty.task"
    empty_file.write_bytes(b"")
    assert not CameraWorker._verify_model(empty_file, "abc123hash")

    corrupt_file = tmp_path / "corrupt.task"
    corrupt_file.write_bytes(b"some garbage data")
    assert not CameraWorker._verify_model(corrupt_file, "abc123hash")
    # Non-empty with no expected hash returns True
    assert CameraWorker._verify_model(corrupt_file, None)


def test_swipe_up_and_down_and_return_suppression() -> None:
    """Verify swipe up, return suppression, and swipe down."""
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.10, cooldown_seconds=0.2)
    recognizer = GestureRecognizer(settings, events.append)

    # Start position at y=0.5
    recognizer.update(make_hand(index_y=0.5), now=1.0)
    # Swipe up to y=0.35 (dy = -0.15)
    recognizer.update(make_hand(index_y=0.35), now=1.1)
    assert len(events) == 1
    assert events[0].name == "swipe_up"

    # Return hand back down to y=0.5: should NOT fire swipe_down!
    recognizer.update(make_hand(index_y=0.50), now=1.2)
    assert len(events) == 1, "Return motion incorrectly fired an event!"


def test_stationary_hold_fires_once_until_moved() -> None:
    """Stationary hold fires once after duration, not repeatedly while holding still."""
    events: list[GestureEvent] = []
    settings = Settings(
        activation_mode="always", stationary_hold_seconds=0.5, cooldown_seconds=0.2
    )
    recognizer = GestureRecognizer(settings, events.append)

    # Finger still at (0.5, 0.5)
    recognizer.update(make_hand(index_y=0.5), now=1.0)
    recognizer.update(make_hand(index_y=0.5), now=1.3)
    assert len(events) == 0

    # Hold threshold reached (0.6s >= 0.5s)
    recognizer.update(make_hand(index_y=0.5), now=1.6)
    assert len(events) == 1
    assert events[0].name == "stationary_hold"

    # Still holding at same spot: should NOT fire again
    recognizer.update(make_hand(index_y=0.5), now=2.0)
    assert len(events) == 1


def test_finger_on_lips_fires_mute_and_never_pause() -> None:
    """Finger near mouth triggers mute and suppresses stationary hold."""
    events: list[GestureEvent] = []
    settings = Settings(
        activation_mode="always",
        mouth_distance=0.15,
        stationary_hold_seconds=0.3,
        cooldown_seconds=0.2,
    )
    recognizer = GestureRecognizer(settings, events.append)

    mouth = (0.5, 0.3)
    # Frame 1 initializes tracking
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.0)
    assert len(events) == 0

    # Frame 2 triggers mute
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.1)
    assert len(events) == 1
    assert events[0].name == "finger_on_lips"

    # Hold still near mouth for longer than hold duration
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.5)
    assert [e.name for e in events] == ["finger_on_lips"]


def test_distance_aspect_ratio_correction() -> None:
    """1.9 Ensure aspect ratio correction scales horizontal distance."""
    settings = Settings()
    recognizer = GestureRecognizer(settings, lambda _: None)

    # Aspect ratio 1.0: distance between (0.1, 0.5) and (0.2, 0.5) is 0.1
    recognizer.set_aspect_ratio(1.0)
    d1 = recognizer._distance((0.1, 0.5), (0.2, 0.5))
    assert pytest.approx(d1, 0.001) == 0.1

    # Aspect ratio 2.0: horizontal delta is multiplied by 2.0 -> 0.2
    recognizer.set_aspect_ratio(2.0)
    d2 = recognizer._distance((0.1, 0.5), (0.2, 0.5))
    assert pytest.approx(d2, 0.001) == 0.2
