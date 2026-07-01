from __future__ import annotations

import sys
from pathlib import Path

from as_docs.packaging import (
    build_standalone_plan,
    default_standalone_install_dir,
    standalone_executable_name,
)


def test_standalone_install_dir_uses_appdata_on_windows() -> None:
    install_dir = default_standalone_install_dir()

    assert install_dir.name == "as-docs-mcp"
    if sys.platform.startswith("win"):
        assert "AppData" in str(install_dir)
    else:
        assert str(install_dir).endswith(".local/share/as-docs-mcp")


def test_standalone_executable_name_matches_platform() -> None:
    if sys.platform.startswith("win"):
        assert standalone_executable_name().endswith(".exe")
    else:
        assert standalone_executable_name() == "as-docs-server"


def test_build_standalone_plan_includes_pyinstaller_and_entrypoint(
    tmp_path: Path,
) -> None:
    plan = build_standalone_plan(
        Path(__file__).resolve().parents[1], dist_dir=tmp_path / "dist"
    )

    assert plan.entrypoint.name == "cli.py"
    assert plan.executable_name.startswith("as-docs-server")
    assert plan.spec_file.name.endswith(".spec")
    assert plan.output_binary.name == plan.executable_name
    assert plan.command[0] == "pyinstaller"
    assert "--onefile" in plan.command
    assert "--distpath" in plan.command
    assert str(plan.dist_dir) in plan.command
    assert str(plan.entrypoint) in plan.command
