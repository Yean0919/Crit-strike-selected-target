from unittest.mock import MagicMock

import numpy as np

from crit_strike.models import Box, Monitor
from crit_strike.worker import CaptureWorker


def test_worker_reuses_identical_frames_and_rechecks_changes(monkeypatch):
    detector = MagicMock()
    detector.detect.return_value = []
    worker = CaptureWorker(detector, [Monitor(0, Box(0, 0, 32, 32), Box(0, 0, 32, 32))], 0.1, 1)
    frames = [np.zeros((32, 32, 4), dtype=np.uint8) for _ in range(4)]
    frames[-1][:] = 100
    calls = []

    class Capture:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def grab(self, area):
            calls.append(area)
            if len(calls) == 4:
                worker.stop()
            return frames[len(calls) - 1]

    monkeypatch.setattr("crit_strike.worker.mss.mss", Capture)
    worker.run()
    assert len(calls) == 4
    assert detector.detect.call_count == 2


def test_worker_error_message_is_generic(monkeypatch):
    worker = CaptureWorker(MagicMock(), [], 0.1, 1)
    messages = []
    worker.failed.connect(messages.append)

    def fail():
        raise OSError("sensitive test detail")

    monkeypatch.setattr("crit_strike.worker.mss.mss", fail)
    worker.run()
    assert len(messages) == 1
    assert "sensitive" not in messages[0]
