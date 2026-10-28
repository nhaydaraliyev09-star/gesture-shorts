"""Tests for GestureRecognizer state machine and synthetic landmarks."""

from __future__ import annotations

from gesture_shorts.recognizer import GestureEvent, GestureRecognizer
from gesture_shorts.settings import Settings


class SyntheticLandmark:
    def __init__(self, x: float, y: float, z: float = 0.0) -> None:
        self.x = x
        self.y = y
        self.z = z


def make_hand(
    index_y: float = 0.4,
    index_x: float = 0.5,
    wrist: tuple[float, float] = (0.5, 0.9),
) -> list[SyntheticLandmark]:
    """Helper to generate 21 hand landmarks in an index-pointing pose."""
    landmarks = [SyntheticLandmark(0.0, 0.0) for _ in range(21)]
    landmarks[0] = SyntheticLandmark(wrist[0], wrist[1])  # wrist
    landmarks[6] = SyntheticLandmark(index_x, index_y + 0.25)  # index PIP
    landmarks[8] = SyntheticLandmark(index_x, index_y)  # index tip
    landmarks[9] = SyntheticLandmark(0.5, 0.70)  # middle MCP (palm base)
    landmarks[12] = SyntheticLandmark(0.5, 0.85)  # middle tip (folded)
    landmarks[16] = SyntheticLandmark(0.55, 0.87)  # ring tip (folded)
    landmarks[20] = SyntheticLandmark(0.60, 0.88)  # pinky tip (folded)
    return landmarks


def make_open_palm(wrist: tuple[float, float] = (0.5, 0.9)) -> list[SyntheticLandmark]:
    """Helper to generate 21 hand landmarks in an open-palm pose."""
    landmarks = [SyntheticLandmark(0.0, 0.0) for _ in range(21)]
    landmarks[0] = SyntheticLandmark(wrist[0], wrist[1])
    landmarks[9] = SyntheticLandmark(0.5, 0.70)  # palm base

    # All 4 fingers extended upwards
    landmarks[6] = SyntheticLandmark(0.40, 0.60)
    landmarks[8] = SyntheticLandmark(0.40, 0.35)  # index

    landmarks[10] = SyntheticLandmark(0.47, 0.58)
    landmarks[12] = SyntheticLandmark(0.47, 0.30)  # middle

    landmarks[14] = SyntheticLandmark(0.53, 0.60)
    landmarks[16] = SyntheticLandmark(0.53, 0.35)  # ring

    landmarks[18] = SyntheticLandmark(0.60, 0.65)
    landmarks[20] = SyntheticLandmark(0.60, 0.45)  # pinky
    return landmarks


def test_swipe_up_and_down_events() -> None:
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.10, cooldown_seconds=0.2)
    recognizer = GestureRecognizer(settings, events.append)

    # Frame 1: start at y=0.60
    recognizer.update(make_hand(index_y=0.60), now=1.0)
    assert len(events) == 0

    # Swipe up to y=0.45 (dy = -0.15)
    recognizer.update(make_hand(index_y=0.45), now=1.1)
    assert len(events) == 1
    assert events[0].name == "swipe_up"

    # Wait past return suppression window (0.85s)
    now = 2.05
    # Frame at y=0.30
    recognizer.update(make_hand(index_y=0.30), now=now)
    # Swipe down to y=0.55 (dy = +0.25)
    recognizer.update(make_hand(index_y=0.55), now=now + 0.1)
    assert len(events) == 2
    assert events[1].name == "swipe_down"


def test_return_motion_after_swipe_suppressed() -> None:
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.10, cooldown_seconds=0.1)
    recognizer = GestureRecognizer(settings, events.append)

    # Swipe down from y=0.30 to y=0.55
    recognizer.update(make_hand(index_y=0.30), now=1.0)
    recognizer.update(make_hand(index_y=0.55), now=1.1)
    assert len(events) == 1
    assert events[0].name == "swipe_down"

    # Moving hand back up to y=0.30 within suppression window should NOT fire swipe_up
    recognizer.update(make_hand(index_y=0.30), now=1.25)
    assert len(events) == 1


