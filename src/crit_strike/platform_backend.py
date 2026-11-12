"""Select the desktop backend without importing foreign native frameworks."""

import sys

import mss

if sys.platform == "darwin":
    from crit_strike.platform_macos import (
        Hotkeys,
        MacCapture,
        configure_overlay,
        ensure_capture_permission,
        monitor_layout,
    )
else:
    from crit_strike.platform_windows import Hotkeys, exclude_capture, monitor_layout

    def configure_overlay(window_id: int, selecting: bool) -> bool:
        return exclude_capture(window_id)

    def ensure_capture_permission() -> None:
        pass


def create_capture():
    if sys.platform == "darwin":
        return MacCapture()
    return mss.mss()


__all__ = [
    "Hotkeys",
    "configure_overlay",
    "create_capture",
    "ensure_capture_permission",
    "monitor_layout",
]
