from __future__ import annotations

from as_docs.mcp_server import (
    find_variable_payload,
    get_flow_diagram_payload,
    get_overview_payload,
    get_pou_list_payload,
    get_pou_payload,
)
from as_docs.model.graph import Edge, FlowDiagram, KnowledgeGraph, POUNode, TaskConfig, Variable


def _graph(level: int = 3) -> KnowledgeGraph:
    return KnowledgeGraph(
        schema_version="1.0",
        project_name="SampleProject",
        as_version="4.10",
        generated_at="2026-06-05T12:00:00Z",
        level=level,
        active_configuration="Config1",
        pous={
            "MainProgram": POUNode(
                name="MainProgram",
                pou_type="PROGRAM",
                source_file="Logical/MainProgram/Main.st",
                description="Main loop",
            ),
            "MotorControl_FB": POUNode(
                name="MotorControl_FB",
                pou_type="FUNCTION_BLOCK",
                source_file="Logical/MotorControl/MotorControl.st",
                description="Motor control",
                patterns=["state machine"],
            ),
        },
        tasks={
            "CyclicTask": TaskConfig(
                name="CyclicTask",
                task_type="cyclic",
                cycle_time_ms=10,
                programs=["MainProgram"],
            )
        },
        global_vars={
            "gMotorSpeed": Variable(
                name="gMotorSpeed",
                var_type="REAL",
                scope="GLOBAL",
                gvl_name="GVL_Main",
                initial_value="0.0",
            )
        },
        data_types={},
        edges=[
            Edge(source="CyclicTask", target="MainProgram", edge_type="OWNS"),
            Edge(source="MainProgram", target="MotorControl_FB", edge_type="CALLS"),
            Edge(source="MotorControl_FB", target="gMotorSpeed", edge_type="WRITES"),
        ],
        flow_diagrams={
            "MotorControl_FB": FlowDiagram(
                pou_name="MotorControl_FB",
                diagram_type="stateDiagram-v2",
                confidence="HIGH",
                source="parsed+ai",
                mermaid_code="stateDiagram-v2\n[*] --> Idle",
                narrative="Flow narrative",
            )
        },
    )


def test_get_overview_payload_contains_metadata() -> None:
    payload = get_overview_payload(_graph(level=2))

    assert payload["status"] == "ok"
    assert payload["level"] == 2
    assert payload["active_configuration"] == "Config1"
    assert payload["data"]["project_name"] == "SampleProject"
    assert payload["data"]["pou_count"] == 2


def test_get_pou_list_payload_contains_basic_fields() -> None:
    payload = get_pou_list_payload(_graph())

    assert payload["status"] == "ok"
    assert len(payload["data"]["pous"]) == 2
    assert payload["data"]["pous"][0]["name"] == "MainProgram"


def test_get_pou_payload_returns_partial_when_level_too_low() -> None:
    payload = get_pou_payload(_graph(level=1), "MotorControl_FB", requested_level=3)

    assert payload["status"] == "partial"
    assert payload["available_level"] == 1
    assert payload["requested_level"] == 3
    assert "upgrade --to 3" in payload["hint"]


def test_find_variable_payload_resolves_task_context() -> None:
    payload = find_variable_payload(_graph(), "gMotorSpeed")

    assert payload["status"] == "ok"
    assert payload["data"]["writers"] == ["MotorControl_FB"]
    assert payload["data"]["tasks"] == ["CyclicTask"]


def test_get_flow_diagram_payload_returns_partial_hint_when_missing() -> None:
    graph = _graph(level=2)
    graph.flow_diagrams = {}

    payload = get_flow_diagram_payload(graph, "MotorControl_FB", requested_level=4)

    assert payload["status"] == "partial"
    assert payload["data"]["flow_diagram"] is None
    assert payload["requested_level"] == 4
    assert "upgrade --to 4" in payload["hint"]
