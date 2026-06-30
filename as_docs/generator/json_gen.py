"""JSON generator — serializes KnowledgeGraph to knowledge_graph.json."""

from __future__ import annotations
import dataclasses
import json
from pathlib import Path

from as_docs.model.graph import KnowledgeGraph


def to_dict(obj) -> object:
    """Recursively convert dataclasses to dicts for JSON serialization."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dict(i) for i in obj]
    return obj


def generate_json(graph: KnowledgeGraph, output_dir: Path) -> Path:
    """Write knowledge_graph.json and return the output path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "knowledge_graph.json"

    data = {
        "schema_version": graph.schema_version,
        "project_name": graph.project_name,
        "as_version": graph.as_version,
        "generated_at": graph.generated_at,
        "level": graph.level,
        "active_configuration": graph.active_configuration,
        "tasks": {k: to_dict(v) for k, v in graph.tasks.items()},
        "pous": {k: to_dict(v) for k, v in graph.pous.items()},
        "global_vars": {k: to_dict(v) for k, v in graph.global_vars.items()},
        "data_types": {k: to_dict(v) for k, v in graph.data_types.items()},
        "edges": [to_dict(e) for e in graph.edges],
        "flow_diagrams": {k: to_dict(v) for k, v in graph.flow_diagrams.items()},
    }

    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_path
