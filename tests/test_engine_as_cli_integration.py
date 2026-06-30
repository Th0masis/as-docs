"""Tests for engine integration with as-cli."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from as_docs.config import Config, AsCliConfig, OutputConfig
from as_docs.engine import (
    _should_use_as_cli,
    _merge_as_cli_data,
    _save_conflict_report,
    run_generate,
)
from as_docs.model.project import ProjectModel
from as_docs.scanner.as_cli_models import AsCliProjectData, AsCliModule
from as_docs.scanner.data_conflict_resolver import ConflictReport, Conflict


class MockPOU:
    """Mock POU for testing."""

    def __init__(self, name, source_file="test.st"):
        self.name = name
        self.source_file = source_file
        self.pou_type = "program"
        self.metadata = {}


class TestShouldUseAsCli:
    """Test precedence logic for use_as_cli decision."""

    def test_cli_flag_true_overrides_all(self):
        """CLI flag True should override config False."""
        config = Config(as_cli=AsCliConfig(enabled=False))
        assert _should_use_as_cli(True, config) is True

    def test_cli_flag_false_overrides_all(self):
        """CLI flag False should override config True."""
        config = Config(as_cli=AsCliConfig(enabled=True))
        assert _should_use_as_cli(False, config) is False

    def test_config_used_when_no_cli_flag(self):
        """Config setting used when CLI flag is None."""
        config_true = Config(as_cli=AsCliConfig(enabled=True))
        config_false = Config(as_cli=AsCliConfig(enabled=False))

        assert _should_use_as_cli(None, config_true) is True
        assert _should_use_as_cli(None, config_false) is False

    def test_default_is_false(self):
        """Default should be False (opt-in)."""
        config = Config()
        assert _should_use_as_cli(None, config) is False


class TestMergeAsCliDataSuccess:
    """Test successful as-cli merge scenarios."""

    def test_merge_with_clean_data(self):
        """Test successful merge with no conflicts."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {
            "Main": MockPOU("Main", "Main.st"),
            "Helper": MockPOU("Helper", "Helper.st"),
        }

        config = Config(
            as_cli=AsCliConfig(
                enabled=True, path="as-cli", timeout_ms=30000, strict=False
            )
        )

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            # Mock adapter
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True
            mock_adapter.scan_project.return_value = AsCliProjectData(
                modules=[
                    AsCliModule("Main", "Main.st", "program"),
                    AsCliModule("Helper", "Helper.st", "program"),
                ]
            )

            # Call merge
            report = _merge_as_cli_data(model, config, Path("."))

            # Verify
            assert report is not None
            assert report.pou_count_fs == 2
            assert report.pou_count_as_cli == 2
            assert len(report.conflicts) == 0
            assert len(report.agreed_pous) == 2

    def test_merge_detects_new_pou_from_as_cli(self):
        """Test that as-cli can discover POUs missed by filesystem."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {"Main": MockPOU("Main", "Main.st")}

        config = Config(as_cli=AsCliConfig(enabled=True, strict=False))

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True
            mock_adapter.scan_project.return_value = AsCliProjectData(
                modules=[
                    AsCliModule("Main", "Main.st", "program"),
                    AsCliModule("NewModule", "NewModule.st", "program"),
                ]
            )

            report = _merge_as_cli_data(model, config, Path("."))

            assert report is not None
            assert len(report.as_cli_only_pous) == 1
            assert "NewModule" in report.as_cli_only_pous
            # Model should be updated with new POU
            assert "NewModule" in model.pous


class TestMergeAsCliDataGracefulFallback:
    """Test graceful fallback when as-cli is unavailable."""

    def test_graceful_fallback_when_as_cli_not_available(self):
        """Test graceful fallback when as-cli not installed."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {"Main": MockPOU("Main")}

        config = Config(as_cli=AsCliConfig(enabled=True, strict=False))

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = False

            # Should gracefully fallback
            report = _merge_as_cli_data(model, config, Path("."))

            assert report is None
            # Model should be unchanged
            assert "Main" in model.pous

    def test_graceful_fallback_on_adapter_error(self):
        """Test graceful fallback on adapter error."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {"Main": MockPOU("Main")}

        config = Config(as_cli=AsCliConfig(enabled=True, strict=False))

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True
            mock_adapter.scan_project.side_effect = Exception("Timeout")

            # Should gracefully fallback
            report = _merge_as_cli_data(model, config, Path("."))

            assert report is None


class TestMergeAsCliDataStrictMode:
    """Test strict mode error handling."""

    def test_strict_mode_raises_on_unavailable(self):
        """Test that strict mode raises error when as-cli unavailable."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {"Main": MockPOU("Main")}

        config = Config(as_cli=AsCliConfig(enabled=True, strict=True))

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = False

            # Should raise error
            with pytest.raises(Exception):
                _merge_as_cli_data(model, config, Path("."))

    def test_strict_mode_raises_on_adapter_error(self):
        """Test that strict mode raises error on adapter failure."""
        model = ProjectModel(
            project_root=Path("."),
            project_name="TestProject",
            as_version="6.0",
            active_configuration="Config1",
        )
        model.pous = {"Main": MockPOU("Main")}

        config = Config(as_cli=AsCliConfig(enabled=True, strict=True))

        with patch("as_docs.engine.AsCliAdapter") as MockAdapter:
            mock_adapter = MagicMock()
            MockAdapter.return_value = mock_adapter
            mock_adapter.is_available.return_value = True
            mock_adapter.scan_project.side_effect = Exception("Adapter failed")

            # Should raise error
            with pytest.raises(Exception):
                _merge_as_cli_data(model, config, Path("."))


