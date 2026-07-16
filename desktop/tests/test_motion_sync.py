from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from gt_super_controller.app import GTApp


def _app_for_motion_test(*, enabled: bool, pending: bool, change_id: int | None):
    app = GTApp.__new__(GTApp)
    app.motion_enabled = enabled
    app.controller_motion_sync_pending = pending
    app.controller_motion_change_id = change_id
    sent: list[tuple[str, str]] = []
    applied: list[tuple[bool, str, bool, bool]] = []
    app.device_manager = SimpleNamespace(
        send_to=lambda role, command: sent.append((role, command)) or True
    )

    def record_apply(
        new_enabled: bool,
        source: str,
        *,
        update_controller: bool,
        notify: bool,
    ) -> None:
        applied.append((new_enabled, source, update_controller, notify))
        app.motion_enabled = new_enabled

    app._set_motion_enabled = record_apply  # type: ignore[method-assign]
    return app, sent, applied


def test_pending_motion_sync_retries_stale_controller_status() -> None:
    app, sent, applied = _app_for_motion_test(
        enabled=False, pending=True, change_id=None
    )
    GTApp._handle_controller_motion_status(
        app,
        {"motion_enabled": True, "motion_change_id": 0},
    )
    assert sent == [("controller", "MOTION 0")]
    assert applied == []
    assert app.controller_motion_sync_pending is True


def test_pending_motion_sync_is_confirmed_by_matching_status() -> None:
    app, sent, applied = _app_for_motion_test(
        enabled=False, pending=True, change_id=None
    )
    GTApp._handle_controller_motion_status(
        app,
        {"motion_enabled": False, "motion_change_id": 4},
    )
    assert sent == []
    assert applied == []
    assert app.controller_motion_sync_pending is False
    assert app.controller_motion_change_id == 4


def test_changed_status_recovers_a_dropped_motion_event() -> None:
    app, sent, applied = _app_for_motion_test(
        enabled=True, pending=False, change_id=8
    )
    GTApp._handle_controller_motion_status(
        app,
        {"motion_enabled": False, "motion_change_id": 9},
    )
    assert sent == []
    assert applied == [
        (False, "controller_status_recovery", False, True)
    ]
    assert app.controller_motion_change_id == 9
