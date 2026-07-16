from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover - dependency error is reported at runtime
    serial = None  # type: ignore[assignment]
    list_ports = None  # type: ignore[assignment]


MAX_LINE_BYTES = 2048
SILENCE_TIMEOUT_SECONDS = 10.0
RESPONSIVE_SECONDS = 5.0
SUPPORTED_VIDS = {0xCAFE, 0x2E8A}


class JsonLineBuffer:
    def __init__(self, maximum: int = MAX_LINE_BYTES) -> None:
        self.maximum = maximum
        self._buffer = bytearray()
        self._discard = False

    def feed(self, data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
        messages: list[dict[str, Any]] = []
        errors: list[str] = []
        for byte in data:
            if byte == 13:
                continue
            if byte == 10:
                if self._discard:
                    self._discard = False
                    self._buffer.clear()
                    continue
                raw = bytes(self._buffer)
                self._buffer.clear()
                if not raw:
                    continue
                try:
                    decoded = raw.decode("utf-8")
                    message = json.loads(decoded)
                    if not isinstance(message, dict):
                        raise ValueError("JSON root is not an object")
                    messages.append(message)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"geçersiz JSON satırı: {exc}")
                continue
            if self._discard:
                continue
            if len(self._buffer) >= self.maximum:
                self._buffer.clear()
                self._discard = True
                errors.append("seri satır sınırı aşıldı")
                continue
            self._buffer.append(byte)
        return messages, errors


@dataclass
class _Connection:
    port: str
    serial_port: Any
    manager: "DeviceManager"
    info: dict[str, Any] | None = None
    last_valid: float = field(default_factory=time.monotonic)
    stop_event: threading.Event = field(default_factory=threading.Event)
    write_lock: threading.Lock = field(default_factory=threading.Lock)
    thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(
            target=self._reader, name=f"GTPico-{self.port}", daemon=True
        )
        self.thread.start()

    def send(self, command: str) -> bool:
        if self.stop_event.is_set():
            return False
        payload = (command.strip() + "\n").encode("ascii", errors="strict")
        try:
            with self.write_lock:
                self.serial_port.write(payload)
                self.serial_port.flush()
            return True
        except Exception as exc:
            self.manager._emit(
                {"event_type": "port_error", "port": self.port, "error": str(exc)}
            )
            self.stop_event.set()
            return False

    def close(self) -> None:
        self.stop_event.set()
        try:
            self.serial_port.close()
        except Exception:
            pass

    def _reader(self) -> None:
        parser = JsonLineBuffer()
        self.manager._emit({"event_type": "port_opened", "port": self.port})
        for command in ("INFO", "GET CONFIG", "STATUS", "STREAM 1"):
            self.send(command)
        try:
            while not self.stop_event.is_set() and not self.manager._stop_event.is_set():
                try:
                    chunk = self.serial_port.read(256)
                except Exception as exc:
                    self.manager._emit(
                        {"event_type": "port_error", "port": self.port, "error": str(exc)}
                    )
                    break
                if chunk:
                    messages, errors = parser.feed(bytes(chunk))
                    for error in errors:
                        self.manager._emit(
                            {"event_type": "protocol_error", "port": self.port, "error": error}
                        )
                    for message in messages:
                        self.last_valid = time.monotonic()
                        if message.get("type") == "info":
                            self.info = message
                        self.manager._emit(
                            {"event_type": "message", "port": self.port, "message": message}
                        )
                elif time.monotonic() - self.last_valid > SILENCE_TIMEOUT_SECONDS:
                    self.manager._emit(
                        {
                            "event_type": "port_error",
                            "port": self.port,
                            "error": "10 saniye geçerli protokol mesajı alınamadı",
                        }
                    )
                    break
                else:
                    time.sleep(0.02)
        finally:
            self.close()
            self.manager._connection_closed(self.port)
            self.manager._emit({"event_type": "port_closed", "port": self.port})


