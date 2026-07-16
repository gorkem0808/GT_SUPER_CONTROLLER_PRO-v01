#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
PY_VERSION_FILE = ROOT / "desktop" / "gt_super_controller" / "version.py"
PYPROJECT_FILE = ROOT / "desktop" / "pyproject.toml"
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


def read_version() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def validate(version: str) -> str:
    version = version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(
            "Sürüm X.Y.Z, X.Y.Z-etiket veya X.Y.Z+build biçiminde olmalıdır."
        )
    return version


def expected_py(version: str) -> str:
    return f'__version__ = "{version}"\n'


def update_pyproject(text: str, version: str) -> str:
    updated, count = re.subn(
        r'(?m)^version\s*=\s*"[^"]+"\s*$',
        f'version = "{version}"',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("pyproject.toml sürüm alanı bulunamadı.")
    return updated


def check() -> None:
    version = validate(read_version())
    py_version = PY_VERSION_FILE.read_text(encoding="utf-8")
    if py_version != expected_py(version):
        raise SystemExit("version.py ile VERSION eşleşmiyor")
    pyproject = PYPROJECT_FILE.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', pyproject)
    if match is None or match.group(1) != version:
        raise SystemExit("pyproject.toml ile VERSION eşleşmiyor")
    print(version)


def set_version(version: str) -> None:
    version = validate(version)
    VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    PY_VERSION_FILE.write_text(expected_py(version), encoding="utf-8")
    pyproject = PYPROJECT_FILE.read_text(encoding="utf-8")
    PYPROJECT_FILE.write_text(update_pyproject(pyproject, version), encoding="utf-8")
    print(version)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version", nargs="?")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.version:
        set_version(args.version)
    else:
        parser.error("version veya --check gerekli")


if __name__ == "__main__":
    main()
