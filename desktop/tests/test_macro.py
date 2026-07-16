from __future__ import annotations

import threading

import pytest

from gt_super_controller.macro import MacroValidationError, run_macro, validate_macro


def test_valid_macro_normalized() -> None:
    result = validate_macro(
        [
            {"type": "wait", "seconds": 0.1},
            {"type": "key", "key": "enter", "duration_ms": 80},
        ]
    )
    assert result[1]["key"] == "ENTER"


def test_invalid_key_rejected() -> None:
    with pytest.raises(MacroValidationError):
        validate_macro([{"type": "key", "key": "NOT_A_KEY"}])


def test_invalid_step_type_rejected() -> None:
    with pytest.raises(MacroValidationError):
        validate_macro([{"type": "click"}])


def test_too_many_steps_rejected() -> None:
    with pytest.raises(MacroValidationError):
        validate_macro([{"type": "wait", "seconds": 0}] * 201)


def test_run_macro_calls_sender() -> None:
    sent: list[tuple[str, int]] = []
    completed = run_macro(
        [{"type": "key", "key": "F2", "duration_ms": 30}],
        threading.Event(),
        key_sender=lambda key, duration: sent.append((key, duration)),
    )
    assert completed == 1
    assert sent == [("F2", 30)]


def test_cancelled_macro_does_not_send() -> None:
    event = threading.Event()
    event.set()
    sent: list[tuple[str, int]] = []
    completed = run_macro(
        [{"type": "key", "key": "1", "duration_ms": 80}],
        event,
        key_sender=lambda key, duration: sent.append((key, duration)),
    )
    assert completed == 0
    assert sent == []
