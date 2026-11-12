import argparse
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QPointF, QSignalBlocker, QSize, QStandardPaths, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from crit_strike.detection import Detector, Template, read_image
from crit_strike.effects import Effect, load_effects
from crit_strike.models import Box, Monitor
from crit_strike.overlay import Overlay
from crit_strike.platform_windows import Hotkeys, enable_dpi_awareness, monitor_layout
from crit_strike.storage import Store, atomic_json
from crit_strike.tracking import Tracker
from crit_strike.widgets import CropDialog
from crit_strike.worker import CaptureWorker

STYLE = """
QMainWindow, QDialog { background: #111820; color: #eaf0f5; }
QWidget { font-family: 'Inter', 'Microsoft YaHei UI'; font-size: 13px; color: #eaf0f5; }
QLabel#title { font-size: 30px; font-weight: 700; color: #ffbe55; }
QLabel#muted { color: #9caebb; }
QLabel#status { background: #1d2b36; border-radius: 8px; padding: 14px; color: #84dfc6; }
QListWidget { background: #18232e; border: 1px solid #2b3947; border-radius: 8px; }
QListWidget::item { padding: 10px; border-radius: 5px; margin: 3px; }
QListWidget::item:selected { background: #344351; }
QPushButton { background: #283746; border: 1px solid #3c4d5c; padding: 9px 15px;
              border-radius: 6px; }
QPushButton:hover { background: #3a4c5c; }
QPushButton:disabled { color: #687886; background: #1a252e; }
QPushButton#primary { background: #ffbe55; color: #151d25; border: 0; font-weight: 700; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #18232e;
    border: 1px solid #3c4d5c; border-radius: 5px; padding: 7px; min-height: 21px; }
QComboBox QAbstractItemView { background: #243341; selection-background-color: #40566a; }
QCheckBox { spacing: 8px; }
QMenu { background: #243341; padding: 5px; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #40566a; }
QToolTip { background: #243341; color: #ffffff; border: 1px solid #40566a; }
"""


