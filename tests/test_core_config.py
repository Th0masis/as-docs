from __future__ import annotations

from pathlib import Path

import pytest

from as_docs.config import load_config


def _write_cfg(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_load_config_defaults_provider_when_missing(tmp_path: Path) -> None:
    cfg_file = tmp_path / ".as-docs.yaml"
    _write_cfg(
        cfg_file,
        """
project:
  name: "X"
ai:
  enabled: true
  model: "gpt-4.1"
""",
    )

    cfg = load_config(cfg_file)
    assert cfg.ai.provider == "copilot"


def test_invalid_provider_fails_validation(tmp_path: Path) -> None:
    cfg_file = tmp_path / ".as-docs.yaml"
    _write_cfg(
        cfg_file,
        """
ai:
  provider: "unknown"
  model: "gpt-4.1"
""",
    )

    with pytest.raises(ValueError, match="Invalid ai.provider"):
        load_config(cfg_file)


def test_copilot_requires_api_key_env(tmp_path: Path) -> None:
    cfg_file = tmp_path / ".as-docs.yaml"
    _write_cfg(
        cfg_file,
        """
ai:
  provider: "copilot"
  model: "gpt-4.1"
  api_key_env: ""
""",
    )

    with pytest.raises(ValueError, match="ai.api_key_env"):
        load_config(cfg_file)
