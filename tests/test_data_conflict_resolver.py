"""Tests for data conflict resolver (merge logic, conflict detection)."""
import pytest
from datetime import datetime

from as_docs.scanner.data_conflict_resolver import (
    Conflict,
    ConflictReport,
    DataConflictResolver,
)
from as_docs.scanner.as_cli_models import (
    AsCliProjectData,
    AsCliModule,
    AsCliSymbol,
)


# Simple POU-like object for testing
class MockPOU:
    """Mock POU object for testing."""
    
    def __init__(self, name, source_file, pou_type="program"):
        self.name = name
        self.source_file = source_file
        self.pou_type = pou_type
        self.metadata = None


class TestConflictClass:
    """Test Conflict data class."""
    
    def test_conflict_creation(self):
        """Test creating a conflict."""
        conflict = Conflict(
            conflict_type="path_mismatch",
            pou_name="Main",
            fs_value="src/Main.prg",
            as_cli_value="lib/Main.prg",
            severity="warning"
        )
        
        assert conflict.conflict_type == "path_mismatch"
        assert conflict.pou_name == "Main"
        assert conflict.fs_value == "src/Main.prg"
        assert conflict.as_cli_value == "lib/Main.prg"
        assert conflict.severity == "warning"
    
    def test_conflict_to_dict(self):
        """Test converting conflict to dictionary."""
        conflict = Conflict(
            conflict_type="type_mismatch",
            pou_name="Helper",
            fs_value="program",
            as_cli_value="function"
        )
        
        d = conflict.to_dict()
        assert d["conflict_type"] == "type_mismatch"
        assert d["pou_name"] == "Helper"
        assert d["fs_value"] == "program"
        assert d["as_cli_value"] == "function"


class TestConflictReportClass:
    """Test ConflictReport data class."""
    
    def test_conflict_report_creation(self):
        """Test creating a conflict report."""
        report = ConflictReport(
            pou_count_fs=10,
            pou_count_as_cli=11,
            pou_count_merged=11,
            agreed_pous=["Main", "Helper"],
            fs_only_pous=["Unused"],
            as_cli_only_pous=["NewModule"]
        )
        
        assert report.pou_count_fs == 10
        assert report.pou_count_as_cli == 11
        assert report.pou_count_merged == 11
        assert len(report.conflicts) == 0
        assert report.has_conflicts is False
    
    def test_conflict_report_has_conflicts(self):
        """Test has_conflicts property."""
        report = ConflictReport(conflicts=[
            Conflict("path_mismatch", "Main")
        ])
        
        assert report.has_conflicts is True
    
    def test_conflict_report_summary_clean_merge(self):
        """Test summary for clean merge (no conflicts)."""
        report = ConflictReport(
            pou_count_fs=5,
            pou_count_as_cli=5,
            pou_count_merged=5,
            agreed_pous=["A", "B", "C", "D", "E"]
        )
        
        summary = report.summary
        assert "5" in summary
        assert "Filesystem POUs: 5" in summary
        assert "Conflicts detected: 0" in summary
    
    def test_conflict_report_summary_with_conflicts(self):
        """Test summary with conflicts."""
        conflicts = [
            Conflict("path_mismatch", "Main"),
            Conflict("type_mismatch", "Helper"),
            Conflict("path_mismatch", "Util"),
        ]
        
        report = ConflictReport(
            conflicts=conflicts,
            pou_count_fs=10,
            pou_count_as_cli=11,
            pou_count_merged=11,
            fs_only_pous=["Old"],
            as_cli_only_pous=["New"]
        )
        
        summary = report.summary
        assert "Conflicts detected: 3" in summary
        assert "path_mismatch: 2" in summary
        assert "type_mismatch: 1" in summary
    
    def test_conflict_report_to_dict(self):
        """Test converting report to dictionary."""
        report = ConflictReport(
            pou_count_fs=5,
            pou_count_as_cli=5,
            pou_count_merged=5
        )
        
        d = report.to_dict()
        assert d["pou_count_fs"] == 5
        assert d["pou_count_as_cli"] == 5
        assert d["pou_count_merged"] == 5
        assert "summary" in d
    
    def test_conflict_report_to_json(self):
        """Test converting report to JSON."""
        report = ConflictReport(
            pou_count_fs=3,
            pou_count_merged=3
        )
        
        json_str = report.to_json()
        assert "pou_count_fs" in json_str
        assert "3" in json_str
        assert isinstance(json_str, str)


