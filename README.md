# as-docs

Documentation generation tool for **B&R Automation Studio (AS) projects** written in Structured Text (IEC 61131-3 ST).

Parses AS project files, extracts structural and semantic information, optionally enriches with AI-generated descriptions, and outputs documentation in multiple formats — readable by both humans and AI agents.

## Features

- **Level 1** — Project map: task list, call graph, global variables, data types (zero AI calls, instant)
- **Level 2** — Task overviews: AI-generated task descriptions, cross-task data coupling
- **Level 3** — POU detail: full per-block documentation with patterns, interfaces, cross-references
- **Level 4** — Flow diagrams: parser-first behavioral Mermaid diagrams with AI enrichment
- **MCP server** — FastMCP server for AI agent integration (Claude Code, VS Code Copilot)

## Installation

```bash
pipx install as-docs
```

Or for development:

```bash
git clone <repo>
cd as-docs
pip install -e .
```

## Quick Start

```bash
# In your AS project directory (or any subdirectory)
as-docs init                    # detect project root, create .as-docs.yaml

# Generate Level 1 docs (no AI, instant)
as-docs generate --no-ai

# Generate full docs with AI descriptions (Level 3 default)
as-docs generate

# Check freshness
as-docs status
```

## Documentation Levels

| Level | AI Calls | Time | Output |
|-------|----------|------|--------|
| 1 | 0 | seconds | overview, architecture, global vars, data types |
| 2 | 1 per task | ~45s | task descriptions, data flow diagram |
| 3 | 1 per POU | ~3min cold | full POU docs, complete knowledge graph |
| 4 | 0–1 per POU | ~6min cold | behavioral flow diagrams |

## MCP Server

```bash
as-docs serve                   # stdio (default, used by MCP clients)
as-docs serve --http --port 8765
```

Add to `.vscode/mcp.json`:
```json
{
  "mcpServers": {
    "as-docs": {
      "command": "as-docs",
      "args": ["serve"]
    }
  }
}
```

## CLI Reference

```bash
as-docs init                              # setup
as-docs generate [--level 1-4] [--no-ai] # generate docs
as-docs upgrade --to N [--pou NAME]       # upgrade to higher level
as-docs status                            # freshness report
as-docs cache clear [--pou NAME]          # clear AI cache
as-docs serve [--http --port 8765]        # MCP server
as-docs watch [--level N]                 # daemon mode
as-docs install-hook                      # git post-commit hook
as-docs diff HEAD~1                       # changed POUs since commit
```

## Configuration

Copy `.as-docs.yaml.example` to `.as-docs.yaml` in your AS project root and edit as needed.

## Requirements

- Python 3.11+
- B&R Automation Studio 4.x project
- Anthropic API key (for Level 2+): set `ANTHROPIC_API_KEY` environment variable
