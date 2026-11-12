import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication

from crit_strike.app import MainWindow
from crit_strike.effects import draw_effect, load_effects
from crit_strike.models import Box, Monitor
from crit_strike.storage import Store
from crit_strike.widgets import CropDialog


@pytest.fixture(scope="module")
def application():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_all_effects_render_and_crop(application, avatar, tmp_path):
    effects, _ = load_effects(tmp_path)
    for effect in effects.values():
        image = QImage(400, 400, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        draw_effect(painter, effect, QPointF(200, 200), 0.3, effect.size)
        painter.end()
        assert not image.isNull()
        assert any(image.constBits())
    dialog = CropDialog(avatar)
    assert dialog.canvas.cropped().shape == avatar.shape
    dialog.close()


@pytest.mark.parametrize("renderer", ["hammer", "burst"])
def test_impact_frames_and_clean_end(application, tmp_path, renderer):
    effects, _ = load_effects(tmp_path)
    effect = effects[renderer]

    def render(phase, size=130):
        image = QImage(600, 600, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_effect(painter, effect, QPointF(300, 300), phase * effect.duration / effect.hits, size)
        painter.end()
        return image

    charge = render(0.12)
    contact = 0.54 if renderer == "hammer" else 0.30
    impact = render(contact)
    assert impact != charge
    assert impact == render(contact)
    center_alpha = sum(
        impact.pixelColor(x, y).alpha() for x in range(285, 316) for y in range(285, 316)
    )
    assert center_alpha > 60_000
    for size in [60, 300, 690]:
        assert any(render(contact, size).constBits())
    assert not any(render(effect.hits).constBits())


def test_ui_settings_manual_and_stop(application, avatar, tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.add("fixture", avatar)
    monitor = Monitor(0, Box(0, 0, 1920, 1080), Box(0, 0, 1920, 1080))
    monkeypatch.setattr(MainWindow, "rebuild_overlays", lambda self: None)
    window = MainWindow(store, [monitor], register_hotkeys=False)
    assert window.current_target().name == "fixture"
    window.threshold.setValue(0.92)
    assert store.targets[0].threshold == 0.92
    window.enabled.setChecked(False)
    assert not store.targets[0].enabled
    window.size.setValue(180)
    assert store.settings.effect_size == 180
    window.save()
    restored = Store(tmp_path)
    restored.load()
    assert restored.targets == store.targets
    window.manual()
    assert window.selecting
    window.picked(QPointF(300, 300))
    assert not window.selecting
    assert window.playing_count() == 1
    window.stop_all()
    assert window.playing_count() == 0
    window.monitors.append(Monitor(1, Box(-1280, 0, 1280, 720), Box(-1280, 0, 1280, 720)))
    window.move(100, 100)
    window.show()
    application.processEvents()
    window.worker = SimpleNamespace(exclusions={})
    window.update_exclusions()
    assert set(window.worker.exclusions) == {0}
    window.worker = None
    window.close()