def app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor("#172330"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#ffbe55"))
    painter.setBrush(QColor("#ffbe55"))
    painter.drawRoundedRect(17, 13, 34, 15, 4, 4)
    painter.drawRoundedRect(29, 25, 9, 28, 3, 3)
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(
        self, store: Store, monitors: list[Monitor] | None = None, register_hotkeys: bool = True
    ):
        super().__init__()
        self.store = store
        self.effects, mod_errors = load_effects(store.mods)
        self.monitors = monitor_layout() if monitors is None else monitors
        self.worker: CaptureWorker | None = None
        self.generation = 0
        self.running = False
        self.closing = False
        self.selecting = False
        self.tracker = Tracker()
        self.last_scan = None
        self.trigger_count = 0
        self.overlays = {monitor.index: Overlay(monitor) for monitor in self.monitors}
        for overlay in self.overlays.values():
            overlay.picked.connect(self.picked)
            overlay.cancelled.connect(self.cancel_selection)
        self.setWindowTitle("Crit Strike · 全桌面头像特效")
        self.setWindowIcon(app_icon())
        self.resize(900, 680)
        self.setMinimumSize(780, 620)
        self.build_ui()
        self.refresh_targets()
        self.refresh_effects()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self.position_timer = QTimer(self)
        self.position_timer.setInterval(200)
        self.position_timer.timeout.connect(self.update_exclusions)
        self.position_timer.start()
        self.hotkeys = Hotkeys()
        QApplication.instance().installNativeEventFilter(self.hotkeys)
        self.hotkeys.events.pressed.connect(self.hotkey)
        failed = self.hotkeys.register() if register_hotkeys else []
        self.build_tray()
        if mod_errors:
            self.status.setText("部分模组加载失败，可重新导入修复后的模组")
        if failed:
            self.status.setText("部分快捷键被其他程序占用，请使用窗口或托盘按钮")
        application = QApplication.instance()
        application.screenAdded.connect(self.screen_changed)
        application.screenRemoved.connect(self.screen_changed)
        for screen in application.screens():
            screen.geometryChanged.connect(self.screen_changed)
            screen.logicalDotsPerInchChanged.connect(self.screen_changed)

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(15)
        title = QLabel("CRIT STRIKE")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("全桌面头像识别 · 停留三秒触发 · 本地运行")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        self.status = QLabel("已暂停，导入头像后启动检测")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 12, 0)
        left_layout.addWidget(QLabel("目标头像"))
        self.target_list = QListWidget()
        self.target_list.setIconSize(QSize(48, 48))
        self.target_list.currentRowChanged.connect(self.select_target)
        left_layout.addWidget(self.target_list)
        target_buttons = QHBoxLayout()
        self.add_button = QPushButton("导入头像")
        self.add_button.clicked.connect(self.import_avatar)
        target_buttons.addWidget(self.add_button)
        self.remove_button = QPushButton("删除")
        self.remove_button.clicked.connect(self.remove_target)
        target_buttons.addWidget(self.remove_button)
        left_layout.addLayout(target_buttons)
        split.addWidget(left)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 0, 0, 0)
        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(60)
        self.name_edit.editingFinished.connect(self.target_changed)
        self.enabled = QCheckBox("参与自动识别")
        self.enabled.toggled.connect(self.target_changed)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(0.70, 0.99)
        self.threshold.setSingleStep(0.01)
        self.threshold.setValue(0.88)
        self.threshold.valueChanged.connect(self.target_changed)
        self.threshold.setToolTip("越高越严格。默认 0.88，误触发时提高，漏检时适当降低。")
        self.effect_combo = QComboBox()
        self.effect_combo.currentIndexChanged.connect(self.target_changed)
        form.addRow("目标名称", self.name_edit)
        form.addRow("目标状态", self.enabled)
        form.addRow("匹配阈值", self.threshold)
        form.addRow("打击特效", self.effect_combo)
        self.size = QSpinBox()
        self.size.setRange(60, 300)
        self.size.setValue(self.store.settings.effect_size)
        self.size.valueChanged.connect(self.settings_changed)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.1, 2)
        self.interval.setSingleStep(0.1)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(self.store.settings.interval)
        self.interval.valueChanged.connect(self.settings_changed)
        self.minimum = QSpinBox()
        self.minimum.setRange(24, 256)
        self.minimum.setValue(self.store.settings.minimum)
        self.minimum.valueChanged.connect(self.settings_changed)
        self.maximum = QSpinBox()
        self.maximum.setRange(24, 256)
        self.maximum.setValue(self.store.settings.maximum)
        self.maximum.valueChanged.connect(self.settings_changed)
        self.sound = QCheckBox("打击时播放系统提示音")
        self.sound.setChecked(self.store.settings.sound)
        self.sound.toggled.connect(self.settings_changed)
        form.addRow("特效大小", self.size)
        form.addRow("检测间隔", self.interval)
        form.addRow("头像最小像素", self.minimum)
        form.addRow("头像最大像素", self.maximum)
        form.addRow("声音", self.sound)
        right_layout.addLayout(form)
        mod_buttons = QHBoxLayout()
        preview = QPushButton("预览效果")
        preview.clicked.connect(self.preview)
        mod_buttons.addWidget(preview)
        import_mod = QPushButton("导入模组")
        import_mod.clicked.connect(self.import_mod)
        mod_buttons.addWidget(import_mod)
        right_layout.addLayout(mod_buttons)
        help_label = QLabel("全局设置适用于全部目标。修改识别参数后需重新启动检测。")
        help_label.setObjectName("muted")
        help_label.setWordWrap(True)
        right_layout.addWidget(help_label)
        right_layout.addStretch()
        split.addWidget(right)
        split.setSizes([340, 480])
        layout.addWidget(split, 1)
        controls = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(["自动识别", "手动选点"])
        self.mode.currentIndexChanged.connect(self.mode_changed)
        controls.addWidget(self.mode)
        self.start_button = QPushButton("启动检测")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.toggle)
        controls.addWidget(self.start_button, 1)
        stop = QPushButton("立即停止 · F9")
        stop.clicked.connect(self.stop_all)
        controls.addWidget(stop)
        tray_button = QPushButton("收起到托盘")
        tray_button.clicked.connect(self.hide_to_tray)
        controls.addWidget(tray_button)
        layout.addLayout(controls)
        shortcut_label = QLabel("F8 暂停 / 恢复    F9 停止全部    F10 手动选点    Esc 取消选点")
        shortcut_label.setObjectName("muted")
        layout.addWidget(shortcut_label)

    def build_tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Crit Strike")
        menu = QMenu(self)
        for title, callback in [
            ("打开主窗口", self.restore_window),
            ("暂停 / 恢复", self.toggle),
            ("手动选点", self.manual),
            ("立即停止", self.stop_all),
            ("退出", self.close),
        ]:
            action = QAction(title, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self.restore_window()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
        self.tray.show()

    def current_target(self):
        row = self.target_list.currentRow()
        return self.store.targets[row] if 0 <= row < len(self.store.targets) else None

    def refresh_targets(self):
        row = self.target_list.currentRow()
        with QSignalBlocker(self.target_list):
            self.target_list.clear()
            for target in self.store.targets:
                suffix = "" if target.enabled else " · 已停用"
                item = QListWidgetItem(
                    QIcon(str(self.store.image_path(target.id))), target.name + suffix
                )
                self.target_list.addItem(item)
        self.target_list.setCurrentRow(max(0, min(row, len(self.store.targets) - 1)))
        self.select_target()

    def refresh_effects(self):
        with QSignalBlocker(self.effect_combo):
            self.effect_combo.clear()
            for effect in self.effects.values():
                self.effect_combo.addItem(effect.name, effect.id)
        self.select_target()

    def select_target(self, *_):
        target = self.current_target()
        for widget in [self.name_edit, self.enabled, self.threshold, self.remove_button]:
            widget.setEnabled(target is not None)
        with (
            QSignalBlocker(self.name_edit),
            QSignalBlocker(self.enabled),
            QSignalBlocker(self.threshold),
            QSignalBlocker(self.effect_combo),
        ):
            self.name_edit.setText(target.name if target else "")
            self.enabled.setChecked(target.enabled if target else False)
            self.threshold.setValue(target.threshold if target else 0.88)
            if target:
                self.effect_combo.setCurrentIndex(max(0, self.effect_combo.findData(target.effect)))

    def target_changed(self, *_):
        target = self.current_target()
        if target is None:
            return
        self.pause()
        target.name = self.name_edit.text().strip() or "新目标"
        target.enabled = self.enabled.isChecked()
        target.threshold = self.threshold.value()
        target.effect = self.effect_combo.currentData() or "hammer"
        item = self.target_list.currentItem()
        item.setText(target.name + ("" if target.enabled else " · 已停用"))
        self.save_timer.start(300)

    def settings_changed(self, *_):
        self.pause()
        if self.minimum.value() > self.maximum.value():
            self.maximum.setValue(self.minimum.value())
        settings = self.store.settings
        settings.interval = self.interval.value()
        settings.minimum = self.minimum.value()
        settings.maximum = self.maximum.value()
        settings.effect_size = self.size.value()
        settings.sound = self.sound.isChecked()
        self.save_timer.start(300)

    def save(self):
        try:
            self.store.save()
        except OSError:
            self.status.setText("设置保存失败，请检查本地应用数据目录的可写权限")

    def import_avatar(self):
        self.pause()
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入头像", "", "头像图片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not filename:
            return
        try:
            dialog = CropDialog(read_image(Path(filename)), self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.store.add("目标 " + str(len(self.store.targets) + 1), dialog.canvas.cropped())
                self.refresh_targets()
                self.target_list.setCurrentRow(len(self.store.targets) - 1)
        except (ValueError, OSError) as error:
            self.status.setText(str(error) if isinstance(error, ValueError) else "图片读写失败")

    def remove_target(self):
        target = self.current_target()
        if target is None:
            return
        if (
            QMessageBox.question(self, "删除目标", "删除选中的目标及本地头像副本？")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.pause()
        try:
            self.store.remove(target.id)
            self.refresh_targets()
        except OSError:
            self.status.setText("删除未完成，请检查本地文件权限")

    def import_mod(self):
        self.pause()
        filename, _ = QFileDialog.getOpenFileName(self, "导入特效模组", "", "模组 (*.json)")
        if not filename:
            return
        try:
            effect = Effect.load(Path(filename))
            if effect.id in self.effects:
                raise ValueError("模组 ID 已存在，请在模组文件中使用新的 ID")
            atomic_json(self.store.mods / f"{effect.id}.json", effect.to_json())
            self.effects[effect.id] = effect
            self.refresh_effects()
            self.effect_combo.setCurrentIndex(self.effect_combo.findData(effect.id))
            self.status.setText("模组已导入，可选择后预览")
        except (ValueError, OSError) as error:
            self.status.setText(str(error) if isinstance(error, ValueError) else "模组文件读写失败")

    def rebuild_overlays(self):
        monitors = monitor_layout()
        if monitors == self.monitors:
            return
        for overlay in self.overlays.values():
            overlay.close()
            overlay.deleteLater()
        self.monitors = monitors
        self.overlays = {monitor.index: Overlay(monitor) for monitor in monitors}
        for overlay in self.overlays.values():
            overlay.picked.connect(self.picked)
            overlay.cancelled.connect(self.cancel_selection)

    def toggle(self):
        if self.mode.currentIndex() == 1:
            self.manual()
        elif self.running:
            self.pause()
        else:
            self.start_detection()

    def start_detection(self):
        if self.worker is not None:
            self.status.setText("正在结束上一轮检测，请稍后启动")
            return
        self.cancel_selection()
        try:
            self.rebuild_overlays()
            if not all(overlay.capture_safe for overlay in self.overlays.values()):
                raise ValueError(
                    "特效层无法排除截图，自动模式已暂停。请使用受支持的 Windows 版本。"
                )
            templates = [
                Template(target.id, read_image(self.store.image_path(target.id)), target.threshold)
                for target in self.store.targets
                if target.enabled
            ]
            if not templates:
                raise ValueError("请先导入并启用一个头像")
        except (ValueError, OSError, RuntimeError) as error:
            self.status.setText(
                str(error) if not isinstance(error, OSError) else "目标图片读取失败，请重新导入"
            )
            return
        self.generation += 1
        self.tracker.clear()
        self.last_scan = None
        settings = self.store.settings
        detector = Detector(templates, settings.minimum, settings.maximum)
        self.worker = CaptureWorker(detector, self.monitors, settings.interval, self.generation)
        self.worker.scanned.connect(self.scanned)
        self.worker.failed.connect(self.capture_failed)
        self.worker.finished.connect(self.worker_finished)
        self.running = True
        self.update_exclusions()
        self.worker.start()
        self.start_button.setText("暂停检测 · F8")
        self.status.setText("正在检测全桌面，目标稳定三秒后触发")

    def update_exclusions(self):
        if self.worker is None:
            return
        exclusions = {}
        if self.isVisible() and not self.isMinimized():
            rect = self.frameGeometry()
            for monitor in self.monitors:
                left = max(rect.x(), monitor.logical.x)
                top = max(rect.y(), monitor.logical.y)
                right = min(rect.x() + rect.width(), monitor.logical.x + monitor.logical.w)
                bottom = min(rect.y() + rect.height(), monitor.logical.y + monitor.logical.h)
                if right <= left or bottom <= top:
                    continue
                scale_x = monitor.physical.w / monitor.logical.w
                scale_y = monitor.physical.h / monitor.logical.h
                exclusions[monitor.index] = [
                    Box(
                        monitor.physical.x + (left - monitor.logical.x) * scale_x,
                        monitor.physical.y + (top - monitor.logical.y) * scale_y,
                        (right - left) * scale_x,
                        (bottom - top) * scale_y,
                    )
                ]
        self.worker.exclusions = exclusions

    def scanned(self, detections, captured_at: float, duration: float, generation: int):
        if generation != self.generation or not self.running:
            return
        now = time.monotonic()
        if now - captured_at > max(2, duration + 0.5):
            self.tracker.clear()
            return
        # Grace includes one actual scan interval, so slow displays do not reset every track.
        gap = 0 if self.last_scan is None else captured_at - self.last_scan
        if gap > max(2, self.tracker.grace * 2):
            self.tracker.clear()
        self.tracker.grace = max(0.6, duration + self.store.settings.interval + 0.15, gap + 0.15)
        self.last_scan = captured_at
        ready = self.tracker.update(detections, captured_at)
        visible_tracks = {
            track.id: track
            for track in self.tracker.tracks.values()
            if track.last_seen == captured_at
        }
        for overlay in self.overlays.values():
            retained = []
            for item in overlay.playing:
                if item.track_id is None:
                    retained.append(item)
                elif item.track_id in visible_tracks:
                    detection = visible_tracks[item.track_id].detection
                    logical = overlay.monitor.to_logical(detection.box)
                    x, y = logical.center
                    item.center = QPointF(
                        x - overlay.monitor.logical.x, y - overlay.monitor.logical.y
                    )
                    retained.append(item)
            overlay.playing = retained
        for track in ready:
            if self.playing_count() >= 4:
                break
            target = next(
                (item for item in self.store.targets if item.id == track.detection.target_id), None
            )
            if target is None:
                continue
            effect = self.effects.get(target.effect, self.effects["hammer"])
            overlay = self.overlays[track.detection.monitor]
            overlay.play(
                effect,
                overlay.monitor.to_logical(track.detection.box),
                self.effect_size(effect),
                track.id,
            )
            self.tracker.mark_fired(track.id)
            self.trigger_count += 1
            self.play_sound()
        self.status.setText(
            f"检测中 · 当前 {len(detections)} 处匹配 · "
            f"本轮 {duration * 1000:.0f} ms · 已触发 {self.trigger_count} 次"
        )

    def effect_size(self, effect: Effect) -> int:
        return round(effect.size * self.store.settings.effect_size / 130)

    def playing_count(self):
        return sum(len(overlay.playing) for overlay in self.overlays.values())

    def capture_failed(self, message):
        self.pause()
        self.status.setText(message)

    def worker_finished(self):
        worker = self.worker
        self.worker = None
        if worker:
            worker.deleteLater()
        if self.closing:
            self.close()

    def pause(self):
        self.running = False
        self.generation += 1
        self.tracker.clear()
        if self.worker:
            self.worker.stop()
        if hasattr(self, "start_button"):
            self.start_button.setText("选择打击位置" if self.mode.currentIndex() else "启动检测")
            self.status.setText("已暂停")

    def mode_changed(self, *_):
        self.stop_all()

    def manual(self):
        self.pause()
        try:
            self.rebuild_overlays()
        except RuntimeError as error:
            self.status.setText(str(error))
            return
        with QSignalBlocker(self.mode):
            self.mode.setCurrentIndex(1)
        self.start_button.setText("选择打击位置")
        self.selecting = True
        for overlay in self.overlays.values():
            overlay.stop()
            overlay.select(True)
        self.status.setText("手动选点中，右键或 Esc 取消")

    def cancel_selection(self):
        if self.selecting:
            for overlay in self.overlays.values():
                overlay.select(False)
            self.selecting = False

    def picked(self, point):
        self.cancel_selection()
        self.play_at(point)
        self.status.setText("手动特效已播放，可再次选点")

    def play_at(self, point: QPointF):
        if self.playing_count() >= 4:
            self.status.setText("最多同时播放四个特效，请稍后重试")
            return
        effect = self.effects.get(self.effect_combo.currentData(), self.effects["hammer"])
        for overlay in self.overlays.values():
            rect = overlay.monitor.logical
            if rect.x <= point.x() < rect.x + rect.w and rect.y <= point.y() < rect.y + rect.h:
                overlay.play(
                    effect, Box(point.x() - 20, point.y() - 20, 40, 40), self.effect_size(effect)
                )
                self.play_sound()
                break

    def preview(self):
        self.pause()
        point = self.geometry().center()
        self.play_at(QPointF(point))

    def play_sound(self):
        if self.store.settings.sound:
            QApplication.beep()

    def stop_all(self):
        self.pause()
        self.cancel_selection()
        for overlay in self.overlays.values():
            overlay.stop()

    def screen_changed(self, *_):
        self.stop_all()
        self.status.setText("显示器布局已变化，重新启动检测后更新屏幕配置")

    def hotkey(self, identifier):
        if identifier == 1:
            self.toggle()
        elif identifier == 2:
            self.stop_all()
        elif identifier == 3:
            self.manual()

    def hide_to_tray(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.hide()
        else:
            self.showMinimized()

    def restore_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.closing = True
        self.stop_all()
        if self.worker is not None:
            event.ignore()
            self.status.setText("正在结束检测线程…")
            return
        self.save_timer.stop()
        self.save()
        self.hotkeys.close()
        QApplication.instance().removeNativeEventFilter(self.hotkeys)
        self.tray.hide()
        for overlay in self.overlays.values():
            overlay.close()
        event.accept()
        QApplication.instance().quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Crit Strike desktop effects")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Launch with temporary empty data"
    )
    args = parser.parse_args()
    enable_dpi_awareness()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("CritStrike")
    app.setApplicationName("CritStrike")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    temporary = (
        tempfile.TemporaryDirectory(prefix="crit-strike-smoke-") if args.smoke_test else None
    )
    root = (
        Path(temporary.name)
        if temporary
        else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
    )
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "app.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "Crit Strike", "应用已经运行，请从系统托盘打开。")
        return 1
    try:
        store = Store(root)
        store.load()
        window = MainWindow(store, register_hotkeys=not args.smoke_test)
    except (OSError, ValueError, RuntimeError) as error:
        if args.smoke_test:
            print("Startup smoke test failed", file=sys.stderr)
        else:
            QMessageBox.critical(None, "启动失败", str(error))
        lock.unlock()
        return 1
    window.show()
    if args.smoke_test:
        QTimer.singleShot(300, window.preview)
        QTimer.singleShot(1800, window.close)
    result = app.exec()
    lock.unlock()
    if temporary:
        temporary.cleanup()
    return result
