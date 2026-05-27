from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from as_docs.cli import cli
from as_docs.model.graph import KnowledgeGraph


def _cfg_text() -> str:
    return """
project:
  name: "SampleProject"
ai:
  provider: "copilot"
  model: "gpt-4.1"
  api_base_url: "https://models.inference.ai.azure.com/chat/completions"
  api_key_env: "GITHUB_TOKEN"
output:
  docs_dir: "docs/as-docs"
"""


def _dummy_graph() -> KnowledgeGraph:
    graph = KnowledgeGraph(
        schema_version="1.0",
        project_name="SampleProject",
        as_version="4.10",
        generated_at="2026-01-01T00:00:00",
        level=2,
        active_configuration="Config1",
        pous={},
        tasks={},
        global_vars={},
        data_types={},
        edges=[],
        flow_diagrams={},
    )
    setattr(graph, "_ai_stats", type("Stats", (), {"hits": 3, "misses": 1, "writes": 1})())
    return graph


def test_generate_prints_provider_model_and_stats(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".as-docs.yaml"
    cfg.write_text(_cfg_text(), encoding="utf-8")

    monkeypatch.setattr("as_docs.engine.run_generate", lambda *args, **kwargs: _dummy_graph())

    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "--level", "2", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "provider: copilot" in result.output
    assert "model: gpt-4.1" in result.output
    assert "AI cache: hits=3, misses=1, writes=1" in result.output


def test_generate_no_ai_skips_ai_banner(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".as-docs.yaml"
    cfg.write_text(_cfg_text(), encoding="utf-8")

    monkeypatch.setattr("as_docs.engine.run_generate", lambda *args, **kwargs: _dummy_graph())

    runner = CliRunner()
    result = runner.invoke(cli, ["generate", "--no-ai", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "AI enrichment enabled" not in result.output
