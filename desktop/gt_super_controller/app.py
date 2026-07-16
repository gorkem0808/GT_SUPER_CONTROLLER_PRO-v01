from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import queue
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from .config import AppConfig, get_config_dir, load_config, save_config
from .device_manager import DeviceManager
from .keyboard_chord import KeyboardCalibrationHotkey
from .launcher import GameLauncher
from .macro import MacroValidationError, validate_macro
from .startup import is_autostart_enabled, set_autostart
from .version import __version__


class TkQueueLogHandler(logging.Handler):
    def __init__(self, event_queue: queue.Queue[tuple[str, Any]]) -> None:
        super().__init__()
        self.event_queue = event_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.event_queue.put_nowait(("log", self.format(record)))
        except (queue.Full, Exception):
            pass


def setup_logging(event_queue: queue.Queue[tuple[str, Any]]) -> logging.Logger:
    logger = logging.getLogger("gt_super_controller")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # The UI log remains available even when the configured log directory is
    # temporarily unwritable. A log-file permission problem must not prevent the
    # controller application from starting.
    queue_handler = TkQueueLogHandler(event_queue)
    queue_handler.setFormatter(formatter)
    logger.addHandler(queue_handler)

    try:
        log_dir = get_config_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "gt_super_controller.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Günlük dosyası açılamadı; yalnız UI günlüğü kullanılacak: %s", exc)
    return logger


