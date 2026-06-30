"""Data models for as-cli integration."""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import json


@dataclass
class AsCliModule:
    """Represents an Automation Studio module (POU) from as-cli logical list."""

    name: str
    """Module/POU name."""

    path: str
    """Module path in project (e.g., 'MainPackage/SubModule')."""

    pou_type: str
    """POU type: 'program', 'function', 'function_block', 'task', 'library', etc."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class AsCliSymbol:
    """Represents an Automation Studio symbol from as-cli symbol search."""

    name: str
    """Symbol name."""

    symbol_type: str
    """Symbol type: 'function', 'program', 'global', 'task', 'data_type', etc."""

    scope: str
    """Full scope path (e.g., 'modules.main.main')."""

    module: Optional[str] = None
    """Module/scope containing this symbol."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class AsCliProjectData:
    """Parsed result from as-cli logical_list + symbol_search commands.

    This represents the "raw" data from as-cli before conversion to as-docs model.
    """

    modules: list[AsCliModule] = field(default_factory=list)
    """List of modules/POUs discovered by as-cli logical_list."""

    symbols: dict[str, AsCliSymbol] = field(default_factory=dict)
    """Dictionary of symbols from as-cli symbol_search (name -> symbol)."""

    raw_logical_list: Optional[dict] = None
    """Raw JSON output from as-cli logical list (for debugging/inspection)."""

    raw_symbol_search: Optional[dict] = None
    """Raw JSON output from as-cli symbol search (for debugging/inspection)."""

    project_path: Optional[str] = None
    """Path to the AS project that was scanned."""

    execution_time_ms: float = 0.0
    """Total time to execute as-cli commands (milliseconds)."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "modules": [m.to_dict() for m in self.modules],
            "symbols": {k: v.to_dict() for k, v in self.symbols.items()},
            "project_path": self.project_path,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


def parse_logical_list_output(raw_output: dict) -> list[AsCliModule]:
    """Parse as-cli logical list JSON output into AsCliModule objects.

    Args:
        raw_output: Raw JSON dict from as-cli logical list --format json

    Returns:
        List of AsCliModule objects

    Raises:
        KeyError: If expected keys are missing from output
        ValueError: If output structure is invalid
    """
    modules = []

    # as-cli logical list output structure:
    # {
    #   "modules": [...],
    #   "tasks": [...],
    #   "programs": [...]
    # }

    for module_dict in raw_output.get("modules", []):
        modules.append(
            AsCliModule(
                name=module_dict.get("name", ""),
                path=module_dict.get("path", ""),
                pou_type="module",
            )
        )

    for task_dict in raw_output.get("tasks", []):
        modules.append(
            AsCliModule(
                name=task_dict.get("name", ""),
                path=task_dict.get("path", ""),
                pou_type="task",
            )
        )

    for program_dict in raw_output.get("programs", []):
        modules.append(
            AsCliModule(
                name=program_dict.get("name", ""),
                path=program_dict.get("path", ""),
                pou_type="program",
            )
        )

    return modules


def parse_symbol_search_output(raw_output: dict) -> dict[str, AsCliSymbol]:
    """Parse as-cli symbol search JSON output into AsCliSymbol dict.

    Args:
        raw_output: Raw JSON dict from as-cli symbol search * --format json

    Returns:
        Dictionary mapping symbol name to AsCliSymbol

    Raises:
        KeyError: If expected keys are missing from output
        ValueError: If output structure is invalid
    """
    symbols = {}

    # as-cli symbol search output structure:
    # {
    #   "symbols": [
    #     {"name": "...", "type": "...", "scope": "...", ...},
    #     ...
    #   ]
    # }

    for symbol_dict in raw_output.get("symbols", []):
        name = symbol_dict.get("name", "")
        if name:
            symbols[name] = AsCliSymbol(
                name=name,
                symbol_type=symbol_dict.get("type", ""),
                scope=symbol_dict.get("scope", ""),
                module=symbol_dict.get("module", None),
            )

    return symbols
