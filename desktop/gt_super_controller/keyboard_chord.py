from __future__ import annotations

import ctypes
import logging
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable


KEY_2 = 2
KEY_5 = 5
VK_2 = 0x32
VK_5 = 0x35
VK_NUMPAD2 = 0x62
VK_NUMPAD5 = 0x65
SUPPORTED_VKS = {
    VK_2: KEY_2,
    VK_NUMPAD2: KEY_2,
    VK_5: KEY_5,
    VK_NUMPAD5: KEY_5,
}


@dataclass
class DualKeyHoldTracker:
    """Pure state machine for a 2+5 hold chord.

    Original key events are expected to be suppressed by the caller. A single
    key is returned as a pulse only after it is released. Once 2 and 5 overlap,
    both are treated as a maintenance chord and no Start pulse is produced,
    even when the hold is cancelled before the timeout.
    """

    hold_seconds: float = 10.0
    down_vks: dict[int, set[int]] = field(
        default_factory=lambda: {KEY_2: set(), KEY_5: set()}
    )
    chord_active: bool = False
    chord_cancelled: bool = False
    chord_fired: bool = False
    chord_started_at: float = 0.0

    def _logical_down(self, key: int) -> bool:
        return bool(self.down_vks[key])

    def key_down(self, logical_key: int, vk_code: int, now: float) -> None:
        if logical_key not in self.down_vks:
            return
        already_down = self._logical_down(logical_key)
        self.down_vks[logical_key].add(vk_code)
        if already_down:
            return

        if self._logical_down(KEY_2) and self._logical_down(KEY_5):
            if not self.chord_active:
                self.chord_active = True
                self.chord_cancelled = False
                self.chord_fired = False
                self.chord_started_at = now

    def key_up(self, logical_key: int, vk_code: int, now: float) -> int | None:
        del now  # Kept in the API so tests/callers can use one clock consistently.
        if logical_key not in self.down_vks:
            return None
        was_down = vk_code in self.down_vks[logical_key]
        self.down_vks[logical_key].discard(vk_code)
        if not was_down:
            return None

        if self.chord_active:
            if not self.chord_fired:
                self.chord_cancelled = True
            if not self._logical_down(KEY_2) and not self._logical_down(KEY_5):
                self._reset_chord()
            return None

        # A normal 2 or 5 tap becomes one clean pulse after release. This keeps
        # the hotkey hook from changing ordinary keyboard/Controller Start use.
        if not self._logical_down(logical_key):
            return vk_code
        return None

    def poll(self, now: float) -> bool:
        if (
            self.chord_active
            and not self.chord_cancelled
            and not self.chord_fired
            and self._logical_down(KEY_2)
            and self._logical_down(KEY_5)
            and now - self.chord_started_at >= self.hold_seconds
        ):
            self.chord_fired = True
            return True
        return False

    def _reset_chord(self) -> None:
        self.chord_active = False
        self.chord_cancelled = False
        self.chord_fired = False
        self.chord_started_at = 0.0
        self.down_vks[KEY_2].clear()
        self.down_vks[KEY_5].clear()


