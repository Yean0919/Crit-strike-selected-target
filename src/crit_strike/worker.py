import threading
import time

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal

from crit_strike.detection import Detector
from crit_strike.models import Box, Monitor


class CaptureWorker(QThread):
    scanned = Signal(object, float, float, int)
    failed = Signal(str)

    def __init__(
        self, detector: Detector, monitors: list[Monitor], interval: float, generation: int
    ):
        super().__init__()
        self.detector = detector
        self.monitors = monitors
        self.interval = interval
        self.generation = generation
        self.stop_event = threading.Event()
        self.exclusions: dict[int, list[Box]] = {}

    def stop(self):
        self.stop_event.set()

    def run(self):
        cv2.setNumThreads(2)
        try:
            with mss.mss() as capture:
                previous_frames = {}
                previous_results = {}
                previous_exclusions = None
                while not self.stop_event.is_set():
                    start = time.monotonic()
                    detections = []
                    exclusions = self.exclusions
                    if exclusions != previous_exclusions:
                        previous_frames.clear()
                        previous_results.clear()
                        previous_exclusions = exclusions
                    for monitor in self.monitors:
                        if self.stop_event.is_set():
                            return
                        area = monitor.physical
                        shot = capture.grab(
                            {
                                "left": int(area.x),
                                "top": int(area.y),
                                "width": int(area.w),
                                "height": int(area.h),
                            }
                        )
                        image = np.asarray(shot)[:, :, :3]
                        previous = previous_frames.get(monitor.index)
                        if previous is None or not np.array_equal(previous, image):
                            previous_results[monitor.index] = self.detector.detect(
                                image,
                                monitor.index,
                                (int(area.x), int(area.y)),
                                exclusions.get(monitor.index, []),
                            )
                            previous_frames[monitor.index] = image.copy()
                        detections.extend(previous_results[monitor.index])
                    duration = time.monotonic() - start
                    self.scanned.emit(detections, start, duration, self.generation)
                    self.stop_event.wait(max(0.05, self.interval - duration))
        except Exception:
            # Do not include screenshot contents, user paths, or template names in diagnostics.
            self.failed.emit("桌面捕获失败，已暂停。解锁桌面或检查显示器后重新启动检测。")
