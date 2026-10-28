"""Platform permission checks and troubleshooting diagnostics."""

from __future__ import annotations

import os
import sys


def check_system_environment() -> list[str]:
    """Check for platform-specific permission restrictions or incompatibilities."""
    warnings: list[str] = []

    # Linux Wayland detection
    if sys.platform.startswith("linux"):
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
        if session_type == "wayland" or wayland_display:
            warnings.append(
                "Linux Wayland detected: pynput keystroke simulation and xdotool "
                "window detection are restricted by Wayland security policy. "
                "Please switch to an X11 / X.Org session or enable XWayland."
            )

    # macOS Accessibility and Camera permissions
    if sys.platform == "darwin":
        warnings.append(
            "macOS Notice: If gestures do not trigger keypresses, ensure Terminal / Python is "
            "granted 'Accessibility' and 'Input Monitoring' access in "
            "System Settings -> Privacy & Security."
        )

    return warnings
