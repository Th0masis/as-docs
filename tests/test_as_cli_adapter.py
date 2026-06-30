"""Tests for as-cli adapter (command execution, daemon management, parsing)."""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json
import subprocess

from as_docs.scanner.as_cli_adapter import (
    AsCliAdapter,
    AsCliError,
    AsCliNotAvailableError,
    AsCliTimeoutError,
    AsCliCommandError,
    AsCliParseError,
)
from as_docs.scanner.as_cli_models import (
    AsCliProjectData,
    AsCliModule,
    AsCliSymbol,
)


class TestAsCliAdapterInit:
    """Test AsCliAdapter initialization."""

    def test_adapter_init_defaults(self):
        """Test adapter initialization with defaults."""
        adapter = AsCliAdapter()
        assert adapter.as_cli_path == "as-cli"
        assert adapter.project_path == "."
        assert adapter.timeout_ms == 30000
        assert adapter._daemon_started is False

    def test_adapter_init_custom_values(self):
        """Test adapter initialization with custom values."""
        adapter = AsCliAdapter(
            as_cli_path="/usr/bin/as-cli",
            project_path="/path/to/project",
            timeout_ms=60000
        )
        assert adapter.as_cli_path == "/usr/bin/as-cli"
        assert adapter.project_path == "/path/to/project"
        assert adapter.timeout_ms == 60000


class TestAsCliAdapterAvailability:
    """Test as-cli availability checks."""

    @patch("subprocess.run")
    def test_is_available_success(self, mock_run):
        """Test as-cli availability check when as-cli is available."""
        mock_run.return_value = Mock(returncode=0)
        
        adapter = AsCliAdapter()
        result = adapter.is_available()
        
        assert result is True
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        assert args[0] == ["as-cli", "--version"]
        assert kwargs["timeout"] == 5

    @patch("subprocess.run")
    def test_is_available_failure_returncode(self, mock_run):
        """Test as-cli availability check when command fails."""
        mock_run.return_value = Mock(returncode=1)
        
        adapter = AsCliAdapter()
        result = adapter.is_available()
        
        assert result is False

    @patch("subprocess.run")
    def test_is_available_not_found(self, mock_run):
        """Test as-cli availability when executable not found."""
        mock_run.side_effect = FileNotFoundError()
        
        adapter = AsCliAdapter()
        result = adapter.is_available()
        
        assert result is False

    @patch("subprocess.run")
    def test_is_available_timeout(self, mock_run):
        """Test as-cli availability when check times out."""
        mock_run.side_effect = subprocess.TimeoutExpired("as-cli", 5)
        
        adapter = AsCliAdapter()
        result = adapter.is_available()
        
        assert result is False


class TestAsCliAdapterDaemonManagement:
    """Test daemon lifecycle management (hybrid approach)."""

    @patch("subprocess.run")
    def test_ensure_daemon_already_started(self, mock_run):
        """Test that existing daemon is reused without restart."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = AsCliAdapter()
        adapter._daemon_started = True  # Already started
        
        result = adapter._ensure_daemon()
        
        assert result is True
        # Should not call subprocess.run since already started
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_ensure_daemon_connect_existing(self, mock_run):
        """Test connecting to existing daemon (fast check succeeds)."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = AsCliAdapter()
        result = adapter._ensure_daemon()
        
        assert result is True
        # First call should be the connectivity check
        first_call = mock_run.call_args_list[0]
        assert first_call[1]["timeout"] == 2  # Fast timeout

    @patch("subprocess.run")
    def test_ensure_daemon_start_new(self, mock_run):
        """Test starting daemon when not already running."""
        # First call (connectivity check) times out, second call (startup) succeeds
        mock_run.side_effect = [
            subprocess.TimeoutExpired("as-cli", 2),  # Connectivity check fails
            Mock(returncode=0, stdout="", stderr=""),  # Startup succeeds
        ]
        
        adapter = AsCliAdapter(timeout_ms=30000)
        result = adapter._ensure_daemon()
        
        assert result is True
        # Should have made two calls
        assert mock_run.call_count == 2
        # Second call should use full timeout
        second_call = mock_run.call_args_list[1]
        assert second_call[1]["timeout"] == 30.0  # Full timeout

    @patch("subprocess.run")
    def test_ensure_daemon_start_fails(self, mock_run):
        """Test failure when daemon cannot start."""
        mock_run.side_effect = FileNotFoundError()
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliNotAvailableError, match="Failed to start"):
            adapter._ensure_daemon()

    @patch("subprocess.run")
    def test_ensure_daemon_start_timeout(self, mock_run):
        """Test timeout during daemon startup."""
        # Both checks time out
        mock_run.side_effect = subprocess.TimeoutExpired("as-cli", 30)
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliTimeoutError, match="startup timed out"):
            adapter._ensure_daemon()


