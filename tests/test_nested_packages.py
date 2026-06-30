"""Tests for nested package (AS6 recursive) scanning."""

from __future__ import annotations
from pathlib import Path

NESTED = Path(__file__).parent / "fixtures" / "NestedProject"
SAMPLE = Path(__file__).parent / "fixtures" / "SampleProject"


# ---------------------------------------------------------------------------
# pkg_parser tests
# ---------------------------------------------------------------------------


class TestParseAs6PackageObjects:
    def test_reads_packages_and_programs(self):
        from as_docs.scanner.pkg_parser import parse_as6_package_objects

        pkg = NESTED / "Logical" / "Infrastructure" / "Alarms" / "Package.pkg"
        objects = parse_as6_package_objects(pkg)
        types = {o.obj_type for o in objects}
        names = {o.name for o in objects}
        assert "Program" in types
        assert "AlarmProg" in names
        assert "BoolSubscription" in names

    def test_returns_empty_for_non_as6_file(self, tmp_path):
        from as_docs.scanner.pkg_parser import parse_as6_package_objects

        f = tmp_path / "Package.pkg"
        f.write_text('<Object Version="4" Name="Foo" ObjectType="661"/>')
        assert parse_as6_package_objects(f) == []

    def test_returns_empty_for_missing_file(self, tmp_path):
        from as_docs.scanner.pkg_parser import parse_as6_package_objects

        assert parse_as6_package_objects(tmp_path / "nonexistent.pkg") == []

    def test_reads_nested_package_refs(self):
        from as_docs.scanner.pkg_parser import parse_as6_package_objects

        pkg = NESTED / "Logical" / "Infrastructure" / "Package.pkg"
        objects = parse_as6_package_objects(pkg)
        types = {o.obj_type for o in objects}
        names = {o.name for o in objects}
        assert "Package" in types
        assert "Alarms" in names

    def test_root_package_objects(self):
        from as_docs.scanner.pkg_parser import parse_as6_package_objects

        pkg = NESTED / "Logical" / "Package.pkg"
        objects = parse_as6_package_objects(pkg)
        names = {o.name for o in objects}
        assert "TopLevelProg" in names
        assert "Infrastructure" in names


class TestParsePkgAs6:
    def test_iec_prg_returns_parent_dir_name(self):
        from as_docs.scanner.pkg_parser import parse_pkg

        iec = NESTED / "Logical" / "Infrastructure" / "Alarms" / "AlarmProg" / "IEC.prg"
        pou = parse_pkg(iec)
        assert pou is not None
        assert pou.name == "AlarmProg"
        assert pou.pou_type == "PROGRAM"

    def test_package_pkg_returns_none(self):
        from as_docs.scanner.pkg_parser import parse_pkg

        pkg = NESTED / "Logical" / "Infrastructure" / "Package.pkg"
        assert parse_pkg(pkg) is None

    def test_as4_prg_still_works(self):
        from as_docs.scanner.pkg_parser import parse_pkg

        prg = SAMPLE / "Logical" / "MainProgram" / "MainProgram.prg"
        pou = parse_pkg(prg)
        assert pou is not None
        assert pou.name == "MainProgram"
        assert pou.pou_type == "PROGRAM"


# ---------------------------------------------------------------------------
# Scanner integration tests
# ---------------------------------------------------------------------------


