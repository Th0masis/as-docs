"""Configuration loader for .as-docs.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProjectConfig:
    name: str = ""
    as_version: str = ""
    root: str = "."
    language: str = "en"


@dataclass
class ScannerConfig:
    active_configuration: str = ""  # empty → first found alphabetically
    ignore_dirs: list[str] = field(
        default_factory=lambda: ["Temp", "Binaries", "Diagnosis"]
    )
    scan_libraries: bool = True
    external_lib_prefixes: list[str] = field(
        default_factory=lambda: ["Mp", "Mc", "ACP10", "Ar"]
    )
    recursive_packages: bool = True  # recursively scan nested Package.pkg hierarchies
    max_recursion_depth: int = 10  # prevent runaway recursion


@dataclass
class AIConfig:
    enabled: bool = True
    provider: str = "copilot"
    model: str = "gpt-4.1"
    api_base_url: str = ""
    api_key_env: str = "GITHUB_TOKEN"
    oauth_client_id: str = ""
    timeout_seconds: int = 60
    max_retries: int = 3
    cache_dir: str = ".as-docs-cache"


@dataclass
class ServerConfig:
    mode: str = "stdio"
    port: int = 8765
    host: str = "127.0.0.1"


@dataclass
class OutputConfig:
    docs_dir: str = "docs/as-docs"
    formats: list[str] = field(default_factory=lambda: ["markdown", "json", "llms.txt"])
    mermaid: bool = True
    default_level: int = 3


@dataclass
class GitConfig:
    hook_enabled: bool = False
    auto_level: int = 2


@dataclass
class AsCliConfig:
    """Configuration for as-cli integration (optional data source).

    When enabled, as-docs can use as-cli logical_list and symbol_search
    commands for more accurate project discovery. Falls back gracefully
    to filesystem scanning if as-cli is unavailable.
    """

    enabled: bool = False
    """Enable as-cli data source. Default: False (opt-in)."""

    path: str = "as-cli"
    """Path to as-cli executable. Default: auto-detect from PATH."""

    timeout_ms: int = 30000
    """Timeout per as-cli command (milliseconds). Default: 30s."""

    strict: bool = False
    """If True: fail hard on as-cli errors.
    If False: gracefully fall back to filesystem scanning.
    Default: False (graceful fallback)."""

    use_commands: list[str] = field(
        default_factory=lambda: ["logical_list", "symbol_search"]
    )
    """Which as-cli commands to use. Default: both main commands."""


@dataclass
class Config:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    git: GitConfig = field(default_factory=GitConfig)
    as_cli: AsCliConfig = field(default_factory=AsCliConfig)
    config_file: Path = field(default=Path(".as-docs.yaml"))

    @property
    def docs_path(self) -> Path:
        return Path(self.output.docs_dir)

    @property
    def cache_path(self) -> Path:
        return Path(self.ai.cache_dir)


def _merge(defaults: Any, overrides: dict) -> Any:
    """Recursively apply yaml overrides onto a dataclass instance."""
    for key, value in overrides.items():
        if not hasattr(defaults, key):
            continue
        if isinstance(value, dict):
            _merge(getattr(defaults, key), value)
        else:
            setattr(defaults, key, value)
    return defaults


def load_config(config_file: Path | None = None) -> Config:
    """Load .as-docs.yaml from *config_file* or search up the directory tree.

    Returns a fully-populated Config with defaults for any missing keys.
    """
    if config_file is None:
        config_file = _find_config(Path.cwd())

    if config_file is None:
        raise ValueError("Cannot locate .as-docs.yaml and no default config found")

    cfg = Config(config_file=config_file)

    if config_file is None or not config_file.exists():
        return cfg

    with config_file.open() as fh:
        raw: dict = yaml.safe_load(fh) or {}

    for section in ("project", "scanner", "ai", "server", "output", "git", "as_cli"):
        if section in raw and isinstance(raw[section], dict):
            _merge(getattr(cfg, section), raw[section])

    _validate_config(cfg)

    return cfg


def _validate_config(cfg: Config) -> None:
    # Validate AI config
    provider = cfg.ai.provider.strip().lower()
    allowed = {"copilot", "anthropic"}
    if provider not in allowed:
        raise ValueError(
            f"Invalid ai.provider '{cfg.ai.provider}'. Allowed values: copilot, anthropic."
        )

    cfg.ai.provider = provider

    if not cfg.ai.model.strip():
        raise ValueError("Invalid ai.model: value must not be empty.")

    if provider == "copilot" and not cfg.ai.api_key_env.strip():
        raise ValueError(
            "Invalid ai.api_key_env: value must not be empty for copilot provider."
        )

    if cfg.ai.timeout_seconds <= 0:
        raise ValueError("Invalid ai.timeout_seconds: value must be greater than 0.")

    if cfg.ai.max_retries < 0:
        raise ValueError("Invalid ai.max_retries: value must be >= 0.")

    # Validate as_cli config
    _validate_as_cli_config(cfg.as_cli)


def _validate_as_cli_config(as_cli_cfg: AsCliConfig) -> None:
    """Validate as-cli configuration.

    Raises:
        ValueError: If configuration is invalid
    """
    if as_cli_cfg.timeout_ms <= 0:
        raise ValueError(
            "Invalid as_cli.timeout_ms: value must be positive (milliseconds)."
        )

    if not as_cli_cfg.path.strip():
        raise ValueError("Invalid as_cli.path: value must not be empty.")

    if not isinstance(as_cli_cfg.use_commands, list):
        raise TypeError("Invalid as_cli.use_commands: value must be a list.")

    valid_commands = {"logical_list", "symbol_search"}
    for cmd in as_cli_cfg.use_commands:
        if cmd not in valid_commands:
            raise ValueError(
                f"Invalid as_cli.use_commands: unknown command '{cmd}'. "
                f"Allowed: {', '.join(sorted(valid_commands))}"
            )


def _find_config(start: Path) -> Path | None:
    """Walk up directory tree looking for .as-docs.yaml."""
    candidate = start / ".as-docs.yaml"
    if candidate.exists():
        return candidate
    if start.parent == start:
        return None
    return _find_config(start.parent)


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up directory tree looking for Logical/ + Physical/ directories."""
    current = start or Path.cwd()
    while True:
        if (current / "Logical").is_dir() and (current / "Physical").is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
