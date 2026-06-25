"""Core engine — orchestrates scan → analyze → generate pipeline."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

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
    scope: str = "all",
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
    started = perf_counter()
    model = scan_project(config, project_root=project_root)
    target_pous = _resolve_scope_targets(config, model, scope)
    touched_pous = sorted(target_pous)

    # 2. Analyze + assemble graph
    if scope == "all":
        graph = _build_full_graph(model, config=config, level=level)
    else:
        graph = _build_scoped_graph(
            config=config,
            model=model,
            level=level,
            scope=scope,
            target_pous=target_pous,
        )
        touched_pous = sorted(set(touched_pous).intersection(set(graph.pous.keys())))

    # 5. AI enrichment (Level 2+)
    if ai_enabled and level >= 2:
        from as_docs.enricher.ai_enricher import enrich_graph
        ai_stats = enrich_graph(graph, level=level, config=config)
        setattr(graph, "_ai_stats", ai_stats)

    # 6. Generate outputs
    output_dir = Path(config.output.docs_dir)
    generate_json(graph, output_dir)
    generate_all_markdown(graph, output_dir)
    generate_llms_txt(graph, output_dir)

    setattr(
        graph,
        "_regen_meta",
        {
            "scope": scope,
            "touched_pous": touched_pous,
            "elapsed_seconds": round(perf_counter() - started, 3),
            "scanned_pous": len(model.pous),
            "fallback_full": bool(getattr(graph, "_scoped_fallback_full", False)),
        },
    )

    return graph


def _resolve_scope_targets(config: Config, model: ProjectModel, scope: str) -> set[str]:
    if scope == "all":
        return set(model.pous.keys())

    if scope.startswith("pou:"):
        pou_name = scope.split(":", 1)[1].strip()
        if not pou_name:
            raise ValueError("Invalid scope 'pou:'. Use 'pou:<name>'.")
        if pou_name not in model.pous:
            raise ValueError(f"Unknown POU in scope: {pou_name}")
        return {pou_name}

    if scope == "changed":
        stale = get_staleness(config, project_root=model.project_root)
        return {
            pou_name
            for pou_name, state in stale.items()
            if state in {"stale", "missing"} and pou_name in model.pous
        }

    raise ValueError("Invalid scope. Use one of: all, changed, pou:<name>.")


def _build_full_graph(model: ProjectModel, config: Config, level: int) -> KnowledgeGraph:
    known_pous = set(model.pous.keys())
    known_vars = set(model.global_vars.keys())
    ext_prefixes = config.scanner.external_lib_prefixes

    analysis_results: list[STAnalysisResult] = []
    for st_file in model.st_files:
        result = analyze_st(st_file, known_pous, known_vars, ext_prefixes)
        analysis_results.append(result)

        pou = model.pous.get(st_file.pou_name)
        if pou and result.instances:
            pou.instances = result.instances

    edges = build_edges(model, analysis_results)

    return KnowledgeGraph(
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


def _build_scoped_graph(
    config: Config,
    model: ProjectModel,
    level: int,
    scope: str,
    target_pous: set[str],
) -> KnowledgeGraph:
    prev = load_graph(config)
    if prev is None:
        graph = _build_full_graph(model, config=config, level=level)
        setattr(graph, "_scoped_fallback_full", True)
        return graph

    prev.project_name = model.project_name
    prev.as_version = model.as_version
    prev.active_configuration = model.active_configuration
    prev.generated_at = datetime.now(timezone.utc).isoformat()
    prev.level = level
    prev.tasks = model.tasks
    prev.global_vars = model.global_vars
    prev.data_types = model.data_types

    # changed scope can resolve to no stale files; keep previous graph content.
    if not target_pous and scope == "changed":
        return prev

    known_pous = set(model.pous.keys())
    known_vars = set(model.global_vars.keys())
    ext_prefixes = config.scanner.external_lib_prefixes
    scoped_analysis: list[STAnalysisResult] = []
    for st_file in model.st_files:
        if st_file.pou_name not in target_pous:
            continue
        result = analyze_st(st_file, known_pous, known_vars, ext_prefixes)
        scoped_analysis.append(result)

        pou = model.pous.get(st_file.pou_name)
        if pou and result.instances:
            pou.instances = result.instances

    for pou_name in target_pous:
        if pou_name in model.pous:
            prev.pous[pou_name] = model.pous[pou_name]

    scoped_edges = build_edges(model, scoped_analysis)
    prev.edges = _merge_scoped_edges(prev.edges, scoped_edges, target_pous)

    return prev


def _merge_scoped_edges(
    existing_edges: list[Edge],
    scoped_edges: list[Edge],
    target_pous: set[str],
) -> list[Edge]:
    kept = [
        e
        for e in existing_edges
        if e.source not in target_pous
        and not (e.edge_type in {"CALLS", "INSTANCE_OF"} and e.target in target_pous)
    ]

    merged = kept + scoped_edges
    dedup: dict[tuple[str, str, str], Edge] = {}
    for edge in merged:
        dedup[(edge.source, edge.target, edge.edge_type)] = edge
    return list(dedup.values())


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
