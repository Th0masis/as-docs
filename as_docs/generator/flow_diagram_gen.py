"""Level 4 Mermaid flow-diagram generation."""
from __future__ import annotations

from pathlib import Path

from as_docs.analyzer.flow_extractor import FlowExtractionResult, extract_flow
from as_docs.model.graph import FlowDiagram, KnowledgeGraph


def build_flow_diagram(
    pou_name: str,
    source: str,
    *,
    ai_enabled: bool = False,
    narrative_hint: str = "",
) -> FlowDiagram | None:
    extracted = extract_flow(pou_name, source, ai_enabled=ai_enabled)
    if extracted is None:
        return None

    mermaid = _to_mermaid(extracted)
    narrative = narrative_hint or extracted.narrative
    if ai_enabled and not narrative:
        narrative = f"Parsed Level 4 control flow for {pou_name}."

    return FlowDiagram(
        pou_name=pou_name,
        diagram_type=extracted.diagram_type,
        confidence=extracted.confidence,
        source=extracted.source,
        mermaid_code=mermaid,
        narrative=narrative,
    )


def generate_flow_markdown(graph: KnowledgeGraph, output_dir: Path) -> list[Path]:
    produced: list[Path] = []
    if not graph.flow_diagrams:
        return produced

    pou_dir = output_dir / "pou"
    pou_dir.mkdir(parents=True, exist_ok=True)

    for pou_name, diagram in sorted(graph.flow_diagrams.items()):
        path = pou_dir / f"{pou_name}.flow.md"
        lines = [
            f"# {pou_name} — Flow Diagram",
            "",
            f"- Diagram type: {diagram.diagram_type}",
            f"- Confidence: {diagram.confidence}",
            f"- Source: {diagram.source}",
            "",
        ]
        if diagram.narrative:
            lines += ["## Narrative", "", diagram.narrative, ""]
        lines += ["```mermaid", diagram.mermaid_code, "```", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
        produced.append(path)

    return produced


def _to_mermaid(extracted: FlowExtractionResult) -> str:
    if extracted.diagram_type == "stateDiagram-v2":
        return _state_mermaid(extracted)
    return _flowchart_mermaid(extracted)


def _state_mermaid(extracted: FlowExtractionResult) -> str:
    lines = ["stateDiagram-v2"]
    seen = {"start"}

    for edge in extracted.edges:
        src = _safe_id(edge.source)
        tgt = _safe_id(edge.target)
        label = f" : {edge.label}" if edge.label else ""
        if edge.source == "start":
            lines.append(f"    [*] --> {tgt}{label}")
        else:
            lines.append(f"    {src} --> {tgt}{label}")
        seen.add(edge.target)

    for node in extracted.nodes:
        if node.node_type == "state" and node.node_id not in seen:
            lines.append(f"    {node.node_id}")

    return "\n".join(lines)


def _flowchart_mermaid(extracted: FlowExtractionResult) -> str:
    lines = ["flowchart TD"]
    for node in extracted.nodes:
        if node.node_type == "branch":
            lines.append(f'    {_safe_id(node.node_id)}{{"{node.label}"}}')
        elif node.node_type == "start":
            lines.append(f'    {_safe_id(node.node_id)}(("{node.label}"))')
        else:
            lines.append(f'    {_safe_id(node.node_id)}["{node.label}"]')

    for edge in extracted.edges:
        label = f' | {edge.label} |' if edge.label else ""
        lines.append(f"    {_safe_id(edge.source)} -->{label} {_safe_id(edge.target)}")

    return "\n".join(lines)


def _safe_id(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)