class TestAsCliAdapterGetLogicalList:
    """Test as-cli logical list command."""

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_logical_list_success(self, mock_run, mock_ensure_daemon):
        """Test successful logical list command."""
        mock_ensure_daemon.return_value = True
        
        logical_list_output = {
            "modules": [
                {"name": "Main", "path": "Main"},
                {"name": "Helper", "path": "Helper"}
            ],
            "tasks": [],
            "programs": []
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(logical_list_output),
            stderr=""
        )
        
        adapter = AsCliAdapter()
        result = adapter.get_logical_list()
        
        assert result == logical_list_output
        mock_ensure_daemon.assert_called_once()
        mock_run.assert_called_once()

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_logical_list_daemon_error(self, mock_run, mock_ensure_daemon):
        """Test logical list when daemon startup fails."""
        mock_ensure_daemon.side_effect = AsCliNotAvailableError("Daemon failed")
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliNotAvailableError):
            adapter.get_logical_list()

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_logical_list_timeout(self, mock_run, mock_ensure_daemon):
        """Test logical list command timeout."""
        mock_ensure_daemon.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired("as-cli", 30)
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliTimeoutError, match="timed out"):
            adapter.get_logical_list()

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_logical_list_command_error(self, mock_run, mock_ensure_daemon):
        """Test logical list when command fails."""
        mock_ensure_daemon.return_value = True
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="Error message"
        )
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliCommandError, match="logical list failed"):
            adapter.get_logical_list()

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_logical_list_malformed_json(self, mock_run, mock_ensure_daemon):
        """Test logical list with malformed JSON output."""
        mock_ensure_daemon.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout="not valid json",
            stderr=""
        )
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliParseError, match="Failed to parse"):
            adapter.get_logical_list()


class TestAsCliAdapterGetSymbolSearch:
    """Test as-cli symbol search command."""

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_symbol_search_success(self, mock_run, mock_ensure_daemon):
        """Test successful symbol search command."""
        mock_ensure_daemon.return_value = True
        
        symbol_search_output = {
            "symbols": [
                {"name": "MainProgram", "type": "program", "scope": "modules.main"},
                {"name": "DoWork", "type": "function", "scope": "modules.main"}
            ]
        }
        mock_run.return_value = Mock(
            returncode=0,
            stdout=json.dumps(symbol_search_output),
            stderr=""
        )
        
        adapter = AsCliAdapter()
        result = adapter.get_symbol_search()
        
        assert result == symbol_search_output
        mock_ensure_daemon.assert_called_once()
        # Check that * was passed as query
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "*" in args

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_symbol_search_custom_query(self, mock_run, mock_ensure_daemon):
        """Test symbol search with custom query."""
        mock_ensure_daemon.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"symbols": []}',
            stderr=""
        )
        
        adapter = AsCliAdapter()
        adapter.get_symbol_search("Motor*")
        
        # Check that custom query was passed
        args = mock_run.call_args[0][0]
        assert "Motor*" in args

    @patch.object(AsCliAdapter, "_ensure_daemon")
    @patch("subprocess.run")
    def test_get_symbol_search_empty_results(self, mock_run, mock_ensure_daemon):
        """Test symbol search with no results."""
        mock_ensure_daemon.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"symbols": []}',
            stderr=""
        )
        
        adapter = AsCliAdapter()
        result = adapter.get_symbol_search()
        
        assert result == {"symbols": []}


class TestAsCliAdapterScanProject:
    """Test convenience scan_project method."""

    @patch.object(AsCliAdapter, "get_symbol_search")
    @patch.object(AsCliAdapter, "get_logical_list")
    def test_scan_project_success(self, mock_logical, mock_symbols):
        """Test complete project scan."""
        mock_logical.return_value = {
            "modules": [{"name": "Main", "path": "Main"}],
            "tasks": [],
            "programs": []
        }
        mock_symbols.return_value = {
            "symbols": [{"name": "MainProgram", "type": "program", "scope": "modules.main"}]
        }
        
        adapter = AsCliAdapter(project_path="/test/project")
        result = adapter.scan_project()
        
        assert isinstance(result, AsCliProjectData)
        assert len(result.modules) == 1
        assert result.modules[0].name == "Main"
        assert len(result.symbols) == 1
        assert "MainProgram" in result.symbols
        assert result.project_path == "/test/project"
        assert result.execution_time_ms >= 0  # May be 0 for fast mocked calls

    @patch.object(AsCliAdapter, "get_logical_list")
    def test_scan_project_logical_list_fails(self, mock_logical):
        """Test scan failure when logical list fails."""
        mock_logical.side_effect = AsCliCommandError("Command failed")
        
        adapter = AsCliAdapter()
        
        with pytest.raises(AsCliCommandError):
            adapter.scan_project()


class TestAsCliExceptionHierarchy:
    """Test exception hierarchy."""

    def test_exception_inheritance(self):
        """Test that all custom exceptions inherit from AsCliError."""
        assert issubclass(AsCliNotAvailableError, AsCliError)
        assert issubclass(AsCliCommandError, AsCliError)
        assert issubclass(AsCliTimeoutError, AsCliError)
        assert issubclass(AsCliParseError, AsCliError)
        assert issubclass(AsCliError, Exception)

    def test_exception_instantiation(self):
        """Test that exceptions can be instantiated with messages."""
        exc = AsCliError("test message")
        assert str(exc) == "test message"
        
        exc = AsCliNotAvailableError("as-cli not found")
        assert "as-cli not found" in str(exc)
