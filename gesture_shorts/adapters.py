"""Platform adapters, window focus detection, and keyboard dispatch."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from collections.abc import Callable
from typing import Any, ClassVar

try:
    from pynput.keyboard import Controller as KeyboardController
    from pynput.keyboard import Key
    _keyboard = KeyboardController()
except (ImportError, Exception):
    _keyboard = None


class WindowFocusChecker:
    """Detects active foreground window titles across Windows, macOS, and Linux."""

    def __init__(self) -> None:
        self.supported = True
        self._warned_unsupported = False

    def get_active_window_title(self) -> str | None:
        if sys.platform.startswith("win"):
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not hwnd:
                    return None
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value
            except Exception:
                return None

        if sys.platform == "darwin":
            try:
                cmd = (
                    "osascript -e 'tell application \"System Events\" to "
                    "get title of front window of (first process whose frontmost is true)'"
                )
                res = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=1.0, check=False
                )
                title = res.stdout.strip()
                if title:
                    return title
                # Fallback to application name
                app_cmd = (
                    "osascript -e 'tell application \"System Events\" to "
                    "get name of first process whose frontmost is true'"
                )
                res2 = subprocess.run(
                    app_cmd, shell=True, capture_output=True, text=True, timeout=1.0, check=False
                )
                return res2.stdout.strip() or None
            except Exception:
                return None

        if sys.platform.startswith("linux"):
            try:
                res = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass

        self.supported = False
        return None

    def is_target_focused(self, platform_name: str) -> tuple[bool, str | None]:
        """Check if focused window belongs to a browser displaying target platform."""
        title = self.get_active_window_title()
        if title is None:
            if not self.supported and not self._warned_unsupported:
                self._warned_unsupported = True
                return True, "Window focus check unavailable on this platform"
            return False, "No active window detected"

        # Check for platform name in window title
        if platform_name.lower() in title.lower():
            return True, None

        return False, f"Focused window ('{title[:25]}...') is not {platform_name}"


class PlatformAdapter:
    URLS: ClassVar[dict[str, str]] = {
        "YouTube": "https://www.youtube.com/shorts",
        "TikTok": "https://www.tiktok.com/foryou",
        "Instagram": "https://www.instagram.com/reels/",
    }

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

    def __init__(
        self,
        platform: str,
        notify: Callable[[str], None],
        focus_checker: WindowFocusChecker | None = None,
        bridge: Any | None = None,
    ) -> None:
        self.platform = platform
        self.notify = notify
        self.focus_checker = focus_checker or WindowFocusChecker()
        self.bridge = bridge
        self.is_playing: bool = True
        self.is_muted: bool = False

    def open_feed(self) -> None:
        if self.platform in self.URLS:
            webbrowser.open(self.URLS[self.platform])
            self.notify(f"{self.platform} opened in browser")

    def handle_extension_status(self, data: dict[str, Any]) -> None:
        """Receive actual video element state from the browser extension."""
        if "playing" in data and isinstance(data["playing"], bool):
            self.is_playing = data["playing"]
        if "muted" in data and isinstance(data["muted"], bool):
            self.is_muted = data["muted"]

    def _send_key(self, key: object) -> bool:
        if _keyboard is None:
            self.notify("pynput not available - keyboard control disabled")
            return False
        try:
            _keyboard.press(key)
            _keyboard.release(key)
            return True
        except Exception as exc:
            self.notify(f"Key send error: {exc}")
            return False

    def perform(self, action: str, require_browser_focus: bool = True) -> bool:
        # Phase 4: Use browser bridge if extension is connected
        if self.bridge and getattr(self.bridge, "is_connected", False):
            if self.bridge.send_action(action):
                if action == "toggle_play":
                    self.is_playing = not self.is_playing
                    label = "Toggled play/pause"
                elif action == "mute":
                    self.is_muted = not self.is_muted
                    label = "Toggled mute"
                elif action == "next":
                    label = "Next ▲"
                elif action == "previous":
                    label = "Previous ▼"
                else:
                    label = action.replace("_", " ").title()
                self.notify(f"{label} (Bridge)")
                return True

        if require_browser_focus:
            focused, reason = self.focus_checker.is_target_focused(self.platform)
            if not focused:
                self.notify("Gesture ignored: browser not focused")
                return False
            if reason:
                self.notify(reason)

        keys = self.KEY_MAP.get(self.platform, {})
        key = keys.get(action)
        if key is None:
            self.notify(f"No key mapping for '{action}' on {self.platform}")
            return False

        if action in ("next", "previous"):
            self.is_playing = True
            label = "Next ▲" if action == "next" else "Previous ▼"
        elif action == "toggle_play":
            self.is_playing = not self.is_playing
            label = "Toggled play/pause"
        elif action == "mute":
            self.is_muted = not self.is_muted
            label = "Toggled mute"
        else:
            label = action.replace("_", " ").title()

        if self._send_key(key):
            self.notify(label)
            return True
        return False
