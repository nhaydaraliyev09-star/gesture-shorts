"""Gesture recognition state machine and events.

This module has NO dependencies on Tkinter, OpenCV, or MediaPipe.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gesture_shorts.settings import Settings


@dataclass(frozen=True)
class GestureEvent:
    name: str
    confidence: float = 1.0


class GestureRecognizer:
    """Index-finger and activation pose state machine.

    Supports:
    - 1-finger pointing (navigation swipe up/down, stationary hold play/pause)
    - Finger near mouth (mute)
    - Open-palm activation pose (arm/disarm)
    """

    def __init__(
        self,
        settings: Settings,
        emit: Callable[[GestureEvent], None],
        on_arm_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.settings = settings
        self.emit = emit
        self.on_arm_change = on_arm_change
        self.aspect_ratio: float = 1.0

        # Motion & gesture tracking
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

        # Activation (arm / disarm) state
        self.is_armed: bool = settings.activation_mode == "always"
        self.last_gesture_time: float = time.monotonic()
        self._palm_since: float | None = None
        self._palm_cooldown_until: float = 0.0

        # State reporting for preview overlay
        self.current_pose_name: str = "no hand"

    def set_aspect_ratio(self, ratio: float) -> None:
        self.aspect_ratio = max(0.1, ratio)

    def _distance(self, p1: tuple[float, float], p2: tuple[float, float]) -> float:
        dx = (p1[0] - p2[0]) * self.aspect_ratio
        dy = p1[1] - p2[1]
        return math.hypot(dx, dy)

    def set_armed(self, armed: bool) -> None:
        if self.settings.activation_mode == "always":
            self.is_armed = True
            return
        if self.is_armed != armed:
            self.is_armed = armed
            if on_change := self.on_arm_change:
                on_change(self.is_armed)

    def get_hold_progress(self, now: float | None = None) -> float:
        """Returns progress of current stationary hold (0.0 to 1.0)."""
        now = time.monotonic() if now is None else now
        if self.stationary_since is None or self.stationary_fired:
            return 0.0
        hold_time = self.settings.stationary_hold_seconds
        if hold_time <= 0:
            return 1.0
        elapsed = now - self.stationary_since
        return max(0.0, min(1.0, elapsed / hold_time))

    def update(
        self,
        landmarks: list[Any],
        mouth_position: tuple[float, float] | None = None,
        now: float | None = None,
    ) -> None:
        now = time.monotonic() if now is None else now

        # Auto-disarm check in pose mode
        if self.settings.activation_mode == "pose" and self.is_armed:
            if (now - self.last_gesture_time) > self.settings.auto_disarm_seconds:
                self.set_armed(False)

        # Check for open palm activation pose (arm/disarm toggle)
        if self._is_open_palm(landmarks, self.aspect_ratio):
            self.current_pose_name = "palm pose"
            self._lost_frames = 0
            if self.settings.activation_mode == "pose":
                if self._palm_since is None:
                    self._palm_since = now
                elif (now - self._palm_since) >= 1.0 and now >= self._palm_cooldown_until:
                    # Toggle armed state
                    self.set_armed(not self.is_armed)
                    self._palm_cooldown_until = now + 1.5
                    self.last_gesture_time = now
                    self._reset_finger_state()
            return

        self._palm_since = None

        if not self._is_index_only(landmarks, self.aspect_ratio):
            self.current_pose_name = "hand"
            self._lost_frames += 1
            if self._lost_frames > 2:
                self._reset_finger_state()
            return

        self.current_pose_name = "index pose"
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

        # If not armed, do not fire any navigation or play/mute gestures
        if not self.is_armed:
            self.last_position = position
            return

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
                    self.last_gesture_time = now
            elif dist_to_mouth > self.settings.mouth_distance * 1.35:
                self.mute_fired = False

        # --- 2. SWIPE DETECTION (Moving UP or DOWN) ---
        if not is_near_mouth:
            elapsed = now - self.started_at
            dx = (position[0] - self.start_position[0]) * self.aspect_ratio
            dy = position[1] - self.start_position[1]

            if (
                elapsed <= self.settings.swipe_window_seconds
                and abs(dy) >= self.settings.swipe_threshold
            ):
                if now >= self.cooldown_until and abs(dy) > abs(dx) * 1.1:
                    swipe_dir = "swipe_up" if dy < 0 else "swipe_down"
                    opposite_dir = "swipe_down" if dy < 0 else "swipe_up"

                    if self._suppress_swipe != swipe_dir:
                        self._fire(swipe_dir, now)
                        self.last_gesture_time = now
                        self._suppress_swipe = opposite_dir
                        self._suppress_until = now + 0.85
                        self.start_position = position
                        self.started_at = now
                        self.stationary_anchor = position
                        self.stationary_since = now
                        self.stationary_fired = True
                        self.last_position = position
                        return
            elif elapsed > self.settings.swipe_window_seconds:
                self.start_position = position
                self.started_at = now

        # --- 3. STATIONARY HOLD (Not moving in mid-air -> Pause / Resume) ---
        if is_near_mouth:
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
                    if (
                        not self.stationary_fired
                        and (now - self.stationary_since) >= self.settings.stationary_hold_seconds
                        and now >= self.cooldown_until
                    ):
                        self._fire("stationary_hold", now)
                        self.last_gesture_time = now
                        self.stationary_fired = True
                        self._suppress_swipe = None
                else:
                    self.stationary_anchor = position
                    self.stationary_since = now
                    self.stationary_fired = False

        self.last_position = position

    def flush(self, now: float | None = None) -> None:
        _ = time.monotonic() if now is None else now
        self.current_pose_name = "no hand"
        self._palm_since = None
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
    def _is_index_only(landmarks: list[Any], aspect_ratio: float = 1.0) -> bool:
        if len(landmarks) < 21:
            return False
        wrist = landmarks[0]

        def dist(p1: Any, p2: Any) -> float:
            dx = (p1.x - p2.x) * aspect_ratio
            dy = p1.y - p2.y
            return math.hypot(dx, dy)

        palm_len = dist(landmarks[9], wrist)
        palm_len = max(palm_len, 0.04)

        index_tip = landmarks[8]
        index_pip = landmarks[6]
        dist_index_wrist = dist(index_tip, wrist)
        dist_index_pip = dist(index_pip, wrist)
        index_extended = (
            dist_index_wrist > dist_index_pip * 1.15 and dist_index_wrist > palm_len * 0.9
        )

        dist_mid_wrist = dist(landmarks[12], wrist)
        middle_folded = dist_index_wrist > dist_mid_wrist * 1.15

        ring_folded = dist(landmarks[16], wrist) < dist_index_wrist * 0.9
        pinky_folded = dist(landmarks[20], wrist) < dist_index_wrist * 0.9

        return index_extended and middle_folded and ring_folded and pinky_folded

    @staticmethod
    def _is_open_palm(landmarks: list[Any], aspect_ratio: float = 1.0) -> bool:
        """Detect open palm: all 4 fingers (index, middle, ring, pinky) extended."""
        if len(landmarks) < 21:
            return False
        wrist = landmarks[0]

        def dist(p1: Any, p2: Any) -> float:
            dx = (p1.x - p2.x) * aspect_ratio
            dy = p1.y - p2.y
            return math.hypot(dx, dy)

        palm_len = dist(landmarks[9], wrist)
        palm_len = max(palm_len, 0.04)

        # Index extended
        index_extended = (
            dist(landmarks[8], wrist) > dist(landmarks[6], wrist) * 1.15
            and dist(landmarks[8], wrist) > palm_len * 0.9
        )
        # Middle extended
        middle_extended = (
            dist(landmarks[12], wrist) > dist(landmarks[10], wrist) * 1.15
            and dist(landmarks[12], wrist) > palm_len * 0.9
        )
        # Ring extended
        ring_extended = (
            dist(landmarks[16], wrist) > dist(landmarks[14], wrist) * 1.15
            and dist(landmarks[16], wrist) > palm_len * 0.9
        )
        # Pinky extended
        pinky_extended = (
            dist(landmarks[20], wrist) > dist(landmarks[18], wrist) * 1.15
            and dist(landmarks[20], wrist) > palm_len * 0.9
        )

        return index_extended and middle_extended and ring_extended and pinky_extended
