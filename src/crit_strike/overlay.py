import time
from dataclasses import dataclass

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from crit_strike.effects import Effect, draw_effect
from crit_strike.models import Box, Monitor
from crit_strike.platform_windows import exclude_capture


@dataclass
class Playing:
    effect: Effect
    center: QPointF
    size: int
    started: float
    track_id: int | None


class Overlay(QWidget):
    picked = Signal(object)
    cancelled = Signal()

    def __init__(self, monitor: Monitor):
        super().__init__()
        self.monitor = monitor
        self.playing: list[Playing] = []
        self.selecting = False
        self.capture_safe = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Crit Strike effects")
        self._configure(False)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)

    def _configure(self, selecting: bool):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        flags |= Qt.WindowType.Tool
        if not selecting:
            flags |= Qt.WindowType.WindowTransparentForInput
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        logical = self.monitor.logical
        self.setGeometry(int(logical.x), int(logical.y), int(logical.w), int(logical.h))
        self.show()
        self.capture_safe = exclude_capture(int(self.winId()))

    def select(self, enabled: bool):
        self.selecting = enabled
        self._configure(enabled)
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        if enabled:
            self.activateWindow()
            self.setFocus()
        self.update()

    def play(self, effect: Effect, box: Box, size: int, track_id: int | None = None):
        x, y = box.center
        self.playing.append(
            Playing(
                effect,
                QPointF(x - self.monitor.logical.x, y - self.monitor.logical.y),
                size,
                time.monotonic(),
                track_id,
            )
        )
        self.timer.start()
        self.update()

    def stop(self):
        self.playing.clear()
        self.timer.stop()
        self.update()

    def tick(self):
        now = time.monotonic()
        self.playing = [item for item in self.playing if now - item.started < item.effect.duration]
        if not self.playing:
            self.timer.stop()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.selecting:
            painter.fillRect(self.rect(), QColor(10, 17, 28, 65))
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(
                self.rect().adjusted(30, 25, -30, -25),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                "左键选择打击位置 · 右键 / Esc 取消",
            )
        now = time.monotonic()
        for item in self.playing:
            draw_effect(painter, item.effect, item.center, now - item.started, item.size)

    def mousePressEvent(self, event: QMouseEvent):
        if not self.selecting:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(event.globalPosition())
        else:
            self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
