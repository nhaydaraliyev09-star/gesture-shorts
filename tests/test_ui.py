"""Tests for PiPApp GUI interactions, platform selection, and settings dialog."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

from gesture_shorts.settings import Settings
from gesture_shorts.ui import PiPApp, SettingsDialog


def test_select_platform_updates_settings_and_adapter() -> None:
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.settings = Settings()
    app.status_queue = queue.Queue()
    app.platform = "YouTube"
    app.platform_buttons = {
        "YouTube": MagicMock(),
        "TikTok": MagicMock(),
        "Instagram": MagicMock(),
    }

    app.select_platform("TikTok")
    assert app.platform == "TikTok"
    assert app.settings.platform == "TikTok"
    assert app.adapter.platform == "TikTok"
    app.platform_buttons["TikTok"].config.assert_called()


def test_toggle_preview_switches_setting() -> None:
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.settings = Settings(preview_enabled=True)
    app.preview_btn = MagicMock()
    app.canvas = MagicMock()

    app.toggle_preview()
    assert app.settings.preview_enabled is False

    app.toggle_preview()
    assert app.settings.preview_enabled is True


def test_arm_toggle_via_ui() -> None:
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.settings = Settings(activation_mode="pose")
    app.recognizer = MagicMock()
    app.recognizer.is_armed = False
    app.adapter = MagicMock()
    app.state_var = MagicMock()
    app.arm_toggle_btn = MagicMock()

    app.toggle_arm()
    app.recognizer.set_armed.assert_called_with(True)


def test_settings_dialog_live_apply(monkeypatch) -> None:
    root = MagicMock()
    app = PiPApp.__new__(PiPApp)
    app.root = root
    app.settings = Settings(camera_fps=12, swipe_threshold=0.13)
    app.recognizer = MagicMock()
    app.update_header_status = MagicMock()
    app.show_status = MagicMock()

    dialog = SettingsDialog.__new__(SettingsDialog)
    dialog.parent = app
    dialog.settings = app.settings
    dialog.cam_idx_var = MagicMock()
    dialog.cam_idx_var.get.return_value = 2
    dialog.fps_var = MagicMock()
    dialog.fps_var.get.return_value = 25
    dialog.swipe_var = MagicMock()
    dialog.swipe_var.get.return_value = 0.22
    dialog.hold_var = MagicMock()
    dialog.hold_var.get.return_value = 1.0
    dialog.cooldown_var = MagicMock()
    dialog.cooldown_var.get.return_value = 0.4
    dialog.mouth_var = MagicMock()
    dialog.mouth_var.get.return_value = 0.18
    dialog.focus_var = MagicMock()
    dialog.focus_var.get.return_value = False
    dialog.mode_var = MagicMock()
    dialog.mode_var.get.return_value = "always"

    dialog._live_apply()
    assert app.settings.camera_fps == 25
    assert app.settings.swipe_threshold == 0.22
    assert app.settings.require_browser_focus is False
    assert app.settings.activation_mode == "always"
