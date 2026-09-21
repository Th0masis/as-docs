"""Cross-reference builder — maps variables to the POUs that read/write them."""

from __future__ import annotations

from dataclasses import dataclass, field

from as_docs.model.graph import Edge


@dataclass
class VariableXRef:
    var_name: str
    readers: list[str] = field(default_factory=list)  # POU names
    writers: list[str] = field(default_factory=list)  # POU names


def build_xrefs(edges: list[Edge]) -> dict[str, VariableXRef]:
    """Build a variable → {readers, writers} cross-reference map."""
    xrefs: dict[str, VariableXRef] = {}

    for edge in edges:
        if edge.edge_type == "READS":
            xref = xrefs.setdefault(edge.target, VariableXRef(var_name=edge.target))
            if edge.source not in xref.readers:
                xref.readers.append(edge.source)
        elif edge.edge_type == "WRITES":
            xref = xrefs.setdefault(edge.target, VariableXRef(var_name=edge.target))
            if edge.source not in xref.writers:
                xref.writers.append(edge.source)

    return xrefs


def get_shared_vars(
    task_a_pous: list[str],
    task_b_pous: list[str],
    xrefs: dict[str, VariableXRef],
) -> list[str]:
    """Return variable names shared (read/written) between two tasks' POU sets."""
    set_a = set(task_a_pous)
    set_b = set(task_b_pous)
    shared = []
    for var_name, xref in xrefs.items():
        touches_a = set(xref.readers + xref.writers) & set_a
        touches_b = set(xref.readers + xref.writers) & set_b
        if touches_a and touches_b:
            shared.append(var_name)
    return sorted(shared)
