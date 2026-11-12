import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF, QRadialGradient


@dataclass(frozen=True)
class Effect:
    id: str
    name: str
    renderer: str
    color: str
    duration: float
    hits: int
    size: int

    @classmethod
    def load(cls, path: Path) -> "Effect":
        if path.stat().st_size > 16_384:
            raise ValueError("模组文件不能超过 16 KB")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.pop("version", None) != 1:
                raise ValueError("不支持的模组版本")
            effect = cls(**data)
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", effect.id):
                raise ValueError("模组 ID 格式无效")
            if not isinstance(effect.name, str) or not 1 <= len(effect.name) <= 40:
                raise ValueError("模组名称无效")
            if effect.renderer not in {"hammer", "burst", "ring"}:
                raise ValueError("模组绘制器不受支持")
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", effect.color):
                raise ValueError("颜色必须为 #RRGGBB")
            if type(effect.duration) not in (int, float) or not 0.4 <= effect.duration <= 5:
                raise ValueError("时长范围为 0.4～5 秒")
            if type(effect.hits) is not int or not 1 <= effect.hits <= 5:
                raise ValueError("打击次数范围为 1～5")
            if type(effect.size) is not int or not 60 <= effect.size <= 300:
                raise ValueError("大小范围为 60～300")
            return effect
        except (TypeError, KeyError, AttributeError) as error:
            raise ValueError("模组字段格式无效") from error

    def to_json(self) -> dict:
        return {"version": 1, **asdict(self)}


def load_effects(user_directory: Path) -> tuple[dict[str, Effect], list[str]]:
    effects = {}
    errors = []
    directories = [Path(__file__).parent / "mods", user_directory]
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            try:
                effect = Effect.load(path)
                if effect.id in effects:
                    raise ValueError("模组 ID 重复")
                effects[effect.id] = effect
            except (ValueError, OSError):
                errors.append("一个模组加载失败，请检查格式或重复 ID")
    return effects, errors


def draw_effect(
    painter: QPainter, effect: Effect, center: QPointF, elapsed: float, size: float
) -> None:
    if elapsed < 0 or elapsed >= effect.duration:
        return
    progress = min(1.0, max(0.0, elapsed / effect.duration))
    phase = (progress * effect.hits) % 1.0
    painter.save()
    painter.translate(center)
    painter.setOpacity(min(1.0, (1 - progress) * 5))
    color = QColor(effect.color)
    if effect.renderer in {"hammer", "burst"}:
        painter.scale(size, size)
        if effect.renderer == "hammer":
            draw_hammer(painter, color, phase)
        else:
            draw_burst(painter, color, phase)
        painter.restore()
        return
    painter.setPen(QPen(color, 3))
    painter.setBrush(QColor(0, 0, 0, 0))
    radius = size * (0.12 + phase * 0.4)
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    count = 8
    for index in range(count):
        angle = index * math.tau / count
        inner = size * (0.08 + phase * 0.18)
        outer = inner + size * 0.12 * (1 - phase)
        painter.drawLine(
            QPointF(math.cos(angle) * inner, math.sin(angle) * inner),
            QPointF(math.cos(angle) * outer, math.sin(angle) * outer),
        )
    if effect.renderer == "ring":
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(QPointF(0, 0), radius * 0.7, radius * 0.7)
    painter.restore()


