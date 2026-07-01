from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from as_docs.model.graph import KnowledgeGraph


def extract_json_block(text: str, *, provider_name: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            f"{provider_name} provider response does not contain a JSON object."
        )
    return text[start : end + 1]


def task_rw_vars(
    graph: KnowledgeGraph, programs: list[str]
) -> tuple[list[str], list[str]]:
    closure = _task_pou_closure(graph, programs)
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
    return reads, writes


def _task_pou_closure(graph: KnowledgeGraph, programs: list[str]) -> set[str]:
    closure = set(programs)
    queue = list(programs)
    while queue:
        current = queue.pop(0)
        callees = [
            e.target
            for e in graph.edges
            if e.edge_type == "CALLS" and e.source == current
        ]
        for callee in callees:
            if callee not in closure:
                closure.add(callee)
                queue.append(callee)
    return closure
