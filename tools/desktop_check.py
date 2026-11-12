"""Interactive Windows end-to-end check using generated artwork and temporary user data.

Only the application window is saved for visual inspection. Desktop pixels stay in memory.
"""

import argparse
import ctypes
import json
import tempfile
import time
from pathlib import Path

import cv2
import mss
import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from crit_strike.app import STYLE, MainWindow
from crit_strike.platform_windows import enable_dpi_awareness, monitor_layout
from crit_strike.storage import Store
from crit_strike.widgets import pixmap_from_bgr


def synthetic_avatar():
    image = np.full((160, 160, 3), (55, 92, 145), dtype=np.uint8)
    cv2.circle(image, (77, 76), 55, (190, 220, 50), -1)
    cv2.rectangle(image, (37, 42), (64, 68), (30, 30, 60), -1)
    cv2.circle(image, (103, 60), 14, (220, 70, 110), -1)
    cv2.line(image, (50, 113), (113, 89), (70, 20, 230), 10)
    cv2.putText(image, "K", (66, 99), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    return image


class SampleWindow(QWidget):
    def __init__(self, image, monitor):
        super().__init__()
        self.setWindowTitle("Crit Strike generated test surface")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setGeometry(int(monitor.logical.x + 60), int(monitor.logical.y + 60), 480, 260)
        self.avatar = pixmap_from_bgr(image)
        self.offset = 0
        self.visible_avatar = True

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#eef2f6"))
        painter.setPen(QColor("#172330"))
        painter.drawText(25, 35, "Generated avatar · desktop integration check")
        if self.visible_avatar:
            painter.drawPixmap(QRect(40 + self.offset, 80, 64, 64), self.avatar)


def working_set_bytes():
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("faults", wintypes.DWORD),
            ("peak", ctypes.c_size_t),
            ("working", ctypes.c_size_t),
            ("quota_peak_paged", ctypes.c_size_t),
            ("quota_paged", ctypes.c_size_t),
            ("quota_peak_nonpaged", ctypes.c_size_t),
            ("quota_nonpaged", ctypes.c_size_t),
            ("pagefile", ctypes.c_size_t),
            ("peak_pagefile", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not get_memory(wintypes.HANDLE(-1), ctypes.byref(counters), counters.cb):
        raise RuntimeError("working set query failed")
    return counters.working


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--soak-seconds", type=int, default=0)
    args = parser.parse_args()
    enable_dpi_awareness()
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    monitors = monitor_layout()
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    report = {
        "monitors": [
            {
                "pixels": [item.physical.w, item.physical.h],
                "scale": round(item.physical.w / item.logical.w, 3),
            }
            for item in monitors
        ],
        "checks": [],
        "scan_ms": [],
        "errors": [],
    }
    temporary = tempfile.TemporaryDirectory(prefix="crit-strike-desktop-check-")
    store = Store(Path(temporary.name))
    store.add("合成测试头像", synthetic_avatar())
    window = MainWindow(store, register_hotkeys=False)
    sample = SampleWindow(synthetic_avatar(), monitors[0])
    window.show()
    start_time = time.monotonic()
    phase = "start"
    phase_time = start_time
    first_capture = None
    ended = False

    def record_scan(detections, captured_at, duration, generation):
        report["scan_ms"].append(round(duration * 1000, 1))

    def finish():
        nonlocal ended
        if ended:
            return
        ended = True
        timer.stop()
        sample.close()
        window.close()

    def capture_sample():
        monitor = monitors[0]
        ratio_x = monitor.physical.w / monitor.logical.w
        ratio_y = monitor.physical.h / monitor.logical.h
        left = monitor.physical.x + (sample.x() - monitor.logical.x) * ratio_x
        top = monitor.physical.y + (sample.y() - monitor.logical.y) * ratio_y
        with mss.mss() as capture:
            return np.asarray(
                capture.grab(
                    {
                        "left": round(left),
                        "top": round(top),
                        "width": round(sample.width() * ratio_x),
                        "height": round(sample.height() * ratio_y),
                    }
                )
            ).copy()

    def step():
        nonlocal phase, phase_time, first_capture
        now = time.monotonic()
        try:
            if now - start_time > 40 + args.soak_seconds:
                raise AssertionError("desktop check timeout, phase=" + phase)
            if phase == "start" and now - phase_time > 0.5:
                window.grab().save(str(output / "app-preview.png"))
                window.hide()
                sample.show()
                phase, phase_time = "launch", now
            elif phase == "launch" and now - phase_time > 0.5:
                first_capture = capture_sample()
                window.start_detection()
                assert window.running, window.status.text()
                assert all(item.capture_safe for item in window.overlays.values())
                window.worker.scanned.connect(record_scan)
                phase, phase_time = "first", now
            elif phase == "first":
                if window.trigger_count:
                    assert now - phase_time >= 3
                    assert window.trigger_count == 1
                    report["checks"].append("visible avatar triggers after 3 seconds")
                    report["first_trigger_seconds"] = round(now - phase_time, 3)
                    # Confirm overlay rendering does not contaminate screen capture.
                    current = capture_sample()
                    error = float(np.abs(current.astype(float) - first_capture).mean())
                    report["overlay_capture_mae"] = round(error, 3)
                    assert error < 2, "overlay leaked into screenshot"
                    report["checks"].append("overlay excluded from captured desktop")
                    phase, phase_time = "hold", now
            elif phase == "hold" and now - phase_time > 2:
                assert window.trigger_count == 1
                report["checks"].append("stationary target does not retrigger")
                sample.offset = 20
                sample.update()
                phase, phase_time = "moved", now
            elif phase == "moved" and window.trigger_count >= 2:
                assert now - phase_time >= 3
                report["checks"].append("movement restarts dwell")
                sample.visible_avatar = False
                sample.update()
                phase, phase_time = "hidden", now
            elif phase == "hidden" and now - phase_time > 2:
                assert not window.tracker.tracks
                sample.visible_avatar = True
                sample.update()
                phase, phase_time = "reappear", now
            elif phase == "reappear" and window.trigger_count >= 3:
                assert now - phase_time >= 3
                report["checks"].append("disappearance and reappearance restarts dwell")
                window.stop_all()
                assert window.playing_count() == 0
                phase, phase_time = "manual", now
            elif phase == "manual" and window.worker is None:
                window.manual()
                overlay = window.overlays[monitors[0].index]
                assert overlay.selecting
                QTest.mouseClick(overlay, Qt.MouseButton.LeftButton, pos=QPoint(180, 180))
                assert not window.selecting
                assert window.playing_count() == 1
                assert overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
                report["checks"].append("manual click and mouse pass-through")
                window.stop_all()
                assert window.playing_count() == 0
                report["checks"].append("emergency stop clears effects")
                phase, phase_time = "cleanup", now
            elif phase == "cleanup" and now - phase_time > 0.5:
                if args.soak_seconds:
                    window.mode.setCurrentIndex(0)
                    window.start_detection()
                    assert window.running
                    window.worker.scanned.connect(record_scan)
                    phase, phase_time = "soak", now
                else:
                    finish()
            elif phase == "soak":
                assert window.running, "detector stopped during soak"
                if now - phase_time >= 10 and "soak_baseline_bytes" not in report:
                    report["soak_baseline_bytes"] = working_set_bytes()
                if now - phase_time >= args.soak_seconds:
                    report["soak_seconds"] = args.soak_seconds
                    report["soak_final_bytes"] = working_set_bytes()
                    baseline = report.get("soak_baseline_bytes", report["soak_final_bytes"])
                    assert report["soak_final_bytes"] - baseline < 64 * 1024 * 1024
                    report["checks"].append("continuous detector and bounded working set")
                    finish()
        except Exception as error:
            report["errors"].append(str(error))
            finish()

    timer = QTimer()
    timer.timeout.connect(step)
    timer.start(80)
    app.exec()
    if report["scan_ms"]:
        report["scan_mean_ms"] = round(float(np.mean(report["scan_ms"])), 1)
        report["scan_p95_ms"] = round(float(np.percentile(report["scan_ms"], 95)), 1)
    report["passed"] = not report["errors"] and len(report["checks"]) >= 7
    (output / "desktop-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=True))
    temporary.cleanup()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
