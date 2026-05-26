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
