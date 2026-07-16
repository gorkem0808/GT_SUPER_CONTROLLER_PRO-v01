from __future__ import annotations

from pathlib import Path

import pytest

from gt_super_controller.config import AppConfig
from gt_super_controller.launcher import GameLauncher


def test_build_command_with_profile(tmp_path: Path) -> None:
    executable = tmp_path / "TeknoParrotUi.exe"
    profile = tmp_path / "ParadiseLost.xml"
    executable.write_bytes(b"")
    profile.write_text("<xml />", encoding="utf-8")
    config = AppConfig(
        game_executable=str(executable),
        game_profile=str(profile),
        game_arguments='--foo "bar baz"',
        game_working_directory=str(tmp_path),
    )
    command, cwd = GameLauncher.build_command(config)
    assert command[0] == str(executable)
    assert f"--profile={profile}" in command
    assert "--startMinimized" in command
    assert cwd == tmp_path


def test_missing_executable_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        GameLauncher.build_command(
            AppConfig(game_executable=str(tmp_path / "missing.exe"))
        )


def test_missing_profile_rejected(tmp_path: Path) -> None:
    executable = tmp_path / "game.exe"
    executable.write_bytes(b"")
    with pytest.raises(ValueError):
        GameLauncher.build_command(
            AppConfig(
                game_executable=str(executable),
                game_profile=str(tmp_path / "missing.xml"),
            )
        )