class TestSaveConflictReport:
    """Test conflict report saving."""

    def test_save_report_to_file(self, tmp_path):
        """Test saving conflict report to JSON file."""
        report = ConflictReport(
            pou_count_fs=5,
            pou_count_as_cli=5,
            pou_count_merged=5,
            conflicts=[Conflict("path_mismatch", "Main", "src/Main", "lib/Main")],
        )

        _save_conflict_report(report, tmp_path)

        # Verify file was created
        report_file = tmp_path / "as_cli_conflict_report.json"
        assert report_file.exists()

        # Verify content
        content = report_file.read_text()
        assert "path_mismatch" in content
        assert "Main" in content

    def test_save_report_creates_directory(self, tmp_path):
        """Test that save creates output directory if needed."""
        report = ConflictReport()
        output_dir = tmp_path / "nested" / "output"

        _save_conflict_report(report, output_dir)

        # Directory should be created
        assert output_dir.exists()
        assert (output_dir / "as_cli_conflict_report.json").exists()


class TestRunGenerateWithAsCli:
    """Test run_generate with as-cli integration."""

    def test_run_generate_without_as_cli(self):
        """Test run_generate when as_cli disabled."""
        config = Config(
            as_cli=AsCliConfig(enabled=False),
            output=OutputConfig(docs_dir="/tmp/docs", formats=["json"]),
        )

        with (
            patch("as_docs.engine.scan_project") as mock_scan,
            patch("as_docs.engine._build_full_graph") as mock_graph,
            patch("as_docs.engine.generate_json"),
            patch("as_docs.engine._merge_as_cli_data") as mock_merge,
        ):
            # Setup mocks
            model = ProjectModel(
                project_root=Path("."),
                project_name="Test",
                as_version="6.0",
                active_configuration="Config1",
            )
            model.pous = {"Main": MockPOU("Main")}
            mock_scan.return_value = model

            graph = Mock()
            graph.pous = model.pous
            mock_graph.return_value = graph

            # Call generate
            result = run_generate(config, level=1)

            # Merge should not be called
            mock_merge.assert_not_called()
            assert result == graph

    def test_run_generate_with_cli_override_true(self):
        """Test run_generate with CLI override to enable as-cli."""
        config = Config(
            as_cli=AsCliConfig(enabled=False),  # Config has it disabled
            output=OutputConfig(docs_dir="/tmp/docs", formats=["json"]),
        )

        with (
            patch("as_docs.engine.scan_project") as mock_scan,
            patch("as_docs.engine._build_full_graph") as mock_graph,
            patch("as_docs.engine.generate_json"),
            patch("as_docs.engine._merge_as_cli_data") as mock_merge,
        ):
            # Setup mocks
            model = ProjectModel(
                project_root=Path("."),
                project_name="Test",
                as_version="6.0",
                active_configuration="Config1",
            )
            mock_scan.return_value = model

            graph = Mock()
            graph.pous = {}
            mock_graph.return_value = graph

            mock_merge.return_value = None  # Graceful fallback

            # Call with CLI override
            run_generate(config, level=1, use_as_cli=True)

            # Merge should be called because CLI override
            mock_merge.assert_called_once()