def test_stationary_hold_fires_once_until_hand_moves() -> None:
    events: list[GestureEvent] = []
    settings = Settings(
        activation_mode="always", stationary_hold_seconds=0.4, cooldown_seconds=0.2
    )
    recognizer = GestureRecognizer(settings, events.append)

    # Hold still at (0.5, 0.5)
    recognizer.update(make_hand(index_y=0.5), now=1.0)
    recognizer.update(make_hand(index_y=0.5), now=1.2)
    assert len(events) == 0

    # Hold threshold crossed (0.5s > 0.4s)
    recognizer.update(make_hand(index_y=0.5), now=1.5)
    assert len(events) == 1
    assert events[0].name == "stationary_hold"

    # Hand remains still: must NOT fire again
    recognizer.update(make_hand(index_y=0.5), now=1.8)
    recognizer.update(make_hand(index_y=0.5), now=2.2)
    assert len(events) == 1

    # Hand moves beyond stationary jitter radius
    recognizer.update(make_hand(index_y=0.7), now=2.5)
    # Re-settles at new location
    recognizer.update(make_hand(index_y=0.7), now=3.0)
    assert len(events) == 2
    assert events[1].name == "stationary_hold"


def test_finger_on_lips_fires_mute_and_never_pause() -> None:
    events: list[GestureEvent] = []
    settings = Settings(
        activation_mode="always",
        mouth_distance=0.15,
        stationary_hold_seconds=0.3,
        cooldown_seconds=0.2,
    )
    recognizer = GestureRecognizer(settings, events.append)

    mouth = (0.5, 0.3)
    # Init hand near mouth
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.0)
    # Frame 2 fires mute
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.1)
    assert len(events) == 1
    assert events[0].name == "finger_on_lips"

    # Hold still near mouth for long period: stationary_hold must never fire
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=1.6)
    recognizer.update(make_hand(index_y=0.32), mouth_position=mouth, now=2.0)
    assert [e.name for e in events] == ["finger_on_lips"]


def test_dropout_then_reappear_produces_no_event() -> None:
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.13)
    recognizer = GestureRecognizer(settings, events.append)

    # Hand at bottom (y=0.85)
    recognizer.update(make_hand(index_y=0.85), now=1.0)

    # 3 lost frames
    recognizer.flush(now=1.1)
    recognizer.flush(now=1.2)
    recognizer.flush(now=1.3)

    # Hand reappears at top (y=0.20)
    recognizer.update(make_hand(index_y=0.20), now=1.4)
    assert len(events) == 0


def test_cooldown_is_respected() -> None:
    events: list[GestureEvent] = []
    settings = Settings(activation_mode="always", swipe_threshold=0.10, cooldown_seconds=0.5)
    recognizer = GestureRecognizer(settings, events.append)

    recognizer.update(make_hand(index_y=0.6), now=1.0)
    recognizer.update(make_hand(index_y=0.4), now=1.1)  # Swipe up
    assert len(events) == 1

    # Attempt another swipe during cooldown period (now=1.3 < 1.1 + 0.5)
    recognizer.update(make_hand(index_y=0.6), now=1.25)
    recognizer.update(make_hand(index_y=0.4), now=1.35)
    assert len(events) == 1, "Gesture fired during cooldown period!"


def test_open_palm_activation_pose() -> None:
    events: list[GestureEvent] = []
    arm_states: list[bool] = []
    settings = Settings(activation_mode="pose")
    recognizer = GestureRecognizer(settings, events.append, on_arm_change=arm_states.append)

    assert not recognizer.is_armed

    palm = make_open_palm()
    # Hold open palm for 1.0 second to arm
    recognizer.update(palm, now=1.0)
    recognizer.update(palm, now=1.5)
    assert not recognizer.is_armed

    recognizer.update(palm, now=2.1)
    assert recognizer.is_armed
    assert arm_states == [True]


def test_auto_disarm_after_inactivity() -> None:
    events: list[GestureEvent] = []
    arm_states: list[bool] = []
    settings = Settings(activation_mode="pose", auto_disarm_seconds=5.0)
    recognizer = GestureRecognizer(settings, events.append, on_arm_change=arm_states.append)

    recognizer.set_armed(True)
    recognizer.last_gesture_time = 1.0

    # Hand update after 6 seconds of inactivity -> auto-disarmed
    recognizer.update(make_hand(index_y=0.5), now=7.5)
    assert not recognizer.is_armed
