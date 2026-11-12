import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QGuiApplication

from crit_strike.models import Box, Monitor


def enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))


def exclude_capture(window_id: int) -> bool:
    if sys.platform != "win32":
        return False
    if sys.getwindowsversion().build < 19041:
        return False
    user32 = ctypes.windll.user32
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    return bool(user32.SetWindowDisplayAffinity(wintypes.HWND(window_id), 0x11))


def monitor_layout() -> list[Monitor]:
    if sys.platform != "win32":
        raise RuntimeError("首版自动检测支持 Windows 10 2004 及以上版本")

    class MonitorInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    devices = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
    )
    get_info = ctypes.windll.user32.GetMonitorInfoW
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]

    @callback_type
    def callback(handle, device_context, rectangle, data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if get_info(handle, ctypes.byref(info)):
            rect = info.rcMonitor
            devices.append(
                (
                    info.szDevice,
                    Box(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
                )
            )
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    screens = list(QGuiApplication.screens())
    monitors = []
    for index, (name, physical) in enumerate(devices):
        screen = next((item for item in screens if item.name() == name), None)
        if screen is None:
            # Qt 6 can expose the EDID model name instead of the Win32 device name.
            # Windows keeps screen origins in native virtual-desktop coordinates.
            candidates = [
                item
                for item in screens
                if item.geometry().x() == physical.x
                and item.geometry().y() == physical.y
                and abs(item.geometry().width() * item.devicePixelRatio() - physical.w) <= 2
                and abs(item.geometry().height() * item.devicePixelRatio() - physical.h) <= 2
            ]
            screen = candidates[0] if len(candidates) == 1 else None
        if screen is None:
            raise RuntimeError("无法对应系统显示器与 Qt 屏幕，请重新启动应用")
        rect = screen.geometry()
        screens.remove(screen)
        monitors.append(
            Monitor(index, physical, Box(rect.x(), rect.y(), rect.width(), rect.height()))
        )
    if not monitors:
        raise RuntimeError("当前没有可用显示器")
    return monitors


class HotkeyEvents(QObject):
    pressed = Signal(int)


class Hotkeys(QAbstractNativeEventFilter):
    KEYS = {1: 0x77, 2: 0x78, 3: 0x79}  # F8 pause, F9 stop, F10 select.

    def __init__(self):
        super().__init__()
        self.events = HotkeyEvents()
        self.registered = []

    def register(self) -> list[int]:
        failed = []
        if sys.platform != "win32":
            return list(self.KEYS)
        for identifier, key in self.KEYS.items():
            if ctypes.windll.user32.RegisterHotKey(None, identifier, 0x4000, key):
                self.registered.append(identifier)
            else:
                failed.append(identifier)
        return failed

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                self.events.pressed.emit(int(msg.wParam))
                return True, 0
        return False, 0

    def close(self):
        for identifier in self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, identifier)
        self.registered.clear()
