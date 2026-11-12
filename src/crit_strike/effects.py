import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen


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
    progress = min(1.0, max(0.0, elapsed / effect.duration))
    phase = (progress * effect.hits) % 1.0
    painter.save()
    painter.translate(center)
    painter.setOpacity(min(1.0, (1 - progress) * 5))
    color = QColor(effect.color)
    painter.setPen(QPen(color, 3))
    painter.setBrush(QColor(0, 0, 0, 0))
    radius = size * (0.12 + phase * 0.4)
    painter.drawEllipse(QPointF(0, 0), radius, radius)
    if effect.renderer == "hammer":
        painter.save()
        painter.rotate(-55 + 75 * math.sin(phase * math.pi))
        painter.setPen(QPen(QColor("#171c25"), 3))
        painter.setBrush(QColor("#f0c27b"))
        painter.drawRoundedRect(QRectF(-size * 0.035, -size * 0.48, size * 0.07, size * 0.5), 3, 3)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(-size * 0.22, -size * 0.55, size * 0.44, size * 0.18), 6, 6)
        painter.restore()
    count = 12 if effect.renderer == "burst" else 8
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
