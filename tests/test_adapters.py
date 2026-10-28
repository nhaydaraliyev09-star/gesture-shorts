"""Tests for PlatformAdapter, window focus safety, and key dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

from gesture_shorts.adapters import PlatformAdapter, WindowFocusChecker


def test_perform_blocks_when_browser_not_focused() -> None:
    notifications: list[str] = []
    checker = MagicMock(spec=WindowFocusChecker)
    checker.is_target_focused.return_value = (False, "Focused window is Code.exe")

    adapter = PlatformAdapter("YouTube", notifications.append, focus_checker=checker)
    adapter._send_key = MagicMock(return_value=True)

    # With focus check required
    res = adapter.perform("next", require_browser_focus=True)
    assert not res
    assert "Gesture ignored: browser not focused" in notifications
    adapter._send_key.assert_not_called()


def test_perform_executes_when_browser_focused() -> None:
    notifications: list[str] = []
    checker = MagicMock(spec=WindowFocusChecker)
    checker.is_target_focused.return_value = (True, None)

    adapter = PlatformAdapter("YouTube", notifications.append, focus_checker=checker)
    adapter._send_key = MagicMock(return_value=True)

    res = adapter.perform("next", require_browser_focus=True)
    assert res
    assert adapter.is_playing is True
    assert "Next ▲" in notifications
    adapter._send_key.assert_called_once()


def test_perform_bypasses_focus_when_disabled() -> None:
    notifications: list[str] = []
    checker = MagicMock(spec=WindowFocusChecker)
    checker.is_target_focused.return_value = (False, "Not focused")

    adapter = PlatformAdapter("TikTok", notifications.append, focus_checker=checker)
    adapter._send_key = MagicMock(return_value=True)

    res = adapter.perform("toggle_play", require_browser_focus=False)
    assert res
    assert adapter.is_playing is False
    assert "Toggled play/pause" in notifications


def test_play_and_mute_state_tracking() -> None:
    notifications: list[str] = []
    checker = MagicMock(spec=WindowFocusChecker)
    checker.is_target_focused.return_value = (True, None)

    adapter = PlatformAdapter("Instagram", notifications.append, focus_checker=checker)
    adapter._send_key = MagicMock(return_value=True)

    # Initial state
    assert adapter.is_playing is True
    assert adapter.is_muted is False

    adapter.perform("toggle_play", require_browser_focus=False)
    assert adapter.is_playing is False

    adapter.perform("next", require_browser_focus=False)
    # Next/previous restores is_playing to True without guessing
    assert adapter.is_playing is True

    adapter.perform("mute", require_browser_focus=False)
    assert adapter.is_muted is True