def draw_impact(painter: QPainter, color: QColor, age: float, strength: float) -> None:
    """Shared contact flash, expanding shockwaves and deterministic ballistic fragments."""
    if not 0 <= age < 1:
        return
    painter.save()
    painter.setOpacity(painter.opacity() * (1 - age) ** 0.7)
    painter.setPen(QPen(color, 0.025))
    painter.setBrush(QColor(0, 0, 0, 0))
    expansion = 1 - (1 - age) ** 3
    radius = strength * (0.18 + expansion * 1.05)
    painter.setPen(QPen(color, max(0.012, 0.085 * (1 - age))))
    painter.drawEllipse(QPointF(0, 0.04), radius, radius * 0.48)
    painter.setPen(QPen(QColor("#fff3d0"), max(0.008, 0.04 * (1 - age))))
    painter.drawEllipse(QPointF(0, 0.04), radius * 0.78, radius * 0.38)

    glow_radius = strength * (0.25 + expansion * 0.45)
    glow = QRadialGradient(QPointF(0, 0), glow_radius)
    glow.setColorAt(0, QColor(255, 255, 240, round(245 * (1 - age) ** 2)))
    glow.setColorAt(
        0.35, QColor(color.red(), color.green(), color.blue(), round(180 * (1 - age) ** 2))
    )
    glow.setColorAt(1, QColor(0, 0, 0, 0))
    painter.setPen(QPen(QColor(0, 0, 0, 0)))
    painter.setBrush(glow)
    painter.drawEllipse(QPointF(0, 0), glow_radius, glow_radius)

    # Fixed angular offsets and speeds keep each fragment on a continuous trajectory.
    for index in range(26):
        angle = index * math.tau / 26 + math.sin(index * 7.13) * 0.1
        speed = strength * (0.6 + (index % 7) * 0.13)
        distance = 0.08 + speed * age
        gravity = 0.65 * age * age
        tip = QPointF(math.cos(angle) * distance, math.sin(angle) * distance + gravity)
        tail_distance = max(0.04, distance - 0.12 * (1 - age))
        tail = QPointF(math.cos(angle) * tail_distance, math.sin(angle) * tail_distance + gravity)
        painter.setPen(QPen(QColor("#fff5d7") if index % 3 else color, 0.015 + (index % 3) * 0.007))
        painter.drawLine(tail, tip)
        painter.setBrush(color if index % 2 else QColor("#fff0b0"))
        painter.setPen(QPen(QColor(0, 0, 0, 0)))
        chip = 0.018 + (index % 4) * 0.006
        painter.drawRect(QRectF(tip.x() - chip / 2, tip.y() - chip / 2, chip, chip))
    painter.restore()


def draw_hammer(painter: QPainter, color: QColor, phase: float) -> None:
    contact = 0.48
    if phase < 0.32:
        lift = 1 - (1 - phase / 0.32) ** 2
        x, y, angle = 0.45 + 0.37 * lift, -0.65 - 0.4 * lift, -25 - 35 * lift
    elif phase < contact:
        swing = ((phase - 0.32) / (contact - 0.32)) ** 2.7
        x, y, angle = 0.82 * (1 - swing), -1.05 * (1 - swing), -60 + 72 * swing
        painter.save()
        painter.setOpacity(painter.opacity() * 0.4)
        painter.setPen(QPen(color, 0.1))
        for offset in [-0.22, 0, 0.22]:
            painter.drawLine(QPointF(x + 0.28 + offset, y - 0.38), QPointF(x + offset, y))
        painter.restore()
    elif phase < 0.60:
        # Hold the contact pose for a readable impact before the rebound.
        x, y, angle = 0, 0, 12
    else:
        rebound = (phase - 0.60) / 0.40
        x, y, angle = -0.12 * rebound, -0.22 * math.sin(rebound * math.pi / 2), 12 - 25 * rebound

    impact_age = (phase - contact) / (1 - contact)
    if impact_age >= 0:
        shake = 0.055 * math.exp(-impact_age * 9)
        painter.translate(math.sin(impact_age * 85) * shake, math.cos(impact_age * 73) * shake)
        draw_impact(painter, color, impact_age, 0.9)
        painter.save()
        painter.setOpacity(painter.opacity() * (1 - impact_age))
        painter.setPen(QPen(QColor("#251c24"), 0.038))
        for index in range(7):
            direction = index * math.tau / 7
            length = 0.38 + (index % 3) * 0.13
            points = QPolygonF(
                [
                    QPointF(0, 0.06),
                    QPointF(
                        math.cos(direction + 0.14) * length * 0.5,
                        math.sin(direction + 0.14) * length * 0.28 + 0.06,
                    ),
                    QPointF(
                        math.cos(direction) * length, math.sin(direction) * length * 0.55 + 0.06
                    ),
                ]
            )
            painter.drawPolyline(points)
        painter.restore()

    painter.save()
    painter.setOpacity(painter.opacity() * min(1.0, (1 - phase) / 0.18))
    painter.translate(x, y - 0.20)
    painter.rotate(angle)
    # Handle, ferrule, side face and bevels give the hammer a solid silhouette.
    painter.setPen(QPen(QColor("#151b26"), 0.025))
    handle = QLinearGradient(-0.07, 0, 0.07, 0)
    handle.setColorAt(0, QColor("#4a2d24"))
    handle.setColorAt(0.5, QColor("#d0a06b"))
    handle.setColorAt(1, QColor("#68402e"))
    painter.setBrush(handle)
    painter.drawRoundedRect(QRectF(-0.065, -0.91, 0.13, 0.94), 0.025, 0.025)
    painter.setPen(QPen(QColor("#382722"), 0.025))
    for index in range(7):
        grip_y = -0.83 + index * 0.055
        painter.drawLine(QPointF(-0.055, grip_y), QPointF(0.055, grip_y + 0.035))
    metal = QLinearGradient(0, -0.20, 0, 0.20)
    metal.setColorAt(0, QColor("#f2f5fa"))
    metal.setColorAt(0.18, QColor("#b5c5d7"))
    metal.setColorAt(0.48, color.darker(125))
    metal.setColorAt(1, QColor("#293747"))
    painter.setBrush(metal)
    painter.setPen(QPen(QColor("#18202b"), 0.03))
    painter.drawRoundedRect(QRectF(-0.48, -0.20, 0.96, 0.4), 0.045, 0.045)
    painter.setBrush(QColor("#354757"))
    painter.drawRoundedRect(QRectF(0.34, -0.18, 0.16, 0.36), 0.025, 0.025)
    painter.setPen(QPen(QColor("#fff2ca"), 0.022))
    painter.drawLine(QPointF(-0.41, -0.15), QPointF(0.29, -0.15))
    painter.setPen(QPen(color, 0.045))
    painter.drawLine(QPointF(-0.19, -0.10), QPointF(-0.10, 0.10))
    painter.drawLine(QPointF(-0.02, -0.10), QPointF(0.07, 0.10))
    painter.restore()