class TestNestedPackageScanning:
    def _scan(self, project_root=NESTED):
        from as_docs.config import Config, ScannerConfig, ProjectConfig
        from as_docs.scanner.project_scanner import scan_project

        config = Config(
            project=ProjectConfig(root=str(project_root)),
            scanner=ScannerConfig(recursive_packages=True, max_recursion_depth=10),
        )
        return scan_project(config, project_root=project_root)

    def test_discovers_top_level_pou(self):
        model = self._scan()
        assert "TopLevelProg" in model.pous

    def test_discovers_nested_pou_alarmProg(self):
        model = self._scan()
        assert "AlarmProg" in model.pous

    def test_discovers_nested_pou_boolSubscription(self):
        model = self._scan()
        assert "BoolSubscription" in model.pous

    def test_total_pou_count(self):
        model = self._scan()
        # TopLevelProg + AlarmProg + BoolSubscription = 3
        assert len(model.pous) >= 3

    def test_package_path_populated(self):
        model = self._scan()
        alarm_pou = model.pous.get("AlarmProg")
        assert alarm_pou is not None
        # Should be "Infrastructure.Alarms" or similar
        assert "Infrastructure" in alarm_pou.package_path
        assert "Alarms" in alarm_pou.package_path

    def test_top_level_pou_has_empty_package_path(self):
        model = self._scan()
        top = model.pous.get("TopLevelProg")
        assert top is not None
        assert top.package_path == ""

    def test_recursive_packages_false_disables_tree_scan(self):
        from as_docs.config import Config, ScannerConfig, ProjectConfig
        from as_docs.scanner.project_scanner import scan_project

        config = Config(
            project=ProjectConfig(root=str(NESTED)),
            scanner=ScannerConfig(recursive_packages=False),
        )
        model = scan_project(config, project_root=NESTED)
        # With tree scan disabled, rglob still finds IEC.prg files via AS6 parse_pkg fix
        # AlarmProg and BoolSubscription come from IEC.prg parent-dir name detection
        assert "AlarmProg" in model.pous or "BoolSubscription" in model.pous

    def test_backward_compat_sample_project(self):
        """AS4-format SampleProject should still scan correctly."""
        from as_docs.config import Config, ScannerConfig, ProjectConfig
        from as_docs.scanner.project_scanner import scan_project

        config = Config(
            project=ProjectConfig(root=str(SAMPLE)),
            scanner=ScannerConfig(recursive_packages=True),
        )
        model = scan_project(config, project_root=SAMPLE)
        assert "MainProgram" in model.pous
        assert "MotorControl" in model.pous


class TestCircularReferenceDetection:
    def test_circular_reference_does_not_hang(self, tmp_path):
        """Scanner must not infinite-loop when Package.pkg files form a cycle."""
        from as_docs.config import Config, ScannerConfig, ProjectConfig
        from as_docs.scanner.project_scanner import scan_project

        # Build: Logical/Package.pkg → PkgA → (Package.pkg references PkgA again)
        logical = tmp_path / "Logical"
        pkg_a = logical / "PkgA"
        pkg_a.mkdir(parents=True)
        (tmp_path / "Physical").mkdir()

        root_pkg = logical / "Package.pkg"
        root_pkg.write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Package xmlns="http://br-automation.co.at/AS/Package">'
            '<Objects><Object Type="Package">PkgA</Object></Objects>'
            "</Package>"
        )
        # PkgA's Package.pkg points back to "PkgA" (same dir — canonical path matches)
        (pkg_a / "Package.pkg").write_text(
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<Package xmlns="http://br-automation.co.at/AS/Package">'
            '<Objects><Object Type="Package">PkgA</Object></Objects>'
            "</Package>"
        )

        config = Config(
            project=ProjectConfig(root=str(tmp_path)),
            scanner=ScannerConfig(recursive_packages=True, max_recursion_depth=5),
        )
        # Should complete without hanging or raising
        model = scan_project(config, project_root=tmp_path)
        assert model is not None


class TestMaxRecursionDepth:
    def test_deep_nesting_stops_at_limit(self, tmp_path):
        from as_docs.config import Config, ScannerConfig, ProjectConfig
        from as_docs.scanner.project_scanner import scan_project

        # Build 12 levels of nesting (exceeds default limit of 10)
        logical = tmp_path / "Logical"
        (tmp_path / "Physical").mkdir()
        current = logical
        current.mkdir(parents=True)
        for i in range(12):
            child = current / f"Level{i}"
            child.mkdir()
            (current / "Package.pkg").write_text(
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<Package xmlns="http://br-automation.co.at/AS/Package">'
                f'<Objects><Object Type="Package">Level{i}</Object></Objects>'
                "</Package>"
            )
            current = child

        config = Config(
            project=ProjectConfig(root=str(tmp_path)),
            scanner=ScannerConfig(recursive_packages=True, max_recursion_depth=5),
        )
        # Should complete without RecursionError
        model = scan_project(config, project_root=tmp_path)
        assert model is not None
