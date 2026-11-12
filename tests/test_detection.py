import cv2
import numpy as np
import pytest

from crit_strike.detection import Detector, Template, prepare_avatar, read_image
from crit_strike.models import Box


@pytest.mark.parametrize("size", [24, 32, 40, 48, 64, 80, 96, 128, 160])
def test_scaled_avatar(avatar, size):
    screen = np.full((300, 420, 3), 245, dtype=np.uint8)
    screen[50 : 50 + size, 90 : 90 + size] = cv2.resize(
        avatar, (size, size), interpolation=cv2.INTER_AREA
    )
    found = Detector([Template("test", avatar)]).detect(screen, 0, (-100, 20))
    assert len(found) == 1
    assert found[0].box.distance(Box(-10, 70, size, size)) <= 3
    assert abs(found[0].box.w - size) <= 4


def test_multiple_positions_and_rounded_corners(avatar):
    screen = np.full((320, 500, 3), 230, dtype=np.uint8)
    sample = cv2.resize(avatar, (64, 64), interpolation=cv2.INTER_AREA)
    for x in [20, 170, 330]:
        screen[80:144, x : x + 64] = sample
        for offset_x, offset_y in [(0, 0), (58, 0), (0, 58), (58, 58)]:
            screen[80 + offset_y : 86 + offset_y, x + offset_x : x + offset_x + 6] = 230
    detector = Detector([Template("test", avatar)])
    assert len(detector.detect(screen, 0, (0, 0))) == 3
    assert len(detector.detect(screen, 0, (0, 0), [Box(10, 60, 90, 100)])) == 2
    assert detector.detect(screen, 0, (0, 0), [Box(0, 0, 500, 320)]) == []


def test_absent_and_wrong_color(avatar):
    screen = np.full((240, 320, 3), 100, dtype=np.uint8)
    detector = Detector([Template("test", avatar)])
    assert detector.detect(screen, 0, (0, 0)) == []
    altered = cv2.resize(avatar, (64, 64))[:, :, ::-1]
    screen[70:134, 60:124] = altered
    assert detector.detect(screen, 0, (0, 0)) == []


def test_unicode_image_and_low_texture(tmp_path, avatar):
    path = tmp_path / "头像.png"
    cv2.imencode(".png", avatar)[1].tofile(path)
    assert np.array_equal(read_image(path), avatar)
    with pytest.raises(ValueError):
        prepare_avatar(np.ones((64, 64, 3), dtype=np.uint8))
    path.write_bytes(b"invalid")
    with pytest.raises(ValueError):
        read_image(path)
