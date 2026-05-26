"""Placeholder AI enricher — Phase 2 implementation."""
from __future__ import annotations
from as_docs.config import Config
from as_docs.model.graph import KnowledgeGraph


def enrich_graph(graph: KnowledgeGraph, level: int, config: Config) -> None:
    """Enrich KnowledgeGraph with AI-generated descriptions (Phase 2).

    Currently a no-op placeholder. Phase 2 will implement:
    - Level 2: 1 Claude call per task (task-scoped prompt, no source)
    - Level 3: 1 Claude call per POU (full source + B&R style guide)
    """
    raise NotImplementedError(
        "AI enrichment is not yet implemented. "
        "Use 'as-docs generate --no-ai' for Level 1 documentation."
    )
