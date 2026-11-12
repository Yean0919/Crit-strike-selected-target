from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from crit_strike.models import Box, Detection


def read_image(path: Path) -> np.ndarray:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("图片必须小于 20 MB")
    try:
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as error:
        raise ValueError("图片解码失败，请转换为标准 PNG 或 JPEG 后重试") from error
    if image is None or min(image.shape[:2]) < 24 or max(image.shape[:2]) > 8192:
        raise ValueError("图片无法读取，或尺寸超出 24～8192 像素范围")
    return image


def prepare_avatar(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    side = min(width, height)
    x, y = (width - side) // 2, (height - side) // 2
    avatar = cv2.resize(image[y : y + side, x : x + side], (160, 160), interpolation=cv2.INTER_AREA)
    if cv2.cvtColor(avatar[16:-16, 16:-16], cv2.COLOR_BGR2GRAY).std() < 9:
        raise ValueError("头像纹理过少，请选择包含清晰图案的头像")
    return avatar


@dataclass
class Template:
    id: str
    image: np.ndarray
    threshold: float = 0.88


class Detector:
    def __init__(self, templates: list[Template], minimum: int = 24, maximum: int = 160):
        self.templates = templates
        sizes = set(range(minimum, maximum + 1, 4))
        sizes.update([minimum, maximum])
        self.sizes = sorted(sizes)
        self._cache: dict[tuple[str, int], tuple[np.ndarray, np.ndarray, int]] = {}

    def _scaled(self, template: Template, size: int):
        key = (template.id, size)
        if key not in self._cache:
            image = cv2.resize(template.image, (size, size), interpolation=cv2.INTER_AREA)
            margin = max(2, round(size * 0.15))
            core = image[margin:-margin, margin:-margin]
            gray = cv2.cvtColor(core, cv2.COLOR_BGR2GRAY)
            self._cache[key] = gray, core, margin
        return self._cache[key]

    def detect(
        self,
        image: np.ndarray,
        monitor: int,
        origin: tuple[int, int],
        excluded: list[Box] | None = None,
    ) -> list[Detection]:
        # Half resolution retains detail for 24px avatars while limiting correlation cost.
        scale = 0.5
        small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        results = []
        for template in self.templates:
            candidates = []
            scanned_sizes = set()
            for physical_size in self.sizes:
                size = round(physical_size * scale)
                if size in scanned_sizes:
                    continue
                scanned_sizes.add(size)
                needle, core, margin = self._scaled(template, size)
                height, width = needle.shape
                if height > gray.shape[0] or width > gray.shape[1]:
                    continue
                scores = cv2.matchTemplate(gray, needle, cv2.TM_CCOEFF_NORMED)
                for _ in range(24):
                    _, score, _, point = cv2.minMaxLoc(scores)
                    if score < template.threshold:
                        break
                    x, y = point
                    patch = small[y : y + height, x : x + width]
                    color_error = np.abs(patch.astype(np.float32) - core).mean()
                    box = Box(
                        (x - margin) / scale + origin[0],
                        (y - margin) / scale + origin[1],
                        size / scale,
                        size / scale,
                    )
                    inside = x >= margin and y >= margin
                    inside &= x - margin + size <= small.shape[1]
                    inside &= y - margin + size <= small.shape[0]
                    blocked = any(box.iou(region) > 0 for region in (excluded or []))
                    if color_error <= 48 and inside and not blocked:
                        candidates.append(Detection(template.id, monitor, box, score))
                    left, top = max(0, x - width // 2), max(0, y - height // 2)
                    scores[top : y + height // 2 + 1, left : x + width // 2 + 1] = -1
            accepted = []
            for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
                if all(candidate.box.iou(other.box) < 0.25 for other in accepted):
                    accepted.append(candidate)
            results.extend(accepted[:24])
        return results
