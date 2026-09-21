"""Mermaid structural diagram generator."""

from __future__ import annotations

import re

from as_docs.model.graph import KnowledgeGraph


def generate_architecture_diagram(graph: KnowledgeGraph) -> str:
    """Generate a Mermaid flowchart showing Task → Program → FB call graph."""
    lines = ["graph TD"]
    has_structure = False

    # Task nodes
    for task_name, task in graph.tasks.items():
        safe_task = _safe_id(task_name)
        interval = f"{task.cycle_time_ms}ms" if task.cycle_time_ms else task.task_type
        lines.append(f'    {safe_task}["{task_name}<br/>{interval}"]')
        lines.append(f"    style {safe_task} fill:#4a90d9,color:#fff,stroke:#2c6fad")
        has_structure = True

    # Program nodes (POUs that are owned by a task)
    owned_programs: set[str] = set()
    for edge in graph.edges:
        if edge.edge_type == "OWNS":
            owned_programs.add(edge.target)

    for prog in owned_programs:
        safe_prog = _safe_id(prog)
        lines.append(f'    {safe_prog}["{prog}"]')
        has_structure = True

    # FB nodes (CALLS targets that are FUNCTION_BLOCKs)
    fb_nodes: set[str] = set()
    for edge in graph.edges:
        if edge.edge_type == "CALLS" and edge.target in graph.pous:
            pou = graph.pous[edge.target]
            if pou.pou_type == "FUNCTION_BLOCK":
                fb_nodes.add(edge.target)

    for fb in fb_nodes:
        safe_fb = _safe_id(fb)
        lines.append(f'    {safe_fb}("{fb}")')
        has_structure = True

    # Edges
    added_edges: set[tuple[str, str]] = set()
    for edge in graph.edges:
        src = _safe_id(edge.source)
        tgt = _safe_id(edge.target)
        key = (src, tgt)
        if key in added_edges:
            continue
        added_edges.add(key)
        if edge.edge_type == "OWNS":
            lines.append(f"    {src} --> {tgt}")
            has_structure = True
        elif edge.edge_type == "CALLS":
            lines.append(f"    {src} -.-> {tgt}")
            has_structure = True

    if not has_structure:
        lines.append("    note[No task-program-call relationships detected]")

    return "\n".join(lines)


def generate_data_flow_diagram(graph: KnowledgeGraph) -> str:
    """Generate a Mermaid graph showing cross-task data coupling via globals."""
    from as_docs.analyzer.xref_builder import build_xrefs

    xrefs = build_xrefs(graph.edges)

    # Build task → programs mapping
    task_programs: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.edge_type == "OWNS":
            task_programs.setdefault(edge.source, set()).add(edge.target)

    # Find shared globals between tasks
    lines = ["graph LR"]
    task_names = list(graph.tasks.keys())

    for i, task_a in enumerate(task_names):
        for task_b in task_names[i + 1 :]:
            pous_a = task_programs.get(task_a, set())
            pous_b = task_programs.get(task_b, set())
            shared = _shared_vars(pous_a, pous_b, xrefs)
            if shared:
                safe_a = _safe_id(task_a)
                safe_b = _safe_id(task_b)
                label = ", ".join(sorted(shared)[:3])
                if len(shared) > 3:
                    label += f" +{len(shared) - 3}"
                lines.append(
                    f'    {safe_a}["{task_a}"] -- "{label}" --> {safe_b}["{task_b}"]'
                )

    if len(lines) == 1:
        lines.append("    note[No cross-task variable sharing detected]")

    return "\n".join(lines)


def _shared_vars(pous_a: set[str], pous_b: set[str], xrefs) -> list[str]:
    shared = []
    for var_name, xref in xrefs.items():
        touches_a = bool(set(xref.readers + xref.writers) & pous_a)
        touches_b = bool(set(xref.readers + xref.writers) & pous_b)
        if touches_a and touches_b:
            shared.append(var_name)
    return shared


def _safe_id(name: str) -> str:
    """Convert a name to a Mermaid-safe node ID."""
    return re.sub(r"[^A-Za-z0-9_]", "_", name)
