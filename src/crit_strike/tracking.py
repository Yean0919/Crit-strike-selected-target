from dataclasses import dataclass

from crit_strike.models import Box, Detection


@dataclass
class Track:
    id: int
    detection: Detection
    anchor: Box
    stable_since: float
    last_seen: float
    fired: bool = False


class Tracker:
    """Time-based tracking. Only currently observed tracks can become ready."""

    def __init__(self, dwell: float = 3.0, tolerance: float = 5.0, grace: float = 0.6):
        self.dwell = dwell
        self.tolerance = tolerance
        self.grace = grace
        self.tracks: dict[int, Track] = {}
        self._next_id = 0

    def clear(self) -> None:
        self.tracks.clear()

    def update(self, detections: list[Detection], now: float) -> list[Track]:
        self.tracks = {
            key: track for key, track in self.tracks.items() if now - track.last_seen <= self.grace
        }
        available = set(self.tracks)
        observed = []
        for detection in sorted(detections, key=lambda item: item.score, reverse=True):
            candidates = [
                self.tracks[key]
                for key in available
                if self.tracks[key].detection.target_id == detection.target_id
                and self.tracks[key].detection.monitor == detection.monitor
                and self.tracks[key].detection.box.distance(detection.box)
                <= max(20, min(detection.box.w, detection.box.h) * 0.65)
            ]
            if candidates:
                track = min(candidates, key=lambda item: item.detection.box.distance(detection.box))
                available.remove(track.id)
                size_change = abs(track.anchor.w - detection.box.w)
                if track.anchor.distance(detection.box) > self.tolerance or size_change > 5:
                    track.anchor = detection.box
                    track.stable_since = now
                    track.fired = False
                track.detection = detection
                track.last_seen = now
            else:
                track = Track(self._next_id, detection, detection.box, now, now)
                self.tracks[track.id] = track
                self._next_id += 1
            observed.append(track)
        return [
            track
            for track in observed
            if not track.fired and now - track.stable_since >= self.dwell
        ]

    def mark_fired(self, track_id: int) -> None:
        if track_id in self.tracks:
            self.tracks[track_id].fired = True
