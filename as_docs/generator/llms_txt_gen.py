"""llms.txt index generator — AI agent entry point."""

from __future__ import annotations

from pathlib import Path

from as_docs.model.graph import KnowledgeGraph


def generate_llms_txt(graph: KnowledgeGraph, output_dir: Path) -> Path:
    """Generate llms.txt index and return the output path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "llms.txt"

    lines: list[str] = [
        f"# {graph.project_name} — AS Documentation Index",
        f"Generated: {graph.generated_at[:10]}  Level: {graph.level}",
        f"AS Version: {graph.as_version}  Configuration: {graph.active_configuration}",
        "",
        "## Entry points",
        "overview.md             Project summary, task list, hardware config",
        "architecture.md         Full call graph: Task → Program → FB",
        "global_vars.md          All global variables with cross-references",
        "data_types.md           All STRUCT/ENUM/ALIAS type definitions",
        "knowledge_graph.json    Machine-readable full project graph",
        "",
    ]

    if graph.level >= 2:
        lines += [
            "data_flow.md            Cross-task data coupling via global variables",
            "",
        ]

    # Tasks section
    if graph.tasks:
        lines.append("## Tasks")
        for task_name, task in sorted(graph.tasks.items()):
            interval = (
                f"{task.cycle_time_ms}ms" if task.cycle_time_ms else task.task_type
            )
            desc = (
                task.description.split(".")[0]
                if task.description
                else f"{interval}, {len(task.programs)} program(s)"
            )
            if graph.level >= 2:
                lines.append(f"tasks/{task_name}.md    {desc}")
            else:
                lines.append(
                    f"# tasks/{task_name}.md    {desc} [Level 2 not generated]"
                )
        lines.append("")

    # POUs section
    if graph.pous:
        lines.append("## POUs")
        for pou_name, pou in sorted(graph.pous.items()):
            if pou.is_external_library:
                continue
            desc = pou.description.split(".")[0] if pou.description else pou.pou_type
            if graph.level >= 3:
                lines.append(f"pou/{pou_name}.md    {desc}")
            else:
                lines.append(f"# pou/{pou_name}.md    {desc} [Level 3 not generated]")
        lines.append("")

    # Flow diagrams section (Level 4)
    if graph.flow_diagrams:
        lines.append("## Flow diagrams (Level 4)")
        for pou_name, fd in sorted(graph.flow_diagrams.items()):
            confidence_icon = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(
                fd.confidence, ""
            )
            lines.append(
                f"pou/{pou_name}.flow.md    {fd.diagram_type} — {confidence_icon} {fd.source}"
            )
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
