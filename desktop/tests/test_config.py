from __future__ import annotations

import json
from pathlib import Path

from gt_super_controller.config import AppConfig, load_config, save_config


def test_defaults_are_valid() -> None:
    config = AppConfig()
    config.validate()
    assert config.require_all_devices is True
    assert config.game_start_delay_seconds == 25


def test_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GT_SUPER_CONTROLLER_CONFIG_DIR", str(tmp_path))
    config = AppConfig(game_executable="C:/TeknoParrot/TeknoParrotUi.exe")
    config.one_credit_macro = [{"type": "wait", "seconds": 1.0}]
    save_config(config)
    loaded = load_config()
    assert loaded.game_executable == config.game_executable
    assert loaded.one_credit_macro == config.one_credit_macro


def test_invalid_json_is_quarantined(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GT_SUPER_CONTROLLER_CONFIG_DIR", str(tmp_path))
    path = tmp_path / "settings.json"
    path.write_text("{broken", encoding="utf-8")
    loaded = load_config()
    assert loaded == AppConfig()
    assert not path.exists()
    assert list(tmp_path.glob("settings.invalid.*.json"))


def test_unknown_keys_are_ignored() -> None:
    config = AppConfig.from_dict({"schema_version": 1, "future_key": 123})
    assert config.schema_version == 1


def test_invalid_range_rejected() -> None:
    config = AppConfig(serial_scan_interval_ms=100)
    try:
        config.validate()
    except ValueError as exc:
        assert "serial_scan_interval_ms" in str(exc)
    else:
        raise AssertionError("invalid range accepted")


def test_saved_file_is_utf8_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GT_SUPER_CONTROLLER_CONFIG_DIR", str(tmp_path))
    save_config(AppConfig(game_arguments="Türkçe"))
    raw = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert raw["game_arguments"] == "Türkçe"
