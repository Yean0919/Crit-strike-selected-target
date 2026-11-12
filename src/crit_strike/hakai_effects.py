"""QPainter adaptations of Hakai's procedural decals (MIT, Matjaz Lipus, 2026).

Source commit 9e6fe469545abbd1a252ebb1fc45ba5e4d7f9ee3, hakai-core/src/decals.rs.
See licenses/HAKAI-MIT.txt and THIRD_PARTY_NOTICES.md. Geometry uses Python's
seeded RNG, Qt rasterization and bounded caches. Timing and tint are local additions.
"""

import math
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPolygonF, QRadialGradient


def point_on_arm(points: list[QPointF], fraction: float) -> QPointF:
    position = min(1.0, max(0.0, fraction)) * (len(points) - 1)
    lower = int(position)
    upper = min(lower + 1, len(points) - 1)
    return points[lower] + (points[upper] - points[lower]) * (position - lower)


def stroke_cracks(painter: QPainter, lines: list[list[QPointF]], width: float, alpha: float):
    for highlight in [True, False]:
        offset = QPointF(2.304, -2.304) if highlight else QPointF()
        for points in lines:
            for index in range(len(points) - 1):
                fraction = index / (len(points) - 1)
                if highlight:
                    opacity = 0.46 * (1 - fraction**2)
                    thickness = max(1.0, width * 1.25 * (1 - fraction * 0.45))
                    color = QColor(255, 255, 255, round(255 * opacity))
                else:
                    opacity = alpha * (1 - (fraction * 0.8) ** 2)
                    thickness = max(0.9, width * (1 - fraction * 0.5))
                    color = QColor(8, 8, 8, round(255 * opacity))
                painter.setPen(QPen(color, thickness))
                painter.drawLine(points[index] + offset, points[index + 1] + offset)


@lru_cache(maxsize=8)
def crack_image(variant: int) -> QImage:
    """Port of make_crack: radial arms, broken rings, tinted shards and branches."""
    rng = random.Random(0xC7AC0000 + variant % 8)
    image = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = QPointF(256, 256)
    count = rng.randrange(8, 14)
    base = rng.uniform(0, math.tau)
    arms, lengths = [], []
    for index in range(count):
        angle = base + index * math.tau / count + rng.uniform(-0.18, 0.18)
        length = 512 * 0.46 * rng.uniform(0.62, 1)
        steps = rng.randrange(3, 6)
        points = [center]
        for step in range(1, steps + 1):
            angle += rng.uniform(-0.1, 0.1)
            distance = length * step / steps
            points.append(center + QPointF(math.cos(angle), math.sin(angle)) * distance)
        arms.append(points)
        lengths.append(length)

    rings = []
    ring_count = rng.randrange(2, 5)
    for ring in range(ring_count):
        fraction = (ring + 1) / (ring_count + 1) * rng.uniform(0.85, 1.15)
        for index in range(count):
            if rng.random() >= 0.82:
                continue
            first = fraction * rng.uniform(0.9, 1.1)
            second = fraction * rng.uniform(0.9, 1.1)
            if max(first, second) >= 1:
                continue
            start = point_on_arm(arms[index], first)
            end = point_on_arm(arms[(index + 1) % count], second)
            middle = (start + end) / 2
            rings.append([start, middle + (center - middle) * rng.uniform(0.04, 0.16), end])

    painter.setPen(Qt.PenStyle.NoPen)
    for index in range(count):
        fraction = 0.12
        while fraction < 0.9:
            end = fraction + rng.uniform(0.18, 0.34)
            if end >= 1:
                break
            adjacent = (index + 1) % count
            shade = 255 if rng.random() < 0.5 else 0
            painter.setBrush(
                QColor(shade, shade, shade, round(255 * rng.uniform(0.03, 0.10) * (1 - fraction)))
            )
            painter.drawPolygon(
                QPolygonF(
                    [
                        point_on_arm(arms[index], fraction),
                        point_on_arm(arms[adjacent], fraction),
                        point_on_arm(arms[adjacent], end),
                        point_on_arm(arms[index], end),
                    ]
                )
            )
            fraction = end

    branches = []
    for index, arm in enumerate(arms):
        if rng.random() >= 0.6:
            continue
        start = arm[rng.randrange(1, len(arm))]
        angle = math.atan2(start.y() - 256, start.x() - 256)
        angle += rng.choice([-1, 1]) * rng.uniform(0.4, 0.9)
        length = lengths[index] * rng.uniform(0.15, 0.38)
        points = [start]
        for step in range(1, rng.randrange(2, 4) + 1):
            angle += rng.uniform(-0.16, 0.16)
            points.append(start + QPointF(math.cos(angle), math.sin(angle)) * length * step / 2.5)
        branches.append(points)
    stroke_cracks(painter, rings, 512 * 0.010, 0.78)
    stroke_cracks(painter, branches, 512 * 0.011, 0.80)
    stroke_cracks(painter, arms, 512 * 0.017, 0.90)

    hole_radius = 512 * rng.uniform(0.028, 0.048)
    lobes = rng.randrange(7, 11)
    hole = []
    for index in range(lobes):
        angle = index * math.tau / lobes
        hole.append(
            center
            + QPointF(math.cos(angle), math.sin(angle)) * hole_radius * rng.uniform(0.7, 1.35)
        )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(5, 5, 5, 235))
    painter.drawPolygon(QPolygonF(hole))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 128), 512 * 0.006))
    painter.drawEllipse(center, hole_radius * 1.15, hole_radius * 1.15)
    painter.end()
    return image


