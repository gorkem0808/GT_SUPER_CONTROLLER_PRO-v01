from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "GT_SUPER_CONTROLLER"


def _command() -> str:
    if getattr(sys, "frozen", False):
        parts = [str(Path(sys.executable).resolve()), "--minimized"]
    else:
        executable = Path(sys.executable)
        pythonw = executable.with_name("pythonw.exe")
        parts = [str(pythonw if pythonw.exists() else executable), "-m", "gt_super_controller", "--minimized"]
    return subprocess.list2cmdline(parts)


def is_autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
        return isinstance(value, str) and bool(value.strip())
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        if enabled:
            raise OSError("Windows otomatik başlangıç ayarı yalnız Windows'ta kullanılabilir.")
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