class KeyboardCalibrationHotkey:
    """Global Windows 2+5 calibration shortcut with Start-safe suppression.

    The low-level hook swallows original 2/5 events. Single taps are replayed as
    short key pulses after release, while a simultaneous hold is reserved for
    the 10-second calibration-service request. No third-party package is needed.
    """

    def __init__(
        self,
        on_request: Callable[[], None],
        logger: logging.Logger,
        hold_seconds: float = 10.0,
    ) -> None:
        self.on_request = on_request
        self.logger = logger
        self.tracker = DualKeyHoldTracker(hold_seconds=max(1.0, hold_seconds))
        self._lock = threading.RLock()
        self._pulse_queue: queue.Queue[int] = queue.Queue()
        self._stop_event = threading.Event()
        self._hook_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._ready_event = threading.Event()
        self._thread_id = 0
        self._hook_handle: int | None = None
        self._hook_proc = None

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def start(self) -> None:
        if not self.supported:
            self.logger.info("Klavye 2+5 genel kısayolu yalnız Windows'ta etkindir")
            return
        if self._hook_thread is not None and self._hook_thread.is_alive():
            return

        self._stop_event.clear()
        self._ready_event.clear()
        self._hook_thread = threading.Thread(
            target=self._hook_loop,
            name="GTKeyboardHook",
            daemon=True,
        )
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="GTKeyboardHold",
            daemon=True,
        )
        self._hook_thread.start()
        self._monitor_thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        self._stop_event.set()
        if self.supported and self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
            except (AttributeError, OSError):
                pass
        if self._hook_thread is not None:
            self._hook_thread.join(timeout=2.0)
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2.0)
        self._hook_thread = None
        self._monitor_thread = None

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(0.02):
            request = False
            with self._lock:
                request = self.tracker.poll(time.monotonic())

            while True:
                try:
                    vk_code = self._pulse_queue.get_nowait()
                except queue.Empty:
                    break
                self._inject_pulse(vk_code)

            if request:
                try:
                    self.on_request()
                except Exception:
                    self.logger.exception("Klavye 2+5 kalibrasyon komutu işlenemedi")

    def _inject_pulse(self, vk_code: int) -> None:
        if not self.supported:
            return
        try:
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            ULONG_PTR = ctypes.c_size_t
            KEYEVENTF_KEYUP = 0x0002
            INPUT_KEYBOARD = 1

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk", wintypes.WORD),
                    ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class MOUSEINPUT(ctypes.Structure):
                _fields_ = [
                    ("dx", wintypes.LONG),
                    ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR),
                ]

            class HARDWAREINPUT(ctypes.Structure):
                _fields_ = [
                    ("uMsg", wintypes.DWORD),
                    ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD),
                ]

            class INPUT_UNION(ctypes.Union):
                # Keep the union layout identical to Win32 INPUT on both
                # 32-bit and 64-bit Python, even though only KEYBDINPUT is used.
                _fields_ = [
                    ("mi", MOUSEINPUT),
                    ("ki", KEYBDINPUT),
                    ("hi", HARDWAREINPUT),
                ]

            class INPUT(ctypes.Structure):
                _anonymous_ = ("data",)
                _fields_ = [("type", wintypes.DWORD), ("data", INPUT_UNION)]

            user32.SendInput.argtypes = [
                wintypes.UINT,
                ctypes.POINTER(INPUT),
                ctypes.c_int,
            ]
            user32.SendInput.restype = wintypes.UINT

            events = (INPUT * 2)(
                INPUT(
                    type=INPUT_KEYBOARD,
                    data=INPUT_UNION(
                        ki=KEYBDINPUT(
                            wVk=vk_code,
                            wScan=0,
                            dwFlags=0,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                ),
                INPUT(
                    type=INPUT_KEYBOARD,
                    data=INPUT_UNION(
                        ki=KEYBDINPUT(
                            wVk=vk_code,
                            wScan=0,
                            dwFlags=KEYEVENTF_KEYUP,
                            time=0,
                            dwExtraInfo=0,
                        )
                    ),
                ),
            )
            # SendInput events carry LLKHF_INJECTED. The hook deliberately lets
            # them pass, which prevents recursion while preserving normal Start.
            sent = int(user32.SendInput(2, events, ctypes.sizeof(INPUT)))
            if sent != 2:
                self.logger.error(
                    "Klavye Start darbesi yeniden gönderilemedi (SendInput=%d/2). "
                    "Oyun yönetici olarak çalışıyorsa GT SUPER CONTROLLER da aynı "
                    "yetki düzeyinde çalıştırılmalıdır.",
                    sent,
                )
        except (AttributeError, OSError, TypeError, ValueError):
            self.logger.exception("Klavye Start darbesi yeniden gönderilemedi")

    def _hook_loop(self) -> None:  # pragma: no cover - Windows integration
        from ctypes import wintypes

        WH_KEYBOARD_LL = 13
        HC_ACTION = 0
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        WM_SYSKEYDOWN = 0x0104
        WM_SYSKEYUP = 0x0105
        LLKHF_INJECTED = 0x00000010

        ULONG_PTR = ctypes.c_size_t

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # WPARAM/LPARAM/LRESULT are pointer-sized on 64-bit Windows. Defining
        # them explicitly avoids depending on Python-version-specific aliases
        # in ctypes.wintypes and prevents handle/message truncation.
        WPARAM_T = ctypes.c_size_t
        LPARAM_T = ctypes.c_ssize_t
        LRESULT_T = ctypes.c_ssize_t
        HHOOK_T = wintypes.HANDLE
        HOOKPROC = ctypes.WINFUNCTYPE(
            LRESULT_T, ctypes.c_int, WPARAM_T, LPARAM_T
        )

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            HOOKPROC,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = HHOOK_T
        user32.CallNextHookEx.argtypes = [
            HHOOK_T,
            ctypes.c_int,
            WPARAM_T,
            LPARAM_T,
        ]
        user32.CallNextHookEx.restype = LRESULT_T
        user32.UnhookWindowsHookEx.argtypes = [HHOOK_T]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT_T

        def callback(code: int, w_param: int, l_param: int) -> int:
            if code != HC_ACTION:
                return int(
                    user32.CallNextHookEx(
                        self._hook_handle or 0, code, w_param, l_param
                    )
                )

            data = ctypes.cast(
                l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)
            ).contents
            if data.flags & LLKHF_INJECTED:
                return int(
                    user32.CallNextHookEx(
                        self._hook_handle or 0, code, w_param, l_param
                    )
                )

            vk_code = int(data.vkCode)
            logical_key = SUPPORTED_VKS.get(vk_code)
            if logical_key is None:
                return int(
                    user32.CallNextHookEx(
                        self._hook_handle or 0, code, w_param, l_param
                    )
                )

            now = time.monotonic()
            if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                with self._lock:
                    self.tracker.key_down(logical_key, vk_code, now)
                return 1
            if w_param in (WM_KEYUP, WM_SYSKEYUP):
                with self._lock:
                    pulse_vk = self.tracker.key_up(logical_key, vk_code, now)
                if pulse_vk is not None:
                    self._pulse_queue.put(pulse_vk)
                return 1

            return int(
                user32.CallNextHookEx(
                    self._hook_handle or 0, code, w_param, l_param
                )
            )

        self._hook_proc = HOOKPROC(callback)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        module = kernel32.GetModuleHandleW(None)
        hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc, module, 0
        )
        if not hook:
            self.logger.error("Windows klavye kancası kurulamadı")
            self._ready_event.set()
            return

        self._hook_handle = int(hook)
        self._ready_event.set()
        self.logger.info("Klavye 2+5 kalibrasyon kısayolu etkin (10 saniye)")

        message = wintypes.MSG()
        try:
            while not self._stop_event.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(hook)
            self._hook_handle = None
            self._thread_id = 0
            self._ready_event.set()


# Eski 0.3.x adını içe aktaran servis araçları için uyumluluk.
KeyboardMotionHotkey = KeyboardCalibrationHotkey
