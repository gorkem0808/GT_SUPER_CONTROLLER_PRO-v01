#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

PICO_FLASH_BYTES = 2 * 1024 * 1024
RESERVED_SETTINGS_BYTES = 2 * 4096
MAX_BINARY_BYTES = PICO_FLASH_BYTES - RESERVED_SETTINGS_BYTES


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Firmware binary'nin kalıcı ayar sektörlerine taşmadığını doğrula"
    )
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    failed = False
    for value in args.files:
        path = Path(value)
        size = path.stat().st_size
        remaining = MAX_BINARY_BYTES - size
        print(f"{path}: {size} byte; ayrılmış alana kalan {remaining} byte")
        if size > MAX_BINARY_BYTES:
            failed = True
    if failed:
        raise SystemExit("Firmware, flash ayar alanına taşıyor")


if __name__ == "__main__":
    main()
