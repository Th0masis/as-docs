"""Tests for as-cli configuration loading and validation."""
import pytest
from as_docs.config import (
    Config,
    AsCliConfig,
    load_config,
    _validate_as_cli_config,
)


class TestAsCliConfigDefaults:
    """Test AsCliConfig default values."""

    def test_as_cli_config_defaults(self):
        """Test that AsCliConfig has correct defaults."""
        cfg = AsCliConfig()
        assert cfg.enabled is False
        assert cfg.path == "as-cli"
        assert cfg.timeout_ms == 30000
        assert cfg.strict is False
        assert cfg.use_commands == ["logical_list", "symbol_search"]

    def test_as_cli_in_config_defaults(self):
        """Test that Config has AsCliConfig with defaults."""
        cfg = Config()
        assert isinstance(cfg.as_cli, AsCliConfig)
        assert cfg.as_cli.enabled is False
        assert cfg.as_cli.timeout_ms == 30000


class TestAsCliConfigValidation:
    """Test AsCliConfig validation."""

    def test_validate_as_cli_enabled_with_defaults(self):
        """Valid config: as_cli enabled with default values."""
        cfg = AsCliConfig(enabled=True)
        # Should not raise
        _validate_as_cli_config(cfg)

    def test_validate_as_cli_disabled(self):
        """Valid config: as_cli disabled (skips some validation)."""
        cfg = AsCliConfig(enabled=False)
        # Should not raise
        _validate_as_cli_config(cfg)

    def test_validate_timeout_positive(self):
        """Valid config: timeout_ms is positive."""
        cfg = AsCliConfig(timeout_ms=5000)
        _validate_as_cli_config(cfg)

    def test_validate_timeout_zero_fails(self):
        """Invalid config: timeout_ms is zero."""
        cfg = AsCliConfig(timeout_ms=0)
        with pytest.raises(ValueError, match="timeout_ms.*positive"):
            _validate_as_cli_config(cfg)

    def test_validate_timeout_negative_fails(self):
        """Invalid config: timeout_ms is negative."""
        cfg = AsCliConfig(timeout_ms=-1000)
        with pytest.raises(ValueError, match="timeout_ms.*positive"):
            _validate_as_cli_config(cfg)

    def test_validate_path_empty_fails(self):
        """Invalid config: path is empty string."""
        cfg = AsCliConfig(path="")
        with pytest.raises(ValueError, match="path.*not be empty"):
            _validate_as_cli_config(cfg)

    def test_validate_path_whitespace_only_fails(self):
        """Invalid config: path is only whitespace."""
        cfg = AsCliConfig(path="   ")
        with pytest.raises(ValueError, match="path.*not be empty"):
            _validate_as_cli_config(cfg)

    def test_validate_use_commands_not_list_fails(self):
        """Invalid config: use_commands is not a list."""
        cfg = AsCliConfig(use_commands="logical_list")  # type: ignore
        with pytest.raises(ValueError, match="use_commands.*list"):
            _validate_as_cli_config(cfg)

    def test_validate_use_commands_valid(self):
        """Valid config: use_commands contains known commands."""
        cfg = AsCliConfig(use_commands=["logical_list", "symbol_search"])
        _validate_as_cli_config(cfg)

    def test_validate_use_commands_single_command(self):
        """Valid config: use_commands with single command."""
        cfg = AsCliConfig(use_commands=["logical_list"])
        _validate_as_cli_config(cfg)

    def test_validate_use_commands_unknown_command_fails(self):
        """Invalid config: use_commands contains unknown command."""
        cfg = AsCliConfig(use_commands=["logical_list", "unknown_command"])
        with pytest.raises(ValueError, match="unknown command 'unknown_command'"):
            _validate_as_cli_config(cfg)

    def test_validate_use_commands_empty_list(self):
        """Valid config: empty use_commands list (may be intentional)."""
        cfg = AsCliConfig(use_commands=[])
        # Empty list is valid (though not useful)
        _validate_as_cli_config(cfg)

    def test_validate_strict_mode_true(self):
        """Valid config: strict mode enabled."""
        cfg = AsCliConfig(strict=True)
        _validate_as_cli_config(cfg)

    def test_validate_strict_mode_false(self):
        """Valid config: strict mode disabled."""
        cfg = AsCliConfig(strict=False)
        _validate_as_cli_config(cfg)


class TestAsCliConfigLoadingFromYaml:
    """Test loading as-cli config from YAML file."""

    def test_load_config_as_cli_disabled(self, tmp_path):
        """Load config with as_cli disabled (default)."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
project:
  name: "TestProject"
as_cli:
  enabled: false
""")
        cfg = load_config(config_file)
        assert cfg.as_cli.enabled is False
        assert cfg.as_cli.path == "as-cli"
        assert cfg.as_cli.timeout_ms == 30000

    def test_load_config_as_cli_enabled(self, tmp_path):
        """Load config with as_cli enabled."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
project:
  name: "TestProject"
as_cli:
  enabled: true
  path: "/usr/local/bin/as-cli"
  timeout_ms: 60000
  strict: true
""")
        cfg = load_config(config_file)
        assert cfg.as_cli.enabled is True
        assert cfg.as_cli.path == "/usr/local/bin/as-cli"
        assert cfg.as_cli.timeout_ms == 60000
        assert cfg.as_cli.strict is True

    def test_load_config_as_cli_custom_commands(self, tmp_path):
        """Load config with custom use_commands."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
as_cli:
  enabled: true
  use_commands:
    - logical_list
""")
        cfg = load_config(config_file)
        assert cfg.as_cli.use_commands == ["logical_list"]

    def test_load_config_as_cli_not_specified(self, tmp_path):
        """Load config without as_cli section → uses defaults."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
project:
  name: "TestProject"
""")
        cfg = load_config(config_file)
        assert cfg.as_cli.enabled is False
        assert cfg.as_cli.path == "as-cli"
        assert cfg.as_cli.timeout_ms == 30000

    def test_load_config_as_cli_invalid_timeout(self, tmp_path):
        """Load config with invalid timeout → validation error."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
as_cli:
  enabled: true
  timeout_ms: 0
""")
        with pytest.raises(ValueError, match="timeout_ms"):
            load_config(config_file)

    def test_load_config_as_cli_invalid_command(self, tmp_path):
        """Load config with invalid command → validation error."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
as_cli:
  enabled: true
  use_commands:
    - invalid_command
""")
        with pytest.raises(ValueError, match="invalid_command"):
            load_config(config_file)


class TestAsCliConfigBackwardCompatibility:
    """Test backward compatibility with old configs."""

    def test_load_old_config_without_as_cli_section(self, tmp_path):
        """Old config file without as_cli section should still work."""
        config_file = tmp_path / ".as-docs.yaml"
        config_file.write_text("""
project:
  name: "OldProject"
  root: "."
scanner:
  active_configuration: "Config1"
ai:
  enabled: true
  provider: "copilot"
  model: "gpt-4"
""")
        cfg = load_config(config_file)
        # Should load successfully with as_cli defaults
        assert cfg.as_cli.enabled is False
        assert cfg.as_cli.timeout_ms == 30000
        assert cfg.project.name == "OldProject"
        assert cfg.ai.provider == "copilot"
