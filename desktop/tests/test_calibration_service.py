from __future__ import annotations

from types import SimpleNamespace

from gt_super_controller.app import GTApp


class _Variable:
    def __init__(self, value: object) -> None:
        self.value = value

    def get(self) -> object:
        return self.value


def test_gun_settings_use_one_atomic_apply_command() -> None:
    app = GTApp.__new__(GTApp)
    app.calibration_vars = {
        1: {
            "overscan": _Variable(3),
            "invert_x": _Variable(True),
            "invert_y": _Variable(False),
        }
    }

    assert GTApp._gun_settings_commands(app, 1) == ["APPLY 3 1 0"]


def test_service_waits_for_every_gun_save_ack() -> None:
    app = GTApp.__new__(GTApp)
    app.calibration_service_pending_saves = {1, 2}
    exits: list[tuple[bool, str]] = []
    app._complete_calibration_service_exit = (  # type: ignore[method-assign]
        lambda *, saved, source: exits.append((saved, source))
    )

    GTApp._handle_service_save_ack(app, 1)
    assert app.calibration_service_pending_saves == {2}
    assert exits == []

    GTApp._handle_service_save_ack(app, 2)
    assert app.calibration_service_pending_saves == set()
    assert exits == [(True, "save_confirmed")]


def test_cancelled_service_does_not_reopen_for_delayed_auto_save() -> None:
    app = GTApp.__new__(GTApp)
    app.calibration_service_active = False
    calls: list[tuple[set[int], str]] = []
    app._begin_service_save_and_exit = (  # type: ignore[method-assign]
        lambda players, *, reason: calls.append((set(players), reason))
    )

    GTApp._auto_save_completed_calibration(app, 1)
    assert calls == []

    app.calibration_service_active = True
    GTApp._auto_save_completed_calibration(app, 2)
    assert calls == [({1, 2}, "calibration_complete_p2")]


def test_controller_status_recovers_lost_calibration_request() -> None:
    app = GTApp.__new__(GTApp)
    app.calibration_service_active = False
    app.controller_motion_sync_pending = False
    app.controller_motion_change_id = None
    app.motion_enabled = True
    opened: list[str] = []
    sent: list[tuple[str, str]] = []
    app.device_manager = SimpleNamespace(
        send_to=lambda role, command: sent.append((role, command)) or True
    )

    def open_service(source: str) -> None:
        opened.append(source)
        app.calibration_service_active = True
        app.motion_enabled = False
        app.controller_motion_sync_pending = True

    app._open_calibration_service = open_service  # type: ignore[method-assign]

    GTApp._handle_controller_motion_status(
        app,
        {
            "maintenance": True,
            "motion_enabled": False,
            "motion_change_id": 7,
        },
    )

    assert opened == ["controller_status_recovery"]
    assert sent == []
    assert app.controller_motion_sync_pending is False
    assert app.controller_motion_change_id == 7
