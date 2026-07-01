"""Shared utility functions."""

from __future__ import annotations

from as_docs.model.graph import KnowledgeGraph


def task_rw_vars(
    graph: KnowledgeGraph, programs: list[str]
) -> tuple[list[str], list[str]]:
    """Find variables read/written by programs in task.

    Args:
        graph: KnowledgeGraph with all POUs and edges
        programs: List of program names in the task

    Returns:
        Tuple of (reads, writes) variable names
    """
    pou_set = set(programs)
    reads = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "READS"
        and e.source in pou_set
        and e.target in graph.global_vars
    )
    writes = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "WRITES"
        and e.source in pou_set
        and e.target in graph.global_vars
    )
    return reads, writes


def extract_json_block(text: str) -> str:
    """Extract JSON block from text between ```json and ```.

    Args:
        text: Text containing JSON block

    Returns:
        Extracted JSON string, or empty string if not found
    """
    if "```json" not in text or "```" not in text[text.index("```json") + 7 :]:
        return ""

    start = text.index("```json") + 7
    end = text.index("```", start)
    return text[start:end].strip()
