"""Render reproducible effect previews over generated artwork, using the desktop renderer."""

from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from crit_strike.effects import draw_effect, load_effects


def backdrop(painter, center):
    painter.setPen(QColor("#42556a"))
    painter.setBrush(QColor("#2a3c4e"))
    painter.drawRoundedRect(QRectF(center.x() - 34, center.y() - 34, 68, 68), 12, 12)
    painter.setPen(QColor("#f0c274"))
    painter.setFont(QFont("Arial", 26, QFont.Weight.Bold))
    painter.drawText(QRectF(center.x() - 34, center.y() - 34, 68, 68), 0x84, "K")


def main():
    app = QApplication.instance() or QApplication([])
    output = Path("artifacts")
    output.mkdir(exist_ok=True)
    effects, _ = load_effects(output / "unused-mods")
    renderers = ["hammer", "burst", "glass", "phaser"]
    sheet = QImage(2520, 2240, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#111820"))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for row, renderer in enumerate(renderers):
        effect = effects[renderer]
        phases = [0.12, 0.36, 0.49, 0.58, 0.75, 0.94]
        if renderer in {"burst", "glass", "phaser"}:
            phases = [0.12, 0.23, 0.30, 0.48, 0.70, 0.94]
        for column, phase in enumerate(phases):
            center = QPointF(column * 420 + 210, row * 560 + 320)
            backdrop(painter, center)
            draw_effect(painter, effect, center, phase * effect.duration / effect.hits, effect.size)
    painter.end()
    sheet.save(str(output / "impact-keyframes.png"))

    writer = cv2.VideoWriter(
        str(output / "impact-preview.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (960, 1080)
    )
    if not writer.isOpened():
        raise RuntimeError("Preview video encoder unavailable")
    try:
        for frame in range(180):
            image = QImage(960, 1080, QImage.Format.Format_RGB32)
            image.fill(QColor("#111820"))
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for index, renderer in enumerate(renderers):
                effect = effects[renderer]
                center = QPointF(240 + index % 2 * 480, 290 + index // 2 * 540)
                backdrop(painter, center)
                painter.setPen(QColor("#eaf0f5"))
                painter.setFont(QFont("Arial", 15))
                painter.drawText(QPointF(center.x() - 75, center.y() - 230), renderer.upper())
                draw_effect(painter, effect, center, (frame / 30) % 2, effect.size)
            painter.end()
            pixels = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(1080, 960, 4)
            writer.write(cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR))
    finally:
        writer.release()
    print("Generated keyframes and six-second motion preview in artifacts/")
    app.quit()


if __name__ == "__main__":
    main()
