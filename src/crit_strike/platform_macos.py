"""macOS 14+ AppKit overlays and ScreenCaptureKit capture.

Overlay flags adapted from Hakai's hakai-mac/src/macos.rs (MIT).
See licenses/HAKAI-MIT.txt. Capture excludes this process through SCContentFilter.
Native imports are lazy so the geometry and callback contracts can be tested elsewhere.
"""

import ctypes
import os
import platform
import threading

import numpy as np
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QGuiApplication

from crit_strike.models import Box, Monitor

PERMISSION_MESSAGE = (
    "请在系统设置 → 隐私与安全性 → 屏幕录制中允许 Crit Strike"
    "（源码运行时为 Python 或终端），然后退出并重新打开应用。手动特效仍可使用。"
)


class CapturePermissionError(RuntimeError):
    pass


def require_supported_system():
    if int(platform.mac_ver()[0].split(".")[0]) < 14:
        raise RuntimeError("Mac 自动识别需要 macOS 14 或更高版本")


def ensure_capture_permission():
    import Quartz

    require_supported_system()
    if not Quartz.CGPreflightScreenCaptureAccess():
        Quartz.CGRequestScreenCaptureAccess()
        raise CapturePermissionError(PERMISSION_MESSAGE)


def configure_overlay(window_id: int, selecting: bool) -> bool:
    if QGuiApplication.platformName() != "cocoa":
        return False
    import objc
    import Quartz

    # QWidget.winId() is an NSView pointer on Qt's Cocoa platform.
    view = objc.objc_object(c_void_p=window_id)
    window = view.window()
    if window is None:
        return False
    window.setOpaque_(False)
    window.setHasShadow_(False)
    window.setLevel_(Quartz.CGShieldingWindowLevel())
    # All Spaces, stationary, excluded from cycling, full-screen auxiliary.
    window.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 6) | (1 << 8))
    window.setMovable_(False)
    window.setIgnoresMouseEvents_(not selecting)
    return True


def monitor_layout() -> list[Monitor]:
    import AppKit
    import Quartz

    require_supported_system()
    screens = list(QGuiApplication.screens())
    monitors = []
    for native in AppKit.NSScreen.screens():
        display_id = int(native.deviceDescription()["NSScreenNumber"])
        bounds = Quartz.CGDisplayBounds(display_id)
        candidates = [
            screen
            for screen in screens
            if abs(screen.geometry().x() - bounds.origin.x) <= 1
            and abs(screen.geometry().y() - bounds.origin.y) <= 1
            and abs(screen.geometry().width() - bounds.size.width) <= 1
            and abs(screen.geometry().height() - bounds.size.height) <= 1
        ]
        if len(candidates) != 1:
            raise RuntimeError("无法对应 Mac 显示器与 Qt 屏幕，请检查镜像显示设置后重启应用")
        screen = candidates[0]
        screens.remove(screen)
        rect = screen.geometry()
        scale = screen.devicePixelRatio()
        # Capture and detection use per-display pixel origins. Monitor.index disambiguates
        # displays, avoiding ambiguous global pixel coordinates on mixed-Retina layouts.
        physical = Box(0, 0, round(rect.width() * scale), round(rect.height() * scale))
        logical = Box(rect.x(), rect.y(), rect.width(), rect.height())
        monitors.append(Monitor(display_id, physical, logical))
    if not monitors:
        raise RuntimeError("当前没有可用显示器")
    return monitors


def await_result(start, timeout: float = 8.0):
    """Bridge a ScreenCaptureKit completion callback on the capture worker only."""
    ready = threading.Event()
    result = []

    def complete(value, error):
        result.append((value, error))
        ready.set()

    start(complete)
    if not ready.wait(timeout):
        raise RuntimeError("屏幕捕获超时")
    value, error = result[0]
    if error is not None or value is None:
        raise RuntimeError("屏幕捕获失败")
    return value


