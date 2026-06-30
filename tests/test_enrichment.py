from __future__ import annotations

from pathlib import Path

from as_docs.config import Config
from as_docs.enricher.ai_enricher import enrich_graph
from as_docs.engine import run_generate
from as_docs.model.graph import Edge, KnowledgeGraph, POUNode, TaskConfig, Variable


class DummyProvider:
    def __init__(self) -> None:
        self.task_calls = 0
        self.pou_calls = 0

    def enrich_task(self, prompt: str, model: str, max_tokens: int):
        self.task_calls += 1
        from as_docs.enricher.providers.base import EnrichmentPayload

        return EnrichmentPayload(
            description="Task summary",
            responsibilities=["Monitor", "Control"],
            patterns=["sequence control"],
            notes="",
        )

    def enrich_pou(self, prompt: str, model: str, max_tokens: int):
        self.pou_calls += 1
        from as_docs.enricher.providers.base import EnrichmentPayload

        return EnrichmentPayload(
            description="POU summary",
            responsibilities=["Read globals", "Write globals"],
            patterns=["state machine"],
            notes="Important note",
        )


def _graph(tmp_path: Path) -> KnowledgeGraph:
    pou_dir = tmp_path / "Logical" / "MainProgram"
    pou_dir.mkdir(parents=True)
    (pou_dir / "Main.st").write_text(
        "PROGRAM Main\ngMotorSpeed := 1.0;", encoding="utf-8"
    )
    (pou_dir / "MainProgram.prg").write_text(
        '<Object Name="MainProgram" />', encoding="utf-8"
    )

    return KnowledgeGraph(
        schema_version="1.0",
        project_name="X",
        as_version="4.10",
        generated_at="2026-01-01T00:00:00",
        level=3,
        active_configuration="Config1",
        pous={
            "MainProgram": POUNode(
                name="MainProgram",
                pou_type="PROGRAM",
                source_file=str(pou_dir / "MainProgram.prg"),
            )
        },
        tasks={
            "CyclicTask": TaskConfig(
                name="CyclicTask",
                task_type="cyclic",
                cycle_time_ms=10,
                programs=["MainProgram"],
            )
        },
        global_vars={
            "gMotorSpeed": Variable(
                name="gMotorSpeed",
                var_type="REAL",
                scope="GLOBAL",
                gvl_name="GVL_Main",
                initial_value="0.0",
            )
        },
        data_types={},
        edges=[
            Edge(source="CyclicTask", target="MainProgram", edge_type="OWNS"),
            Edge(source="MainProgram", target="gMotorSpeed", edge_type="READS"),
            Edge(source="MainProgram", target="gMotorSpeed", edge_type="WRITES"),
        ],
        flow_diagrams={},
    )


def _cfg(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.ai.provider = "copilot"
    cfg.ai.model = "gpt-4.1"
    cfg.ai.cache_dir = str(tmp_path / ".cache")
    cfg.ai.api_key_env = "GITHUB_TOKEN"
    return cfg


def test_enrichment_populates_task_and_pou(monkeypatch, tmp_path: Path) -> None:
    provider = DummyProvider()
    graph = _graph(tmp_path)
    cfg = _cfg(tmp_path)

    monkeypatch.setattr(
        "as_docs.enricher.ai_enricher.create_provider", lambda _cfg: provider
    )

    stats = enrich_graph(graph, level=3, config=cfg)

    assert graph.tasks["CyclicTask"].description == "Task summary"
    assert graph.pous["MainProgram"].description == "POU summary"
    assert graph.pous["MainProgram"].patterns == ["state machine"]
    assert stats.hits == 0
    assert stats.misses == 2
    assert provider.task_calls == 1
    assert provider.pou_calls == 1


def test_enrichment_uses_cache_on_second_run(monkeypatch, tmp_path: Path) -> None:
    provider = DummyProvider()
    graph = _graph(tmp_path)
    cfg = _cfg(tmp_path)

    monkeypatch.setattr(
        "as_docs.enricher.ai_enricher.create_provider", lambda _cfg: provider
    )

    first = enrich_graph(graph, level=3, config=cfg)
    second = enrich_graph(graph, level=3, config=cfg)

    assert first.misses == 2
    assert second.hits == 2
    assert provider.task_calls == 1
    assert provider.pou_calls == 1


def test_level3_generates_task_and_pou_markdown(monkeypatch, tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "SampleProject"

    provider = DummyProvider()
    monkeypatch.setattr(
        "as_docs.enricher.ai_enricher.create_provider", lambda _cfg: provider
    )

    cfg = Config()
    cfg.project.name = "SampleProject"
    cfg.scanner.active_configuration = "Config1"
    cfg.output.docs_dir = str(tmp_path / "docs")
    cfg.ai.cache_dir = str(tmp_path / ".cache")
    cfg.ai.provider = "copilot"
    cfg.ai.model = "gpt-4.1"

    graph = run_generate(cfg, level=3, ai_enabled=True, project_root=fixture)

    assert graph.level == 3
    assert (tmp_path / "docs" / "tasks" / "CyclicTask.md").exists()
    assert (tmp_path / "docs" / "pou" / "MainProgram.md").exists()
