"""Tests for Phase 1 — scanner and analyzer."""
from __future__ import annotations
from pathlib import Path
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "SampleProject"


def test_fixture_exists():
    assert (FIXTURE / "Logical").is_dir()
    assert (FIXTURE / "Physical").is_dir()


def test_var_parser():
    from as_docs.scanner.var_parser import parse_var_file
    var_file = FIXTURE / "Logical" / "GlobalVars" / "GVL_Main.var"
    vars_, gvl_name = parse_var_file(var_file)
    assert len(vars_) >= 3
    names = {v.name for v in vars_}
    assert "gMotorSpeed" in names
    assert "gFault" in names
    speed_var = next(v for v in vars_ if v.name == "gMotorSpeed")
    assert speed_var.var_type == "REAL"
    assert speed_var.unit == "rpm"


def test_typ_parser():
    from as_docs.scanner.typ_parser import parse_typ_file
    typ_file = FIXTURE / "Logical" / "GlobalVars" / "GlobalTypes.typ"
    types = parse_typ_file(typ_file)
    names = {t.name for t in types}
    assert "MotorStateEnum" in names
    assert "MotorConfigType" in names
    enum = next(t for t in types if t.name == "MotorStateEnum")
    assert enum.kind == "ENUM"
    assert len(enum.members) == 5
    struct = next(t for t in types if t.name == "MotorConfigType")
    assert struct.kind == "STRUCT"
    assert any(m.name == "MaxSpeed" for m in struct.members)


def test_pkg_parser_program():
    from as_docs.scanner.pkg_parser import parse_pkg
    prg_file = FIXTURE / "Logical" / "MainProgram" / "MainProgram.prg"
    pou = parse_pkg(prg_file)
    assert pou is not None
    assert pou.name == "MainProgram"
    assert pou.pou_type == "PROGRAM"


def test_pkg_parser_fb():
    from as_docs.scanner.pkg_parser import parse_pkg
    prg_file = FIXTURE / "Logical" / "MotorControl" / "MotorControl.prg"
    pou = parse_pkg(prg_file)
    assert pou is not None
    assert pou.pou_type == "FUNCTION_BLOCK"


def test_per_parser():
    from as_docs.scanner.per_parser import parse_per_file
    per_file = FIXTURE / "Physical" / "Config1" / "X20CP3173" / "Cpu.per"
    tasks = parse_per_file(per_file, configuration="Config1")
    assert len(tasks) >= 1
    names = {t.name for t in tasks}
    assert "CyclicTask" in names
    cyclic = next(t for t in tasks if t.name == "CyclicTask")
    assert cyclic.task_type == "cyclic"
    assert cyclic.cycle_time_ms == 10


def test_per_parser_sw_taskclass_format(tmp_path):
        from as_docs.scanner.per_parser import parse_per_file

        sw_file = tmp_path / "Cpu.sw"
        sw_file.write_text(
                """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<SwConfiguration xmlns=\"http://br-automation.co.at/AS/SwConfiguration\">
    <TaskClass Name=\"Cyclic#1\">
        <Task Name=\"SubsAlarms\" Source=\"Infrastructure.SubsAlarms.prg\" />
        <Task Name=\"AlarmProg\" Source=\"Infrastructure.Alarms.AlarmProg.prg\" />
    </TaskClass>
    <TaskClass Name=\"Init\">
        <Task Name=\"InitProg\" Source=\"Infrastructure.System.InitProg.prg\" />
    </TaskClass>
</SwConfiguration>
""",
                encoding="utf-8",
        )

        tasks = parse_per_file(sw_file, configuration="OptimaMaster")
        by_name = {t.name: t for t in tasks}

        assert "Cyclic#1" in by_name
        assert by_name["Cyclic#1"].task_type == "cyclic"
        assert by_name["Cyclic#1"].programs == ["SubsAlarms", "AlarmProg"]

        assert "Init" in by_name
        assert by_name["Init"].task_type == "init"
        assert by_name["Init"].programs == ["InitProg"]


def test_full_scan():
    from as_docs.config import Config, ScannerConfig
    from as_docs.scanner.project_scanner import scan_project

    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.project.name = "SampleProject"

    model = scan_project(cfg, project_root=FIXTURE)

    assert "MainProgram" in model.pous
    assert "MotorControl" in model.pous
    assert "gMotorSpeed" in model.global_vars
    assert "MotorConfigType" in model.data_types
    assert "CyclicTask" in model.tasks
    assert len(model.st_files) >= 2


