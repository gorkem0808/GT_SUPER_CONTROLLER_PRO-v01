from __future__ import annotations

import re
from pathlib import Path

from gt_super_controller.version import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_version_files_match() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__


def test_calibration_is_four_corner_without_center() -> None:
    source = (ROOT / "firmware" / "gun" / "main.c").read_text(encoding="utf-8")
    assert 'names[CAL_POINT_COUNT] = {"TL", "TR", "BR", "BL"}' in source
    assert "CAL_CENTER" not in source


def test_professional_calibration_guards_exist() -> None:
    source = (ROOT / "firmware" / "gun" / "main.c").read_text(encoding="utf-8")
    for token in (
        "cal_retry",
        "wrong_order",
        "CALIBRATION_TIMEOUT_MS",
        "calibration_restore_previous",
        'equals_ignore_case(arg1, "CAPTURE")',
    ):
        assert token in source


def test_trigger_and_calibration_service_architecture() -> None:
    controller = (ROOT / "firmware" / "controller" / "main.c").read_text(
        encoding="utf-8"
    )
    gun = (ROOT / "firmware" / "gun" / "main.c").read_text(encoding="utf-8")
    app = (ROOT / "desktop" / "gt_super_controller" / "app.py").read_text(
        encoding="utf-8"
    )
    assert "CALIBRATION_REQUEST_HOLD_MS 10000u" in controller
    assert 'calibration_request' in controller
    assert 'set_gun_motion_enabled(false, "calibration_start_buttons")' in controller
    assert "set_gun_motion_enabled(!gun_motion_enabled" not in controller
    assert "motion_change_id" in controller
    assert "PIN_TRIGGER" not in gun
    assert "PIN_MOUSE_DISABLE" not in gun
    assert 'equals_ignore_case(command, "MOTION")' in gun
    assert "MOTION_DISABLE_TIMEOUT_MS 180000u" in gun
    assert r'\"protocol\":3' in controller
    assert r'\"protocol\":3' in gun
    assert '"CAL CAPTURE"' in app
    assert "_open_calibration_service" in app
    assert "_begin_service_save_and_exit" in app
    assert "KAYDET VE SİLAHLARI AKTİF ET" in app
    assert 'message.get("profile") is True' in app
    assert '{1, 2}' in app


def test_controller_has_maintenance_timeout() -> None:
    source = (ROOT / "firmware" / "controller" / "main.c").read_text(encoding="utf-8")
    assert "MAINTENANCE_TIMEOUT_MS" in source
    assert 'equals_ignore_case(command, "MAINTENANCE")' in source


def test_workflow_outputs_three_uf2() -> None:
    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert len(re.findall(r"gt_(?:controller|gun_p[12])\.uf2", workflow)) >= 3
    assert "actions/setup-python@v6.3.0" in workflow
    assert "flash_store_test" in workflow


def test_pyinstaller_uses_absolute_launcher() -> None:
    spec = (ROOT / "desktop" / "GT_SUPER_CONTROLLER.spec").read_text(encoding="utf-8")
    launcher = (ROOT / "desktop" / "gt_super_controller_launcher.py").read_text(
        encoding="utf-8"
    )
    assert "gt_super_controller_launcher.py" in spec
    assert "from gt_super_controller.app import main" in launcher


def test_schema_two_migration_keeps_legacy_records_safe() -> None:
    controller = (ROOT / "firmware" / "controller" / "main.c").read_text(
        encoding="utf-8"
    )
    gun = (ROOT / "firmware" / "gun" / "main.c").read_text(encoding="utf-8")
    flash = (ROOT / "firmware" / "common" / "flash_store.c").read_text(
        encoding="utf-8"
    )
    assert "CONTROLLER_FLASH_SCHEMA 2u" in controller
    assert "CONTROLLER_FLASH_SCHEMA_LEGACY 1u" in controller
    assert "GUN_FLASH_SCHEMA 2u" in gun
    assert "GUN_FLASH_SCHEMA_LEGACY 1u" in gun
    assert "inspect_slot_any_schema" in flash
