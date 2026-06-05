"""Markdown generator — produces overview.md, architecture.md, global_vars.md, data_types.md."""
from __future__ import annotations
from pathlib import Path

from as_docs.model.graph import KnowledgeGraph
from as_docs.analyzer.xref_builder import build_xrefs
from as_docs.generator.diagram_gen import generate_architecture_diagram, generate_data_flow_diagram


def generate_all_markdown(graph: KnowledgeGraph, output_dir: Path) -> list[Path]:
    """Generate all Level 1 markdown files. Returns list of created paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    produced.append(_write_overview(graph, output_dir))
    produced.append(_write_architecture(graph, output_dir))
    produced.append(_write_global_vars(graph, output_dir))
    produced.append(_write_data_types(graph, output_dir))

    if graph.level >= 2:
        produced.append(_write_data_flow(graph, output_dir))
        produced.extend(_write_task_pages(graph, output_dir))

    if graph.level >= 3:
        produced.extend(_write_pou_pages(graph, output_dir))

    return produced


# ---------------------------------------------------------------------------
# overview.md
# ---------------------------------------------------------------------------

def _write_overview(graph: KnowledgeGraph, output_dir: Path) -> Path:
    path = output_dir / "overview.md"
    lines = [
        f"# {graph.project_name}",
        "",
        f"| Field | Value |",
        f"|---|---|",
        f"| AS Version | {graph.as_version or '—'} |",
        f"| Active Configuration | {graph.active_configuration or '—'} |",
        f"| Generated | {graph.generated_at[:19].replace('T', ' ')} |",
        f"| Documentation Level | {graph.level} |",
        f"| POUs | {len([p for p in graph.pous.values() if not p.is_external_library])} (+ {len([p for p in graph.pous.values() if p.is_external_library])} external) |",
        f"| Tasks | {len(graph.tasks)} |",
        f"| Global Variables | {len(graph.global_vars)} |",
        f"| Data Types | {len(graph.data_types)} |",
        "",
        "## Tasks",
        "",
        "| Task | Type | Interval | Programs |",
        "|---|---|---|---|",
    ]
    for task_name, task in sorted(graph.tasks.items()):
        interval = f"{task.cycle_time_ms} ms" if task.cycle_time_ms else "—"
        progs = ", ".join(task.programs) if task.programs else "—"
        lines.append(f"| {task_name} | {task.task_type} | {interval} | {progs} |")

    lines += [
        "",
        "## Programs and Function Blocks",
        "",
        "| POU | Type | External |",
        "|---|---|---|",
    ]
    for pou_name, pou in sorted(graph.pous.items()):
        ext = "✓" if pou.is_external_library else ""
        lines.append(f"| {pou_name} | {pou.pou_type} | {ext} |")

    lines += [
        "",
        "## Global Variable Lists",
        "",
    ]
    # Group by GVL
    gvl_groups: dict[str, list[str]] = {}
    for var in graph.global_vars.values():
        gvl = var.gvl_name or "(ungrouped)"
        gvl_groups.setdefault(gvl, []).append(var.name)
    for gvl, var_names in sorted(gvl_groups.items()):
        lines.append(f"- **{gvl}**: {len(var_names)} variables")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# architecture.md
# ---------------------------------------------------------------------------

def _write_architecture(graph: KnowledgeGraph, output_dir: Path) -> Path:
    path = output_dir / "architecture.md"
    diagram = generate_architecture_diagram(graph)
    lines = [
        f"# {graph.project_name} — Architecture",
        "",
        "> Structural call graph: Task → Program → Function Block",
        "> Generated at Level 1 — shows structural relationships only.",
        "",
        "```mermaid",
        diagram,
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# global_vars.md
# ---------------------------------------------------------------------------

def _write_global_vars(graph: KnowledgeGraph, output_dir: Path) -> Path:
    path = output_dir / "global_vars.md"
    xrefs = build_xrefs(graph.edges) if graph.level >= 2 else {}

    lines = [
        f"# {graph.project_name} — Global Variables",
        "",
    ]

    # Group by GVL
    gvl_groups: dict[str, list] = {}
    for var in graph.global_vars.values():
        gvl = var.gvl_name or "(ungrouped)"
        gvl_groups.setdefault(gvl, []).append(var)

    for gvl_name, vars_ in sorted(gvl_groups.items()):
        lines += [f"## {gvl_name}", ""]
        if graph.level >= 2:
            lines += [
                "| Variable | Type | Initial | Unit | Description | Readers | Writers |",
                "|---|---|---|---|---|---|---|",
            ]
            for v in sorted(vars_, key=lambda x: x.name):
                xref = xrefs.get(v.name)
                readers = ", ".join(xref.readers) if xref else ""
                writers = ", ".join(xref.writers) if xref else ""
                lines.append(
                    f"| {v.name} | {v.var_type} | {v.initial_value or ''} | "
                    f"{v.unit or ''} | {v.description} | {readers} | {writers} |"
                )
        else:
            lines += [
                "| Variable | Type | Initial | Unit | Description |",
                "|---|---|---|---|---|",
            ]
            for v in sorted(vars_, key=lambda x: x.name):
                lines.append(
                    f"| {v.name} | {v.var_type} | {v.initial_value or ''} | "
                    f"{v.unit or ''} | {v.description} |"
                )
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# data_types.md
# ---------------------------------------------------------------------------

def _write_data_types(graph: KnowledgeGraph, output_dir: Path) -> Path:
    path = output_dir / "data_types.md"
    lines = [
        f"# {graph.project_name} — Data Types",
        "",
    ]

    structs = {k: v for k, v in graph.data_types.items() if v.kind == "STRUCT"}
    enums = {k: v for k, v in graph.data_types.items() if v.kind == "ENUM"}
    aliases = {k: v for k, v in graph.data_types.items() if v.kind == "ALIAS"}

    if structs:
        lines += ["## Structures", ""]
        for name, dt in sorted(structs.items()):
            lines += [
                f"### {name}",
                f"*Source: `{dt.source_file}`*",
                "",
                "| Member | Type | Initial | Unit | Description |",
                "|---|---|---|---|---|",
            ]
            for m in dt.members:
                lines.append(
                    f"| {m.name} | {m.member_type} | {m.initial_value or ''} | "
                    f"{m.unit or ''} | {m.description} |"
                )
            lines.append("")

    if enums:
        lines += ["## Enumerations", ""]
        for name, dt in sorted(enums.items()):
            lines += [
                f"### {name}",
                "",
                "| Value | Integer |",
                "|---|---|",
            ]
            for m in dt.members:
                lines.append(f"| {m.name} | {m.initial_value or ''} |")
            lines.append("")

    if aliases:
        lines += ["## Aliases", ""]
        lines += [
            "| Alias | Target Type |",
            "|---|---|",
        ]
        for name, dt in sorted(aliases.items()):
            lines.append(f"| {name} | {dt.alias_target} |")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# data_flow.md  (Level 2+)
# ---------------------------------------------------------------------------

def _write_data_flow(graph: KnowledgeGraph, output_dir: Path) -> Path:
    path = output_dir / "data_flow.md"
    diagram = generate_data_flow_diagram(graph)
    lines = [
        f"# {graph.project_name} — Data Flow",
        "",
        "> Cross-task variable coupling: global variables shared between tasks.",
        "",
        "```mermaid",
        diagram,
        "```",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# tasks/*.md  (Level 2+)
# ---------------------------------------------------------------------------

def _write_task_pages(graph: KnowledgeGraph, output_dir: Path) -> list[Path]:
    tasks_dir = output_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    for task_name, task in sorted(graph.tasks.items()):
        reads, writes = _task_rw_vars(graph, task.programs)
        coupling = _task_coupling(graph, task_name, set(reads) | set(writes))

        path = tasks_dir / f"{task_name}.md"
        lines = [
            f"# Task: {task_name}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Type | {task.task_type} |",
            f"| Interval | {f'{task.cycle_time_ms} ms' if task.cycle_time_ms else '—'} |",
            f"| Programs | {', '.join(task.programs) if task.programs else '—'} |",
            "",
        ]

        if task.description:
            lines += ["## Description", "", task.description, ""]

        if task.responsibilities:
            lines += ["## Responsibilities", ""]
            lines.extend([f"- {item}" for item in task.responsibilities])
            lines.append("")

        lines += [
            "## Global Variable Access",
            "",
            f"- Reads: {', '.join(reads) if reads else '—'}",
            f"- Writes: {', '.join(writes) if writes else '—'}",
            f"- Coupled tasks: {', '.join(coupling) if coupling else '—'}",
            "",
        ]

        path.write_text("\n".join(lines), encoding="utf-8")
        produced.append(path)

    return produced


def _task_rw_vars(graph: KnowledgeGraph, programs: list[str]) -> tuple[list[str], list[str]]:
    closure = _task_pou_closure(graph, programs)
    reads = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "READS" and e.source in closure and e.target in graph.global_vars
    )
    writes = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "WRITES" and e.source in closure and e.target in graph.global_vars
    )
    return reads, writes


def _task_pou_closure(graph: KnowledgeGraph, programs: list[str]) -> set[str]:
    closure = set(programs)
    queue = list(programs)
    while queue:
        current = queue.pop(0)
        callees = [
            e.target for e in graph.edges if e.edge_type == "CALLS" and e.source == current
        ]
        for callee in callees:
            if callee not in closure:
                closure.add(callee)
                queue.append(callee)
    return closure


def _task_coupling(graph: KnowledgeGraph, task_name: str, var_set: set[str]) -> list[str]:
    coupled: list[str] = []
    for other_name, other in sorted(graph.tasks.items()):
        if other_name == task_name:
            continue
        other_reads, other_writes = _task_rw_vars(graph, other.programs)
        if var_set.intersection(other_reads) or var_set.intersection(other_writes):
            coupled.append(other_name)
    return coupled


# ---------------------------------------------------------------------------
# pou/*.md  (Level 3+)
# ---------------------------------------------------------------------------

def _write_pou_pages(graph: KnowledgeGraph, output_dir: Path) -> list[Path]:
    pou_dir = output_dir / "pou"
    pou_dir.mkdir(parents=True, exist_ok=True)
    produced: list[Path] = []

    for pou_name, pou in sorted(graph.pous.items()):
        if pou.is_external_library:
            continue

        callers = sorted(
            e.source for e in graph.edges if e.edge_type == "CALLS" and e.target == pou_name
        )
        callees = sorted(
            e.target for e in graph.edges if e.edge_type == "CALLS" and e.source == pou_name
        )
        reads = sorted(
            e.target
            for e in graph.edges
            if e.edge_type == "READS" and e.source == pou_name and e.target in graph.global_vars
        )
        writes = sorted(
            e.target
            for e in graph.edges
            if e.edge_type == "WRITES" and e.source == pou_name and e.target in graph.global_vars
        )

        path = pou_dir / f"{pou_name}.md"
        lines = [
            f"# POU: {pou_name}",
            "",
            "| Field | Value |",
            "|---|---|",
            f"| Type | {pou.pou_type} |",
            f"| Source | {pou.source_file} |",
            "",
        ]

        if pou.description:
            lines += ["## Description", "", pou.description, ""]

        if pou.responsibilities:
            lines += ["## Responsibilities", ""]
            lines.extend([f"- {item}" for item in pou.responsibilities])
            lines.append("")

        if pou.patterns:
            lines += ["## Patterns", ""]
            lines.extend([f"- {item}" for item in pou.patterns])
            lines.append("")

        if pou.notes:
            lines += ["## Notes", "", pou.notes, ""]

        lines += [
            "## Relationships",
            "",
            f"- Callers: {', '.join(callers) if callers else '—'}",
            f"- Callees: {', '.join(callees) if callees else '—'}",
            f"- Reads: {', '.join(reads) if reads else '—'}",
            f"- Writes: {', '.join(writes) if writes else '—'}",
            "",
        ]

        path.write_text("\n".join(lines), encoding="utf-8")
        produced.append(path)

    return produced
