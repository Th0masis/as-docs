from __future__ import annotations

from as_docs.model.graph import KnowledgeGraph, TaskConfig, POUNode


def build_level2_task_prompt(
    graph: KnowledgeGraph,
    task: TaskConfig,
    reads: list[str],
    writes: list[str],
    coupling_tasks: list[str],
) -> str:
    programs = ", ".join(task.programs) if task.programs else "none"
    read_text = ", ".join(reads) if reads else "none"
    write_text = ", ".join(writes) if writes else "none"
    coupling_text = ", ".join(coupling_tasks) if coupling_tasks else "none"

    return (
        "You are documenting a B&R Automation Studio project task.\n\n"
        f"Task: {task.name}\n"
        f"Type: {task.task_type}\n"
        f"Interval: {task.cycle_time_ms if task.cycle_time_ms is not None else 'unknown'} ms\n"
        f"Programs: {programs}\n"
        f"Global reads: {read_text}\n"
        f"Global writes: {write_text}\n"
        f"Cross-task variable sharing with: {coupling_text}\n\n"
        "Return strict JSON only with keys:\n"
        "description, responsibilities, patterns, notes"
    )


def build_level3_pou_prompt(
    graph: KnowledgeGraph,
    pou: POUNode,
    source: str,
    reads: list[str],
    writes: list[str],
    callers: list[str],
    callees: list[str],
) -> str:
    vars_summary = ", ".join(f"{v.name}:{v.var_type}" for v in pou.local_vars) or "none"
    return (
        "You are documenting a B&R Automation Studio POU.\n\n"
        "B&R naming conventions:\n"
        "- Global vars start with g (e.g., gMotorSpeed)\n"
        "- Inputs often use di/si/ai/at prefixes\n"
        "- Outputs often use do/ao prefixes\n"
        "- Constants are SCREAMING_SNAKE_CASE\n"
        "- FB call idiom: set Instance.Field values before Instance()\n\n"
        f"POU: {pou.name}\n"
        f"Type: {pou.pou_type}\n"
        f"Local vars: {vars_summary}\n"
        f"Global reads: {', '.join(reads) if reads else 'none'}\n"
        f"Global writes: {', '.join(writes) if writes else 'none'}\n"
        f"Called by: {', '.join(callers) if callers else 'none'}\n"
        f"Calls: {', '.join(callees) if callees else 'none'}\n\n"
        "Source code:\n"
        f"{source}\n\n"
        "Return strict JSON only with keys:\n"
        "description, responsibilities, patterns, notes"
    )
