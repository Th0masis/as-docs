"""Shared utility functions."""
from __future__ import annotations

from as_docs.model.graph import KnowledgeGraph


def task_rw_vars(graph: KnowledgeGraph, programs: list[str]) -> tuple[list[str], list[str]]:
    """Find variables read/written by programs in task.
    
    Args:
        graph: KnowledgeGraph with all POUs and edges
        programs: List of program names in the task
    
    Returns:
        Tuple of (reads, writes) variable names
    """
    read_vars: set[str] = set()
    write_vars: set[str] = set()
    
    for prog in programs:
        pou = graph.pous.get(prog)
        if not pou or not pou.edges_to_variable:
            continue
        
        for var_name, access_type in pou.edges_to_variable.items():
            if access_type in ("R", "RW"):
                read_vars.add(var_name)
            if access_type in ("W", "RW"):
                write_vars.add(var_name)
    
    return sorted(read_vars), sorted(write_vars)


def extract_json_block(text: str) -> str:
    """Extract JSON block from text between ```json and ```.
    
    Args:
        text: Text containing JSON block
        
    Returns:
        Extracted JSON string, or empty string if not found
    """
    if "```json" not in text or "```" not in text[text.index("```json") + 7:]:
        return ""
    
    start = text.index("```json") + 7
    end = text.index("```", start)
    return text[start:end].strip()
