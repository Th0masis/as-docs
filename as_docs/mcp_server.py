"""MCP server for querying and operating on generated AS docs."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from as_docs.config import Config
from as_docs.engine import get_staleness, load_graph, run_generate
from as_docs.generator.diagram_gen import generate_data_flow_diagram
from as_docs.model.graph import KnowledgeGraph


def _meta(graph: KnowledgeGraph) -> dict[str, Any]:
    return {
        "level": graph.level,
        "active_configuration": graph.active_configuration,
        "generated_at": graph.generated_at,
    }


def _partial_or_ok(
    graph: KnowledgeGraph,
    *,
    requested_level: int,
    data: dict[str, Any],
    hint: str,
) -> dict[str, Any]:
    status = "ok" if graph.level >= requested_level else "partial"
    payload: dict[str, Any] = {
        "status": status,
        **_meta(graph),
        "data": data,
    }
    if status == "partial":
        payload["available_level"] = graph.level
        payload["requested_level"] = requested_level
        payload["hint"] = hint
    return payload


def _load_graph_required(config: Config) -> KnowledgeGraph:
    graph = load_graph(config)
    if graph is None:
        raise RuntimeError(
            "No generated docs found. Run 'as-docs generate --no-ai' first."
        )
    return graph


def _task_program_map(graph: KnowledgeGraph) -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {
        name: set(task.programs) for name, task in graph.tasks.items()
    }
    for edge in graph.edges:
        if edge.edge_type == "OWNS":
            mapping.setdefault(edge.source, set()).add(edge.target)
    return mapping


def _task_closure(graph: KnowledgeGraph, programs: set[str]) -> set[str]:
    closure = set(programs)
    queue = list(programs)
    while queue:
        current = queue.pop(0)
        for edge in graph.edges:
            if edge.edge_type != "CALLS" or edge.source != current:
                continue
            if edge.target in closure:
                continue
            closure.add(edge.target)
            queue.append(edge.target)
    return closure


def _tasks_for_pou(graph: KnowledgeGraph, pou_name: str) -> list[str]:
    owners: list[str] = []
    for task_name, task in graph.tasks.items():
        closure = _task_closure(graph, set(task.programs))
        if pou_name in closure:
            owners.append(task_name)
    return sorted(owners)


def get_task_payload(
    graph: KnowledgeGraph,
    name: str,
    requested_level: int = 2,
) -> dict[str, Any]:
    task = graph.tasks.get(name)
    if task is None:
        return {
            "status": "not_found",
            **_meta(graph),
            "message": f"Unknown task: {name}",
        }

    programs = set(task.programs)
    closure = _task_closure(graph, programs)
    reads = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "READS"
        and e.source in closure
        and e.target in graph.global_vars
    )
    writes = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "WRITES"
        and e.source in closure
        and e.target in graph.global_vars
    )

    data = {
        "name": task.name,
        "task_type": task.task_type,
        "cycle_time_ms": task.cycle_time_ms,
        "programs": sorted(programs),
        "description": task.description,
        "responsibilities": list(task.responsibilities),
        "reads": reads,
        "writes": writes,
    }

    return _partial_or_ok(
        graph,
        requested_level=requested_level,
        data=data,
        hint=f"Run: as-docs upgrade --to {requested_level}",
    )


def get_overview_payload(graph: KnowledgeGraph) -> dict[str, Any]:
    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "project_name": graph.project_name,
            "as_version": graph.as_version,
            "tasks": sorted(graph.tasks.keys()),
            "task_count": len(graph.tasks),
            "pou_count": len(graph.pous),
            "global_var_count": len(graph.global_vars),
            "data_type_count": len(graph.data_types),
        },
    }


def get_pou_list_payload(graph: KnowledgeGraph) -> dict[str, Any]:
    pous = [
        {
            "name": pou.name,
            "pou_type": pou.pou_type,
            "source_file": pou.source_file,
            "description": pou.description,
            "is_external_library": pou.is_external_library,
        }
        for pou in graph.pous.values()
    ]
    pous.sort(key=lambda item: item["name"])
    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "pous": pous,
        },
    }


def get_pou_payload(
    graph: KnowledgeGraph,
    name: str,
    requested_level: int = 3,
) -> dict[str, Any]:
    pou = graph.pous.get(name)
    if pou is None:
        return {
            "status": "not_found",
            **_meta(graph),
            "message": f"Unknown POU: {name}",
        }

    callers = sorted(
        e.source for e in graph.edges if e.edge_type == "CALLS" and e.target == name
    )
    callees = sorted(
        e.target for e in graph.edges if e.edge_type == "CALLS" and e.source == name
    )
    reads = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "READS" and e.source == name and e.target in graph.global_vars
    )
    writes = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "WRITES"
        and e.source == name
        and e.target in graph.global_vars
    )

    data = {
        "name": pou.name,
        "pou_type": pou.pou_type,
        "source_file": pou.source_file,
        "description": pou.description,
        "responsibilities": list(pou.responsibilities),
        "patterns": list(pou.patterns),
        "notes": pou.notes,
        "tasks": _tasks_for_pou(graph, name),
        "callers": callers,
        "callees": callees,
        "reads": reads,
        "writes": writes,
        "is_external_library": pou.is_external_library,
    }

    return _partial_or_ok(
        graph,
        requested_level=requested_level,
        data=data,
        hint=f"Run: as-docs upgrade --to {requested_level} --pou {name}",
    )


def find_variable_payload(graph: KnowledgeGraph, name: str) -> dict[str, Any]:
    var = graph.global_vars.get(name)
    if var is None:
        return {
            "status": "not_found",
            **_meta(graph),
            "message": f"Unknown variable: {name}",
        }

    readers = sorted(
        {e.source for e in graph.edges if e.edge_type == "READS" and e.target == name}
    )
    writers = sorted(
        {e.source for e in graph.edges if e.edge_type == "WRITES" and e.target == name}
    )

    owners: set[str] = set()
    for pou_name in set(readers + writers):
        owners.update(_tasks_for_pou(graph, pou_name))

    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "variable": asdict(var),
            "readers": readers,
            "writers": writers,
            "tasks": sorted(owners),
        },
    }


def get_global_vars_payload(
    graph: KnowledgeGraph, gvl: str | None = None
) -> dict[str, Any]:
    items: dict[str, list[dict[str, Any]]] = {}
    for var in graph.global_vars.values():
        group = var.gvl_name or "(ungrouped)"
        if gvl and group != gvl:
            continue
        items.setdefault(group, []).append(asdict(var))

    for vars_ in items.values():
        vars_.sort(key=lambda entry: str(entry.get("name", "")))

    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "gvl": gvl,
            "global_vars": items,
        },
    }


def get_call_graph_payload(
    graph: KnowledgeGraph, root: str | None = None
) -> dict[str, Any]:
    calls = [(e.source, e.target) for e in graph.edges if e.edge_type == "CALLS"]
    adjacency: dict[str, list[str]] = {}
    for src, tgt in calls:
        adjacency.setdefault(src, []).append(tgt)
    for src in list(adjacency.keys()):
        adjacency[src] = sorted(set(adjacency[src]))

    if root:
        visited = {root}
        queue = [root]
        filtered: list[tuple[str, str]] = []
        while queue:
            current = queue.pop(0)
            for nxt in adjacency.get(current, []):
                filtered.append((current, nxt))
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        calls = filtered

    lines = ["graph TD"]
    for src, tgt in calls:
        lines.append(f"    {src} --> {tgt}")

    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "root": root,
            "edges": [{"source": src, "target": tgt} for src, tgt in calls],
            "mermaid": "\n".join(lines),
        },
    }


def get_data_flow_payload(
    graph: KnowledgeGraph, requested_level: int = 2
) -> dict[str, Any]:
    task_programs = _task_program_map(graph)
    task_closures = {
        task_name: _task_closure(graph, programs)
        for task_name, programs in task_programs.items()
    }

    readers: dict[str, set[str]] = {}
    writers: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.edge_type == "READS" and edge.target in graph.global_vars:
            readers.setdefault(edge.target, set()).add(edge.source)
        if edge.edge_type == "WRITES" and edge.target in graph.global_vars:
            writers.setdefault(edge.target, set()).add(edge.source)

    couplings: list[dict[str, Any]] = []
    task_names = sorted(graph.tasks.keys())
    for i, task_a in enumerate(task_names):
        for task_b in task_names[i + 1 :]:
            shared: set[str] = set()
            closure_a = task_closures.get(task_a, set())
            closure_b = task_closures.get(task_b, set())
            for var_name in graph.global_vars:
                touched_a = bool(
                    (readers.get(var_name, set()) | writers.get(var_name, set()))
                    & closure_a
                )
                touched_b = bool(
                    (readers.get(var_name, set()) | writers.get(var_name, set()))
                    & closure_b
                )
                if touched_a and touched_b:
                    shared.add(var_name)
            if shared:
                couplings.append(
                    {
                        "task_a": task_a,
                        "task_b": task_b,
                        "shared_variables": sorted(shared),
                    }
                )

    data = {
        "couplings": couplings,
        "mermaid": generate_data_flow_diagram(graph),
    }
    return _partial_or_ok(
        graph,
        requested_level=requested_level,
        data=data,
        hint=f"Run: as-docs upgrade --to {requested_level}",
    )


def get_flow_diagram_payload(
    graph: KnowledgeGraph, name: str, requested_level: int = 4
) -> dict[str, Any]:
    diagram = graph.flow_diagrams.get(name)
    if diagram is None:
        response = _partial_or_ok(
            graph,
            requested_level=requested_level,
            data={"flow_diagram": None, "pou": name},
            hint=f"Run: as-docs upgrade --to {requested_level} --pou {name}",
        )
        if response["status"] == "ok":
            response["status"] = "not_found"
            response["message"] = f"No Level 4 flow diagram found for POU: {name}"
        return response

    return _partial_or_ok(
        graph,
        requested_level=requested_level,
        data={"flow_diagram": asdict(diagram)},
        hint=f"Run: as-docs upgrade --to {requested_level} --pou {name}",
    )


def search_payload(graph: KnowledgeGraph, query: str) -> dict[str, Any]:
    q = query.lower().strip()
    if not q:
        return {"status": "ok", **_meta(graph), "data": {"query": query, "results": []}}

    results: list[dict[str, Any]] = []

    for pou in graph.pous.values():
        haystacks = [pou.name, pou.description, pou.notes, " ".join(pou.patterns)]
        if any(q in (h or "").lower() for h in haystacks):
            results.append({"kind": "pou", "name": pou.name, "type": pou.pou_type})

    for task in graph.tasks.values():
        haystacks = [task.name, task.description, " ".join(task.responsibilities)]
        if any(q in (h or "").lower() for h in haystacks):
            results.append({"kind": "task", "name": task.name, "type": task.task_type})

    for var in graph.global_vars.values():
        haystacks = [var.name, var.var_type, var.description, var.gvl_name or ""]
        if any(q in (h or "").lower() for h in haystacks):
            results.append({"kind": "variable", "name": var.name, "type": var.var_type})

    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "query": query,
            "results": sorted(results, key=lambda item: (item["kind"], item["name"])),
        },
    }


def regenerate_payload(config: Config, scope: str = "all") -> dict[str, Any]:
    valid_prefix = "pou:"
    if scope != "all" and scope != "changed" and not scope.startswith(valid_prefix):
        raise ValueError("Invalid scope. Use one of: all, changed, pou:{name}.")

    prev = load_graph(config)
    target_level = prev.level if prev else config.output.default_level
    ai_enabled = bool(config.ai.enabled and target_level >= 2)

    graph = run_generate(config, level=target_level, ai_enabled=ai_enabled, scope=scope)
    stats = getattr(graph, "_ai_stats", None)
    meta = getattr(graph, "_regen_meta", {})
    touched = list(meta.get("touched_pous", []))

    response = {
        "status": "ok",
        **_meta(graph),
        "data": {
            "scope": meta.get("scope", scope),
            "scanned_pous": int(meta.get("scanned_pous", len(graph.pous))),
            "changed_pous": len(touched),
            "touched_pous": touched,
            "elapsed_seconds": float(meta.get("elapsed_seconds", 0.0)),
            "ai_calls": int(getattr(stats, "misses", 0)) if stats is not None else 0,
            "cache_hits": int(getattr(stats, "hits", 0)) if stats is not None else 0,
        },
    }

    if meta.get("fallback_full"):
        response["warning"] = (
            "No prior graph found for scoped operation; executed a full baseline regeneration."
        )

    return response


def get_cache_status_payload(config: Config) -> dict[str, Any]:
    graph = _load_graph_required(config)
    staleness = get_staleness(config)
    cache_dir = Path(config.ai.cache_dir)

    entries: list[dict[str, Any]] = []
    for pou_name in sorted(graph.pous.keys()):
        cache_file = cache_dir / f"{pou_name}.hash"
        entries.append(
            {
                "pou": pou_name,
                "cached": cache_file.exists(),
                "status": staleness.get(pou_name, "missing"),
                "cached_level": graph.level if cache_file.exists() else None,
            }
        )

    return {
        "status": "ok",
        **_meta(graph),
        "data": {
            "cache_dir": str(cache_dir),
            "entries": entries,
        },
    }


def upgrade_payload(
    config: Config, to_level: int, pou: str | None = None
) -> dict[str, Any]:
    if to_level < 1 or to_level > 4:
        raise ValueError("Target level must be between 1 and 4.")

    ai_enabled = bool(config.ai.enabled and to_level >= 2)
    scope = f"pou:{pou}" if pou else "all"
    graph = run_generate(config, level=to_level, ai_enabled=ai_enabled, scope=scope)
    meta = getattr(graph, "_regen_meta", {})

    response = {
        "status": "ok",
        **_meta(graph),
        "data": {
            "target_level": to_level,
            "scope": meta.get("scope", scope),
            "touched_pous": list(meta.get("touched_pous", [])),
            "elapsed_seconds": float(meta.get("elapsed_seconds", 0.0)),
            "upgraded": True,
        },
    }

    if meta.get("fallback_full"):
        response["warning"] = (
            "No prior graph found for scoped upgrade; executed a full baseline regeneration."
        )

    return response


def _register_tool(server: Any, fn: Any, *, name: str, description: str) -> None:
    if hasattr(server, "tool"):
        tool_attr = server.tool
        # FastMCP supports decorator style. Keep this tolerant to minor API variants.
        for kwargs in (
            {"name": name, "description": description},
            {"name": name},
            {},
        ):
            try:
                decorator = tool_attr(**kwargs)
                decorator(fn)
                return
            except TypeError:
                continue

    if hasattr(server, "add_tool"):
        add_tool = server.add_tool
        for kwargs in (
            {"name": name, "description": description},
            {"name": name},
            {},
        ):
            try:
                add_tool(fn, **kwargs)
                return
            except TypeError:
                continue

    raise RuntimeError("Unsupported FastMCP API: could not register MCP tools.")


def _run_server(server: Any, config: Config, *, use_http: bool, port: int) -> None:
    if use_http:
        host = config.server.host or "127.0.0.1"
        resolved_port = int(port or config.server.port)

        if hasattr(server, "run"):
            run_method = server.run
            for kwargs in (
                {"transport": "http", "host": host, "port": resolved_port},
                {"transport": "streamable-http", "host": host, "port": resolved_port},
                {"host": host, "port": resolved_port},
            ):
                try:
                    run_method(**kwargs)
                    return
                except TypeError:
                    continue

        if hasattr(server, "run_http"):
            server.run_http(host=host, port=resolved_port)
            return

        raise RuntimeError("Unsupported FastMCP API: HTTP transport is unavailable.")

    if hasattr(server, "run"):
        run_method = server.run
        for kwargs in ({"transport": "stdio"}, {}):
            try:
                run_method(**kwargs)
                return
            except TypeError:
                continue

    raise RuntimeError("Unsupported FastMCP API: stdio transport is unavailable.")


def start_server(config: Config, use_http: bool = False, port: int = 8765) -> None:
    try:
        from fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP server dependencies are missing. Install with: pip install as-docs[mcp]"
        ) from exc

    server = FastMCP("as-docs")

    def _graph() -> KnowledgeGraph:
        return _load_graph_required(config)

    def get_task(name: str, requested_level: int = 2) -> dict[str, Any]:
        """Return full task information at the highest available level."""

        return get_task_payload(_graph(), name=name, requested_level=requested_level)

    def get_overview() -> dict[str, Any]:
        """Return project-level summary and generation metadata."""

        return get_overview_payload(_graph())

    def get_pou_list() -> dict[str, Any]:
        """Return all POUs with type, source, and short description."""

        return get_pou_list_payload(_graph())

    def get_pou(name: str, requested_level: int = 3) -> dict[str, Any]:
        """Return full POU information at the highest available level."""

        return get_pou_payload(_graph(), name=name, requested_level=requested_level)

    def find_variable(name: str) -> dict[str, Any]:
        """Find all POUs and tasks that read or write a global variable."""

        return find_variable_payload(_graph(), name=name)

    def get_data_flow(requested_level: int = 2) -> dict[str, Any]:
        """Return cross-task coupling summary and Mermaid data-flow diagram."""

        return get_data_flow_payload(_graph(), requested_level=requested_level)

    def get_call_graph(root: str | None = None) -> dict[str, Any]:
        """Return call hierarchy edges and Mermaid graph."""

        return get_call_graph_payload(_graph(), root=root)

    def get_global_vars(gvl: str | None = None) -> dict[str, Any]:
        """Return global variables grouped by GVL, optionally filtered."""

        return get_global_vars_payload(_graph(), gvl=gvl)

    def search(query: str) -> dict[str, Any]:
        """Text search across tasks, POUs, patterns, and global variables."""

        return search_payload(_graph(), query=query)

    def get_flow_diagram(name: str, requested_level: int = 4) -> dict[str, Any]:
        """Return Level 4 flow diagram for a POU when available."""

        return get_flow_diagram_payload(
            _graph(), name=name, requested_level=requested_level
        )

    def regenerate(scope: str = "all") -> dict[str, Any]:
        """Regenerate docs for all/changed/single-POU scope."""

        return regenerate_payload(config, scope=scope)

    def get_cache_status() -> dict[str, Any]:
        """Return cache freshness per POU."""

        return get_cache_status_payload(config)

    def upgrade(to_level: int, pou: str | None = None) -> dict[str, Any]:
        """Upgrade docs to a higher level for all POUs or a single POU."""

        return upgrade_payload(config, to_level=to_level, pou=pou)

    tool_specs = [
        (
            get_overview,
            "get_overview",
            "Return project summary and generation metadata.",
        ),
        (get_pou_list, "get_pou_list", "Return all POUs with basic metadata."),
        (get_task, "get_task", "Return full task documentation."),
        (get_pou, "get_pou", "Return full POU documentation."),
        (
            find_variable,
            "find_variable",
            "Find all readers/writers of a global variable.",
        ),
        (
            get_data_flow,
            "get_data_flow",
            "Return cross-task coupling data and diagram.",
        ),
        (
            get_call_graph,
            "get_call_graph",
            "Return call hierarchy from root or whole project.",
        ),
        (get_global_vars, "get_global_vars", "Return global variables grouped by GVL."),
        (search, "search", "Text search across knowledge graph entities."),
        (
            get_flow_diagram,
            "get_flow_diagram",
            "Return Level 4 flow diagram for a POU.",
        ),
        (regenerate, "regenerate", "Regenerate docs for all/changed/single-POU scope."),
        (get_cache_status, "get_cache_status", "Return cache freshness per POU."),
        (upgrade, "upgrade", "Upgrade docs to a higher level."),
    ]

    for fn, name, description in tool_specs:
        _register_tool(server, fn, name=name, description=description)

    _run_server(server, config, use_http=use_http, port=port)
