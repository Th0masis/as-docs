from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class Variable:
    name: str
    var_type: str  # REAL, BOOL, custom STRUCT, etc.
    scope: Literal["LOCAL", "GLOBAL"]
    gvl_name: str | None  # if GLOBAL: which GVL
    initial_value: str | None
    var_class: Literal["VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"] = "VAR"
    description: str = ""  # from trailing (* comment *) in .var/.typ
    unit: str | None = None  # engineering unit from [unit] in description


@dataclass
class DataTypeMember:
    name: str
    member_type: str
    initial_value: str | None
    description: str = ""
    unit: str | None = None


@dataclass
class DataType:
    name: str
    kind: Literal["STRUCT", "ENUM", "ALIAS"]
    members: list[DataTypeMember]  # STRUCT fields or ENUM values
    alias_target: str | None  # only for ALIAS
    source_file: str


@dataclass
class POUNode:
    name: str
    pou_type: Literal["PROGRAM", "FUNCTION_BLOCK", "FUNCTION"]
    source_file: str
    description: str = ""  # AI generated (Level 3)
    patterns: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    notes: str = ""
    local_vars: list[Variable] = field(default_factory=list)
    instances: list[str] = field(default_factory=list)  # instance names in parents
    is_external_library: bool = False
    package_path: str = (
        ""  # dot-separated package hierarchy, e.g. "Infrastructure.Alarms"
    )


@dataclass
class TaskConfig:
    name: str
    task_type: Literal["cyclic", "init", "exit"]
    cycle_time_ms: int | None
    programs: list[str]
    configuration: str = ""
    description: str = ""  # AI generated (Level 2)
    responsibilities: list[str] = field(default_factory=list)


@dataclass
class Edge:
    source: str  # POU name or task name
    target: str  # POU name or variable name
    edge_type: Literal["CALLS", "READS", "WRITES", "INSTANCE_OF", "OWNS"]


@dataclass
class FlowNode:
    node_id: str
    label: str  # plain English label (AI enriched)
    raw_condition: str | None  # original ST condition text
    node_type: Literal["state", "branch", "action", "start", "end"]


@dataclass
class FlowDiagram:
    pou_name: str
    diagram_type: Literal["stateDiagram-v2", "flowchart", "sequenceDiagram"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    source: Literal["parsed", "parsed+ai", "ai-generated"]
    mermaid_code: str
    narrative: str = ""


SCHEMA_VERSION = "1.0"


@dataclass
class KnowledgeGraph:
    schema_version: str
    project_name: str
    as_version: str
    generated_at: str
    level: int  # 1-4
    active_configuration: str
    pous: dict[str, POUNode]
    tasks: dict[str, TaskConfig]
    global_vars: dict[str, Variable]
    data_types: dict[str, DataType]
    edges: list[Edge]
    flow_diagrams: dict[str, FlowDiagram]  # keyed by POU name, Level 4 only
    _ai_stats: Any = field(default=None, repr=False)
    _regen_meta: dict[str, Any] = field(default_factory=dict, repr=False)
    _scoped_fallback_full: bool = field(default=False, repr=False)