class TestDataConflictResolverBasics:
    """Test basic DataConflictResolver functionality."""
    
    def test_resolver_creation(self):
        """Test creating a resolver."""
        resolver = DataConflictResolver()
        assert resolver is not None
    
    def test_merge_empty_sources(self):
        """Test merge with empty sources."""
        resolver = DataConflictResolver()
        as_cli_data = AsCliProjectData()
        
        merged, report = resolver.merge({}, as_cli_data)
        
        assert merged == {}
        assert report.pou_count_fs == 0
        assert report.pou_count_as_cli == 0
        assert report.pou_count_merged == 0
        assert not report.has_conflicts
    
    def test_merge_invalid_fs_pous(self):
        """Test merge with invalid filesystem data."""
        resolver = DataConflictResolver()
        as_cli_data = AsCliProjectData()
        
        with pytest.raises(ValueError, match="fs_pous must be"):
            resolver.merge("not a dict", as_cli_data)
    
    def test_merge_invalid_as_cli_data(self):
        """Test merge with invalid as-cli data."""
        resolver = DataConflictResolver()
        
        with pytest.raises(ValueError, match="as_cli_data must be"):
            resolver.merge({}, "not AsCliProjectData")


class TestDataConflictResolverCleanMerge:
    """Test merge scenarios with no conflicts."""
    
    def test_merge_filesystem_only(self):
        """Test merge when only filesystem has POUs."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "src/Main.prg", "program"),
            "Helper": MockPOU("Helper", "src/Helper.prg", "program")
        }
        as_cli_data = AsCliProjectData()
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(merged) == 2
        assert "Main" in merged
        assert "Helper" in merged
        assert report.pou_count_fs == 2
        assert report.pou_count_as_cli == 0
        assert report.pou_count_merged == 2
        assert len(report.fs_only_pous) == 2
        assert len(report.as_cli_only_pous) == 0
        assert len(report.agreed_pous) == 0
    
    def test_merge_as_cli_only(self):
        """Test merge when only as-cli has POUs."""
        resolver = DataConflictResolver()
        
        fs_pous = {}
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "Main", "program"),
                AsCliModule("Helper", "Helper", "program")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(merged) == 2
        assert "Main" in merged
        assert "Helper" in merged
        assert report.pou_count_fs == 0
        assert report.pou_count_as_cli == 2
        assert report.pou_count_merged == 2
        assert len(report.fs_only_pous) == 0
        assert len(report.as_cli_only_pous) == 2
    
    def test_merge_perfect_agreement(self):
        """Test merge when both sources fully agree."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "Main.prg", "program"),
            "Helper": MockPOU("Helper", "Helper.prg", "program")
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "Main.prg", "program"),
                AsCliModule("Helper", "Helper.prg", "program")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(merged) == 2
        assert report.pou_count_fs == 2
        assert report.pou_count_as_cli == 2
        assert report.pou_count_merged == 2
        assert len(report.agreed_pous) == 2
        assert len(report.conflicts) == 0
        assert not report.has_conflicts


class TestDataConflictResolverPathMismatches:
    """Test detection of path mismatches."""
    
    def test_path_mismatch_detection(self):
        """Test detection of path mismatches."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "src/Main.prg", "program")
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "lib/Main.prg", "program")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(report.conflicts) == 1
        assert report.has_conflicts
        
        conflict = report.conflicts[0]
        assert conflict.conflict_type == "path_mismatch"
        assert conflict.pou_name == "Main"
        assert conflict.fs_value == "src/Main.prg"
        assert conflict.as_cli_value == "lib/Main.prg"
        assert conflict.severity == "warning"
    
    def test_multiple_path_mismatches(self):
        """Test detection of multiple path mismatches."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "src/Main.prg", "program"),
            "Helper": MockPOU("Helper", "src/Helper.prg", "program")
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "lib/Main.prg", "program"),
                AsCliModule("Helper", "lib/Helper.prg", "program")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(report.conflicts) == 2
        path_mismatches = [c for c in report.conflicts if c.conflict_type == "path_mismatch"]
        assert len(path_mismatches) == 2