def test_st_analyzer():
    from as_docs.model.project import RawSTFile
    from as_docs.analyzer.st_analyzer import analyze_st

    st_file = FIXTURE / "Logical" / "MainProgram" / "Main.st"
    raw = RawSTFile(
        path=st_file,
        pou_name="MainProgram",
        source=st_file.read_text(encoding="utf-8"),
    )
    result = analyze_st(
        raw,
        known_pous={"MainProgram", "MotorControl"},
        known_vars={"gMotorSpeed", "gFault", "gCycleCount"},
    )
    assert result.has_case
    assert "gMotorSpeed" in result.writes or "gMotorSpeed" in result.reads
    assert "gFault" in result.writes or "gFault" in result.reads


def test_level1_generate(tmp_path):
    from as_docs.config import Config, ScannerConfig, OutputConfig
    from as_docs.engine import run_generate

    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.project.name = "SampleProject"
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"))

    graph = run_generate(cfg, level=1, ai_enabled=False, project_root=FIXTURE)

    assert graph.level == 1
    assert (tmp_path / "docs" / "knowledge_graph.json").exists()
    assert (tmp_path / "docs" / "overview.md").exists()
    assert (tmp_path / "docs" / "architecture.md").exists()
    assert (tmp_path / "docs" / "global_vars.md").exists()
    assert (tmp_path / "docs" / "data_types.md").exists()
    assert (tmp_path / "docs" / "llms.txt").exists()


def test_generate_honors_output_formats_json_only(tmp_path):
    from as_docs.config import Config, ScannerConfig, OutputConfig
    from as_docs.engine import run_generate

    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.project.name = "SampleProject"
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"), formats=["json"])

    run_generate(cfg, level=2, ai_enabled=False, project_root=FIXTURE)

    assert (tmp_path / "docs" / "knowledge_graph.json").exists()
    assert not (tmp_path / "docs" / "overview.md").exists()
    assert not (tmp_path / "docs" / "architecture.md").exists()
    assert not (tmp_path / "docs" / "data_flow.md").exists()
    assert not (tmp_path / "docs" / "llms.txt").exists()


def test_generate_honors_output_formats_markdown_only(tmp_path):
    from as_docs.config import Config, ScannerConfig, OutputConfig
    from as_docs.engine import run_generate

    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.project.name = "SampleProject"
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"), formats=["markdown"])

    run_generate(cfg, level=2, ai_enabled=False, project_root=FIXTURE)

    assert not (tmp_path / "docs" / "knowledge_graph.json").exists()
    assert (tmp_path / "docs" / "overview.md").exists()
    assert (tmp_path / "docs" / "architecture.md").exists()
    assert (tmp_path / "docs" / "data_flow.md").exists()
    assert not (tmp_path / "docs" / "llms.txt").exists()


def test_instance_of_edges_use_real_fb_type_mapping(tmp_path):
    from as_docs.analyzer.call_graph import build_edges
    from as_docs.analyzer.st_analyzer import STAnalysisResult
    from as_docs.model.graph import POUNode
    from as_docs.model.project import ProjectModel

    model = ProjectModel(
        project_root=FIXTURE,
        project_name="SampleProject",
        as_version="4.10",
        active_configuration="Config1",
    )
    model.pous["MainProgram"] = POUNode(
        name="MainProgram",
        pou_type="PROGRAM",
        source_file="Logical/MainProgram/MainProgram.prg",
    )
    model.pous["MotorControl"] = POUNode(
        name="MotorControl",
        pou_type="FUNCTION_BLOCK",
        source_file="Logical/MotorControl/MotorControl.prg",
    )
    model.pous["OtherFb"] = POUNode(
        name="OtherFb",
        pou_type="FUNCTION_BLOCK",
        source_file="Logical/OtherFb/OtherFb.prg",
    )

    analysis = STAnalysisResult(
        pou_name="MainProgram",
        instance_types={"motorInst": "MotorControl"},
    )

    edges = build_edges(model, [analysis])
    instance_edges = [e for e in edges if e.edge_type == "INSTANCE_OF" and e.source == "MainProgram"]
    targets = {e.target for e in instance_edges}

    assert targets == {"MotorControl"}


def test_architecture_diagram_has_fallback_note_when_empty():
    from as_docs.generator.diagram_gen import generate_architecture_diagram
    from as_docs.model.graph import KnowledgeGraph

    graph = KnowledgeGraph(
        schema_version="1.0",
        project_name="EmptyProject",
        as_version="",
        generated_at="2026-01-01T00:00:00+00:00",
        level=1,
        active_configuration="",
        pous={},
        tasks={},
        global_vars={},
        data_types={},
        edges=[],
        flow_diagrams={},
    )

    diagram = generate_architecture_diagram(graph)
    assert "No task-program-call relationships detected" in diagram
