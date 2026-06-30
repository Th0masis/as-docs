"""Tests for CLI updates with as-cli integration."""
import pytest
from click.testing import CliRunner
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from as_docs.cli import cli, generate, as_cli_check
from as_docs.config import Config, AsCliConfig


@pytest.fixture
def runner():
    """CLI test runner."""
    return CliRunner()


class TestGenerateCommandWithAsCliFlag:
    """Test generate command with --use-as-cli flag."""
    
    def test_generate_without_use_as_cli_flag(self, runner):
        """Test generate runs normally without --use-as-cli."""
        with runner.isolated_filesystem():
            # Create minimal .as-docs.yaml
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.engine.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {"Main": Mock()}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--no-ai"])
                
                # Should call run_generate with use_as_cli=False (default)
                mock_gen.assert_called_once()
                call_kwargs = mock_gen.call_args[1]
                assert "use_as_cli" in call_kwargs
                assert call_kwargs["use_as_cli"] is False
    
    def test_generate_with_use_as_cli_flag(self, runner):
        """Test generate with --use-as-cli flag."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.engine.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                # Should call run_generate with use_as_cli=True
                mock_gen.assert_called_once()
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["use_as_cli"] is True
    
    def test_generate_displays_as_cli_message(self, runner):
        """Test that generate displays as-cli message when flag is set."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.engine.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                assert result.exit_code == 0
                assert "as-cli integration enabled" in result.output
    
    def test_generate_displays_conflict_report(self, runner):
        """Test that generate displays conflict report from as-cli merge."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.engine.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {"Main": Mock()}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {
                    "as_cli_merge_report": {
                        "pou_count_fs": 5,
                        "pou_count_as_cli": 5,
                        "pou_count_merged": 5,
                        "conflicts": [
                            {
                                "pou_name": "Main",
                                "conflict_type": "path_mismatch"
                            }
                        ]
                    }
                }
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                assert result.exit_code == 0
                assert "as-cli merge report" in result.output
                assert "Filesystem: 5 POUs" in result.output
                assert "Conflicts: 1" in result.output
                assert "path_mismatch" in result.output


class TestAsCliCheckCommand:
    """Test as-cli-check diagnostic command."""
    
    def test_as_cli_check_basic_run(self, runner):
        """Test as-cli-check command runs without errors."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            # Import inside to patch where it's used in cli.py
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Diagnosing as-cli integration" in result.output
    
    def test_as_cli_check_shows_configuration(self, runner):
        """Test as-cli-check displays configuration."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "/usr/local/bin/as-cli"
  timeout_ms: 60000
  strict: true
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Enabled: True" in result.output
                assert "/usr/local/bin/as-cli" in result.output
                assert "60000ms" in result.output
                assert "Strict mode: True" in result.output
    
    def test_as_cli_check_available(self, runner):
        """Test as-cli-check when as-cli is available."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = True
                mock_adapter._ensure_daemon.return_value = None
                mock_adapter.get_logical_list.return_value = {"modules": [{"name": "Main"}]}
                mock_adapter.get_symbol_search.return_value = {"symbols": {"Main": {}}}
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "✅  as-cli is installed" in result.output
                assert "✅  Connected to daemon" in result.output
                assert "1 modules found" in result.output
                assert "1 symbols found" in result.output
    
    def test_as_cli_check_not_available(self, runner):
        """Test as-cli-check when as-cli is not available."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "❌  as-cli is not available" in result.output
                assert "Ensure as-cli is installed" in result.output
    
    def test_as_cli_check_command_failures(self, runner):
        """Test as-cli-check shows warnings on command failures."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
  use_commands: [logical_list, symbol_search]
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            from as_docs.scanner.as_cli_adapter import AsCliError
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = True
                mock_adapter._ensure_daemon.return_value = None
                mock_adapter.get_logical_list.side_effect = AsCliError("Timeout")
                mock_adapter.get_symbol_search.side_effect = AsCliError("Failed")
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "⚠️   logical_list failed" in result.output
                assert "⚠️   symbol_search failed" in result.output
    
    def test_as_cli_check_recommendations_enabled(self, runner):
        """Test as-cli-check shows recommendation when enabled."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Running in graceful fallback mode (recommended)" in result.output
    
    def test_as_cli_check_recommendations_disabled(self, runner):
        """Test as-cli-check shows recommendation when disabled."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            import as_docs.cli
            with patch.object(as_docs.cli, "AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Enable as-cli in .as-docs.yaml" in result.output
                mock_graph = Mock()
                mock_graph.pous = {"Main": Mock()}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--no-ai"])
                
                # Should call run_generate with use_as_cli=False (default)
                mock_gen.assert_called_once()
                call_kwargs = mock_gen.call_args[1]
                assert "use_as_cli" in call_kwargs
                assert call_kwargs["use_as_cli"] is False
    
    def test_generate_with_use_as_cli_flag(self, runner):
        """Test generate with --use-as-cli flag."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                # Should call run_generate with use_as_cli=True
                mock_gen.assert_called_once()
                call_kwargs = mock_gen.call_args[1]
                assert call_kwargs["use_as_cli"] is True
    
    def test_generate_displays_as_cli_message(self, runner):
        """Test that generate displays as-cli message when flag is set."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {}
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                assert result.exit_code == 0
                assert "as-cli integration enabled" in result.output
    
    def test_generate_displays_conflict_report(self, runner):
        """Test that generate displays conflict report from as-cli merge."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.run_generate") as mock_gen:
                mock_graph = Mock()
                mock_graph.pous = {"Main": Mock()}
                mock_graph.tasks = {}
                mock_graph._regen_meta = {
                    "as_cli_merge_report": {
                        "pou_count_fs": 5,
                        "pou_count_as_cli": 5,
                        "pou_count_merged": 5,
                        "conflicts": [
                            {
                                "pou_name": "Main",
                                "conflict_type": "path_mismatch"
                            }
                        ]
                    }
                }
                mock_gen.return_value = mock_graph
                
                result = runner.invoke(generate, ["--use-as-cli", "--no-ai"])
                
                assert result.exit_code == 0
                assert "as-cli merge report" in result.output
                assert "Filesystem: 5 POUs" in result.output
                assert "Conflicts: 1" in result.output
                assert "path_mismatch" in result.output


class TestAsCliCheckCommand:
    """Test as-cli-check diagnostic command."""
    
    def test_as_cli_check_basic_run(self, runner):
        """Test as-cli-check command runs without errors."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Diagnosing as-cli integration" in result.output
    
    def test_as_cli_check_shows_configuration(self, runner):
        """Test as-cli-check displays configuration."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "/usr/local/bin/as-cli"
  timeout_ms: 60000
  strict: true
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Enabled: True" in result.output
                assert "/usr/local/bin/as-cli" in result.output
                assert "60000ms" in result.output
                assert "Strict mode: True" in result.output
    
    def test_as_cli_check_available(self, runner):
        """Test as-cli-check when as-cli is available."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = True
                mock_adapter._ensure_daemon.return_value = None
                mock_adapter.get_logical_list.return_value = {"modules": [{"name": "Main"}]}
                mock_adapter.get_symbol_search.return_value = {"symbols": {"Main": {}}}
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "✅  as-cli is installed" in result.output
                assert "✅  Connected to daemon" in result.output
                assert "1 modules found" in result.output
                assert "1 symbols found" in result.output
    
    def test_as_cli_check_not_available(self, runner):
        """Test as-cli-check when as-cli is not available."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "❌  as-cli is not available" in result.output
                assert "Ensure as-cli is installed" in result.output
    
    def test_as_cli_check_command_failures(self, runner):
        """Test as-cli-check shows warnings on command failures."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
  use_commands: [logical_list, symbol_search]
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = True
                mock_adapter._ensure_daemon.return_value = None
                
                from as_docs.scanner.as_cli_adapter import AsCliError
                mock_adapter.get_logical_list.side_effect = AsCliError("Timeout")
                mock_adapter.get_symbol_search.side_effect = AsCliError("Failed")
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "⚠️   logical_list failed" in result.output
                assert "⚠️   symbol_search failed" in result.output
    
    def test_as_cli_check_recommendations_enabled(self, runner):
        """Test as-cli-check shows recommendation when enabled."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: true
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Running in graceful fallback mode (recommended)" in result.output
    
    def test_as_cli_check_recommendations_disabled(self, runner):
        """Test as-cli-check shows recommendation when disabled."""
        with runner.isolated_filesystem():
            Path(".as-docs.yaml").write_text("""
project:
  name: "TestProject"
  root: "."
as_cli:
  enabled: false
  path: "as-cli"
  timeout_ms: 30000
  strict: false
ai:
  enabled: false
output:
  docs_dir: "docs"
  formats: [json]
""")
            
            with patch("as_docs.cli.AsCliAdapter") as MockAdapter:
                mock_adapter = MagicMock()
                MockAdapter.return_value = mock_adapter
                mock_adapter.is_available.return_value = False
                
                result = runner.invoke(as_cli_check)
                
                assert result.exit_code == 0
                assert "Enable as-cli in .as-docs.yaml" in result.output
