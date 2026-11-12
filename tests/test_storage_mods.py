import json
from dataclasses import asdict

import pytest

from crit_strike.effects import Effect, load_effects
from crit_strike.storage import Store


def test_round_trip_remove_and_duplicate(tmp_path, avatar):
    store = Store(tmp_path)
    target = store.add("测试目标", avatar)
    with pytest.raises(ValueError):
        store.add("重复", avatar)
    loaded = Store(tmp_path)
    loaded.load()
    assert loaded.targets == [target]
    assert loaded.image_path(target.id).is_file()
    loaded.remove(target.id)
    assert not loaded.image_path(target.id).exists()
    loaded.load()
    assert loaded.targets == []


def test_bad_config_preserved(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("broken", encoding="utf-8")
    with pytest.raises(ValueError):
        Store(tmp_path).load()
    assert path.read_text(encoding="utf-8") == "broken"


def test_path_traversal_and_invalid_values(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.image_path("../outside")
    data = {"version": 1, "settings": asdict(store.settings), "targets": []}
    data["settings"]["interval"] = float("nan")
    (tmp_path / "settings.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        store.load()


def test_atomic_save_failure_rolls_back(tmp_path, avatar, monkeypatch):
    store = Store(tmp_path)

    def fail():
        raise OSError("test")

    monkeypatch.setattr(store, "save", fail)
    with pytest.raises(OSError):
        store.add("test", avatar)
    assert store.targets == []
    assert list(store.avatars.iterdir()) == []


def test_builtin_mods_and_custom_mod(tmp_path):
    effects, errors = load_effects(tmp_path)
    assert not errors
    assert set(effects) == {"hammer", "burst", "ring", "glass", "phaser"}
    data = effects["hammer"].to_json()
    data.update(id="custom", name="自定义", color="#123456")
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Effect.load(path).id == "custom"
    assert len(load_effects(tmp_path)[0]) == 6


def test_legacy_user_mod_with_new_builtin_id_is_preserved(tmp_path):
    effects, _ = load_effects(tmp_path)
    data = effects["hammer"].to_json()
    data.update(id="glass", name="已有自定义锤子")
    (tmp_path / "glass.json").write_text(json.dumps(data), encoding="utf-8")
    restored, errors = load_effects(tmp_path)
    assert not errors
    assert restored["glass"].renderer == "hammer"


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "../escape"),
        ("duration", float("nan")),
        ("duration", 100),
        ("hits", True),
        ("hits", 20),
        ("renderer", "exec"),
        ("color", "red"),
        ("size", -1),
        ("version", 99),
        ("unknown", "ignored?"),
    ],
)
def test_invalid_mod(tmp_path, field, value):
    effects, _ = load_effects(tmp_path)
    data = effects["hammer"].to_json()
    data[field] = value
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        Effect.load(path)
