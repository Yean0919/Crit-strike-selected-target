import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from crit_strike.detection import prepare_avatar, read_image


@dataclass
class Target:
    id: str
    name: str
    enabled: bool = True
    threshold: float = 0.88
    effect: str = "hammer"


@dataclass
class Settings:
    interval: float = 0.3
    minimum: int = 24
    maximum: int = 160
    effect_size: int = 130
    sound: bool = False


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.avatars = root / "avatars"
        self.mods = root / "mods"
        self.targets: list[Target] = []
        self.settings = Settings()
        self.avatars.mkdir(parents=True, exist_ok=True)
        self.mods.mkdir(parents=True, exist_ok=True)

    def image_path(self, target_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", target_id):
            raise ValueError("目标标识无效")
        return self.avatars / f"{target_id}.png"

    def load(self) -> None:
        path = self.root / "settings.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                raise ValueError("配置版本不受支持")
            settings = Settings(**data.get("settings", {}))
            if not 0.1 <= settings.interval <= 2:
                raise ValueError("检测间隔超出范围")
            if (
                type(settings.minimum) is not int
                or type(settings.maximum) is not int
                or not 24 <= settings.minimum <= settings.maximum <= 256
            ):
                raise ValueError("头像尺寸范围无效")
            if (
                type(settings.effect_size) is not int
                or not 60 <= settings.effect_size <= 300
                or type(settings.sound) is not bool
            ):
                raise ValueError("特效参数无效")
            targets = [Target(**item) for item in data.get("targets", [])]
            if len(targets) > 8 or len({item.id for item in targets}) != len(targets):
                raise ValueError("目标数量或标识无效")
            for target in targets:
                self.image_path(target.id)
                if not isinstance(target.name, str) or not 1 <= len(target.name) <= 60:
                    raise ValueError("目标名称无效")
                if not 0.7 <= target.threshold <= 0.99 or type(target.enabled) is not bool:
                    raise ValueError("目标参数无效")
                if not isinstance(target.effect, str):
                    raise ValueError("特效标识无效")
            self.settings, self.targets = settings, targets
        except (ValueError, TypeError, AttributeError, OSError) as error:
            raise ValueError("本地配置无法读取，原文件已保留，请检查配置后重启") from error

    def save(self) -> None:
        atomic_json(
            self.root / "settings.json",
            {
                "version": 1,
                "settings": asdict(self.settings),
                "targets": [asdict(target) for target in self.targets],
            },
        )

    def add(self, name: str, image: np.ndarray) -> Target:
        if len(self.targets) >= 8:
            raise ValueError("首版最多保存 8 个目标")
        avatar = prepare_avatar(image)
        for existing in self.targets:
            path = self.image_path(existing.id)
            if path.exists() and np.array_equal(read_image(path), avatar):
                raise ValueError("该头像已经导入")
        target = Target(uuid.uuid4().hex, name.strip()[:60] or "新目标")
        success, encoded = cv2.imencode(".png", avatar)
        if not success:
            raise ValueError("头像保存失败")
        path = self.image_path(target.id)
        encoded.tofile(path)
        self.targets.append(target)
        try:
            self.save()
        except OSError:
            self.targets.remove(target)
            path.unlink(missing_ok=True)
            raise
        return target

    def remove(self, target_id: str) -> None:
        previous = self.targets
        self.targets = [target for target in previous if target.id != target_id]
        try:
            self.save()
        except OSError:
            self.targets = previous
            raise
        self.image_path(target_id).unlink(missing_ok=True)
