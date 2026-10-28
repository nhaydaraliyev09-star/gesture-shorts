"""Tests for Settings validation, clamping, and error recovery."""

from __future__ import annotations

import json
from pathlib import Path

from gesture_shorts.settings import Settings


def test_settings_default_values() -> None:
    s = Settings()
    assert s.camera_fps == 12
    assert s.swipe_threshold == 0.13
    assert s.gesture_actions["swipe_up"] == "next"
    assert s.platform == "YouTube"
    assert s.activation_mode == "pose"
    assert s.require_browser_focus is True


def test_settings_load_corrupt_file(tmp_path: Path) -> None:
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{ this is not valid json : [[", encoding="utf-8")

    s = Settings.load(corrupt_file)
    # Should fall back safely to defaults
    assert s.camera_fps == 12
    assert s.swipe_threshold == 0.13


def test_settings_load_wrong_types_and_clamping(tmp_path: Path) -> None:
    bad_data = {
        "camera_fps": "super_fast",  # Wrong type -> default 12
        "camera_index": 999,  # Out of bounds -> clamped to 10
        "swipe_threshold": -5.0,  # Below min -> clamped to 0.01
        "stationary_radius": 20.0,  # Above max -> clamped to 1.0
        "pip_width": "wide",  # Wrong type -> default 360
        "gesture_actions": {
            "swipe_up": "unknown_action",  # Unknown action -> fallback default
            "swipe_down": "previous",
        },
        "unknown_extra_key": 12345,  # Unknown key -> ignored
    }
    config_file = tmp_path / "bad.json"
    config_file.write_text(json.dumps(bad_data), encoding="utf-8")

    s = Settings.load(config_file)
    assert s.camera_fps == 12
    assert s.camera_index == 10
    assert s.swipe_threshold == 0.01
    assert s.stationary_radius == 1.0
    assert s.pip_width == 360
    assert s.gesture_actions["swipe_up"] == "next"
    assert s.gesture_actions["swipe_down"] == "previous"


def test_settings_fallback_per_key(tmp_path: Path) -> None:
    """Valid keys should be preserved even if some other keys are invalid or missing."""
    partial_data = {
        "camera_fps": 24,  # valid
        "swipe_threshold": "invalid",  # invalid -> fallback
        "platform": "TikTok",  # valid
    }
    config_file = tmp_path / "partial.json"
    config_file.write_text(json.dumps(partial_data), encoding="utf-8")

    s = Settings.load(config_file)
    assert s.camera_fps == 24
    assert s.swipe_threshold == 0.13
    assert s.platform == "TikTok"


def test_settings_modification_tracking(tmp_path: Path) -> None:
    config_file = tmp_path / "settings.json"
    s = Settings.load(config_file)
    assert not s.is_modified()

    s.camera_fps = 30
    assert s.is_modified()

    s.save(config_file)
    assert not s.is_modified()

    # Re-reading should match saved
    reloaded = Settings.load(config_file)
    assert reloaded.camera_fps == 30
