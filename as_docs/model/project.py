"""ProjectModel: intermediate parse results assembled by scanner layer."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

from as_docs.model.graph import DataType, Edge, POUNode, TaskConfig, Variable


@dataclass
class RawSTFile:
    """Raw .st file before ST analysis."""

    path: Path
    pou_name: str
    source: str


@dataclass
class ProjectModel:
    """Intermediate representation populated by scanner parsers.

    Consumed by analyzer and generator layers.
    """

    project_root: Path
    project_name: str
    as_version: str
    active_configuration: str

    pous: dict[str, POUNode] = field(default_factory=dict)

    global_vars: dict[str, Variable] = field(default_factory=dict)
    gvl_map: dict[str, list[Variable]] = field(default_factory=dict)  # gvl_name → vars

    data_types: dict[str, DataType] = field(default_factory=dict)

    tasks: dict[str, TaskConfig] = field(default_factory=dict)

    st_files: list[RawSTFile] = field(default_factory=list)

    edges: list[Edge] = field(default_factory=list)