class CalibrationOverlay:
    """Tam ekran, dört köşeli profesyonel kalibrasyon yönlendirmesi."""

    POINTS = ("TL", "TR", "BR", "BL")
    POINT_NAMES = {
        "TL": "SOL ÜST",
        "TR": "SAĞ ÜST",
        "BR": "SAĞ ALT",
        "BL": "SOL ALT",
    }

    def __init__(
        self,
        root: tk.Tk,
        player: int,
        on_cancel: Callable[[], None],
    ) -> None:
        self.player = player
        self.on_cancel = on_cancel
        self.point = "TL"
        self.mode = "calibrating"
        self.quality = 0
        self.x_span = 0
        self.y_span = 0
        self._closed = False

        self.window = tk.Toplevel(root)
        self.window.title(f"Oyuncu {player} Kalibrasyon")
        self.window.configure(bg="#090d12")
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", self._request_cancel)
        self.window.bind("<Escape>", lambda _event: self._request_cancel())

        self.canvas = tk.Canvas(
            self.window,
            bg="#090d12",
            highlightthickness=0,
            cursor="none",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.window.after_idle(self._activate)

    def _activate(self) -> None:
        if self._closed:
            return
        try:
            self.window.grab_set()
            self.window.focus_force()
        except tk.TclError:
            return
        self._draw()

    def _request_cancel(self) -> None:
        if not self._closed:
            self.on_cancel()

    def set_point(self, point: str) -> None:
        if point not in self.POINTS or self._closed:
            return
        self.mode = "calibrating"
        self.point = point
        self.canvas.configure(cursor="none")
        self._draw()

    def show_retry(self, point: str) -> None:
        if self._closed:
            return
        if point in self.POINTS:
            self.point = point
        self.mode = "retry"
        self._draw()
        self.window.after(900, self._resume_current_point)

    def _resume_current_point(self) -> None:
        if self._closed or self.mode != "retry":
            return
        self.mode = "calibrating"
        self._draw()

    def show_success(self, quality: int, x_span: int, y_span: int) -> None:
        if self._closed:
            return
        self.mode = "success"
        self.quality = max(0, min(100, int(quality)))
        self.x_span = max(0, int(x_span))
        self.y_span = max(0, int(y_span))
        self.canvas.configure(cursor="arrow")
        self._draw()

    def _draw_target(self, x: float, y: float, radius: float) -> None:
        c = self.canvas
        c.create_oval(
            x - radius, y - radius, x + radius, y + radius,
            outline="#ffffff", width=5,
        )
        c.create_oval(
            x - radius * 0.42, y - radius * 0.42,
            x + radius * 0.42, y + radius * 0.42,
            outline="#25d366", width=5,
        )
        c.create_line(x - radius * 1.35, y, x + radius * 1.35, y, fill="#25d366", width=3)
        c.create_line(x, y - radius * 1.35, x, y + radius * 1.35, fill="#25d366", width=3)
        c.create_oval(x - 5, y - 5, x + 5, y + 5, fill="#ffffff", outline="")

    def _draw(self) -> None:
        if self._closed:
            return
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 800)
        height = max(c.winfo_height(), 600)

        c.create_text(
            width / 2, 44,
            text=f"OYUNCU {self.player} • PROFESYONEL KALİBRASYON",
            fill="#e8edf2", font=("Segoe UI", 24, "bold"),
        )

        if self.mode == "success":
            c.create_oval(
                width / 2 - 78, height / 2 - 135,
                width / 2 + 78, height / 2 + 21,
                outline="#25d366", width=8,
            )
            c.create_line(
                width / 2 - 40, height / 2 - 55,
                width / 2 - 8, height / 2 - 20,
                width / 2 + 52, height / 2 - 93,
                fill="#25d366", width=12, smooth=True,
            )
            c.create_text(
                width / 2, height / 2 + 80,
                text="KALİBRASYON TAMAMLANDI",
                fill="#ffffff", font=("Segoe UI", 30, "bold"),
            )
            c.create_text(
                width / 2, height / 2 + 128,
                text=f"Ölçüm kalitesi: %{self.quality}",
                fill="#a8b3bd", font=("Segoe UI", 18),
            )
            return

        index = self.POINTS.index(self.point)
        margin_x = max(78.0, min(width, height) * 0.075)
        margin_top = max(118.0, height * 0.13)
        margin_bottom = max(82.0, height * 0.09)
        positions = {
            "TL": (margin_x, margin_top),
            "TR": (width - margin_x, margin_top),
            "BR": (width - margin_x, height - margin_bottom),
            "BL": (margin_x, height - margin_bottom),
        }
        target_x, target_y = positions[self.point]
        radius = max(34.0, min(width, height) * 0.045)
        self._draw_target(target_x, target_y, radius)

        if self.mode == "retry":
            instruction = "ÖLÇÜM KARARSIZ • AYNI HEDEFE TEKRAR ATEŞ EDİN"
            instruction_color = "#ffb020"
        else:
            instruction = "HEDEFE NİŞAN ALIN • TETİĞE BASIP BIRAKIN"
            instruction_color = "#ffffff"

        c.create_text(
            width / 2, height * 0.48,
            text=self.POINT_NAMES[self.point],
            fill="#25d366", font=("Segoe UI", 40, "bold"),
        )
        c.create_text(
            width / 2, height * 0.55,
            text=instruction,
            fill=instruction_color, font=("Segoe UI", 19, "bold"),
        )
        dot_y = height - 34
        spacing = 34
        start_x = width / 2 - (len(self.POINTS) - 1) * spacing / 2
        for dot_index, _point in enumerate(self.POINTS):
            x = start_x + dot_index * spacing
            fill = "#25d366" if dot_index <= index else "#36404a"
            c.create_oval(x - 7, dot_y - 7, x + 7, dot_y + 7, fill=fill, outline="")
        c.create_text(
            width - 26, height - 26,
            text="ESC: İptal", anchor="se",
            fill="#6f7a84", font=("Segoe UI", 11),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.window.grab_release()
        except tk.TclError:
            pass
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class GTApp:
    def __init__(self, root: tk.Tk, start_minimized: bool = False) -> None:
        self.root = root
        self.root.title(f"GT SUPER CONTROLLER {__version__}")
        self.root.geometry("1080x760")
        self.root.minsize(940, 650)

        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=2000)
        self.logger = setup_logging(self.event_queue)
        self.config = load_config()
        self.device_data: dict[str, dict[str, dict[str, Any]]] = {
            "controller": {},
            "gun1": {},
            "gun2": {},
        }
        self.port_roles: dict[str, str] = {}
        self.calibration_active: dict[int, bool] = {1: False, 2: False}
        self.active_calibration_player: int | None = None
        self.calibration_overlay: CalibrationOverlay | None = None
        # Runtime-only by design: every application/power start begins with gun
        # movement active. A passive state is never written to disk or Pico flash.
        self.motion_enabled = True
        self.controller_motion_change_id: int | None = None
        self.controller_motion_sync_pending = False
        self.motion_notice: tk.Toplevel | None = None
        self.calibration_service_active = False
        self.calibration_service_source = ""
        self.calibration_service_pending_saves: set[int] = set()
        self.calibration_service_save_after_id: str | None = None
        self.calibration_service_last_refresh = 0.0
        self.auto_launch_done = False
        self.last_auto_launch_attempt = 0.0
        self.started_at = time.monotonic()

        self.device_manager = DeviceManager(
            callback=lambda event: self._queue_event("device", event),
            logger=self.logger,
            scan_interval_ms=self.config.serial_scan_interval_ms,
        )
        self.launcher = GameLauncher(
            callback=lambda event: self._queue_event("launcher", event),
            logger=self.logger,
        )
        self.calibration_hotkey = KeyboardCalibrationHotkey(
            on_request=lambda: self._queue_event("calibration_hotkey", None),
            logger=self.logger,
            hold_seconds=10.0,
        )

        self._build_ui()
        self._load_config_into_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.device_manager.start()
        self.calibration_hotkey.start()
        self.logger.info("GT SUPER CONTROLLER başlatıldı. Sürüm %s", __version__)

        self.root.after(100, self._process_events)
        self.root.after(500, self._periodic_tasks)
        if start_minimized or self.config.startup_minimized:
            self.root.after(250, self.root.iconify)

    def _queue_event(self, event_type: str, payload: Any) -> None:
        try:
            self.event_queue.put_nowait((event_type, payload))
        except queue.Full:
            self.logger.warning("UI olay kuyruğu dolu; olay atlandı: %s", event_type)

    def _build_ui(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 10))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="GT SUPER CONTROLLER",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        self.game_status_var = tk.StringVar(value="Oyun: durdu")
        ttk.Label(header, textvariable=self.game_status_var).pack(side="right")
        self.motion_status_var = tk.StringVar(value="Silah hareketi: AKTİF")
        ttk.Label(
            header,
            textvariable=self.motion_status_var,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right", padx=(0, 22))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_tab = ttk.Frame(self.notebook, padding=12)
        self.calibration_tab = ttk.Frame(self.notebook, padding=12)
        self.controller_tab = ttk.Frame(self.notebook, padding=12)
        self.game_tab = ttk.Frame(self.notebook, padding=12)
        self.firmware_tab = ttk.Frame(self.notebook, padding=12)
        self.log_tab = ttk.Frame(self.notebook, padding=8)

        self.notebook.add(self.status_tab, text="Durum")
        self.notebook.add(self.calibration_tab, text="Kalibrasyon")
        self.notebook.add(self.controller_tab, text="Kontrol / Röle")
        self.notebook.add(self.game_tab, text="Oyun")
        self.notebook.add(self.firmware_tab, text="Firmware")
        self.notebook.add(self.log_tab, text="Günlük")

        self._build_status_tab()
        self._build_calibration_tab()
        self._build_controller_tab()
        self._build_game_tab()
        self._build_firmware_tab()
        self._build_log_tab()

    def _build_status_tab(self) -> None:
        self.status_vars: dict[str, dict[str, tk.StringVar]] = {}
        for column, (key, title) in enumerate(
            (("controller", "ORTAK KONTROL"), ("gun1", "OYUNCU 1 SİLAH"), ("gun2", "OYUNCU 2 SİLAH"))
        ):
            self.status_tab.columnconfigure(column, weight=1)
            frame = ttk.LabelFrame(self.status_tab, text=title, padding=12)
            frame.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)
            variables = {
                "connection": tk.StringVar(value="Bağlı değil"),
                "version": tk.StringVar(value="Sürüm: -"),
                "line1": tk.StringVar(value="-"),
                "line2": tk.StringVar(value="-"),
                "line3": tk.StringVar(value="-"),
            }
            self.status_vars[key] = variables
            ttk.Label(frame, textvariable=variables["connection"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
            ttk.Label(frame, textvariable=variables["version"]).pack(anchor="w", pady=(4, 12))
            ttk.Separator(frame).pack(fill="x", pady=4)
            for name in ("line1", "line2", "line3"):
                ttk.Label(frame, textvariable=variables[name], wraplength=280).pack(anchor="w", pady=4)

        self.status_tab.rowconfigure(0, weight=1)
        motion_frame = ttk.LabelFrame(
            self.status_tab, text="Silah hareketi", padding=10
        )
        motion_frame.grid(row=1, column=0, columnspan=3, sticky="ew", padx=8, pady=(8, 4))
        ttk.Label(
            motion_frame,
            textvariable=self.motion_status_var,
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        ttk.Button(
            motion_frame,
            text="KALİBRASYON MODUNU AÇ",
            command=lambda: self._open_calibration_service("program_button"),
        ).pack(side="right")

        note = (
            "Kalibrasyon programını açmak için Start 1 + Start 2 veya klavyede 2 + 5 "
            "tuşlarını kesintisiz 10 saniye basılı tutun. İki silahın hareketi geçici "
            "olarak durur ve Controller bakım moduna geçer. Kalibrasyon/ayar kaydı "
            "tamamlanınca iki silah otomatik olarak yeniden AKTİF olur."
        )
        ttk.Label(self.status_tab, text=note, wraplength=950).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=8, pady=12
        )

    def _build_calibration_tab(self) -> None:
        self.calibration_vars: dict[int, dict[str, tk.Variable]] = {}
        session = ttk.LabelFrame(
            self.calibration_tab,
            text="KALİBRASYON OTURUMU",
            padding=12,
        )
        session.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 8))
        self.calibration_service_var = tk.StringVar(
            value="Kapalı — iki silahın hareketi AKTİF"
        )
        ttk.Label(
            session,
            textvariable=self.calibration_service_var,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        ttk.Button(
            session,
            text="KAYDET VE SİLAHLARI AKTİF ET",
            command=self._save_service_settings_and_exit,
        ).pack(side="right", padx=(8, 0))
        ttk.Button(
            session,
            text="İPTAL / HAREKETİ AKTİF ET",
            command=self._cancel_calibration_service,
        ).pack(side="right")

        for column, player in enumerate((1, 2)):
            self.calibration_tab.columnconfigure(column, weight=1)
            frame = ttk.LabelFrame(
                self.calibration_tab,
                text=f"OYUNCU {player} SİLAH",
                padding=16,
            )
            frame.grid(row=1, column=column, sticky="nsew", padx=8, pady=6)
            variables: dict[str, tk.Variable] = {
                "state": tk.StringVar(value="Cihaz bekleniyor"),
                "raw": tk.StringVar(value="Ham sinyal X/Y: - / -"),
                "quality": tk.StringVar(value="Ölçüm kalitesi: -"),
                "quality_score": tk.IntVar(value=0),
                "overscan": tk.IntVar(value=2),
                "invert_x": tk.BooleanVar(value=False),
                "invert_y": tk.BooleanVar(value=False),
            }
            self.calibration_vars[player] = variables

            ttk.Label(
                frame,
                textvariable=variables["state"],
                font=("Segoe UI", 12, "bold"),
                wraplength=430,
            ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
            ttk.Label(frame, textvariable=variables["raw"]).grid(
                row=1, column=0, columnspan=4, sticky="w"
            )
            ttk.Label(frame, textvariable=variables["quality"]).grid(
                row=2, column=0, columnspan=4, sticky="w", pady=(4, 2)
            )
            ttk.Progressbar(
                frame,
                maximum=100,
                variable=variables["quality_score"],
            ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 14))

            ttk.Button(
                frame,
                text="KALİBRASYONU BAŞLAT",
                command=lambda p=player: self._start_calibration(p),
            ).grid(row=4, column=0, columnspan=4, sticky="ew", ipady=8, pady=(0, 8))
            ttk.Button(
                frame, text="İptal", command=lambda p=player: self._cancel_calibration(p)
            ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=(0, 4), pady=4)
            ttk.Button(
                frame, text="Kalibrasyonu Sıfırla", command=lambda p=player: self._reset_calibration(p)
            ).grid(row=5, column=2, columnspan=2, sticky="ew", padx=(4, 0), pady=4)

            service = ttk.LabelFrame(frame, text="Servis ayarları", padding=10)
            service.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(14, 4))
            ttk.Label(service, text="Kenar payı %").grid(row=0, column=0, sticky="w")
            ttk.Spinbox(
                service, from_=0, to=8, textvariable=variables["overscan"], width=6
            ).grid(row=0, column=1, sticky="w", padx=(6, 18))
            ttk.Checkbutton(service, text="X ters", variable=variables["invert_x"]).grid(
                row=0, column=2, sticky="w"
            )
            ttk.Checkbutton(service, text="Y ters", variable=variables["invert_y"]).grid(
                row=0, column=3, sticky="w", padx=(10, 0)
            )
            ttk.Button(
                service,
                text="Uygula ve Kaydet",
                command=lambda p=player: self._apply_gun_settings(p),
            ).grid(row=1, column=0, columnspan=3, sticky="ew", padx=(0, 4), pady=(8, 0))
            ttk.Button(
                service, text="BOOTSEL", command=lambda p=player: self._send_gun(p, "BOOTSEL")
            ).grid(row=1, column=3, sticky="ew", padx=(4, 0), pady=(8, 0))
            for index in range(4):
                frame.columnconfigure(index, weight=1)
                service.columnconfigure(index, weight=1)

        instruction = (
            "İşlem tam ekran yürür: SOL ÜST → SAĞ ÜST → SAĞ ALT → SOL ALT. "
            "Her hedefte tetiğe bir kez basıp bırakın. Sonuç otomatik doğrulanır ve "
            "Pico'nun kalıcı belleğine kaydedilir."
        )
        ttk.Label(self.calibration_tab, text=instruction, wraplength=980).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=12
        )

    def _build_controller_tab(self) -> None:
        frame = ttk.LabelFrame(self.controller_tab, text="Röle ve Tuş Ayarları", padding=14)
        frame.pack(fill="x", padx=8, pady=6)
        self.controller_vars: dict[str, tk.Variable] = {
            "relay_mode": tk.StringVar(value="PULSE"),
            "active_low": tk.BooleanVar(value=True),
            "pulse_ms": tk.IntVar(value=60),
            "cooldown_ms": tk.IntVar(value=120),
            "follow_max_ms": tk.IntVar(value=250),
            "key_pulse_ms": tk.IntVar(value=80),
            "inactivity_s": tk.IntVar(value=300),
            "trigger_hid": tk.BooleanVar(value=True),
        }

        fields = [
            ("Röle modu", "relay_mode"),
            ("Darbe süresi (ms)", "pulse_ms"),
            ("Bekleme süresi (ms)", "cooldown_ms"),
            ("FOLLOW güvenlik kesmesi (ms)", "follow_max_ms"),
            ("Coin/Start/Bomba tuş darbesi (ms)", "key_pulse_ms"),
            ("Hareketsizlik (sn, 0=kapalı)", "inactivity_s"),
        ]
        for row, (label, key) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=5)
            if key == "relay_mode":
                ttk.Combobox(
                    frame,
                    values=("PULSE", "FOLLOW", "OFF"),
                    state="readonly",
                    textvariable=self.controller_vars[key],
                    width=18,
                ).grid(row=row, column=1, sticky="w", padx=4, pady=5)
            else:
                limits = {
                    "pulse_ms": (10, 500),
                    "cooldown_ms": (20, 2000),
                    "follow_max_ms": (20, 1000),
                    "key_pulse_ms": (20, 200),
                    "inactivity_s": (0, 3600),
                }
                minimum, maximum = limits[key]
                ttk.Spinbox(
                    frame,
                    from_=minimum,
                    to=maximum,
                    textvariable=self.controller_vars[key],
                    width=20,
                ).grid(row=row, column=1, sticky="w", padx=4, pady=5)

        ttk.Checkbutton(frame, text="Röle aktif LOW", variable=self.controller_vars["active_low"]).grid(
            row=0, column=2, sticky="w", padx=16
        )
        ttk.Checkbutton(
            frame,
            text="Controller tetiklerini oyuna gönder (önerilen: açık)",
            variable=self.controller_vars["trigger_hid"],
        ).grid(row=1, column=2, sticky="w", padx=16)

        ttk.Button(frame, text="Uygula ve Pico'ya Kaydet", command=self._apply_controller_settings).grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=4, pady=(14, 4)
        )
        ttk.Button(frame, text="Varsayılanlar + Kaydet", command=self._controller_defaults).grid(
            row=6, column=2, sticky="ew", padx=4, pady=(14, 4)
        )
        ttk.Button(frame, text="Controller BOOTSEL", command=self._controller_bootsel).grid(
            row=7, column=2, sticky="ew", padx=4, pady=4
        )
        frame.columnconfigure(2, weight=1)

        warning = (
            "PULSE modu önerilir: tetik yükselen kenarında röle kısa süre çalışır. FOLLOW modu tetiği izler ancak bobin/solenoid koruması için "
            "belirlenen maksimum sürede zorla kapanır. Röleyi Pico GPIO'suna doğrudan bağlamayın; sürücü/transistör ve flyback diyot kullanın."
        )
        ttk.Label(self.controller_tab, text=warning, wraplength=980).pack(anchor="w", padx=12, pady=12)

    def _build_game_tab(self) -> None:
        frame = ttk.LabelFrame(self.game_tab, text="TeknoParrot / Oyun Başlatıcı", padding=12)
        frame.pack(fill="both", expand=True)
        self.game_vars: dict[str, tk.Variable] = {
            "executable": tk.StringVar(),
            "profile": tk.StringVar(),
            "arguments": tk.StringVar(),
            "working_dir": tk.StringVar(),
            "start_minimized": tk.BooleanVar(value=True),
            "start_delay": tk.IntVar(value=25),
            "restart_delay": tk.IntVar(value=10),
            "auto_start": tk.BooleanVar(value=False),
            "auto_restart": tk.BooleanVar(value=False),
            "require_devices": tk.BooleanVar(value=True),
            "macro_enabled": tk.BooleanVar(value=False),
            "windows_autostart": tk.BooleanVar(value=False),
        }

        ttk.Label(frame, text="TeknoParrotUi.exe / oyun EXE").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.game_vars["executable"]).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Seç", command=self._browse_executable).grid(row=0, column=2)

        ttk.Label(frame, text="Profil XML").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.game_vars["profile"]).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Seç", command=self._browse_profile).grid(row=1, column=2)

        ttk.Label(frame, text="Ek argümanlar").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.game_vars["arguments"]).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)

        ttk.Label(frame, text="Çalışma klasörü (boşsa EXE klasörü)").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.game_vars["working_dir"]).grid(row=3, column=1, columnspan=2, sticky="ew", padx=6)

        options = ttk.Frame(frame)
        options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(options, text="--startMinimized", variable=self.game_vars["start_minimized"]).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="Windows açılınca oyunu başlat", variable=self.game_vars["auto_start"]).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="Oyun kapanırsa yeniden başlat", variable=self.game_vars["auto_restart"]).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="3 Pico bağlı olsun", variable=self.game_vars["require_devices"]).pack(side="left", padx=4)

        delay_frame = ttk.Frame(frame)
        delay_frame.grid(row=5, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(delay_frame, text="Oyun yükleme / makro gecikmesi (sn):").pack(side="left")
        ttk.Spinbox(delay_frame, from_=0, to=300, textvariable=self.game_vars["start_delay"], width=8).pack(side="left", padx=6)
        ttk.Label(delay_frame, text="Yeniden başlatma (sn):").pack(side="left", padx=(14, 0))
        ttk.Spinbox(delay_frame, from_=1, to=300, textvariable=self.game_vars["restart_delay"], width=8).pack(side="left", padx=6)
        ttk.Checkbutton(delay_frame, text="1 kredi servis makrosunu çalıştır", variable=self.game_vars["macro_enabled"]).pack(side="left", padx=16)

        ttk.Label(
            frame,
            text="Servis makrosu JSON (oyunun test menüsü tuş sırasına göre doldurulur):",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 4))
        self.macro_text = tk.Text(frame, height=10, wrap="none", font=("Consolas", 10))
        self.macro_text.grid(row=7, column=0, columnspan=3, sticky="nsew")

        bottom = ttk.Frame(frame)
        bottom.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        ttk.Checkbutton(bottom, text="Programı Windows açılışına ekle", variable=self.game_vars["windows_autostart"]).pack(side="left")
        ttk.Button(bottom, text="Ayarları Kaydet", command=self._save_game_settings).pack(side="right", padx=4)
        ttk.Button(bottom, text="Oyunu Başlat", command=self._launch_game).pack(side="right", padx=4)
        ttk.Button(bottom, text="Oyunu Durdur", command=self._stop_game).pack(side="right", padx=4)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

    def _build_firmware_tab(self) -> None:
        text = (
            "GitHub Actions üç UF2 üretir: gt_controller.uf2, gt_gun_p1.uf2 ve gt_gun_p2.uf2. "
            "Aşağıdaki düğme ilgili Pico'yu RPI-RP2/BOOTSEL disk moduna geçirir. Ardından doğru UF2 dosyasını o diske kopyalayın."
        )
        ttk.Label(self.firmware_tab, text=text, wraplength=960).pack(anchor="w", pady=(0, 14))
        buttons = ttk.Frame(self.firmware_tab)
        buttons.pack(anchor="w")
        ttk.Button(buttons, text="Controller → BOOTSEL", command=self._controller_bootsel).pack(side="left", padx=4)
        ttk.Button(buttons, text="P1 Silah → BOOTSEL", command=lambda: self._send_gun(1, "BOOTSEL")).pack(side="left", padx=4)
        ttk.Button(buttons, text="P2 Silah → BOOTSEL", command=lambda: self._send_gun(2, "BOOTSEL")).pack(side="left", padx=4)
        ttk.Separator(self.firmware_tab).pack(fill="x", pady=18)
        ttk.Label(
            self.firmware_tab,
            text=(
                "Yanlış rol UF2'sini yüklediyseniz Pico bozulmaz; BOOTSEL düğmesini basılı tutarak USB'ye takın ve doğru dosyayı yeniden kopyalayın. "
                "Kalibrasyon kaydı firmware güncellemesinde çoğu zaman korunur; şema değişirse güvenli varsayılanlara dönülür ve yeniden kalibrasyon gerekir."
            ),
            wraplength=960,
        ).pack(anchor="w")

    def _build_log_tab(self) -> None:
        self.log_text = tk.Text(self.log_tab, state="disabled", wrap="none", font=("Consolas", 9))
        y_scroll = ttk.Scrollbar(self.log_tab, orient="vertical", command=self.log_text.yview)
        x_scroll = ttk.Scrollbar(self.log_tab, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.log_tab.columnconfigure(0, weight=1)
        self.log_tab.rowconfigure(0, weight=1)

    def _load_config_into_ui(self) -> None:
        cfg = self.config
        self.game_vars["executable"].set(cfg.game_executable)
        self.game_vars["profile"].set(cfg.game_profile)
        self.game_vars["arguments"].set(cfg.game_arguments)
        self.game_vars["working_dir"].set(cfg.game_working_directory)
        self.game_vars["start_minimized"].set(cfg.teknoparrot_start_minimized)
        self.game_vars["start_delay"].set(cfg.game_start_delay_seconds)
        self.game_vars["restart_delay"].set(cfg.restart_delay_seconds)
        self.game_vars["auto_start"].set(cfg.auto_start_game)
        self.game_vars["auto_restart"].set(cfg.auto_restart_game)
        self.game_vars["require_devices"].set(cfg.require_all_devices)
        self.game_vars["macro_enabled"].set(cfg.one_credit_macro_enabled)
        self.game_vars["windows_autostart"].set(is_autostart_enabled())
        self.macro_text.delete("1.0", "end")
        self.macro_text.insert("1.0", json.dumps(cfg.one_credit_macro, ensure_ascii=False, indent=2))

    def _process_events(self) -> None:
        for _ in range(200):
            try:
                event_type, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            try:
                if event_type == "log":
                    self._append_log(str(payload))
                elif event_type == "device" and isinstance(payload, dict):
                    self._handle_device_event(payload)
                elif event_type == "launcher" and isinstance(payload, dict):
                    self._handle_launcher_event(payload)
                elif event_type == "calibration_hotkey":
                    self._open_calibration_service("keyboard")
            except Exception:  # pragma: no cover - Tk/hardware safety boundary
                self.logger.exception("UI olayı işlenemedi: %s", event_type)
        self.root.after(100, self._process_events)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 3000:
            self.log_text.delete("1.0", "500.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    @staticmethod
    def _device_key(message: dict[str, Any]) -> str | None:
        if message.get("role") == "controller":
            return "controller"
        if message.get("role") == "gun":
            try:
                player = int(message.get("player", 0))
            except (TypeError, ValueError):
                return None
            if player in (1, 2):
                return f"gun{player}"
        return None

    def _sync_motion_to_device(self, key: str) -> None:
        command = f"MOTION {int(self.motion_enabled)}"
        if key == "controller":
            self.controller_motion_sync_pending = self.device_manager.send_to(
                "controller", command
            )
        elif key in {"gun1", "gun2"}:
            player = 1 if key == "gun1" else 2
            self.device_manager.send_to("gun", command, player=player)

    def _show_motion_notice(self, enabled: bool) -> None:
        try:
            self.root.bell()
        except tk.TclError:
            pass

        if self.motion_notice is not None:
            try:
                self.motion_notice.destroy()
            except tk.TclError:
                pass
            self.motion_notice = None

        notice = tk.Toplevel(self.root)
        self.motion_notice = notice
        notice.overrideredirect(True)
        notice.attributes("-topmost", True)
        notice.configure(bg="#111820")
        text = "SİLAH HAREKETİ AKTİF" if enabled else "SİLAH HAREKETİ PASİF"
        label = tk.Label(
            notice,
            text=text,
            bg="#111820",
            fg="#ffffff",
            font=("Segoe UI", 22, "bold"),
            padx=32,
            pady=20,
        )
        label.pack()
        notice.update_idletasks()
        width = notice.winfo_reqwidth()
        height = notice.winfo_reqheight()
        screen_width = notice.winfo_screenwidth()
        x = max(0, (screen_width - width) // 2)
        notice.geometry(f"{width}x{height}+{x}+40")

        def close_notice() -> None:
            if self.motion_notice is notice:
                self.motion_notice = None
            try:
                notice.destroy()
            except tk.TclError:
                pass

        notice.after(1800, close_notice)

    def _set_motion_enabled(
        self,
        enabled: bool,
        source: str,
        *,
        update_controller: bool,
        notify: bool,
    ) -> None:
        enabled = bool(enabled)
        changed = self.motion_enabled != enabled
        self.motion_enabled = enabled
        self.motion_status_var.set(
            "Silah hareketi: AKTİF" if enabled else "Silah hareketi: PASİF"
        )

        controller_status = self.device_data["controller"].setdefault("status", {})
        controller_status["motion_enabled"] = enabled
        for player in (1, 2):
            gun_status = self.device_data[f"gun{player}"].setdefault("status", {})
            gun_status["motion_enabled"] = enabled
            if not gun_status.get("calibrating"):
                gun_status["enabled"] = enabled

        command = f"MOTION {int(enabled)}"
        if update_controller:
            self.controller_motion_sync_pending = self.device_manager.send_to(
                "controller", command
            )
        for player in (1, 2):
            self.device_manager.send_to("gun", command, player=player)

        if changed:
            state = "AKTİF" if enabled else "PASİF"
            self.logger.info("Silah hareketi %s yapıldı. Kaynak: %s", state, source)
            if notify:
                self._show_motion_notice(enabled)
        self._refresh_status_ui()

    def _set_calibration_service_text(self, text: str) -> None:
        variable = getattr(self, "calibration_service_var", None)
        if variable is not None:
            variable.set(text)

    def _restore_calibration_window(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.notebook.select(self.calibration_tab)
            self.root.attributes("-topmost", True)
            self.root.after(800, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except tk.TclError:
            self.logger.warning("Kalibrasyon penceresi öne getirilemedi")

    def _open_calibration_service(self, source: str) -> None:
        """Enter one fail-safe calibration/settings session.

        The dual-Start command is deliberately not a motion toggle. It always
        enters this session, disables both gun cursors, suppresses game input
        through Controller maintenance mode, and restores the calibration UI.
        """

        was_active = self.calibration_service_active
        self.calibration_service_active = True
        self.calibration_service_source = source
        self.calibration_service_last_refresh = time.monotonic()
        self._enter_maintenance_mode()
        self._set_motion_enabled(
            False,
            f"calibration_service:{source}",
            update_controller=True,
            notify=not was_active,
        )
        self._set_calibration_service_text(
            "AÇIK — iki silahın hareketi PASİF; ayar/kalibrasyon bekleniyor"
        )
        self._restore_calibration_window()
        if not was_active:
            self.logger.info("Kalibrasyon oturumu açıldı. Kaynak: %s", source)

    def _cancel_pending_service_save_timer(self) -> None:
        if self.calibration_service_save_after_id is None:
            return
        try:
            self.root.after_cancel(self.calibration_service_save_after_id)
        except tk.TclError:
            pass
        self.calibration_service_save_after_id = None

    def _complete_calibration_service_exit(
        self,
        *,
        saved: bool,
        source: str,
    ) -> None:
        self._cancel_pending_service_save_timer()
        self.calibration_service_pending_saves.clear()
        if self.calibration_overlay is not None:
            self.calibration_overlay.close()
            self.calibration_overlay = None
        self.active_calibration_player = None
        for player in (1, 2):
            self.calibration_active[player] = False
            status = self.device_data[f"gun{player}"].setdefault("status", {})
            status["calibrating"] = False

        # Enable X/Y first, then release Controller maintenance. This prevents
        # game buttons from returning before the cursors are ready.
        self._set_motion_enabled(
            True,
            source,
            update_controller=True,
            notify=True,
        )
        self._leave_maintenance_mode()
        self.calibration_service_active = False
        self.calibration_service_source = ""
        self._set_calibration_service_text(
            "Tamamlandı ve kaydedildi — iki silah AKTİF"
            if saved
            else "Kapatıldı — önceki kayıt korundu, iki silah AKTİF"
        )
        self.logger.info(
            "Kalibrasyon oturumu kapatıldı. kayıt=%s kaynak=%s",
            saved,
            source,
        )

    def _cancel_calibration_service(self) -> None:
        player = self.active_calibration_player
        if player in (1, 2):
            self.device_manager.send_to("gun", "CAL CANCEL", player=player)
            self.calibration_vars[player]["state"].set(
                "Kalibrasyon iptal edildi; önceki ayar korunuyor"
            )
        self._complete_calibration_service_exit(
            saved=False,
            source="service_cancel",
        )

    def _gun_settings_commands(self, player: int) -> list[str]:
        variables = self.calibration_vars[player]
        overscan = self._bounded_int(
            variables["overscan"], "Kenar payı", 0, 8
        )
        return [
            "APPLY "
            f"{overscan} "
            f"{int(bool(variables['invert_x'].get()))} "
            f"{int(bool(variables['invert_y'].get()))}"
        ]

    def _begin_service_save_and_exit(
        self,
        players: set[int],
        *,
        reason: str,
    ) -> None:
        if not self.calibration_service_active:
            self._open_calibration_service(reason)

        connected_players = {
            player
            for player in players
            if self.device_data[f"gun{player}"].get("info")
        }
        if not connected_players:
            messagebox.showwarning(
                "Silah Pico bulunamadı",
                "Kaydedilecek bağlı bir silah Pico bulunamadı. Hareket yeniden aktif edilecek.",
            )
            self._complete_calibration_service_exit(
                saved=False,
                source="save_no_device",
            )
            return

        try:
            command_map = {
                player: self._gun_settings_commands(player)
                for player in connected_players
            }
        except ValueError as exc:
            messagebox.showerror("Silah ayarı", str(exc))
            return

        self._cancel_pending_service_save_timer()
        self.calibration_service_pending_saves = set(connected_players)
        self._set_calibration_service_text("Ayarlar Pico belleğine kaydediliyor…")
        for player, commands in command_map.items():
            for command in commands:
                if not self.device_manager.send_to("gun", command, player=player):
                    self._service_save_failed(
                        player,
                        "Seri bağlantıya komut gönderilemedi.",
                    )
                    return

        self.calibration_service_save_after_id = self.root.after(
            5000,
            self._service_save_timeout,
        )
        self.logger.info(
            "Kalibrasyon oturumu kayıt kuyruğu: oyuncular=%s neden=%s",
            sorted(connected_players),
            reason,
        )

    def _handle_service_save_ack(self, player: int) -> None:
        if player not in self.calibration_service_pending_saves:
            return
        self.calibration_service_pending_saves.discard(player)
        if self.calibration_service_pending_saves:
            return
        self._complete_calibration_service_exit(
            saved=True,
            source="save_confirmed",
        )

    def _service_save_failed(self, player: int, error: str) -> None:
        if player not in self.calibration_service_pending_saves:
            return
        self._cancel_pending_service_save_timer()
        self.calibration_service_pending_saves.clear()
        messagebox.showerror(
            "Ayar kaydı başarısız",
            f"Oyuncu {player} ayarları kaydedilemedi: {error}\n"
            "Önceki geçerli kayıt korunmuştur.",
        )
        self._complete_calibration_service_exit(
            saved=False,
            source="save_failed",
        )

    def _service_save_timeout(self) -> None:
        self.calibration_service_save_after_id = None
        if not self.calibration_service_pending_saves:
            return
        players = ", ".join(str(player) for player in sorted(
            self.calibration_service_pending_saves
        ))
        self.calibration_service_pending_saves.clear()
        messagebox.showerror(
            "Ayar kaydı zaman aşımı",
            f"Oyuncu {players} Pico kayıt onayı alınamadı. "
            "Önceki geçerli kayıt korunmuştur.",
        )
        self._complete_calibration_service_exit(
            saved=False,
            source="save_timeout",
        )

    def _save_service_settings_and_exit(self) -> None:
        if self.active_calibration_player is not None:
            messagebox.showwarning(
                "Kalibrasyon devam ediyor",
                "Önce açık dört köşe kalibrasyonunu tamamlayın veya iptal edin.",
            )
            return
        if not self.calibration_service_active:
            self._open_calibration_service("settings_button")
        self._begin_service_save_and_exit({1, 2}, reason="settings_button")

    def _auto_save_completed_calibration(self, player: int) -> None:
        if not self.calibration_service_active:
            return
        # The corner data of the calibrated gun is already committed by its
        # firmware. Save the visible service profile of every connected gun as
        # one acknowledged exit transaction, then reactivate both cursors.
        self._begin_service_save_and_exit(
            {1, 2},
            reason=f"calibration_complete_p{player}",
        )

    @staticmethod
    def _optional_nonnegative_int(value: Any) -> int | None:
        try:
            result = int(value)
        except (TypeError, ValueError):
            return None
        return result if result >= 0 else None

    def _handle_motion_message(self, message: dict[str, Any]) -> None:
        if message.get("role") != "controller":
            return
        enabled = bool(message.get("enabled", True))
        source = str(message.get("source", "controller"))
        change_id = self._optional_nonnegative_int(message.get("change_id"))
        if change_id is not None:
            self.controller_motion_change_id = change_id
        self.controller_motion_sync_pending = False
        if self.calibration_service_active and enabled:
            self._set_motion_enabled(
                False,
                "calibration_service_reassert",
                update_controller=True,
                notify=False,
            )
            return
        self._set_motion_enabled(
            enabled,
            source,
            update_controller=False,
            notify=self.motion_enabled != enabled,
        )

    def _handle_controller_motion_status(self, message: dict[str, Any]) -> None:
        if "motion_enabled" not in message:
            return
        enabled = bool(message.get("motion_enabled"))
        change_id = self._optional_nonnegative_int(
            message.get("motion_change_id")
        )

        # The one-shot calibration_request line may be dropped by a busy CDC
        # queue. Controller's periodic state still exposes the fail-safe pair
        # maintenance=true + motion=false, which is sufficient to restore the
        # calibration window without turning this into a general motion toggle.
        if (
            bool(message.get("maintenance"))
            and not enabled
            and not self.calibration_service_active
        ):
            self._open_calibration_service("controller_status_recovery")

        if self.controller_motion_sync_pending:
            if enabled == self.motion_enabled:
                self.controller_motion_sync_pending = False
                if change_id is not None:
                    self.controller_motion_change_id = change_id
            else:
                # The status may have been queued just before our command. Retry
                # until Controller confirms the runtime-only session state.
                self.device_manager.send_to(
                    "controller", f"MOTION {int(self.motion_enabled)}"
                )
            return

        if change_id is None:
            return
        if self.controller_motion_change_id is None:
            self.controller_motion_change_id = change_id
            if enabled != self.motion_enabled:
                self.controller_motion_sync_pending = self.device_manager.send_to(
                    "controller", f"MOTION {int(self.motion_enabled)}"
                )
            return
        if change_id == self.controller_motion_change_id:
            return

        # Recovery path: a one-shot motion_state event may be dropped when the
        # CDC TX queue is busy. The periodic status carries the same change ID.
        self.controller_motion_change_id = change_id
        self._set_motion_enabled(
            enabled,
            "controller_status_recovery",
            update_controller=False,
            notify=self.motion_enabled != enabled,
        )

    def _handle_controller_input(self, message: dict[str, Any]) -> None:
        player = self.active_calibration_player
        if player not in (1, 2) or not bool(message.get("active")):
            return
        expected = f"P{player}_TRIGGER"
        if str(message.get("name", "")) != expected:
            return
        if not self.device_manager.send_to("gun", "CAL CAPTURE", player=player):
            self.logger.warning(
                "P%d kalibrasyon ölçümü silah Pico'ya gönderilemedi", player
            )

    def _mark_device_disconnected(self, key: str) -> None:
        self.device_data[key].clear()
        if key == "controller":
            self.controller_motion_change_id = None
            self.controller_motion_sync_pending = False
        if key == "controller" and self.calibration_service_active:
            player = self.active_calibration_player
            if player in (1, 2):
                self.device_manager.send_to("gun", "CAL CANCEL", player=player)
                self.calibration_active[player] = False
                self.calibration_vars[player]["state"].set(
                    "Ortak kontrol bağlantısı kesildi; kalibrasyon güvenlik için iptal edildi"
                )
            self._complete_calibration_service_exit(
                saved=False,
                source="controller_disconnect",
            )
            self.logger.warning(
                "Kalibrasyon oturumu Controller bağlantısı kesildiği için kapatıldı"
            )
        elif key in {"gun1", "gun2"}:
            player = 1 if key == "gun1" else 2
            was_active = self.active_calibration_player == player
            self.calibration_active[player] = False
            self.calibration_vars[player]["state"].set("Cihaz bağlantısı kesildi")
            self.calibration_vars[player]["raw"].set("Ham sinyal X/Y: - / -")
            self.calibration_vars[player]["quality"].set("Ölçüm kalitesi: -")
            self.calibration_vars[player]["quality_score"].set(0)
            if player in self.calibration_service_pending_saves:
                self._service_save_failed(player, "USB bağlantısı kesildi.")
                return
            if was_active:
                self._finish_calibration_session(player)
        self._refresh_status_ui()

    def _handle_device_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event_type")
        if event_type in {"port_error", "protocol_error"}:
            self.logger.warning("%s: %s", event.get("port"), event.get("error"))
            if event_type == "port_error":
                key = self.port_roles.pop(str(event.get("port")), None)
                if key is not None:
                    self._mark_device_disconnected(key)
            return
        if event_type == "port_closed":
            key = self.port_roles.pop(str(event.get("port")), None)
            if key is not None:
                self._mark_device_disconnected(key)
            return
        if event_type == "port_opened":
            self.logger.info("Seri port açıldı: %s", event.get("port"))
            return
        if event_type != "message":
            return

        message = event.get("message")
        if not isinstance(message, dict):
            return
        key = self._device_key(message)
        if key is not None:
            message_type = str(message.get("type", "event"))
            self.device_data[key][message_type] = message
            if message_type == "info":
                self.port_roles[str(event.get("port"))] = key
                # Gun reconnects receive the current runtime state immediately.
                # Controller is different: first wait for its STATUS packet so
                # a calibration request made while the desktop was restarting
                # is not overwritten with MOTION 1 before it can be recovered.
                if key != "controller":
                    self._sync_motion_to_device(key)

        if (
            message.get("event") == "input"
            and message.get("role") == "controller"
        ):
            self._handle_controller_input(message)
        elif message.get("event") == "motion_state":
            self._handle_motion_message(message)
        elif (
            message.get("event") == "calibration_request"
            and message.get("role") == "controller"
        ):
            self._open_calibration_service(
                str(message.get("source", "start_buttons"))
            )
        elif (
            message.get("type") == "status"
            and message.get("role") == "controller"
        ):
            self._handle_controller_motion_status(message)

        if (
            message.get("ok") is True
            and message.get("saved") is True
            and message.get("profile") is True
            and message.get("role") == "gun"
        ):
            try:
                saved_player = int(message.get("player", 0))
            except (TypeError, ValueError):
                saved_player = 0
            if saved_player in (1, 2):
                self._handle_service_save_ack(saved_player)
        elif message.get("ok") is False and message.get("role") == "gun":
            try:
                failed_player = int(message.get("player", 0))
            except (TypeError, ValueError):
                failed_player = 0
            if failed_player in self.calibration_service_pending_saves:
                self._service_save_failed(
                    failed_player,
                    str(message.get("error", "bilinmeyen hata")),
                )

        calibration_events = {
            "cal_ready",
            "cal_point",
            "cal_retry",
            "cal_complete",
            "cal_error",
            "cal_cancelled",
            "cal_reset",
        }
        if message.get("event") in calibration_events:
            self._handle_calibration_event(message)
        elif message.get("event") and message.get("event") not in {
            "input",
            "motion_state",
            "calibration_request",
            "calibration_hold_started",
            "calibration_hold_cancelled",
        }:
            self.logger.info("Pico olayı: %s", message)
        elif message.get("ok") is False:
            self.logger.warning("Pico komut hatası: %s", message.get("error"))

        self._refresh_status_ui()
        if message.get("type") == "config":
            self._load_device_config(message)

    def _handle_calibration_event(self, message: dict[str, Any]) -> None:
        try:
            player = int(message.get("player", 0))
        except (TypeError, ValueError):
            return
        if player not in (1, 2):
            return

        state = self.calibration_vars[player]["state"]
        status = self.device_data[f"gun{player}"].setdefault("status", {})
        event = str(message.get("event", ""))
        names = {"TL": "SOL ÜST", "TR": "SAĞ ÜST", "BR": "SAĞ ALT", "BL": "SOL ALT"}

        if event == "cal_ready":
            self.calibration_active[player] = True
            status["calibrating"] = True
            point = str(message.get("point", ""))
            status["next_point"] = point
            state.set(f"{names.get(point, point)} hedefi bekleniyor")
            if self.active_calibration_player == player and self.calibration_overlay is not None:
                self.calibration_overlay.set_point(point)
        elif event == "cal_point":
            self.calibration_active[player] = True
            status["calibrating"] = True
            point = str(message.get("point", ""))
            state.set(f"{names.get(point, point)} kaydedildi")
        elif event == "cal_retry":
            self.calibration_active[player] = True
            status["calibrating"] = True
            point = str(message.get("point", ""))
            state.set(f"{names.get(point, point)} ölçümü kararsız; aynı hedefe tekrar ateş edin")
            if self.active_calibration_player == player and self.calibration_overlay is not None:
                self.calibration_overlay.show_retry(point)
        elif event == "cal_complete":
            self.calibration_active[player] = False
            status["calibrating"] = False
            status["calibrated"] = True
            quality = int(message.get("quality", 100))
            x_span = int(message.get("x_span", 0))
            y_span = int(message.get("y_span", 0))
            status["quality"] = quality
            status["x_span"] = x_span
            status["y_span"] = y_span
            self.calibration_vars[player]["quality_score"].set(quality)
            self.calibration_vars[player]["quality"].set(f"Ölçüm kalitesi: %{quality}")
            state.set("Kalibrasyon tamamlandı ve Pico'ya kaydedildi")
            if self.active_calibration_player == player and self.calibration_overlay is not None:
                self.calibration_overlay.show_success(quality, x_span, y_span)
            if self.calibration_service_active:
                # Even if the desktop was restored after a temporary UI loss,
                # never bypass the acknowledged profile-save stage.
                self._set_calibration_service_text(
                    "Kalibrasyon kaydedildi; bağlı silah ayarları onaylanıyor…"
                )
                self.root.after(
                    1200,
                    lambda p=player: self._auto_save_completed_calibration(p),
                )
            else:
                self._complete_calibration_service_exit(
                    saved=True,
                    source="calibration_complete_without_service",
                )
            self.logger.info("P%d kalibrasyonu tamamlandı: %s", player, message)
        elif event == "cal_error":
            self.calibration_active[player] = False
            status["calibrating"] = False
            errors = {
                "range_too_small": "Hareket aralığı yetersiz. Mekanik bağlantıyı kontrol edip yeniden deneyin.",
                "wrong_order": "Köşeler doğru sırada alınmadı. Kalibrasyonu yeniden başlatın.",
                "flash_save_failed": "Kayıt başarısız; önceki geçerli ayar korundu.",
                "calibration_busy": "Kalibrasyon zaten çalışıyor.",
                "calibration_not_active": "Kalibrasyon ölçümü için etkin bir oturum bulunamadı.",
                "timeout": "Kalibrasyon zaman aşımına uğradı; önceki ayar korundu.",
            }
            error = str(message.get("error", "unknown"))
            text = errors.get(error, f"Kalibrasyon hatası: {error}")
            state.set(text)
            self._finish_calibration_session(player)
            messagebox.showerror(f"Oyuncu {player} kalibrasyon", text)
            self.logger.warning("P%d kalibrasyon hatası: %s", player, message)
        elif event == "cal_cancelled":
            self.calibration_active[player] = False
            status["calibrating"] = False
            state.set("Kalibrasyon iptal edildi; önceki ayar korundu")
            self._finish_calibration_session(player)
        elif event == "cal_reset":
            self.calibration_active[player] = False
            status["calibrating"] = False
            status["calibrated"] = False
            self.calibration_vars[player]["quality_score"].set(0)
            self.calibration_vars[player]["quality"].set("Ölçüm kalitesi: -")
            state.set("Kalibrasyon sıfırlandı; yeniden kalibrasyon gerekli")

    def _load_device_config(self, message: dict[str, Any]) -> None:
        if message.get("role") == "controller":
            mapping = {
                "relay_mode": message.get("relay_mode", "PULSE"),
                "active_low": bool(message.get("relay_active_low", True)),
                "pulse_ms": int(message.get("pulse_ms", 60)),
                "cooldown_ms": int(message.get("cooldown_ms", 120)),
                "follow_max_ms": int(message.get("follow_max_ms", 250)),
                "key_pulse_ms": int(message.get("key_pulse_ms", 80)),
                "inactivity_s": int(message.get("inactivity_s", 300)),
                "trigger_hid": bool(message.get("trigger_hid", True)),
            }
            for key, value in mapping.items():
                self.controller_vars[key].set(value)
        elif message.get("role") == "gun":
            try:
                player = int(message.get("player", 0))
            except (TypeError, ValueError):
                return
            if player not in self.calibration_vars:
                return
            variables = self.calibration_vars[player]
            variables["overscan"].set(int(message.get("overscan", 2)))
            variables["invert_x"].set(bool(message.get("invert_x", False)))
            variables["invert_y"].set(bool(message.get("invert_y", False)))
            quality = int(message.get("quality", 0)) if message.get("calibrated") else 0
            variables["quality_score"].set(quality)
            variables["quality"].set(
                f"Ölçüm kalitesi: %{quality}" if quality else "Ölçüm kalitesi: -"
            )

    def _refresh_status_ui(self) -> None:
        point_names = {"TL": "SOL ÜST", "TR": "SAĞ ÜST", "BR": "SAĞ ALT", "BL": "SOL ALT"}
        device_health: dict[str, bool] = {}
        for snapshot in self.device_manager.snapshot():
            info = snapshot.get("info")
            if not isinstance(info, dict):
                continue
            device_key = self._device_key(info)
            if device_key is not None:
                device_health[device_key] = bool(snapshot.get("responsive"))

        for key in ("controller", "gun1", "gun2"):
            info = self.device_data[key].get("info", {})
            status = self.device_data[key].get("status", {})
            variables = self.status_vars[key]
            if not info:
                variables["connection"].set("Bağlı değil")
                variables["version"].set("Sürüm: -")
                variables["line1"].set("-")
                variables["line2"].set("-")
                variables["line3"].set("-")
                continue

            if device_health.get(key):
                variables["connection"].set("BAĞLI / HAZIR")
            else:
                variables["connection"].set("BAĞLI / CANLI VERİ BEKLENİYOR")
            variables["version"].set(f"Sürüm: {info.get('version', '-')}")
            if key == "controller":
                variables["line1"].set(
                    f"Coin: {self._on_off(status.get('coin'))} | "
                    f"P1 Start: {self._on_off(status.get('p1_start'))} | "
                    f"P2 Start: {self._on_off(status.get('p2_start'))}"
                )
                variables["line2"].set(
                    f"P1 Röle: {self._on_off(status.get('p1_relay'))} | "
                    f"P2 Röle: {self._on_off(status.get('p2_relay'))}"
                )
                variables["line3"].set(
                    f"P1 hazır: {self._on_off(status.get('p1_armed'))} | "
                    f"P2 hazır: {self._on_off(status.get('p2_armed'))} | "
                    f"Hareket: {self._on_off(status.get('motion_enabled', self.motion_enabled))} | "
                    f"Bakım: {self._on_off(status.get('maintenance'))}"
                )
                continue

            player = 1 if key == "gun1" else 2
            variables["line1"].set(
                f"Ham X/Y: {status.get('raw_x', '-')} / {status.get('raw_y', '-')}"
            )
            variables["line2"].set(
                f"Ekran X/Y: {status.get('x', '-')} / {status.get('y', '-')}"
            )
            variables["line3"].set(
                f"Hareket: {self._on_off(status.get('motion_enabled', self.motion_enabled))} | "
                f"Kalibre: {self._on_off(status.get('calibrated'))}"
            )
            self.calibration_vars[player]["raw"].set(
                f"Ham sinyal X/Y: {status.get('raw_x', '-')} / {status.get('raw_y', '-')}"
            )
            quality = int(status.get("quality", 0) or 0)
            if quality:
                self.calibration_vars[player]["quality_score"].set(quality)
                self.calibration_vars[player]["quality"].set(f"Ölçüm kalitesi: %{quality}")

            if bool(status.get("calibrating")):
                self.calibration_active[player] = True
                point = str(status.get("next_point", ""))
                if point in point_names:
                    self.calibration_vars[player]["state"].set(
                        f"{point_names[point]} konumuna nişan al, tetiğe bas ve bırak"
                    )
            elif not self.calibration_active[player] and status:
                self.calibration_vars[player]["state"].set(
                    "Kalibre / hazır" if status.get("calibrated") else "Kalibrasyon gerekli"
                )

    @staticmethod
    def _bounded_int(variable: tk.Variable, label: str, minimum: int, maximum: int) -> int:
        try:
            value = int(variable.get())
        except (TypeError, ValueError, tk.TclError) as exc:
            raise ValueError(f"{label} sayı olmalıdır.") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{label} {minimum} ile {maximum} arasında olmalıdır.")
        return value

    @staticmethod
    def _on_off(value: Any) -> str:
        return "AÇIK" if bool(value) else "KAPALI"

    def _handle_launcher_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("event_type")
        if event_type == "started":
            self.game_status_var.set(f"Oyun: çalışıyor (PID {event.get('pid')})")
            self.logger.info("Oyun işlemi başladı: PID %s", event.get("pid"))
        elif event_type == "exited":
            self.game_status_var.set(f"Oyun: kapandı ({event.get('return_code')})")
            self.logger.warning("Oyun kapandı. Kod: %s", event.get("return_code"))
        elif event_type == "macro_started":
            self.game_status_var.set("Oyun: 1 kredi makrosu çalışıyor")
        elif event_type == "macro_finished":
            self.game_status_var.set("Oyun: çalışıyor")
            self.logger.info("Servis makrosu tamamlandı: %s", event.get("completed"))
        elif event_type == "macro_error":
            self.game_status_var.set("Oyun: çalışıyor / servis makrosu başarısız")
            self.logger.error("Servis makrosu hatası: %s", event.get("error"))
        elif event_type == "restart_wait":
            self.game_status_var.set("Oyun: yeniden başlatma bekleniyor")
        elif event_type == "error":
            self.game_status_var.set("Oyun: başlatma hatası")
            self.logger.error("Oyun başlatma hatası: %s", event.get("error"))
            if self.config.auto_start_game and not self.launcher.is_running:
                self.auto_launch_done = False

    def _periodic_tasks(self) -> None:
        self._refresh_status_ui()
        now = time.monotonic()
        if (
            self.calibration_service_active
            and now - self.calibration_service_last_refresh >= 60.0
        ):
            # Both firmwares have a 180-second fail-safe. Refresh only while the
            # desktop service session is genuinely alive.
            self.calibration_service_last_refresh = now
            self._enter_maintenance_mode()
            self._set_motion_enabled(
                False,
                "calibration_service_keepalive",
                update_controller=True,
                notify=False,
            )
        if self.launcher.is_running:
            self.auto_launch_done = True

        if self.config.auto_start_game and not self.auto_launch_done:
            devices_ready = self.device_manager.all_required_connected()
            if devices_ready or not self.config.require_all_devices:
                if now - self.last_auto_launch_attempt >= 30.0:
                    self.last_auto_launch_attempt = now
                    try:
                        started = self.launcher.launch(self.config)
                    except (ValueError, MacroValidationError) as exc:
                        self.logger.error("Otomatik oyun başlatma ayarı geçersiz: %s", exc)
                    else:
                        if started:
                            self.auto_launch_done = True
                        else:
                            self.logger.warning(
                                "Otomatik oyun başlatma uygulanamadı; 30 saniye sonra yeniden denenecek"
                            )
            elif int(now - self.started_at) % 30 == 0:
                self.game_status_var.set("Oyun: Pico bağlantıları ve canlı veri bekleniyor")
        self.root.after(500, self._periodic_tasks)

    def _send_controller(self, command: str) -> bool:
        sent = self.device_manager.send_to("controller", command)
        if not sent:
            messagebox.showwarning("Cihaz yok", "Ortak kontrol Pico bağlı değil.")
        return sent

    def _send_gun(self, player: int, command: str) -> bool:
        sent = self.device_manager.send_to("gun", command, player=player)
        if not sent:
            messagebox.showwarning("Cihaz yok", f"Oyuncu {player} silah Pico bağlı değil.")
        return sent

    def _enter_maintenance_mode(self) -> bool:
        if not self.device_data["controller"].get("info"):
            return False
        sent = self.device_manager.send_to("controller", "MAINTENANCE 1")
        if not sent:
            self.logger.warning("Kalibrasyon güvenlik modu controller'a gönderilemedi")
        return sent

    def _leave_maintenance_mode(self) -> None:
        if self.device_data["controller"].get("info"):
            self.device_manager.send_to("controller", "MAINTENANCE 0")

    def _finish_calibration_session(self, player: int | None = None) -> None:
        if player is not None and self.active_calibration_player not in {None, player}:
            return
        if self.calibration_service_active:
            self._complete_calibration_service_exit(
                saved=False,
                source="calibration_session_end",
            )
            return
        if self.calibration_overlay is not None:
            self.calibration_overlay.close()
            self.calibration_overlay = None
        self.active_calibration_player = None
        self._set_motion_enabled(
            True,
            "calibration_session_end",
            update_controller=True,
            notify=False,
        )
        self._leave_maintenance_mode()

    def _start_calibration(self, player: int) -> None:
        if self.active_calibration_player is not None:
            messagebox.showwarning(
                "Kalibrasyon çalışıyor",
                f"Önce Oyuncu {self.active_calibration_player} kalibrasyonunu tamamlayın veya iptal edin.",
            )
            return

        info = self.device_data[f"gun{player}"].get("info")
        status = self.device_data[f"gun{player}"].get("status", {})
        controller_status = self.device_data["controller"].get("status", {})
        if not self.device_data["controller"].get("info"):
            messagebox.showwarning(
                "Ortak kontrol bağlı değil",
                "Güvenli kalibrasyon için ortak Controller Pico bağlı ve hazır olmalıdır.",
            )
            return
        if not info:
            messagebox.showwarning("Cihaz yok", f"Oyuncu {player} silah Pico bağlı değil.")
            return
        trigger_key = "p1_trigger" if player == 1 else "p2_trigger"
        if bool(controller_status.get(trigger_key)):
            messagebox.showwarning("Tetik basılı", "Kalibrasyonu başlatmadan önce tetiği bırakın.")
            return

        if not self.calibration_service_active:
            self._open_calibration_service(f"player_{player}_button")

        self.active_calibration_player = player
        self.calibration_overlay = CalibrationOverlay(
            self.root,
            player,
            on_cancel=lambda p=player: self._cancel_calibration(p),
        )
        if not self._enter_maintenance_mode():
            self._finish_calibration_session(player)
            messagebox.showwarning(
                "Güvenlik modu açılamadı",
                "Controller bakım moduna alınamadı; kalibrasyon başlatılmadı.",
            )
            return
        if not self.device_manager.send_to("gun", "CAL START", player=player):
            self._finish_calibration_session(player)
            messagebox.showwarning("Cihaz yok", f"Oyuncu {player} silah Pico'ya ulaşılamadı.")
            return

        self.calibration_active[player] = True
        status = self.device_data[f"gun{player}"].setdefault("status", {})
        status["calibrating"] = True
        status["next_point"] = "TL"
        self.calibration_vars[player]["state"].set("SOL ÜST hedefi bekleniyor")

    def _cancel_calibration(self, player: int) -> None:
        sent = self.device_manager.send_to("gun", "CAL CANCEL", player=player)
        self.calibration_active[player] = False
        status = self.device_data[f"gun{player}"].setdefault("status", {})
        status["calibrating"] = False
        self.calibration_vars[player]["state"].set(
            "Kalibrasyon iptal edildi; önceki ayar korunuyor"
        )
        self._finish_calibration_session(player)
        if not sent:
            self.logger.warning("P%d kalibrasyon iptali cihaza gönderilemedi", player)

    def _reset_calibration(self, player: int) -> None:
        if self.active_calibration_player is not None:
            messagebox.showwarning("Kalibrasyon çalışıyor", "Önce açık kalibrasyonu kapatın.")
            return
        if not messagebox.askyesno(
            "Kalibrasyonu sıfırla",
            f"Oyuncu {player} kalibrasyonu silinecek. Devam edilsin mi?",
        ):
            return
        if self._send_gun(player, "CAL RESET"):
            self.calibration_vars[player]["state"].set("Sıfırlama Pico'ya kaydediliyor…")

    def _apply_gun_settings(self, player: int) -> None:
        try:
            commands = self._gun_settings_commands(player)
        except ValueError as exc:
            messagebox.showerror("Silah ayarı", str(exc))
            return
        for command in commands:
            if not self._send_gun(player, command):
                return
        self.logger.info("P%d servis ayarları kaydetme kuyruğuna alındı", player)

    def _apply_controller_settings(self) -> None:
        variables = self.controller_vars
        relay_mode = str(variables["relay_mode"].get()).upper()
        if relay_mode not in {"PULSE", "FOLLOW", "OFF"}:
            messagebox.showerror("Controller ayarı", "Röle modu geçersiz.")
            return
        try:
            pulse_ms = self._bounded_int(variables["pulse_ms"], "Darbe süresi", 10, 500)
            cooldown_ms = self._bounded_int(variables["cooldown_ms"], "Bekleme süresi", 20, 2000)
            follow_max_ms = self._bounded_int(
                variables["follow_max_ms"], "FOLLOW güvenlik kesmesi", 20, 1000
            )
            key_pulse_ms = self._bounded_int(
                variables["key_pulse_ms"], "Tuş darbesi", 20, 200
            )
            inactivity_s = self._bounded_int(
                variables["inactivity_s"], "Hareketsizlik", 0, 3600
            )
        except ValueError as exc:
            messagebox.showerror("Controller ayarı", str(exc))
            return

        commands = [
            f"SET RELAY_MODE {relay_mode}",
            f"SET RELAY_ACTIVE_LOW {int(bool(variables['active_low'].get()))}",
            f"SET PULSE_MS {pulse_ms}",
            f"SET COOLDOWN_MS {cooldown_ms}",
            f"SET FOLLOW_MAX_MS {follow_max_ms}",
            f"SET KEY_PULSE_MS {key_pulse_ms}",
            f"SET INACTIVITY_S {inactivity_s}",
            f"SET TRIGGER_HID {int(bool(variables['trigger_hid'].get()))}",
            "SAVE",
        ]
        for command in commands:
            if not self._send_controller(command):
                return
        self.logger.info("Controller ayarları kaydetme kuyruğuna alındı")

    def _controller_bootsel(self) -> None:
        confirmed = messagebox.askyesno(
            "Controller BOOTSEL",
            "Controller Pico BOOTSEL moduna alınırken GPIO çıkışları yüksek empedanslı olabilir. "
            "Röle/solenoid yük gücünü kapatın ve mümkünse yük konektörünü ayırın. "
            "Sürücü girişinde harici fail-safe pull-up/pull-down bulunmadan devam etmeyin. "
            "Güvenli bağlantıyı doğruladınız mı?",
        )
        if confirmed:
            self._send_controller("BOOTSEL")

    def _controller_defaults(self) -> None:
        confirmed = messagebox.askyesno(
            "Controller varsayılanları",
            "Varsayılan röle polaritesi AKTİF LOW'dur. Gerçek bobin/solenoid yükü "
            "bağlıyken yanlış polarite tehlikeli olabilir. Yükü ayırdığınızı veya yalnız "
            "LED ile test yaptığınızı doğruluyor musunuz?",
        )
        if confirmed and self._send_controller("DEFAULTS"):
            self._send_controller("SAVE")

    def _browse_executable(self) -> None:
        path = filedialog.askopenfilename(
            title="Oyun çalıştırılabilir dosyasını seç",
            filetypes=(("Windows uygulaması", "*.exe"), ("Tüm dosyalar", "*.*")),
        )
        if path:
            self.game_vars["executable"].set(path)
            if not self.game_vars["working_dir"].get():
                self.game_vars["working_dir"].set(str(Path(path).parent))

    def _browse_profile(self) -> None:
        path = filedialog.askopenfilename(
            title="TeknoParrot profil XML dosyasını seç",
            filetypes=(("XML profil", "*.xml"), ("Tüm dosyalar", "*.*")),
        )
        if path:
            self.game_vars["profile"].set(path)

    def _save_game_settings(self, show_message: bool = True) -> bool:
        try:
            macro_raw = self.macro_text.get("1.0", "end").strip() or "[]"
            macro = validate_macro(json.loads(macro_raw))
            self.config.game_executable = str(self.game_vars["executable"].get()).strip()
            self.config.game_profile = str(self.game_vars["profile"].get()).strip()
            self.config.game_arguments = str(self.game_vars["arguments"].get()).strip()
            self.config.game_working_directory = str(self.game_vars["working_dir"].get()).strip()
            self.config.teknoparrot_start_minimized = bool(self.game_vars["start_minimized"].get())
            self.config.game_start_delay_seconds = self._bounded_int(
                self.game_vars["start_delay"], "Oyun yükleme gecikmesi", 0, 300
            )
            self.config.restart_delay_seconds = self._bounded_int(
                self.game_vars["restart_delay"], "Yeniden başlatma gecikmesi", 1, 300
            )
            self.config.auto_start_game = bool(self.game_vars["auto_start"].get())
            self.config.auto_restart_game = bool(self.game_vars["auto_restart"].get())
            self.config.require_all_devices = bool(self.game_vars["require_devices"].get())
            self.config.one_credit_macro_enabled = bool(self.game_vars["macro_enabled"].get())
            if self.config.one_credit_macro_enabled and not macro:
                raise MacroValidationError(
                    "1 kredi makrosu açıkken en az bir 'wait' veya 'key' adımı gerekir."
                )
            self.config.one_credit_macro = macro
            save_config(self.config)
            set_autostart(bool(self.game_vars["windows_autostart"].get()))
            if show_message:
                messagebox.showinfo("Kaydedildi", "Oyun ve otomatik başlatma ayarları kaydedildi.")
            self.auto_launch_done = self.launcher.is_running
            self.last_auto_launch_attempt = 0.0
            self.logger.info("Uygulama ayarları kaydedildi")
            return True
        except (ValueError, json.JSONDecodeError, MacroValidationError, OSError, tk.TclError) as exc:
            messagebox.showerror("Ayar hatası", str(exc))
            return False

    def _launch_game(self) -> None:
        if not self._save_game_settings(show_message=False):
            return
        if self.config.require_all_devices and not self.device_manager.all_required_connected():
            messagebox.showwarning("Pico eksik", "Controller, P1 ve P2 Pico bağlı olmadan oyun başlatılmadı.")
            return
        try:
            started = self.launcher.launch(self.config)
        except (ValueError, MacroValidationError) as exc:
            messagebox.showerror("Başlatma hatası", str(exc))
            return
        if not started:
            messagebox.showwarning("Oyun", "Oyun zaten çalışıyor veya çalıştırılabilir dosya geçersiz.")

    def _stop_game(self) -> None:
        self.launcher.stop()
        self.game_status_var.set("Oyun: durdu")

    def _on_close(self) -> None:
        self.logger.info("Uygulama kapatılıyor")
        if self.active_calibration_player is not None:
            self.device_manager.send_to(
                "gun", "CAL CANCEL", player=self.active_calibration_player
            )
        self._cancel_pending_service_save_timer()
        self._set_motion_enabled(
            True,
            "application_close",
            update_controller=True,
            notify=False,
        )
        self._leave_maintenance_mode()
        if self.calibration_overlay is not None:
            self.calibration_overlay.close()
            self.calibration_overlay = None
        if self.motion_notice is not None:
            try:
                self.motion_notice.destroy()
            except tk.TclError:
                pass
            self.motion_notice = None
        self.calibration_hotkey.stop()
        self.device_manager.stop()
        self.launcher.stop()
        self.root.destroy()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GT SUPER CONTROLLER")
    parser.add_argument("--minimized", action="store_true", help="Başlangıçta küçült")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    root = tk.Tk()
    GTApp(root, start_minimized=args.minimized)
    root.mainloop()


if __name__ == "__main__":
    main()
