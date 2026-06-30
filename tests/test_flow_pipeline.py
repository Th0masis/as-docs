from __future__ import annotations

from pathlib import Path

from as_docs.config import Config, OutputConfig, ScannerConfig
from as_docs.engine import load_graph, run_generate
from as_docs.mcp_server import get_flow_diagram_payload
from as_docs.generator.flow_diagram_gen import build_flow_diagram

FIXTURE = Path(__file__).parent / "fixtures" / "SampleProject"


def _config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.project.name = "SampleProject"
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"), default_level=4)
    cfg.ai.enabled = False
    cfg.ai.cache_dir = str(tmp_path / ".cache")
    return cfg


def test_flow_extractor_builds_case_and_if_diagrams() -> None:
    main_source = (FIXTURE / "Logical" / "MainProgram" / "Main.st").read_text(
        encoding="utf-8"
    )
    motor_source = (FIXTURE / "Logical" / "MotorControl" / "MotorControl.st").read_text(
        encoding="utf-8"
    )

    main_diagram = build_flow_diagram("MainProgram", main_source)
    motor_diagram = build_flow_diagram("MotorControl", motor_source)

    assert main_diagram is not None
    assert main_diagram.diagram_type == "stateDiagram-v2"
    assert main_diagram.confidence == "HIGH"
    assert "stateDiagram-v2" in main_diagram.mermaid_code
    assert "MOTORSTATE_IDLE" in main_diagram.mermaid_code

    assert motor_diagram is not None
    assert motor_diagram.diagram_type == "flowchart"
    assert motor_diagram.confidence in {"MEDIUM", "LOW"}
    assert "flowchart TD" in motor_diagram.mermaid_code


def test_flow_diagram_uses_ai_fallback_narrative() -> None:
    main_source = (FIXTURE / "Logical" / "MainProgram" / "Main.st").read_text(
        encoding="utf-8"
    )

    diagram = build_flow_diagram(
        "MainProgram",
        main_source,
        ai_enabled=True,
        narrative_hint="AI summary for MainProgram",
    )

    assert diagram is not None
    assert diagram.source == "parsed+ai"
    assert diagram.narrative == "AI summary for MainProgram"


def test_level4_generate_populates_flow_diagrams_and_markdown(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    graph = run_generate(cfg, level=4, ai_enabled=False, project_root=FIXTURE)

    assert graph.level == 4
    assert "MainProgram" in graph.flow_diagrams
    assert "MotorControl" in graph.flow_diagrams
    assert graph.flow_diagrams["MainProgram"].diagram_type == "stateDiagram-v2"
    assert graph.flow_diagrams["MainProgram"].source == "parsed"
    assert graph.flow_diagrams["MotorControl"].diagram_type == "flowchart"

    docs_dir = tmp_path / "docs"
    assert (docs_dir / "knowledge_graph.json").exists()
    assert (docs_dir / "pou" / "MainProgram.flow.md").exists()
    assert (docs_dir / "pou" / "MotorControl.flow.md").exists()
    assert (docs_dir / "llms.txt").exists()


def test_mcp_flow_diagram_payload_returns_real_diagram(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    run_generate(cfg, level=4, ai_enabled=False, project_root=FIXTURE)

    loaded = load_graph(cfg)
    assert loaded is not None

    payload = get_flow_diagram_payload(loaded, "MainProgram", requested_level=4)

    assert payload["status"] == "ok"
    assert payload["data"]["flow_diagram"]["pou_name"] == "MainProgram"
    assert payload["data"]["flow_diagram"]["diagram_type"] == "stateDiagram-v2"
    assert "MOTORSTATE_IDLE" in payload["data"]["flow_diagram"]["mermaid_code"]
