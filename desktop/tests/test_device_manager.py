from __future__ import annotations

import logging
import time
from types import SimpleNamespace

from gt_super_controller.device_manager import DeviceManager, JsonLineBuffer


def test_split_json_line_is_reassembled() -> None:
    parser = JsonLineBuffer()
    messages, errors = parser.feed(b'{"type":"info",')
    assert messages == []
    assert errors == []
    messages, errors = parser.feed(b'"role":"gun","player":1}\r\n')
    assert errors == []
    assert messages[0]["player"] == 1


def test_bad_line_does_not_break_next_line() -> None:
    parser = JsonLineBuffer()
    messages, errors = parser.feed(b"not-json\n{\"ok\":true}\n")
    assert errors
    assert messages == [{"ok": True}]


def test_oversized_line_is_discarded_until_newline() -> None:
    parser = JsonLineBuffer(maximum=8)
    messages, errors = parser.feed(b"123456789012\n{\"x\":1}\n")
    assert errors
    assert messages == [{"x": 1}]


def test_candidate_accepts_project_vid() -> None:
    assert DeviceManager._candidate(SimpleNamespace(vid=0xCAFE)) is True


def test_candidate_rejects_unrelated_vid() -> None:
    assert DeviceManager._candidate(SimpleNamespace(vid=0x1234)) is False


def test_all_required_connected() -> None:
    manager = DeviceManager(lambda _event: None, logging.getLogger("test"))
    now = time.monotonic()
    manager.snapshot = lambda: [  # type: ignore[method-assign]
        {"responsive": True, "info": {"role": "controller"}},
        {"responsive": True, "info": {"role": "gun", "player": 1}},
        {"responsive": True, "info": {"role": "gun", "player": 2}},
    ]
    assert manager.all_required_connected() is True


def test_stale_device_not_ready() -> None:
    manager = DeviceManager(lambda _event: None, logging.getLogger("test"))
    manager.snapshot = lambda: [  # type: ignore[method-assign]
        {"responsive": False, "info": {"role": "controller"}},
        {"responsive": True, "info": {"role": "gun", "player": 1}},
        {"responsive": True, "info": {"role": "gun", "player": 2}},
    ]
    assert manager.all_required_connected() is False
