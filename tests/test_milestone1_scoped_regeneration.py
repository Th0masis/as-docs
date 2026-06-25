from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from as_docs.cli import cli
from as_docs.config import Config, OutputConfig, ScannerConfig
from as_docs.engine import run_generate
from as_docs.mcp_server import regenerate_payload
from as_docs.model.graph import KnowledgeGraph

FIXTURE = Path(__file__).parent / "fixtures" / "SampleProject"


def _dummy_graph() -> KnowledgeGraph:
    graph = KnowledgeGraph(
        schema_version="1.0",
        project_name="SampleProject",
        as_version="4.10",
        generated_at="2026-06-25T00:00:00Z",
        level=3,
        active_configuration="Config1",
        pous={},
        tasks={},
        global_vars={},
        data_types={},
        edges=[],
        flow_diagrams={},
    )
    setattr(
        graph,
        "_regen_meta",
        {
            "scope": "pou:MainProgram",
            "touched_pous": ["MainProgram"],
            "elapsed_seconds": 0.123,
            "scanned_pous": 2,
            "fallback_full": False,
        },
    )
    return graph


def test_engine_scope_pou_unknown_raises(tmp_path: Path) -> None:
    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"))

    with pytest.raises(ValueError, match="Unknown POU"):
        run_generate(
            cfg,
            level=1,
            ai_enabled=False,
            project_root=FIXTURE,
            scope="pou:DoesNotExist",
        )


def test_engine_scope_pou_reports_touched(tmp_path: Path) -> None:
    cfg = Config()
    cfg.scanner = ScannerConfig(active_configuration="Config1")
    cfg.output = OutputConfig(docs_dir=str(tmp_path / "docs"))

    run_generate(cfg, level=1, ai_enabled=False, project_root=FIXTURE, scope="all")
    graph = run_generate(
        cfg,
        level=1,
        ai_enabled=False,
        project_root=FIXTURE,
        scope="pou:MainProgram",
    )

    meta = getattr(graph, "_regen_meta", {})
    assert meta.get("scope") == "pou:MainProgram"
    assert meta.get("touched_pous") == ["MainProgram"]
    assert meta.get("fallback_full") is False


def test_mcp_regenerate_payload_includes_scope_metadata(monkeypatch) -> None:
    monkeypatch.setattr("as_docs.mcp_server.run_generate", lambda *args, **kwargs: _dummy_graph())

    cfg = Config()
    payload = regenerate_payload(cfg, scope="pou:MainProgram")

    assert payload["status"] == "ok"
    assert payload["data"]["scope"] == "pou:MainProgram"
    assert payload["data"]["touched_pous"] == ["MainProgram"]
    assert payload["data"]["changed_pous"] == 1


def test_cli_upgrade_pou_prints_scope_metadata(monkeypatch, tmp_path: Path) -> None:
    cfg_file = tmp_path / ".as-docs.yaml"
    cfg_file.write_text(
        """
project:
  name: "SampleProject"
ai:
  enabled: true
  provider: "copilot"
  model: "gpt-4.1"
output:
  docs_dir: "docs/as-docs"
""",
        encoding="utf-8",
    )

    monkeypatch.setattr("as_docs.engine.run_generate", lambda *args, **kwargs: _dummy_graph())

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["upgrade", "--to", "3", "--pou", "MainProgram", "--config", str(cfg_file)],
    )

    assert result.exit_code == 0
    assert "Scope: pou:MainProgram" in result.output
    assert "Touched POUs: MainProgram" in result.output
