"""Core engine — orchestrates scan → analyze → generate pipeline."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import logging
from typing import TYPE_CHECKING

from as_docs.config import Config
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
from as_docs.generator.flow_diagram_gen import build_flow_diagram
from as_docs.generator.markdown_gen import generate_all_markdown
from as_docs.generator.llms_txt_gen import generate_llms_txt
from as_docs.scanner.as_cli_adapter import AsCliAdapter, AsCliError
from as_docs.scanner.data_conflict_resolver import DataConflictResolver

if TYPE_CHECKING:
    from as_docs.scanner.data_conflict_resolver import ConflictReport

logger = logging.getLogger(__name__)


def run_generate(
    config: Config,
    level: int = 1,
    ai_enabled: bool = False,
    project_root: Path | None = None,
    scope: str = "all",
    use_as_cli: bool | None = None,
) -> KnowledgeGraph:
    """Run the full scan → analyze → generate pipeline.

    Args:
        config: Loaded project config.
        level: Documentation level (1–4).
        ai_enabled: If True and level >= 2, call Claude API for enrichment.
        project_root: Override project root detection.
        scope: Scope for regeneration (all, changed, pou:<name>).
        use_as_cli: Override config to use as-cli for project discovery.
                    Precedence: CLI flag > config setting > default (False).

    Returns:
        The assembled KnowledgeGraph.
    """
    # 1. Scan (filesystem, optionally merged with as-cli)
    started = perf_counter()
    model = scan_project(config, project_root=project_root)
    
    # 2. Optional as-cli integration
    conflict_report = None
    if _should_use_as_cli(use_as_cli, config):
        conflict_report = _merge_as_cli_data(model, config, project_root)
    
    target_pous = _resolve_scope_targets(config, model, scope)
    touched_pous = sorted(target_pous)

    # 3. Analyze + assemble graph
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

    # 4. AI enrichment (Level 2+)
    if ai_enabled and level >= 2:
        from as_docs.enricher.ai_enricher import enrich_graph
        ai_stats = enrich_graph(graph, level=level, config=config, project_root=project_root)
        setattr(graph, "_ai_stats", ai_stats)

    if level >= 4:
        _populate_flow_diagrams(graph, model, ai_enabled=ai_enabled, scope=scope, target_pous=target_pous)

    # 5. Generate outputs (honor configured output.formats)
    output_dir = Path(config.output.docs_dir)
    configured_formats = {f.strip().lower() for f in config.output.formats if str(f).strip()}
    if not configured_formats:
        configured_formats = {"markdown", "json", "llms.txt"}

    if "json" in configured_formats:
        generate_json(graph, output_dir)
    if "markdown" in configured_formats:
        generate_all_markdown(graph, output_dir)
    if "llms.txt" in configured_formats or "llms" in configured_formats:
        generate_llms_txt(graph, output_dir)

    # 6. Write POU hash files for freshness tracking (if not already done)
    if level < 3 or not ai_enabled:
        from as_docs.enricher.ai_enricher import _write_pou_hashes
        _write_pou_hashes(graph, config, project_root)

    # 7. Save conflict report if as-cli was used
    if conflict_report is not None:
        _save_conflict_report(conflict_report, output_dir)

    setattr(
        graph,
        "_regen_meta",
        {
            "scope": scope,
            "touched_pous": touched_pous,
            "elapsed_seconds": round(perf_counter() - started, 3),
            "scanned_pous": len(model.pous),
            "fallback_full": bool(getattr(graph, "_scoped_fallback_full", False)),
            "as_cli_merge_report": conflict_report.to_dict() if conflict_report else None,
        },
    )

    return graph


def _should_use_as_cli(cli_flag: bool | None, config: Config) -> bool:
    """Determine if as-cli should be used (precedence: CLI > config > default).
    
    Args:
        cli_flag: CLI override (--use-as-cli)
        config: Loaded configuration
    
    Returns:
        True if as-cli should be used
    """
    if cli_flag is not None:
        return cli_flag
    return config.as_cli.enabled


def _merge_as_cli_data(model: ProjectModel, config: Config, project_root: Path | None) -> ConflictReport | None:
    """Attempt to merge as-cli data with filesystem scanner results.
    
    Args:
        model: ProjectModel from filesystem scanner
        config: Loaded configuration
        project_root: Project root path
    
    Returns:
        ConflictReport if merge was successful, None if fallback only (graceful)
    """
    logger.info("Attempting as-cli integration...")
    
    try:
        # Initialize adapter
        adapter = AsCliAdapter(
            as_cli_path=config.as_cli.path,
            project_path=str(project_root or "."),
            timeout_ms=config.as_cli.timeout_ms
        )
        
        # Check availability
        if not adapter.is_available():
            raise AsCliError("as-cli is not available (not found or not installed)")
        
        # Scan project with as-cli
        logger.debug("Scanning project with as-cli...")
        as_cli_data = adapter.scan_project()
        
        # Merge with filesystem data
        resolver = DataConflictResolver()
        merged_pous, conflict_report = resolver.merge(model.pous, as_cli_data)
        
        # Update model with merged data
        model.pous = merged_pous
        
        logger.info(f"as-cli merge complete: {conflict_report.pou_count_merged} POUs, "
                   f"{len(conflict_report.conflicts)} conflicts")
        
        return conflict_report
    
    except AsCliError as e:
        # Graceful fallback
        if config.as_cli.strict:
            logger.error(f"as-cli integration failed (strict mode): {e}")
            raise
        
        logger.warning(f"as-cli integration failed, falling back to filesystem: {e}")
        return None
    
    except Exception as e:
        # Unexpected error
        if config.as_cli.strict:
            logger.error(f"Unexpected error in as-cli integration (strict mode): {e}")
            raise
        
        logger.warning(f"Unexpected error in as-cli integration, falling back: {e}")
        return None


def _save_conflict_report(conflict_report: ConflictReport, output_dir: Path) -> None:
    """Save conflict report to output directory.
    
    Args:
        conflict_report: ConflictReport to save
        output_dir: Output directory path
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_file = output_dir / "as_cli_conflict_report.json"
        
        with report_file.open("w", encoding="utf-8") as f:
            f.write(conflict_report.to_json())
        
        logger.info(f"Conflict report saved to {report_file}")
    
    except Exception as e:
        logger.warning(f"Failed to save conflict report: {e}")