class DeviceManager:
    def __init__(
        self,
        callback: Callable[[dict[str, Any]], None],
        logger: logging.Logger,
        scan_interval_ms: int = 1000,
    ) -> None:
        self.callback = callback
        self.logger = logger
        self.scan_interval = max(0.25, scan_interval_ms / 1000.0)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._connections: dict[str, _Connection] = {}
        self._scanner: threading.Thread | None = None

    def _emit(self, event: dict[str, Any]) -> None:
        try:
            self.callback(event)
        except Exception:
            self.logger.exception("Cihaz olayı callback içinde işlenemedi")

    @staticmethod
    def _candidate(port: Any) -> bool:
        vid = getattr(port, "vid", None)
        if vid is not None:
            return int(vid) in SUPPORTED_VIDS
        text = " ".join(
            str(getattr(port, name, "") or "")
            for name in ("description", "manufacturer", "product", "hwid")
        ).upper()
        return any(token in text for token in ("GT GUN", "GT SUPER", "PICO", "USB SERIAL"))

    def start(self) -> None:
        if serial is None or list_ports is None:
            raise RuntimeError("pyserial kurulu değil. 'pip install pyserial' çalıştırın.")
        if self._scanner is not None and self._scanner.is_alive():
            return
        self._stop_event.clear()
        self._scanner = threading.Thread(
            target=self._scan_loop, name="GTPicoScanner", daemon=True
        )
        self._scanner.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            connections = list(self._connections.values())
        for connection in connections:
            connection.close()
        if self._scanner is not None:
            self._scanner.join(timeout=3)

    def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                ports = [port for port in list_ports.comports() if self._candidate(port)]
                present = {str(port.device) for port in ports}
                with self._lock:
                    existing = set(self._connections)
                for removed in existing - present:
                    with self._lock:
                        connection = self._connections.get(removed)
                    if connection is not None:
                        connection.close()
                for port in ports:
                    name = str(port.device)
                    with self._lock:
                        already_open = name in self._connections
                    if not already_open:
                        self._open(name)
            except Exception as exc:
                self.logger.warning("Seri cihaz taraması başarısız: %s", exc)
            self._stop_event.wait(self.scan_interval)

    def _open(self, port: str) -> None:
        try:
            serial_port = serial.Serial(
                port=port,
                baudrate=115200,
                timeout=0.1,
                write_timeout=0.5,
                exclusive=False if hasattr(serial.Serial, "exclusive") else None,
            )
        except (TypeError, ValueError):
            # Older pyserial versions do not accept the exclusive keyword on Windows.
            try:
                serial_port = serial.Serial(
                    port=port, baudrate=115200, timeout=0.1, write_timeout=0.5
                )
            except Exception as exc:
                self._emit({"event_type": "port_error", "port": port, "error": str(exc)})
                return
        except Exception as exc:
            self._emit({"event_type": "port_error", "port": port, "error": str(exc)})
            return
        connection = _Connection(port=port, serial_port=serial_port, manager=self)
        with self._lock:
            if port in self._connections:
                serial_port.close()
                return
            self._connections[port] = connection
        connection.start()

    def _connection_closed(self, port: str) -> None:
        with self._lock:
            self._connections.pop(port, None)

    def send_to(self, role: str, command: str, player: int | None = None) -> bool:
        with self._lock:
            connections = list(self._connections.values())
        for connection in connections:
            info = connection.info or {}
            if info.get("role") != role:
                continue
            if role == "gun":
                try:
                    actual_player = int(info.get("player", 0))
                except (TypeError, ValueError):
                    continue
                if actual_player != player:
                    continue
            return connection.send(command)
        return False

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            connections = list(self._connections.values())
        return [
            {
                "port": connection.port,
                "info": dict(connection.info) if connection.info else None,
                "responsive": now - connection.last_valid <= RESPONSIVE_SECONDS,
                "last_valid_age": max(0.0, now - connection.last_valid),
            }
            for connection in connections
        ]

    def all_required_connected(self) -> bool:
        identities: set[tuple[str, int]] = set()
        for item in self.snapshot():
            if not item["responsive"] or not isinstance(item["info"], dict):
                continue
            info = item["info"]
            if info.get("role") == "controller":
                identities.add(("controller", 0))
            elif info.get("role") == "gun":
                try:
                    player = int(info.get("player", 0))
                except (TypeError, ValueError):
                    continue
                if player in (1, 2):
                    identities.add(("gun", player))
        return {
            ("controller", 0),
            ("gun", 1),
            ("gun", 2),
        }.issubset(identities)
