from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIG_FILENAME = "settings.json"


@dataclass(slots=True)
class AppConfig:
    schema_version: int = 1
    game_executable: str = ""
    game_profile: str = ""
    game_arguments: str = ""
    game_working_directory: str = ""
    teknoparrot_start_minimized: bool = True
    game_start_delay_seconds: int = 25
    restart_delay_seconds: int = 10
    auto_start_game: bool = False
    auto_restart_game: bool = False
    require_all_devices: bool = True
    one_credit_macro_enabled: bool = False
    one_credit_macro: list[dict[str, Any]] = field(default_factory=list)
    startup_minimized: bool = False
    serial_scan_interval_ms: int = 1000

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        if not isinstance(raw, dict):
            raise ValueError("Ayar dosyasının kökü JSON nesnesi olmalıdır.")
        known = {item.name for item in fields(cls)}
        values = {key: value for key, value in raw.items() if key in known}
        config = cls(**values)
        config.validate()
        return config

    def validate(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"Desteklenmeyen ayar şeması: {self.schema_version}")
        for name in (
            "game_executable",
            "game_profile",
            "game_arguments",
            "game_working_directory",
        ):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} metin olmalıdır.")
        for name in (
            "teknoparrot_start_minimized",
            "auto_start_game",
            "auto_restart_game",
            "require_all_devices",
            "one_credit_macro_enabled",
            "startup_minimized",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} true/false olmalıdır.")
        if not isinstance(self.one_credit_macro, list):
            raise ValueError("one_credit_macro liste olmalıdır.")
        if not 0 <= int(self.game_start_delay_seconds) <= 300:
            raise ValueError("game_start_delay_seconds 0..300 arasında olmalıdır.")
        if not 1 <= int(self.restart_delay_seconds) <= 300:
            raise ValueError("restart_delay_seconds 1..300 arasında olmalıdır.")
        if not 250 <= int(self.serial_scan_interval_ms) <= 10000:
            raise ValueError("serial_scan_interval_ms 250..10000 arasında olmalıdır.")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


def get_config_dir() -> Path:
    override = os.environ.get("GT_SUPER_CONTROLLER_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "GT_SUPER_CONTROLLER"


def _quarantine_invalid(path: Path) -> None:
    if not path.exists():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(f"{path.stem}.invalid.{timestamp}{path.suffix}")
    try:
        path.replace(destination)
    except OSError:
        # A read-only or locked configuration must not prevent safe defaults.
        pass


def load_config() -> AppConfig:
    path = get_config_dir() / CONFIG_FILENAME
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return AppConfig.from_dict(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        _quarantine_invalid(path)
        return AppConfig()


def save_config(config: AppConfig) -> None:
    config.validate()
    directory = get_config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / CONFIG_FILENAME
    payload = json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=directory
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        finally:
            raise
