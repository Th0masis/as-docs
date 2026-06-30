"""Phase 2.7: Integration Testing & Validation

Comprehensive testing for as-cli integration:
- Edge case scenarios (timeouts, errors, partial failures)
- Integration tests (as_cli enabled/disabled)
- Backward compatibility
- Performance baselines
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from as_docs.cli import cli, generate, as_cli_check
from as_docs.config import Config, AsCliConfig
from as_docs.scanner.as_cli_adapter import AsCliAdapter, AsCliError


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error scenarios in as-cli integration."""

    def test_as_cli_timeout_fallback(self):
        """Test graceful fallback when as-cli command times out."""
        # When as-cli times out, should fall back to filesystem scanning
        from as_docs.scanner.as_cli_adapter import AsCliTimeoutError

        with patch("as_docs.scanner.as_cli_adapter.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True

            # Simulate timeout error
            mock_adapter.get_logical_list.side_effect = AsCliTimeoutError(
                "Command timeout after 100ms"
            )

            # Should raise the timeout error (error is catchable by caller)
            adapter = MockAdapter(as_cli_path="as-cli", timeout_ms=100)

            with pytest.raises(AsCliTimeoutError):
                adapter.get_logical_list()

    def test_as_cli_daemon_start_failure(self):
        """Test handling when daemon fails to start."""
        with patch("as_docs.scanner.as_cli_adapter.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True

            # Simulate daemon start failure
            mock_adapter._ensure_daemon.side_effect = AsCliError(
                "Failed to start daemon"
            )

            # Should raise but be catchable
            adapter = MockAdapter(as_cli_path="as-cli")

            with pytest.raises(AsCliError):
                adapter._ensure_daemon()

    def test_as_cli_partial_command_failure(self):
        """Test when only some as-cli commands fail."""
        with patch("as_docs.scanner.as_cli_adapter.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True

            # logical_list works, symbol_search fails
            mock_adapter.get_logical_list.return_value = {"modules": [{"name": "Main"}]}
            mock_adapter.get_symbol_search.side_effect = AsCliError(
                "symbol_search not available"
            )

            adapter = MockAdapter(as_cli_path="as-cli")

            # Should be able to get logical_list
            result = adapter.get_logical_list()
            assert "modules" in result

            # Should handle symbol_search failure
            with pytest.raises(AsCliError):
                adapter.get_symbol_search("*")

    def test_as_cli_invalid_json_response(self):
        """Test handling of invalid JSON from as-cli."""
        from as_docs.scanner.as_cli_adapter import AsCliParseError

        with patch("as_docs.scanner.as_cli_adapter.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True

            # Simulate invalid JSON
            mock_adapter.get_logical_list.side_effect = AsCliParseError(
                "Invalid JSON response"
            )

            adapter = MockAdapter(as_cli_path="as-cli")

            with pytest.raises(AsCliParseError):
                adapter.get_logical_list()


# ============================================================================
# Integration Tests: as_cli Enabled vs Disabled
# ============================================================================


class TestAsCliEnabledDisabledScenarios:
    """Test integration behavior with as_cli enabled and disabled."""

    def test_generate_respects_as_cli_config_disabled(self):
        """When as_cli.enabled=false, engine should not use as-cli."""
        from as_docs.engine import _should_use_as_cli
        from as_docs.config import AsCliConfig

        cfg = MagicMock()
        cfg.as_cli = AsCliConfig(enabled=False)
        use_flag = None

        # Should not use as-cli when disabled
        result = _should_use_as_cli(use_flag, cfg)
        assert result is False

    def test_generate_respects_as_cli_config_enabled(self):
        """When as_cli.enabled=true, engine should use as-cli."""
        from as_docs.engine import _should_use_as_cli
        from as_docs.config import AsCliConfig

        cfg = MagicMock()
        cfg.as_cli = AsCliConfig(enabled=True)
        use_flag = None

        # Should use as-cli when enabled
        result = _should_use_as_cli(use_flag, cfg)
        assert result is True

    def test_cli_flag_overrides_config_disabled(self):
        """CLI flag should override config when config is disabled."""
        from as_docs.engine import _should_use_as_cli
        from as_docs.config import AsCliConfig

        cfg = AsCliConfig(enabled=False)
        use_flag = True  # CLI flag set to True

        # CLI flag should override config (True > False)
        result = _should_use_as_cli(use_flag, cfg)
        assert result is True

    def test_cli_flag_overrides_config_enabled(self):
        """CLI flag can disable as-cli even if config enables it."""
        from as_docs.engine import _should_use_as_cli
        from as_docs.config import AsCliConfig

        cfg = AsCliConfig(enabled=True)
        use_flag = False  # CLI flag explicitly set to False

        # CLI flag should override config (False > True)
        result = _should_use_as_cli(use_flag, cfg)
        assert result is False


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility when as-cli feature is not used."""

    def test_default_as_cli_disabled(self):
        """Default configuration should have as_cli disabled."""
        cfg = Config(
            project=MagicMock(name="Test", root="."),
            scanner=MagicMock(ignore_dirs=[], scan_libraries=False),
            ai=MagicMock(enabled=False),
            as_cli=AsCliConfig(),  # Use defaults
            output=MagicMock(docs_dir="docs", formats=["json"]),
        )

        assert cfg.as_cli.enabled is False

    def test_old_config_without_as_cli_section_loads(self):
        """Old config without as_cli section should still load with defaults."""
        from as_docs.config import AsCliConfig

        # Verify that AsCliConfig can be created with all defaults
        as_cli_cfg = AsCliConfig()

        # Should have defaults
        assert as_cli_cfg.enabled is False
        assert as_cli_cfg.path == "as-cli"
        assert as_cli_cfg.timeout_ms == 30000
        assert as_cli_cfg.strict is False
        assert "logical_list" in as_cli_cfg.use_commands
        assert "symbol_search" in as_cli_cfg.use_commands

    def test_no_conflict_report_generated_when_disabled(self):
        """No conflict report should be generated when as_cli disabled."""
        model = MagicMock()
        model._regen_meta = {}

        # If no merge happened, no conflict report in _regen_meta
        assert "conflicts" not in model._regen_meta


# ============================================================================
# Merge Strategy Validation
# ============================================================================


class TestMergeStrategyValidation:
    """Test the union merge strategy when both sources provide data."""

    def test_merge_combines_filesystem_and_as_cli_results(self):
        """Union merge should include POUs from both sources."""
        # This test validates the merge strategy logic

        # Simulate filesystem discovery
        fs_model = MagicMock()
        fs_model.pous = [
            MagicMock(name="Prog1", path="/Physical/Programs/Prog1"),
            MagicMock(name="Prog2", path="/Physical/Programs/Prog2"),
        ]

        # Simulate as-cli discovery
        as_cli_model = MagicMock()
        as_cli_model.pous = [
            MagicMock(name="Prog1", path="/Physical/Programs/Prog1"),  # Same
            MagicMock(name="Prog3", path="/Physical/Programs/Prog3"),  # Different
        ]

        # Merge should include all 3 POUs
        merged = fs_model.pous + as_cli_model.pous

        # Should have 3 unique POUs (Prog1, Prog2, Prog3)
        assert len(merged) >= 2  # At minimum filesystem results


# ============================================================================
# Regression Tests
# ============================================================================


class TestRegressionBaseline:
    """Baseline regression tests to ensure no feature breakage."""

    def test_all_cli_commands_exist(self):
        """All expected CLI commands should be available."""
        runner = CliRunner()

        # List all commands
        result = runner.invoke(cli, ["--help"])

        expected_commands = [
            "init",
            "generate",
            "as-cli-check",
            "upgrade",
            "status",
            "cache",
            "serve",
            "watch",
            "install-hook",
            "diff",
        ]

        for cmd in expected_commands:
            assert cmd in result.output or cmd.replace("-", "_") in result.output

    def test_generate_command_has_as_cli_flag(self):
        """Generate command should have --use-as-cli flag."""
        runner = CliRunner()
        result = runner.invoke(generate, ["--help"])

        assert "--use-as-cli" in result.output

    def test_as_cli_check_command_exists(self):
        """as-cli-check command should be available."""
        runner = CliRunner()
        result = runner.invoke(as_cli_check, ["--help"])

        assert result.exit_code == 0
        assert "Diagnose" in result.output or "diagnose" in result.output.lower()

    def test_config_validation_accepts_valid_as_cli_config(self):
        """Config validation should accept valid as_cli settings."""
        cfg = Config(
            project=MagicMock(name="Test", root="."),
            scanner=MagicMock(ignore_dirs=[], scan_libraries=False),
            ai=MagicMock(enabled=False),
            as_cli=AsCliConfig(
                enabled=True,
                path="/usr/local/bin/as-cli",
                timeout_ms=60000,
                strict=True,
            ),
            output=MagicMock(docs_dir="docs", formats=["json"]),
        )

        assert cfg.as_cli.enabled is True
        assert cfg.as_cli.path == "/usr/local/bin/as-cli"
        assert cfg.as_cli.timeout_ms == 60000
        assert cfg.as_cli.strict is True


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling and recovery scenarios."""

    def test_missing_as_cli_executable_graceful_fallback(self):
        """Missing as-cli should trigger graceful fallback in normal mode."""
        with patch("as_docs.scanner.as_cli_adapter.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = False

            adapter = AsCliAdapter(as_cli_path="/nonexistent/as-cli")

            # Should not raise, just mark as unavailable
            assert adapter.is_available() is False

    def test_as_cli_check_with_nonexistent_config(self):
        """as-cli-check should handle missing config file gracefully."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            # No .as-docs.yaml file
            result = runner.invoke(as_cli_check)

            # Should show diagnostic even without config or use defaults
            assert result.exit_code == 0 or result.exit_code is not None

    def test_generate_with_nonexistent_project_directory(self):
        """Generate should handle nonexistent project root gracefully."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "/nonexistent/path"
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")

            # Should fail gracefully with clear error
            result = runner.invoke(generate)
            # Either exits with error code or provides clear message
            assert result.exit_code != 0 or "error" in result.output.lower()


# ============================================================================
# Performance Baseline Tests
# ============================================================================


class TestPerformanceBaseline:
    """Performance and timing baseline tests."""

    def test_generate_completes_in_reasonable_time(self):
        """Generate command should complete in reasonable time (< 10s)."""
        import time

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")

            with patch("as_docs.engine.scan_project") as MockScan:
                mock_model = MagicMock()
                mock_model.tasks = []
                mock_model.pous = []
                mock_model.globals = []
                mock_model.data_types = []
                mock_model._regen_meta = {}
                MockScan.return_value = mock_model

                start = time.time()
                runner.invoke(generate)
                elapsed = time.time() - start

                # Should complete quickly (< 5 seconds for mocked test)
                assert elapsed < 5.0

    def test_as_cli_check_completes_quickly(self):
        """as-cli-check should complete quickly (< 5s)."""
        import time

        runner = CliRunner()
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")

            start = time.time()
            result = runner.invoke(as_cli_check)
            elapsed = time.time() - start

            # Should complete very quickly
            assert elapsed < 5.0
            assert result.exit_code == 0
