"""Standalone packaging helpers for the optional Phase 7 executable."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StandaloneBuildPlan:
    project_root: Path
    entrypoint: Path
    dist_dir: Path
    build_dir: Path
    spec_dir: Path
    spec_file: Path
    output_binary: Path
    executable_name: str
    command: list[str]


def default_standalone_install_dir() -> Path:
    """Return the default install directory for a prebuilt as-docs executable."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "as-docs-mcp"
    return Path.home() / ".local" / "share" / "as-docs-mcp"


def standalone_executable_name() -> str:
    return "as-docs-server.exe" if sys.platform.startswith("win") else "as-docs-server"


def build_standalone_plan(
    project_root: Path | None = None,
    *,
    dist_dir: Path | None = None,
) -> StandaloneBuildPlan:
    """Create a reproducible PyInstaller build plan for the standalone executable."""
    resolved_root = (project_root or Path(__file__).resolve().parents[1]).resolve()
    entrypoint = resolved_root / "as_docs" / "cli.py"
    if not entrypoint.exists():
        raise FileNotFoundError(f"Cannot find CLI entrypoint: {entrypoint}")

    output_dir = (dist_dir or default_standalone_install_dir()).resolve()
    build_dir = output_dir / "build"
    spec_dir = output_dir / "spec"
    executable_name = standalone_executable_name()
    spec_file = spec_dir / f"{executable_name.replace('.exe', '')}.spec"
    output_binary = output_dir / executable_name

    command = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        executable_name.replace(".exe", ""),
        "--distpath",
        str(output_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(spec_dir),
        str(entrypoint),
    ]

    return StandaloneBuildPlan(
        project_root=resolved_root,
        entrypoint=entrypoint,
        dist_dir=output_dir,
        build_dir=build_dir,
        spec_dir=spec_dir,
        spec_file=spec_file,
        output_binary=output_binary,
        executable_name=executable_name,
        command=command,
    )
