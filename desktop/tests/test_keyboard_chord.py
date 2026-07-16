from __future__ import annotations

from gt_super_controller.keyboard_chord import (
    KEY_2,
    KEY_5,
    VK_2,
    VK_5,
    DualKeyHoldTracker,
)


def test_single_key_is_replayed_on_release() -> None:
    tracker = DualKeyHoldTracker(hold_seconds=10.0)
    tracker.key_down(KEY_2, VK_2, 0.0)
    assert tracker.poll(15.0) is False
    assert tracker.key_up(KEY_2, VK_2, 15.0) == VK_2


def test_two_key_hold_fires_once_after_ten_seconds() -> None:
    tracker = DualKeyHoldTracker(hold_seconds=10.0)
    tracker.key_down(KEY_2, VK_2, 1.0)
    tracker.key_down(KEY_5, VK_5, 1.2)

    assert tracker.poll(11.19) is False
    assert tracker.poll(11.20) is True
    assert tracker.poll(20.0) is False
    assert tracker.key_up(KEY_2, VK_2, 20.1) is None
    assert tracker.key_up(KEY_5, VK_5, 20.2) is None


def test_cancelled_chord_does_not_replay_start_keys() -> None:
    tracker = DualKeyHoldTracker(hold_seconds=10.0)
    tracker.key_down(KEY_2, VK_2, 0.0)
    tracker.key_down(KEY_5, VK_5, 0.1)
    assert tracker.key_up(KEY_5, VK_5, 5.0) is None
    assert tracker.poll(20.0) is False
    assert tracker.key_up(KEY_2, VK_2, 5.1) is None


def test_new_chord_requires_full_release_after_cancel() -> None:
    tracker = DualKeyHoldTracker(hold_seconds=10.0)
    tracker.key_down(KEY_2, VK_2, 0.0)
    tracker.key_down(KEY_5, VK_5, 0.0)
    tracker.key_up(KEY_5, VK_5, 1.0)
    tracker.key_down(KEY_5, VK_5, 2.0)
    assert tracker.poll(20.0) is False

    tracker.key_up(KEY_2, VK_2, 20.1)
    tracker.key_up(KEY_5, VK_5, 20.2)
    tracker.key_down(KEY_2, VK_2, 21.0)
    tracker.key_down(KEY_5, VK_5, 21.0)
    assert tracker.poll(31.0) is True
