from crit_strike.models import Box, Detection, Monitor
from crit_strike.tracking import Tracker


def detection(x=0, target="one", monitor=0):
    return Detection(target, monitor, Box(x, 40, 64, 64), 0.95)


def feed(tracker, start, stop, item):
    ready = []
    for tick in range(round(start * 10), round(stop * 10) + 1):
        ready = tracker.update([item], tick / 10)
    return ready


def test_three_seconds_and_once():
    tracker = Tracker()
    assert feed(tracker, 0, 2.9, detection()) == []
    ready = tracker.update([detection()], 3)
    assert len(ready) == 1
    tracker.mark_fired(ready[0].id)
    assert feed(tracker, 3.1, 8, detection()) == []


def test_movement_resets_and_jitter_keeps_anchor():
    tracker = Tracker()
    feed(tracker, 0, 2, detection())
    assert tracker.update([detection(3)], 2.1) == []
    assert tracker.update([detection(7)], 2.2) == []
    assert feed(tracker, 2.3, 5.1, detection(7)) == []
    assert len(tracker.update([detection(7)], 5.3)) == 1


def test_missing_frames_never_fire():
    tracker = Tracker()
    feed(tracker, 0, 2.9, detection())
    assert tracker.update([], 3) == []
    assert len(tracker.update([detection()], 3.2)) == 1
    tracker.clear()
    feed(tracker, 0, 2.9, detection())
    assert tracker.update([], 3.6) == []
    assert tracker.update([detection()], 3.7) == []


def test_independent_targets_and_monitors():
    tracker = Tracker()
    detections = [detection(), detection(150), detection(target="two"), detection(monitor=1)]
    for tick in range(31):
        ready = tracker.update(detections, tick / 10)
    assert len(ready) == 4
    assert len({track.id for track in ready}) == 4
    tracker.mark_fired(ready[0].id)
    assert len(tracker.update(detections, 3.1)) == 3


def test_negative_mixed_dpi_coordinates():
    monitor = Monitor(1, Box(-2560, -200, 2560, 1440), Box(-1706, -133, 1706, 960))
    logical = monitor.to_logical(Box(-1280, 520, 96, 96))
    assert logical.x == -853
    assert logical.y == 347
    assert logical.h == 64


def test_overlap():
    assert Box(0, 0, 10, 10).iou(Box(0, 0, 10, 10)) == 1
    assert Box(0, 0, 10, 10).iou(Box(20, 20, 10, 10)) == 0
