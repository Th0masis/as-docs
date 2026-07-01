"""Parser-first Level 4 flow extraction for Structured Text POUs."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from as_docs.model.graph import FlowNode


_STATE_LABEL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*$")
_CASE_RE = re.compile(r"\bCASE\s+(.+?)\s+OF\b", re.IGNORECASE)
_IF_RE = re.compile(r"\bIF\s+(.+?)\s+THEN\b", re.IGNORECASE)
_LOOP_RE = re.compile(r"\b(FOR|WHILE)\b", re.IGNORECASE)
_STATE_ASSIGN_RE = re.compile(
    r"\bState\s*:=\s*([A-Za-z_][A-Za-z0-9_]*)\b", re.IGNORECASE
)


@dataclass
class FlowEdge:
    source: str
    target: str
    label: str = ""


@dataclass
class FlowExtractionResult:
    pou_name: str
    diagram_type: str
    confidence: str
    source: str
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)
    narrative: str = ""


def extract_flow(
    pou_name: str, source: str, *, ai_enabled: bool = False
) -> FlowExtractionResult | None:
    """Extract a lightweight control-flow model from ST source.

    The extractor prefers deterministic parsing of CASE/IF/loop constructs.
    Returns None when the source does not contain enough structure to justify a flow diagram.
    """
    stripped = _strip_comments(source)
    has_case = bool(_CASE_RE.search(stripped))
    has_if = bool(_IF_RE.search(stripped))
    has_loop = bool(_LOOP_RE.search(stripped))

    if not (has_case or has_if or has_loop):
        return None

    diagram_type = "stateDiagram-v2" if has_case else "flowchart"
    confidence = (
        "HIGH" if has_case and has_if else ("MEDIUM" if has_case or has_if else "LOW")
    )
    source_kind = "parsed+ai" if ai_enabled else "parsed"

    result = FlowExtractionResult(
        pou_name=pou_name,
        diagram_type=diagram_type,
        confidence=confidence,
        source=source_kind,
    )

    if has_case:
        _extract_case_flow(stripped, result)
    else:
        _extract_if_flow(stripped, result)

    if has_loop:
        _annotate_loops(stripped, result)

    if ai_enabled and result.narrative == "":
        result.narrative = f"Parsed control flow for {pou_name}."

    return result


def _extract_case_flow(source: str, result: FlowExtractionResult) -> None:
    case_match = _CASE_RE.search(source)
    if case_match is None:
        return

    case_expr = case_match.group(1).strip()
    result.nodes.append(
        FlowNode(
            node_id="start",
            label=f"Start {result.pou_name}",
            raw_condition=None,
            node_type="start",
        )
    )

    states: list[str] = []
    current_state: str | None = None
    current_conditions: list[str] = []
    in_case = False

    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _CASE_RE.search(stripped):
            in_case = True
            continue
        if stripped.upper().startswith("END_CASE"):
            in_case = False
            current_state = None
            current_conditions.clear()
            continue
        if not in_case:
            continue

        state_label = _STATE_LABEL_RE.match(stripped)
        if state_label and not stripped.upper().startswith(("IF ", "ELSE", "ELSIF")):
            state_name = state_label.group(1)
            if state_name:
                current_state = state_name
                states.append(state_name)
                result.nodes.append(
                    FlowNode(
                        node_id=state_name,
                        label=state_name,
                        raw_condition=None,
                        node_type="state",
                    )
                )
            current_conditions.clear()
            continue

        if_match = _IF_RE.search(stripped)
        if if_match and current_state:
            condition = if_match.group(1).strip()
            current_conditions.append(condition)
            result.nodes.append(
                FlowNode(
                    node_id=f"if_{len(result.nodes)}",
                    label=condition,
                    raw_condition=condition,
                    node_type="branch",
                )
            )
            continue

        assign_match = _STATE_ASSIGN_RE.search(stripped)
        if assign_match and current_state and current_conditions:
            target_state = assign_match.group(1)
            result.edges.append(
                FlowEdge(
                    source=current_state,
                    target=target_state,
                    label=current_conditions[-1],
                )
            )
            if target_state not in states:
                states.append(target_state)
                result.nodes.append(
                    FlowNode(
                        node_id=target_state,
                        label=target_state,
                        raw_condition=None,
                        node_type="state",
                    )
                )

    if states:
        result.edges.insert(
            0, FlowEdge(source="start", target=states[0], label=case_expr)
        )


def _extract_if_flow(source: str, result: FlowExtractionResult) -> None:
    result.nodes.append(
        FlowNode(
            node_id="start",
            label=f"Start {result.pou_name}",
            raw_condition=None,
            node_type="start",
        )
    )
    current_branch = "start"
    branch_idx = 0

    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if_match = _IF_RE.search(stripped)
        if if_match:
            condition = if_match.group(1).strip()
            node_id = f"branch_{branch_idx}"
            branch_idx += 1
            result.nodes.append(
                FlowNode(
                    node_id=node_id,
                    label=condition,
                    raw_condition=condition,
                    node_type="branch",
                )
            )
            result.edges.append(
                FlowEdge(source=current_branch, target=node_id, label=condition)
            )
            current_branch = node_id
            continue

        assign_match = _STATE_ASSIGN_RE.search(stripped)
        if assign_match:
            target = assign_match.group(1)
            node_id = f"action_{branch_idx}"
            result.nodes.append(
                FlowNode(
                    node_id=node_id,
                    label=f"State := {target}",
                    raw_condition=None,
                    node_type="action",
                )
            )
            result.edges.append(
                FlowEdge(source=current_branch, target=node_id, label="action")
            )
            branch_idx += 1


def _annotate_loops(source: str, result: FlowExtractionResult) -> None:
    if re.search(r"\bFOR\b", source, re.IGNORECASE):
        result.nodes.append(
            FlowNode(
                node_id="loop_for",
                label="FOR loop",
                raw_condition=None,
                node_type="branch",
            )
        )
    if re.search(r"\bWHILE\b", source, re.IGNORECASE):
        result.nodes.append(
            FlowNode(
                node_id="loop_while",
                label="WHILE loop",
                raw_condition=None,
                node_type="branch",
            )
        )


def _strip_comments(source: str) -> str:
    source = re.sub(r"\(\*.*?\*\)", " ", source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", " ", source)
    return source