class TestDataConflictResolverTypeMismatches:
    """Test detection of type mismatches."""
    
    def test_type_mismatch_detection(self):
        """Test detection of type mismatches."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "Main.prg", "program")
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "Main.prg", "function")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert len(report.conflicts) == 1
        conflict = report.conflicts[0]
        assert conflict.conflict_type == "type_mismatch"
        assert conflict.fs_value == "program"
        assert conflict.as_cli_value == "function"
    
    def test_multiple_conflict_types(self):
        """Test detection of different conflict types simultaneously."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "src/Main.prg", "program"),
            "Helper": MockPOU("Helper", "src/Helper.prg", "function")
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "lib/Main.prg", "function"),  # Path + type mismatch
                AsCliModule("Helper", "src/Helper.prg", "function")  # No mismatch
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        # Main should have 2 conflicts (path + type), Helper should have none
        main_conflicts = [c for c in report.conflicts if c.pou_name == "Main"]
        assert len(main_conflicts) == 2
        
        conflict_types = {c.conflict_type for c in main_conflicts}
        assert "path_mismatch" in conflict_types
        assert "type_mismatch" in conflict_types


class TestDataConflictResolverSmartUnion:
    """Test smart union strategy."""
    
    def test_union_strategy_comprehensive(self):
        """Test comprehensive union merge scenario."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "Main.prg", "program"),
            "Unused": MockPOU("Unused", "Unused.prg", "program"),  # fs only
            "Helper": MockPOU("Helper", "Helper.prg", "program")  # both
        }
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "Main.prg", "program"),  # both
                AsCliModule("Helper", "Helper.prg", "program"),  # both
                AsCliModule("NewLib", "Lib/NewLib.lib", "library")  # as-cli only
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        # Union should have 4 POUs
        assert len(merged) == 4
        assert "Main" in merged
        assert "Helper" in merged
        assert "Unused" in merged
        assert "NewLib" in merged
        
        # Verify categorization
        assert set(report.agreed_pous) == {"Helper", "Main"}
        assert set(report.fs_only_pous) == {"Unused"}
        assert set(report.as_cli_only_pous) == {"NewLib"}
        
        # Verify report counts
        assert report.pou_count_fs == 3
        assert report.pou_count_as_cli == 3
        assert report.pou_count_merged == 4
    
    def test_as_cli_data_preferred_on_conflicts(self):
        """Test that as-cli data is preferred when merging conflicts."""
        resolver = DataConflictResolver()
        
        fs_pou = MockPOU("Main", "src/Main.prg", "program")
        fs_pous = {"Main": fs_pou}
        
        as_cli_data = AsCliProjectData(
            modules=[
                AsCliModule("Main", "lib/Main.prg", "function")
            ]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        # Merged POU should have as-cli values
        main_pou = merged["Main"]
        assert main_pou.source_file == "lib/Main.prg"
        assert main_pou.pou_type == "function"
        assert main_pou.metadata["as_cli_verified"] is True


class TestDataConflictResolverMetadata:
    """Test metadata tracking in merged POUs."""
    
    def test_metadata_fs_only(self):
        """Test metadata for fs-only POUs."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Old": MockPOU("Old", "Old.prg", "program")
        }
        
        merged, report = resolver.merge(fs_pous, AsCliProjectData())
        
        assert merged["Old"].metadata["source"] == "filesystem"
        assert "as_cli_verified" not in merged["Old"].metadata
    
    def test_metadata_as_cli_only(self):
        """Test metadata for as-cli-only POUs."""
        resolver = DataConflictResolver()
        
        as_cli_data = AsCliProjectData(
            modules=[AsCliModule("New", "New.prg", "program")]
        )
        
        merged, report = resolver.merge({}, as_cli_data)
        
        assert merged["New"]["metadata"]["source"] == "as_cli_only"
        assert merged["New"]["metadata"]["discovered_by_as_cli"] is True
    
    def test_metadata_both_sources(self):
        """Test metadata for POUs in both sources."""
        resolver = DataConflictResolver()
        
        fs_pous = {
            "Main": MockPOU("Main", "Main.prg", "program")
        }
        as_cli_data = AsCliProjectData(
            modules=[AsCliModule("Main", "Main.prg", "program")]
        )
        
        merged, report = resolver.merge(fs_pous, as_cli_data)
        
        assert merged["Main"].metadata["source"] == "both"
        assert merged["Main"].metadata["as_cli_verified"] is True