def image_to_bgra(image) -> np.ndarray:
    import Quartz

    width = Quartz.CGImageGetWidth(image)
    height = Quartz.CGImageGetHeight(image)
    if not width or not height:
        raise RuntimeError("屏幕捕获返回空图像")
    pixels = np.zeros((height, width, 4), dtype=np.uint8)
    context = Quartz.CGBitmapContextCreate(
        pixels,
        width,
        height,
        8,
        width * 4,
        Quartz.CGColorSpaceCreateDeviceRGB(),
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little,
    )
    if context is None:
        raise RuntimeError("无法转换屏幕图像")
    Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), image)
    return pixels


class MacCapture:
    def __init__(self):
        self.filters = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.filters.clear()

    def grab(self, area: dict) -> np.ndarray:
        import objc
        import Quartz
        import ScreenCaptureKit as sc

        if not Quartz.CGPreflightScreenCaptureAccess():
            raise CapturePermissionError(PERMISSION_MESSAGE)
        with objc.autorelease_pool():
            display_id = area["display_id"]
            if display_id not in self.filters:
                content = await_result(
                    sc.SCShareableContent.getShareableContentWithCompletionHandler_
                )
                display = next(
                    (item for item in content.displays() if item.displayID() == display_id), None
                )
                own_apps = [
                    item for item in content.applications() if item.processID() == os.getpid()
                ]
                if display is None or not own_apps:
                    raise RuntimeError("无法建立排除自身应用的屏幕捕获")
                content_filter = sc.SCContentFilter.alloc()
                self.filters[display_id] = (
                    content_filter.initWithDisplay_excludingApplications_exceptingWindows_(  # noqa: E501
                        display, own_apps, []
                    )
                )
            configuration = sc.SCStreamConfiguration.alloc().init()
            configuration.setWidth_(area["width"])
            configuration.setHeight_(area["height"])
            configuration.setShowsCursor_(False)

            def capture(complete):
                sc.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_(
                    self.filters[display_id], configuration, complete
                )

            image = await_result(capture)
            pixels = image_to_bgra(image)
            if pixels.shape[:2] != (area["height"], area["width"]):
                raise RuntimeError("屏幕像素尺寸变化，请重新启动检测")
            return pixels


class HotkeyEvents(QObject):
    pressed = Signal(int)


def accessibility_trusted() -> bool:
    services = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )
    services.AXIsProcessTrusted.argtypes = []
    services.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(services.AXIsProcessTrusted())


class Hotkeys(QAbstractNativeEventFilter):
    KEYS = {100: 1, 101: 2, 109: 3}  # macOS virtual key codes F8, F9, F10.

    def __init__(self):
        super().__init__()
        self.events = HotkeyEvents()
        self.monitors = []

    def register(self) -> list[int]:
        import AppKit

        if not accessibility_trusted():
            return [1, 2, 3]

        def handle(event):
            identifier = self.KEYS.get(event.keyCode())
            # Keep modified function keys available to their existing callers.
            modifiers = event.modifierFlags() & (
                AppKit.NSEventModifierFlagCommand
                | AppKit.NSEventModifierFlagControl
                | AppKit.NSEventModifierFlagOption
                | AppKit.NSEventModifierFlagShift
            )
            if identifier and not event.isARepeat() and not modifiers:
                self.events.pressed.emit(identifier)
            return event

        def global_handle(event):
            handle(event)

        self.monitors = [
            AppKit.NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                AppKit.NSEventMaskKeyDown, global_handle
            ),
            AppKit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                AppKit.NSEventMaskKeyDown, handle
            ),
        ]
        if any(item is None for item in self.monitors):
            self.close()
            return [1, 2, 3]
        return []

    def nativeEventFilter(self, event_type, message):
        return False, 0

    def close(self):
        import AppKit

        for monitor in self.monitors:
            if monitor is not None:
                AppKit.NSEvent.removeMonitor_(monitor)
        self.monitors.clear()
