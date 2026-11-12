import cv2
import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget


def pixmap_from_bgr(image: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return QPixmap.fromImage(
        QImage(rgb.data, width, height, rgb.strides[0], QImage.Format.Format_RGB888).copy()
    )


class CropCanvas(QWidget):
    def __init__(self, image: np.ndarray):
        super().__init__()
        self.image = image
        self.preview = pixmap_from_bgr(image).scaled(
            520, 420, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self.setFixedSize(self.preview.size())
        side = min(self.width(), self.height())
        self.selection = QRect((self.width() - side) // 2, (self.height() - side) // 2, side, side)
        self.start = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.preview)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        painter.drawPixmap(self.selection, self.preview, self.selection)
        painter.setPen(QPen(QColor("#ffbe55"), 2))
        painter.drawRect(self.selection.adjusted(1, 1, -1, -1))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.start is None:
            return
        point = event.position().toPoint()
        left = max(0, min(self.start.x(), point.x()))
        top = max(0, min(self.start.y(), point.y()))
        side = max(1, min(abs(point.x() - self.start.x()), abs(point.y() - self.start.y())))
        side = min(side, self.width() - left, self.height() - top)
        self.selection = QRect(left, top, side, side)
        self.update()

    def mouseReleaseEvent(self, event):
        self.start = None

    def cropped(self) -> np.ndarray:
        scale = self.image.shape[1] / self.width()
        x, y = round(self.selection.x() * scale), round(self.selection.y() * scale)
        side = round(self.selection.width() * scale)
        if side < 24:
            raise ValueError("裁剪区域至少需要 24×24 像素")
        return self.image[y : y + side, x : x + side].copy()


class CropDialog(QDialog):
    def __init__(self, image: np.ndarray, parent=None):
        super().__init__(parent)
        self.setWindowTitle("裁剪目标头像")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("拖动选择方形头像区域，默认使用居中裁剪。"))
        self.canvas = CropCanvas(image)
        layout.addWidget(self.canvas, alignment=Qt.AlignmentFlag.AlignCenter)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
