"""Test and benchmark face landmarker conditional execution optimization (Phase 3.4)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from gesture_shorts.camera import CameraWorker
from gesture_shorts.recognizer import GestureRecognizer
from gesture_shorts.settings import Settings


class MockLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


def make_hand_at_y(tip_y: float) -> list[MockLandmark]:
    landmarks = [MockLandmark(0.0, 0.0) for _ in range(21)]
    landmarks[0] = MockLandmark(0.5, 0.9)  # wrist
    landmarks[6] = MockLandmark(0.5, tip_y + 0.2)  # pip
    landmarks[8] = MockLandmark(0.5, tip_y)  # tip
    landmarks[9] = MockLandmark(0.5, 0.7)  # palm
    landmarks[12] = MockLandmark(0.5, 0.85)  # middle folded
    landmarks[16] = MockLandmark(0.55, 0.85)  # ring folded
    landmarks[20] = MockLandmark(0.6, 0.85)  # pinky folded
    return landmarks


def test_face_model_only_called_when_hand_in_upper_area() -> None:
    settings = Settings()
    worker = CameraWorker.__new__(CameraWorker)
    worker.recognizer = GestureRecognizer(settings, lambda _: None)
    worker._cached_mouth = None
    worker._mouth_cache_ttl = 0

    mock_hands = MagicMock()
    mock_face = MagicMock()

    # Configure mock return values
    hand_ret = MagicMock()
    # Hand at lower area: y = 0.85 (> 0.65)
    hand_ret.hand_landmarks = [make_hand_at_y(0.85)]
    mock_hands.detect.return_value = hand_ret

    # In lower area, face detect should NOT be called
    import numpy as np

    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    landmarks, mouth = worker._detect_tasks_optimized(mock_hands, mock_face, fake_frame)
    assert landmarks is not None
    assert mouth is None
    mock_face.detect.assert_not_called()

    # Move hand to upper area: y = 0.30 (<= 0.65)
    hand_ret.hand_landmarks = [make_hand_at_y(0.30)]
    face_ret = MagicMock()
    face_landmarks_mock = [MockLandmark(0.5, 0.3) for _ in range(20)]
    face_ret.face_landmarks = [face_landmarks_mock]
    mock_face.detect.return_value = face_ret

    landmarks, mouth = worker._detect_tasks_optimized(mock_hands, mock_face, fake_frame)
    assert landmarks is not None
    assert mouth is not None
    mock_face.detect.assert_called_once()


def test_benchmark_face_optimization_savings() -> None:
    """Benchmark the call count and execution savings between unoptimized and optimized paths."""
    settings = Settings()
    worker = CameraWorker.__new__(CameraWorker)
    worker.recognizer = GestureRecognizer(settings, lambda _: None)
    worker._cached_mouth = None
    worker._mouth_cache_ttl = 0

    mock_hands = MagicMock()
    mock_face = MagicMock()

    # Simulate 50 frames with simulated face detection workload (e.g. 5ms per call)
    def simulated_face_detect(_):
        time.sleep(0.002)
        ret = MagicMock()
        ret.face_landmarks = [[MockLandmark(0.5, 0.3) for _ in range(20)]]
        return ret

    mock_face.detect.side_effect = simulated_face_detect

    import numpy as np

    fake_frame = np.zeros((64, 64, 3), dtype=np.uint8)

    # 1. Unoptimized: runs every frame regardless of hand pose
    unoptimized_calls = 0
    t0 = time.perf_counter()
    for _ in range(30):
        # Always call face
        mock_face.detect(fake_frame)
        unoptimized_calls += 1
    unoptimized_time = time.perf_counter() - t0

    # 2. Optimized: only runs when hand is in upper frame (e.g. 20% of the time)
    mock_face.reset_mock()
    hand_lower = MagicMock()
    hand_lower.hand_landmarks = [make_hand_at_y(0.85)]
    hand_upper = MagicMock()
    hand_upper.hand_landmarks = [make_hand_at_y(0.25)]

    t1 = time.perf_counter()
    for i in range(30):
        # 80% frames in lower/neutral, 20% near face
        mock_hands.detect.return_value = hand_upper if (i % 5 == 0) else hand_lower
        worker._detect_tasks_optimized(mock_hands, mock_face, fake_frame)
    optimized_time = time.perf_counter() - t1

    optimized_calls = mock_face.detect.call_count

    # Optimized calls must be dramatically lower
    assert optimized_calls < unoptimized_calls
    # Time must be significantly faster
    assert optimized_time < unoptimized_time
