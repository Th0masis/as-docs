"""AI enricher for documentation Levels 2 and 3."""
from __future__ import annotations

from pathlib import Path

from as_docs.config import Config
from as_docs.enricher.cache import CacheStats, EnrichmentCache
from as_docs.enricher.prompts import build_level2_task_prompt, build_level3_pou_prompt
from as_docs.enricher.providers import create_provider
from as_docs.model.graph import KnowledgeGraph


def enrich_graph(graph: KnowledgeGraph, level: int, config: Config) -> CacheStats:
    """Enrich KnowledgeGraph with AI-generated descriptions for Level 2/3.

    Returns cache stats for CLI observability.
    """
    provider = create_provider(config)
    cache = EnrichmentCache(
        cache_dir=Path(config.ai.cache_dir),
        provider=config.ai.provider,
        model=config.ai.model,
    )
    stats = CacheStats()

    if level >= 2:
        _enrich_tasks(graph=graph, config=config, cache=cache, provider=provider, stats=stats)

    if level >= 3:
        _enrich_pous(graph=graph, config=config, cache=cache, provider=provider, stats=stats)

    return stats


def _enrich_tasks(
    graph: KnowledgeGraph,
    config: Config,
    cache: EnrichmentCache,
    provider,
    stats: CacheStats,
) -> None:
    for task_name, task in sorted(graph.tasks.items()):
        reads, writes = _task_rw_vars(graph, task.programs)
        coupling_tasks = _task_coupling(graph, task_name, reads, writes)
        key_material = "\n".join(
            [
                task.name,
                task.task_type,
                str(task.cycle_time_ms),
                ",".join(task.programs),
                "R:" + ",".join(reads),
                "W:" + ",".join(writes),
                "C:" + ",".join(coupling_tasks),
            ]
        )

        hit = cache.get(scope="task", name=task_name, level=2, content=key_material)
        if hit:
            task.description = hit.description
            task.responsibilities = hit.responsibilities
            stats.hits += 1
            continue

        prompt = build_level2_task_prompt(
            graph=graph,
            task=task,
            reads=reads,
            writes=writes,
            coupling_tasks=coupling_tasks,
        )
        payload = provider.enrich_task(prompt=prompt, model=config.ai.model, max_tokens=1024)
        task.description = payload.description
        task.responsibilities = payload.responsibilities
        cache.set(scope="task", name=task_name, level=2, content=key_material, payload=payload)
        stats.misses += 1
        stats.writes += 1


def _enrich_pous(
    graph: KnowledgeGraph,
    config: Config,
    cache: EnrichmentCache,
    provider,
    stats: CacheStats,
) -> None:
    for pou_name, pou in sorted(graph.pous.items()):
        if pou.is_external_library:
            continue

        source = _resolve_st_source(pou)
        reads, writes = _pou_rw_vars(graph, pou_name)
        callers, callees = _pou_callers_callees(graph, pou_name)

        hit = cache.get(scope="pou", name=pou_name, level=3, content=source)
        if hit:
            pou.description = hit.description
            pou.responsibilities = hit.responsibilities
            pou.patterns = hit.patterns
            pou.notes = hit.notes
            stats.hits += 1
            continue

        prompt = build_level3_pou_prompt(
            graph=graph,
            pou=pou,
            source=source,
            reads=reads,
            writes=writes,
            callers=callers,
            callees=callees,
        )
        payload = provider.enrich_pou(prompt=prompt, model=config.ai.model, max_tokens=1024)
        pou.description = payload.description
        pou.responsibilities = payload.responsibilities
        pou.patterns = payload.patterns
        pou.notes = payload.notes
        cache.set(scope="pou", name=pou_name, level=3, content=source, payload=payload)
        stats.misses += 1
        stats.writes += 1


def _resolve_st_source(pou) -> str:
    src = Path(pou.source_file)
    if src.suffix.lower() == ".st" and src.exists():
        return src.read_text(encoding="utf-8", errors="replace")

    if src.exists() and src.parent.exists():
        same_name = src.parent / f"{src.stem}.st"
        if same_name.exists():
            return same_name.read_text(encoding="utf-8", errors="replace")

        candidates = sorted(src.parent.glob("*.st"))
        if candidates:
            return candidates[0].read_text(encoding="utf-8", errors="replace")

    return ""


def _pou_callers_callees(graph: KnowledgeGraph, pou_name: str) -> tuple[list[str], list[str]]:
    callers = sorted(
        e.source for e in graph.edges if e.edge_type == "CALLS" and e.target == pou_name
    )
    callees = sorted(
        e.target for e in graph.edges if e.edge_type == "CALLS" and e.source == pou_name
    )
    return callers, callees


def _pou_rw_vars(graph: KnowledgeGraph, pou_name: str) -> tuple[list[str], list[str]]:
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
    return reads, writes


def _task_rw_vars(graph: KnowledgeGraph, programs: list[str]) -> tuple[list[str], list[str]]:
    pou_set = _task_pou_closure(graph, programs)
    reads = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "READS" and e.source in pou_set and e.target in graph.global_vars
    )
    writes = sorted(
        e.target
        for e in graph.edges
        if e.edge_type == "WRITES" and e.source in pou_set and e.target in graph.global_vars
    )
    return reads, writes


def _task_coupling(graph: KnowledgeGraph, task_name: str, reads: list[str], writes: list[str]) -> list[str]:
    vars_used = set(reads) | set(writes)
    coupling: list[str] = []
    for other_name, task in graph.tasks.items():
        if other_name == task_name:
            continue
        other_reads, other_writes = _task_rw_vars(graph, task.programs)
        if vars_used.intersection(other_reads) or vars_used.intersection(other_writes):
            coupling.append(other_name)
    return sorted(coupling)


def _task_pou_closure(graph: KnowledgeGraph, programs: list[str]) -> set[str]:
    closure = set(programs)
    queue = list(programs)

    while queue:
        current = queue.pop(0)
        children = [
            e.target for e in graph.edges if e.edge_type == "CALLS" and e.source == current
        ]
        for child in children:
            if child not in closure:
                closure.add(child)
                queue.append(child)

    return closure