def _resolve_scope_targets(config: Config, model: ProjectModel, scope: str) -> set[str]:
    """Resolve target POUs for the given scope.
    
    Args:
        config: Loaded configuration
        model: ProjectModel to resolve targets from
        scope: Scope specification (all, changed, pou:<name>)
    
    Returns:
        Set of target POU names
    """
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


def _populate_flow_diagrams(
    graph: KnowledgeGraph,
    model: ProjectModel,
    *,
    ai_enabled: bool,
    scope: str,
    target_pous: set[str],
) -> None:
    st_sources: dict[str, str] = {}
    for st_file in model.st_files:
        st_sources[st_file.pou_name] = st_file.source
        st_sources[st_file.path.parent.name] = st_file.source
        st_sources[st_file.path.stem] = st_file.source
    pou_names = target_pous if scope != "all" else set(graph.pous.keys())

    if scope == "changed" and not pou_names:
        pou_names = set(graph.flow_diagrams.keys()) or set(graph.pous.keys())

    if scope != "all" and graph.flow_diagrams:
        next_flow_diagrams = dict(graph.flow_diagrams)
    else:
        next_flow_diagrams = {}

    for pou_name in sorted(pou_names):
        pou = graph.pous.get(pou_name)
        source = st_sources.get(pou_name)
        if pou is None or source is None or pou.is_external_library:
            continue

        narrative_hint = pou.description if ai_enabled else ""
        diagram = build_flow_diagram(pou_name, source, ai_enabled=ai_enabled, narrative_hint=narrative_hint)
        if diagram is not None:
            next_flow_diagrams[pou_name] = diagram

    graph.flow_diagrams = next_flow_diagrams


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
