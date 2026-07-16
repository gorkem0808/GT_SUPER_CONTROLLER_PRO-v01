from __future__ import annotations

import ctypes
import os
import threading
import time
from typing import Any, Callable


class MacroValidationError(ValueError):
    pass


_ALLOWED_KEYS = {
    "ENTER": 0x0D,
    "ESC": 0x1B,
    "SPACE": 0x20,
    "TAB": 0x09,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "INSERT": 0x2D,
    "DELETE": 0x2E,
}
_ALLOWED_KEYS.update({f"F{number}": 0x6F + number for number in range(1, 13)})
_ALLOWED_KEYS.update({str(number): 0x30 + number for number in range(10)})
_ALLOWED_KEYS.update({chr(code): code for code in range(ord("A"), ord("Z") + 1)})


def validate_macro(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise MacroValidationError("Makro bir JSON listesi olmalıdır.")
    if len(raw) > 200:
        raise MacroValidationError("Makro en fazla 200 adım içerebilir.")

    normalized: list[dict[str, Any]] = []
    total_wait = 0.0
    for index, step in enumerate(raw, start=1):
        if not isinstance(step, dict):
            raise MacroValidationError(f"Makro adımı {index} nesne olmalıdır.")
        step_type = str(step.get("type", "")).strip().lower()
        if step_type == "wait":
            try:
                seconds = float(step.get("seconds"))
            except (TypeError, ValueError) as exc:
                raise MacroValidationError(
                    f"Makro adımı {index}: seconds sayı olmalıdır."
                ) from exc
            if not 0.0 <= seconds <= 300.0:
                raise MacroValidationError(
                    f"Makro adımı {index}: bekleme 0..300 saniye olmalıdır."
                )
            total_wait += seconds
            normalized.append({"type": "wait", "seconds": seconds})
        elif step_type == "key":
            key = str(step.get("key", "")).strip().upper()
            if key not in _ALLOWED_KEYS:
                raise MacroValidationError(
                    f"Makro adımı {index}: desteklenmeyen tuş '{key}'."
                )
            try:
                duration_ms = int(step.get("duration_ms", 80))
            except (TypeError, ValueError) as exc:
                raise MacroValidationError(
                    f"Makro adımı {index}: duration_ms sayı olmalıdır."
                ) from exc
            if not 20 <= duration_ms <= 1000:
                raise MacroValidationError(
                    f"Makro adımı {index}: duration_ms 20..1000 olmalıdır."
                )
            normalized.append(
                {"type": "key", "key": key, "duration_ms": duration_ms}
            )
        else:
            raise MacroValidationError(
                f"Makro adımı {index}: type yalnız 'wait' veya 'key' olabilir."
            )
    if total_wait > 900.0:
        raise MacroValidationError("Makronun toplam bekleme süresi 900 saniyeyi aşamaz.")
    return normalized


def _send_windows_key(key: str, duration_ms: int) -> None:
    if os.name != "nt":
        raise OSError("Klavye makrosu yalnız Windows üzerinde çalışır.")
    virtual_key = _ALLOWED_KEYS[key]
    keybd_event = ctypes.windll.user32.keybd_event
    keybd_event(virtual_key, 0, 0, 0)
    time.sleep(duration_ms / 1000.0)
    keybd_event(virtual_key, 0, 0x0002, 0)


def run_macro(
    steps: list[dict[str, Any]],
    cancel_event: threading.Event,
    key_sender: Callable[[str, int], None] = _send_windows_key,
) -> int:
    completed = 0
    for step in validate_macro(steps):
        if cancel_event.is_set():
            break
        if step["type"] == "wait":
            if cancel_event.wait(float(step["seconds"])):
                break
        else:
            key_sender(str(step["key"]), int(step["duration_ms"]))
        completed += 1
    return completed
