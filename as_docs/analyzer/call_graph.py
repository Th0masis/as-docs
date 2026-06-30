"""Call graph builder — assembles POU call hierarchy from ST analysis results."""
from __future__ import annotations
from as_docs.analyzer.st_analyzer import STAnalysisResult
from as_docs.model.graph import Edge
from as_docs.model.project import ProjectModel


def build_edges(model: ProjectModel, analysis_results: list[STAnalysisResult]) -> list[Edge]:
    """Build all graph edges from scan + analysis results.

    Edge types produced:
      OWNS      — Task → Program
      CALLS     — POU → POU (including FB instances)
      READS     — POU → Variable
      WRITES    — POU → Variable
      INSTANCE_OF — POU → FB type (FB instance declarations)
    """
    edges: list[Edge] = []

    # OWNS edges: Task → Program
    for task in model.tasks.values():
        for prog in task.programs:
            edges.append(Edge(source=task.name, target=prog, edge_type="OWNS"))

    # CALLS / READS / WRITES from ST analysis
    for result in analysis_results:
        pou_name = result.pou_name
        for callee in result.calls:
            edges.append(Edge(source=pou_name, target=callee, edge_type="CALLS"))
        for var in result.reads:
            edges.append(Edge(source=pou_name, target=var, edge_type="READS"))
        for var in result.writes:
            edges.append(Edge(source=pou_name, target=var, edge_type="WRITES"))

    # INSTANCE_OF edges from analyzed instance type mappings
    for result in analysis_results:
        source_pou = result.pou_name
        for fb_type in result.instance_types.values():
            if fb_type in model.pous and fb_type != source_pou:
                edges.append(Edge(
                    source=source_pou,
                    target=fb_type,
                    edge_type="INSTANCE_OF",
                ))

    return edges


def get_callers(pou_name: str, edges: list[Edge]) -> list[str]:
    """Return all POUs that CALL the given POU."""
    return [e.source for e in edges if e.edge_type == "CALLS" and e.target == pou_name]


def get_callees(pou_name: str, edges: list[Edge]) -> list[str]:
    """Return all POUs called by the given POU."""
    return [e.target for e in edges if e.edge_type == "CALLS" and e.source == pou_name]


def get_task_for_pou(pou_name: str, edges: list[Edge]) -> str | None:
    """Return the task that owns the given program (OWNS edge)."""
    for e in edges:
        if e.edge_type == "OWNS" and e.target == pou_name:
            return e.source
    return None
