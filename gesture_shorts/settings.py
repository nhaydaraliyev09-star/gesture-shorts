"""Configuration and settings validation for gesture-shorts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = APP_DIR / "gesture_settings.json"

KNOWN_ACTIONS = {"next", "previous", "toggle_play", "mute"}
KNOWN_GESTURES = {"swipe_up", "swipe_down", "stationary_hold", "finger_on_lips"}
DEFAULT_ACTIONS: dict[str, str] = {
    "swipe_up": "next",
    "swipe_down": "previous",
    "stationary_hold": "toggle_play",
    "finger_on_lips": "mute",
}


def _clamp_int(val: Any, min_v: int, max_v: int, default: int) -> int:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        int_val = int(val)
        return max(min_v, min(max_v, int_val))
    return default


def _clamp_float(val: Any, min_v: float, max_v: float, default: float) -> float:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        f_val = float(val)
        return max(min_v, min(max_v, f_val))
    return default


def _validate_bool(val: Any, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    return default


def _validate_str(val: Any, allowed: set[str], default: str) -> str:
    if isinstance(val, str) and val in allowed:
        return val
    return default


def _validate_actions(val: Any, default: dict[str, str]) -> dict[str, str]:
    if not isinstance(val, dict):
        return dict(default)
    validated: dict[str, str] = {}
    for gesture, action in val.items():
        if gesture in KNOWN_GESTURES and isinstance(action, str) and action in KNOWN_ACTIONS:
            validated[gesture] = action
        elif gesture in KNOWN_GESTURES:
            validated[gesture] = default.get(gesture, "toggle_play")
    # Guarantee all known gestures have an action assigned
    for g, a in default.items():
        if g not in validated:
            validated[g] = a
    return validated


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
    gesture_actions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ACTIONS))
    platform: str = "YouTube"
    require_browser_focus: bool = True
    activation_mode: str = "pose"  # "always" | "pose"
    auto_disarm_seconds: float = 20.0
    preview_enabled: bool = True

    _loaded_snapshot: str = field(default="", init=False, repr=False)
    _settings_path: Path = field(default=DEFAULT_SETTINGS_PATH, init=False, repr=False)

    def to_dict(self) -> dict[str, Any]:
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
            "platform": self.platform,
            "require_browser_focus": self.require_browser_focus,
            "activation_mode": self.activation_mode,
            "auto_disarm_seconds": self.auto_disarm_seconds,
            "preview_enabled": self.preview_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], path: Path = DEFAULT_SETTINGS_PATH) -> Settings:
        inst = cls(
            camera_index=_clamp_int(data.get("camera_index"), 0, 10, 0),
            camera_fps=_clamp_int(data.get("camera_fps"), 1, 60, 12),
            swipe_threshold=_clamp_float(data.get("swipe_threshold"), 0.01, 1.0, 0.13),
            swipe_window_seconds=_clamp_float(data.get("swipe_window_seconds"), 0.05, 5.0, 0.60),
            cooldown_seconds=_clamp_float(data.get("cooldown_seconds"), 0.05, 5.0, 0.50),
            stationary_radius=_clamp_float(data.get("stationary_radius"), 0.01, 1.0, 0.05),
            stationary_hold_seconds=_clamp_float(
                data.get("stationary_hold_seconds"), 0.1, 5.0, 0.80
            ),
            mouth_distance=_clamp_float(data.get("mouth_distance"), 0.01, 1.0, 0.13),
            pip_width=_clamp_int(data.get("pip_width"), 100, 3840, 360),
            pip_height=_clamp_int(data.get("pip_height"), 100, 2160, 640),
            gesture_actions=_validate_actions(data.get("gesture_actions"), DEFAULT_ACTIONS),
            platform=_validate_str(
                data.get("platform"), {"YouTube", "TikTok", "Instagram"}, "YouTube"
            ),
            require_browser_focus=_validate_bool(data.get("require_browser_focus"), True),
            activation_mode=_validate_str(
                data.get("activation_mode"), {"always", "pose"}, "pose"
            ),
            auto_disarm_seconds=_clamp_float(data.get("auto_disarm_seconds"), 1.0, 300.0, 20.0),
            preview_enabled=_validate_bool(data.get("preview_enabled"), True),
        )
        inst._settings_path = path
        inst._loaded_snapshot = json.dumps(inst.to_dict(), sort_keys=True)
        return inst

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        target_path = path or DEFAULT_SETTINGS_PATH
        if not target_path.exists():
            inst = cls()
            inst._settings_path = target_path
            inst._loaded_snapshot = json.dumps(inst.to_dict(), sort_keys=True)
            return inst
        try:
            raw = target_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                inst = cls()
                inst._settings_path = target_path
                inst._loaded_snapshot = json.dumps(inst.to_dict(), sort_keys=True)
                return inst
            return cls.from_dict(data, target_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            inst = cls()
            inst._settings_path = target_path
            inst._loaded_snapshot = json.dumps(inst.to_dict(), sort_keys=True)
            return inst

    def save(self, path: Path | None = None) -> None:
        target_path = path or self._settings_path
        target_path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self._loaded_snapshot = json.dumps(self.to_dict(), sort_keys=True)

    def is_modified(self) -> bool:
        current = json.dumps(self.to_dict(), sort_keys=True)
        return current != self._loaded_snapshot
