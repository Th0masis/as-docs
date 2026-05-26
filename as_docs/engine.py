"""Core engine — orchestrates scan → analyze → generate pipeline."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from as_docs.config import Config, load_config
from as_docs.model.graph import (
    SCHEMA_VERSION,
    Edge,
    KnowledgeGraph,
)
from as_docs.model.project import ProjectModel
from as_docs.scanner.project_scanner import scan_project
from as_docs.analyzer.st_analyzer import analyze_st, STAnalysisResult
from as_docs.analyzer.call_graph import build_edges
from as_docs.generator.json_gen import generate_json
from as_docs.generator.markdown_gen import generate_all_markdown
from as_docs.generator.llms_txt_gen import generate_llms_txt


def run_generate(
    config: Config,
    level: int = 1,
    ai_enabled: bool = False,
    project_root: Path | None = None,
) -> KnowledgeGraph:
    """Run the full scan → analyze → generate pipeline.

    Args:
        config: Loaded project config.
        level: Documentation level (1–4).
        ai_enabled: If True and level >= 2, call Claude API for enrichment.
        project_root: Override project root detection.

    Returns:
        The assembled KnowledgeGraph.
    """
    # 1. Scan
    model = scan_project(config, project_root=project_root)

    # 2. Analyze ST files
    known_pous = set(model.pous.keys())
    known_vars = set(model.global_vars.keys())
    ext_prefixes = config.scanner.external_lib_prefixes

    analysis_results: list[STAnalysisResult] = []
    for st_file in model.st_files:
        result = analyze_st(st_file, known_pous, known_vars, ext_prefixes)
        analysis_results.append(result)

        # Backfill instances into POUNode
        pou = model.pous.get(st_file.pou_name)
        if pou and result.instances:
            pou.instances = result.instances

    # 3. Build edges
    edges = build_edges(model, analysis_results)
    model.edges = edges

    # 4. Assemble KnowledgeGraph
    graph = KnowledgeGraph(
        schema_version=SCHEMA_VERSION,
        project_name=model.project_name,
        as_version=model.as_version,
        generated_at=datetime.now(timezone.utc).isoformat(),
        level=level,
        active_configuration=model.active_configuration,
        pous=model.pous,
        tasks=model.tasks,
        global_vars=model.global_vars,
        data_types=model.data_types,
        edges=edges,
        flow_diagrams={},
    )

    # 5. AI enrichment (Level 2+)
    if ai_enabled and level >= 2:
        from as_docs.enricher.ai_enricher import enrich_graph
        enrich_graph(graph, level=level, config=config)

    # 6. Generate outputs
    output_dir = Path(config.output.docs_dir)
    generate_json(graph, output_dir)
    generate_all_markdown(graph, output_dir)
    generate_llms_txt(graph, output_dir)

    return graph


def load_graph(config: Config) -> KnowledgeGraph | None:
    """Load an existing knowledge_graph.json. Returns None if not found."""
    import json
    graph_file = Path(config.output.docs_dir) / "knowledge_graph.json"
    if not graph_file.exists():
        return None

    with graph_file.open(encoding="utf-8") as fh:
        data = json.load(fh)

    # Schema version check
    if data.get("schema_version") != SCHEMA_VERSION:
        return None  # Force regeneration on mismatch

    return _dict_to_graph(data)


def get_staleness(config: Config, project_root: Path | None = None) -> dict[str, str]:
    """Return a dict of pou_name → staleness status (fresh/stale/missing)."""
    import hashlib
    cache_dir = Path(config.ai.cache_dir)

    if project_root is None:
        from as_docs.config import find_project_root
        project_root = find_project_root() or Path(".")

    logical = project_root / "Logical"
    status: dict[str, str] = {}

    for st_file in logical.rglob("*.st"):
        if any(part in config.scanner.ignore_dirs for part in st_file.parts):
            continue
        pou_name = st_file.parent.name
        content_hash = hashlib.sha256(st_file.read_bytes()).hexdigest()
        cache_file = cache_dir / f"{pou_name}.hash"
        if not cache_file.exists():
            status[pou_name] = "missing"
        elif cache_file.read_text().strip() != content_hash:
            status[pou_name] = "stale"
        else:
            status[pou_name] = "fresh"

    return status


def _dict_to_graph(data: dict) -> KnowledgeGraph:
    """Reconstruct KnowledgeGraph from JSON dict (shallow — for MCP use)."""
    from as_docs.model.graph import (
        DataType, DataTypeMember, Edge, FlowDiagram, POUNode, TaskConfig, Variable,
    )

    def _var(d: dict) -> Variable:
        return Variable(**d)

    def _pou(d: dict) -> POUNode:
        d = dict(d)
        d["local_vars"] = [_var(v) for v in d.get("local_vars", [])]
        return POUNode(**d)

    def _task(d: dict) -> TaskConfig:
        return TaskConfig(**d)

    def _dt(d: dict) -> DataType:
        d = dict(d)
        d["members"] = [DataTypeMember(**m) for m in d.get("members", [])]
        return DataType(**d)

    def _edge(d: dict) -> Edge:
        return Edge(**d)

    def _flow(d: dict) -> FlowDiagram:
        return FlowDiagram(**d)

    return KnowledgeGraph(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        project_name=data.get("project_name", ""),
        as_version=data.get("as_version", ""),
        generated_at=data.get("generated_at", ""),
        level=data.get("level", 1),
        active_configuration=data.get("active_configuration", ""),
        pous={k: _pou(v) for k, v in data.get("pous", {}).items()},
        tasks={k: _task(v) for k, v in data.get("tasks", {}).items()},
        global_vars={k: _var(v) for k, v in data.get("global_vars", {}).items()},
        data_types={k: _dt(v) for k, v in data.get("data_types", {}).items()},
        edges=[_edge(e) for e in data.get("edges", [])],
        flow_diagrams={k: _flow(v) for k, v in data.get("flow_diagrams", {}).items()},
    )