@lru_cache(maxsize=32)
def phaser_image(color_name: str, variant: int) -> QImage:
    """Port of make_phaser_hit with a configurable glow color."""
    rng = random.Random(0x7A5E0000 + variant % 8)
    image = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    center = QPointF(256, 256)
    radius = 512 * rng.uniform(0.10, 0.16)
    lobes = rng.randrange(9, 14)
    points = []
    for index in range(lobes):
        angle = index * math.tau / lobes
        points.append(
            center
            + QPointF(math.cos(angle), math.sin(angle)) * radius * 2.1 * rng.uniform(0.76, 1.24)
        )
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(26, 10, 8, 184))
    painter.drawPolygon(QPolygonF(points))
    color = QColor(color_name)
    gradient = QRadialGradient(center, radius * 2)
    for position, shade, alpha in [
        (0.0, QColor("#fffff2"), 255),
        (0.22, color.lighter(180), 242),
        (0.45, color, 204),
        (0.72, color.darker(150), 115),
        (1.0, color, 0),
    ]:
        shade.setAlpha(alpha)
        gradient.setColorAt(position, shade)
    painter.setBrush(gradient)
    painter.drawEllipse(center, radius * 2, radius * 2)
    streaks = rng.randrange(5, 11)
    for index in range(streaks):
        angle = index * math.tau / streaks + rng.uniform(-0.4, 0.4)
        direction = QPointF(math.cos(angle), math.sin(angle))
        length = 512 * rng.uniform(0.12, 0.34)
        for segment in range(8):
            fraction = segment / 8
            shade = QColor(color)
            shade.setAlpha(round(140 * (1 - fraction)))
            painter.setPen(QPen(shade, max(1, 512 * 0.03 * (1 - fraction))))
            painter.drawLine(
                center + direction * (radius + length * fraction),
                center + direction * (radius + length * (segment + 1) / 8),
            )
    painter.end()
    return image


def draw_crack(painter: QPainter, age: float, variant: int = 0):
    painter.save()
    painter.setOpacity(painter.opacity() * min(1, (1 - age) * 3))
    painter.drawImage(QRectF(-0.8, -0.8, 1.6, 1.6), crack_image(variant % 8))
    painter.restore()


def draw_phaser(painter: QPainter, color: QColor, phase: float):
    painter.save()
    expansion = 0.55 + 0.65 * (1 - (1 - phase) ** 3)
    painter.setOpacity(painter.opacity() * min(1, (1 - phase) * 3))
    painter.drawImage(
        QRectF(-expansion, -expansion, expansion * 2, expansion * 2), phaser_image(color.name(), 0)
    )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(color.lighter(160), 0.04 * (1 - phase)))
    radius = 0.15 + phase * 1.1
    painter.drawEllipse(QPointF(), radius, radius)
    painter.restore()
