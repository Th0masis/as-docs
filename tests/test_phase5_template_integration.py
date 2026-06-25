from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_as_docs_template_assets_exist() -> None:
    base = ROOT / "agentic-engineering-in-automation-studio" / "copilot"

    expected_files = [
        base / "mcp" / "as-docs" / "README.md",
        base / "mcp" / "as-docs" / "mcp.json",
        base / "template" / ".github" / "skills" / "as-docs" / "SKILL.md",
        base / "template" / ".github" / "instructions" / "as-project-documentation.instructions.md",
        base / "template" / ".github" / "collections" / "as-project-documentation.collection.yml",
        base / "template" / ".github" / "agents" / "as-project.agent.md",
    ]

    for path in expected_files:
        assert path.exists(), f"Missing expected template asset: {path}"


def test_as_docs_template_assets_are_linked() -> None:
    agent = (ROOT / "agentic-engineering-in-automation-studio" / "copilot" / "template" / ".github" / "agents" / "as-project.agent.md").read_text(encoding="utf-8")
    collection = (ROOT / "agentic-engineering-in-automation-studio" / "copilot" / "template" / ".github" / "collections" / "as-project-documentation.collection.yml").read_text(encoding="utf-8")
    instruction = (ROOT / "agentic-engineering-in-automation-studio" / "copilot" / "template" / ".github" / "instructions" / "as-project-documentation.instructions.md").read_text(encoding="utf-8")

    assert "as-docs" in agent
    assert "as-project-documentation" in collection
    assert "as-docs" in instruction
