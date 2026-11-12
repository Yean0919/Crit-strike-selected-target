from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    def distance(self, other: "Box") -> float:
        x, y = self.center
        other_x, other_y = other.center
        return hypot(x - other_x, y - other_y)

    def iou(self, other: "Box") -> float:
        width = max(0, min(self.x + self.w, other.x + other.w) - max(self.x, other.x))
        height = max(0, min(self.y + self.h, other.y + other.h) - max(self.y, other.y))
        intersection = width * height
        union = self.w * self.h + other.w * other.h - intersection
        return intersection / union if union else 0


@dataclass(frozen=True)
class Detection:
    target_id: str
    monitor: int
    box: Box
    score: float


@dataclass(frozen=True)
class Monitor:
    index: int
    physical: Box
    logical: Box

    def to_logical(self, box: Box) -> Box:
        scale_x = self.logical.w / self.physical.w
        scale_y = self.logical.h / self.physical.h
        return Box(
            self.logical.x + (box.x - self.physical.x) * scale_x,
            self.logical.y + (box.y - self.physical.y) * scale_y,
            box.w * scale_x,
            box.h * scale_y,
        )