def draw_burst(painter: QPainter, color: QColor, phase: float) -> None:
    contact = 0.22
    if phase < contact:
        charge = phase / contact
        radius = 0.30 * (1 - charge) + 0.07
        painter.setPen(QPen(color, 0.035))
        painter.setBrush(color.lighter(150))
        painter.drawEllipse(QPointF(0, 0), radius * 0.22, radius * 0.22)
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawEllipse(QPointF(0, 0), radius, radius)
        for index in range(8):
            angle = index * math.tau / 8 + charge * 0.4
            painter.drawLine(
                QPointF(math.cos(angle) * radius, math.sin(angle) * radius),
                QPointF(math.cos(angle) * (radius + 0.16), math.sin(angle) * (radius + 0.16)),
            )
        return

    age = (phase - contact) / (1 - contact)
    shake = 0.065 * math.exp(-age * 11)
    painter.translate(math.sin(age * 91) * shake, math.cos(age * 79) * shake)
    painter.save()
    painter.setOpacity(painter.opacity() * (1 - age) ** 1.4)
    # Expanding lobes sit behind a sharp, white-hot center and the flying fragments.
    painter.setPen(QPen(QColor(0, 0, 0, 0)))
    for index in range(9):
        angle = index * math.tau / 9
        distance = 0.12 + age * 0.55
        radius = 0.13 + age * 0.20
        painter.setBrush(color.darker(180 + index % 3 * 35))
        painter.drawEllipse(
            QPointF(math.cos(angle) * distance, math.sin(angle) * distance), radius, radius
        )
    radius = 0.28 + (1 - (1 - age) ** 3) * 0.6
    points = []
    for index in range(24):
        angle = index * math.tau / 24
        reach = radius * (1 if index % 2 == 0 else 0.33)
        points.append(QPointF(math.cos(angle) * reach, math.sin(angle) * reach))
    painter.setPen(QPen(color, 0.05))
    painter.setBrush(QColor("#fff7c2"))
    painter.drawPolygon(QPolygonF(points))
    painter.restore()
    draw_impact(painter, color, age, 1.15)
