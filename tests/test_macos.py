import contextlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from crit_strike import platform_macos
from crit_strike.models import Box, Monitor
from crit_strike.platform_macos import CapturePermissionError, MacCapture, await_result


def test_capture_callback_success_failure_and_timeout():
    assert await_result(lambda done: done(42, None)) == 42
    with pytest.raises(RuntimeError, match="屏幕捕获失败"):
        await_result(lambda done: done(None, "private OS error"))
    with pytest.raises(RuntimeError, match="屏幕捕获超时"):
        await_result(lambda done: None, timeout=0.001)


def test_permission_denied_requests_access_and_gives_instructions(monkeypatch):
    quartz = MagicMock()
    quartz.CGPreflightScreenCaptureAccess.return_value = False
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    monkeypatch.setattr(platform_macos, "require_supported_system", lambda: None)
    with pytest.raises(CapturePermissionError, match="屏幕录制"):
        platform_macos.ensure_capture_permission()
    quartz.CGRequestScreenCaptureAccess.assert_called_once()


def test_retina_mapping_has_independent_display_coordinates():
    retina = Monitor(7, Box(0, 0, 2880, 1800), Box(-1440, -200, 1440, 900))
    normal = Monitor(8, Box(0, 0, 1920, 1080), Box(0, 0, 1920, 1080))
    assert retina.to_logical(Box(200, 100, 100, 100)) == Box(-1340, -150, 50, 50)
    assert normal.to_logical(Box(200, 100, 100, 100)) == Box(200, 100, 100, 100)


def test_capture_excludes_own_app_and_reuses_filter(monkeypatch):
    own_app = SimpleNamespace(processID=lambda: os.getpid())
    other_app = SimpleNamespace(processID=lambda: -1)
    display = SimpleNamespace(displayID=lambda: 77)
    content = SimpleNamespace(displays=lambda: [display], applications=lambda: [own_app, other_app])
    sc = MagicMock()
    sc.SCShareableContent.getShareableContentWithCompletionHandler_.side_effect = lambda done: done(
        content, None
    )
    sc.SCScreenshotManager.captureImageWithFilter_configuration_completionHandler_.side_effect = (
        lambda content_filter, configuration, done: done("image", None)
    )
    quartz = MagicMock()
    quartz.CGPreflightScreenCaptureAccess.return_value = True
    monkeypatch.setitem(sys.modules, "Quartz", quartz)
    monkeypatch.setitem(sys.modules, "ScreenCaptureKit", sc)
    monkeypatch.setitem(
        sys.modules, "objc", SimpleNamespace(autorelease_pool=contextlib.nullcontext)
    )
    pixels = np.zeros((32, 64, 4), dtype=np.uint8)
    monkeypatch.setattr(platform_macos, "image_to_bgra", lambda image: pixels)
    with MacCapture() as capture:
        area = {"display_id": 77, "width": 64, "height": 32}
        assert capture.grab(area) is pixels
        assert capture.grab(area) is pixels
        factory = sc.SCContentFilter.alloc.return_value
        factory.initWithDisplay_excludingApplications_exceptingWindows_.assert_called_once_with(
            display, [own_app], []
        )
        configuration = sc.SCStreamConfiguration.alloc.return_value.init.return_value
        configuration.setWidth_.assert_called_with(64)
        configuration.setHeight_.assert_called_with(32)
        configuration.setShowsCursor_.assert_called_with(False)
        with pytest.raises(RuntimeError, match="像素尺寸变化"):
            capture.grab({**area, "width": 65})
        quartz.CGPreflightScreenCaptureAccess.return_value = False
        with pytest.raises(CapturePermissionError):
            capture.grab(area)
    assert capture.filters == {}


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native CoreGraphics")
def test_native_bgra_conversion_preserves_colors_and_orientation():
    import Quartz

    pixels = np.array(
        [
            [[255, 0, 0, 255], [0, 255, 0, 255]],
            [[0, 0, 255, 255], [50, 100, 150, 255]],
        ],
        dtype=np.uint8,
    )
    context = Quartz.CGBitmapContextCreate(
        pixels,
        2,
        2,
        8,
        8,
        Quartz.CGColorSpaceCreateDeviceRGB(),
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little,
    )
    image = Quartz.CGBitmapContextCreateImage(context)
    assert np.array_equal(platform_macos.image_to_bgra(image), pixels)


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native ApplicationServices")
def test_native_accessibility_permission_check():
    assert type(platform_macos.accessibility_trusted()) is bool


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native ScreenCaptureKit")
def test_native_screenshot_api_contract():
    import ScreenCaptureKit as sc

    assert hasattr(
        sc.SCScreenshotManager, "captureImageWithFilter_configuration_completionHandler_"
    )
    assert hasattr(sc.SCContentFilter, "initWithDisplay_excludingApplications_exceptingWindows_")
    configuration = sc.SCStreamConfiguration.alloc().init()
    configuration.setWidth_(640)
    configuration.setHeight_(480)
    configuration.setShowsCursor_(False)
    assert (configuration.width(), configuration.height()) == (640, 480)
    assert not configuration.showsCursor()
