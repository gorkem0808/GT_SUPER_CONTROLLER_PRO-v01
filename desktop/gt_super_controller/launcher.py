from __future__ import annotations

import logging
import os
import shlex
import subprocess
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig
from .macro import MacroValidationError, run_macro, validate_macro


class GameLauncher:
    def __init__(self, callback: Callable[[dict[str, Any]], None], logger: logging.Logger) -> None:
        self.callback = callback
        self.logger = logger
        self._lock = threading.RLock()
        self._process: subprocess.Popen[Any] | None = None
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._generation = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    @staticmethod
    def build_command(config: AppConfig) -> tuple[list[str], Path]:
        executable = Path(config.game_executable).expanduser()
        if not executable.is_file():
            raise ValueError("Oyun/TeknoParrot çalıştırılabilir dosyası bulunamadı.")
        command = [str(executable)]
        if config.game_profile:
            profile = Path(config.game_profile).expanduser()
            if not profile.is_file():
                raise ValueError("TeknoParrot profil XML dosyası bulunamadı.")
            command.append(f"--profile={profile}")
        if config.teknoparrot_start_minimized:
            command.append("--startMinimized")
        if config.game_arguments.strip():
            command.extend(shlex.split(config.game_arguments, posix=False))
        working_directory = (
            Path(config.game_working_directory).expanduser()
            if config.game_working_directory.strip()
            else executable.parent
        )
        if not working_directory.is_dir():
            raise ValueError("Oyun çalışma klasörü bulunamadı.")
        return command, working_directory

    def launch(self, config: AppConfig) -> bool:
        config.validate()
        if config.one_credit_macro_enabled:
            validate_macro(config.one_credit_macro)
        command, working_directory = self.build_command(config)
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return False
            self._stop_event.clear()
            self._generation += 1
            generation = self._generation
            snapshot = replace(config, one_credit_macro=list(config.one_credit_macro))
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(working_directory),
                    creationflags=creationflags,
                )
            except OSError as exc:
                self.callback({"event_type": "error", "error": str(exc)})
                raise ValueError(f"Oyun başlatılamadı: {exc}") from exc
            self._process = process
            self.callback({"event_type": "started", "pid": process.pid})
            self._monitor_thread = threading.Thread(
                target=self._monitor,
                args=(process, snapshot, generation),
                name="GTGameMonitor",
                daemon=True,
            )
            self._monitor_thread.start()
            if snapshot.one_credit_macro_enabled:
                threading.Thread(
                    target=self._run_delayed_macro,
                    args=(snapshot, generation),
                    name="GTServiceMacro",
                    daemon=True,
                ).start()
            return True

    def _run_delayed_macro(self, config: AppConfig, generation: int) -> None:
        if self._stop_event.wait(config.game_start_delay_seconds):
            return
        with self._lock:
            process = self._process
            valid = generation == self._generation and process is not None and process.poll() is None
        if not valid:
            return
        self.callback({"event_type": "macro_started"})
        try:
            completed = run_macro(config.one_credit_macro, self._stop_event)
        except (OSError, MacroValidationError, RuntimeError) as exc:
            self.callback({"event_type": "macro_error", "error": str(exc)})
            return
        self.callback({"event_type": "macro_finished", "completed": completed})

    def _monitor(self, process: subprocess.Popen[Any], config: AppConfig, generation: int) -> None:
        return_code = process.wait()
        with self._lock:
            if generation != self._generation:
                return
            self._process = None
        self.callback({"event_type": "exited", "return_code": return_code})
        if config.auto_restart_game and not self._stop_event.is_set():
            self.callback(
                {"event_type": "restart_wait", "seconds": config.restart_delay_seconds}
            )
            if not self._stop_event.wait(config.restart_delay_seconds):
                try:
                    self.launch(config)
                except (ValueError, MacroValidationError) as exc:
                    self.callback({"event_type": "error", "error": str(exc)})

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._generation += 1
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        except OSError as exc:
            self.logger.warning("Oyun işlemi kapatılamadı: %s", exc)
