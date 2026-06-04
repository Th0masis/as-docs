# as-docs

Documentation generation tool for **B&R Automation Studio (AS) projects** written in Structured Text (IEC 61131-3 ST).

Parses AS project files, extracts structural and semantic information, optionally enriches with AI-generated descriptions, and outputs documentation in multiple formats — readable by both humans and AI agents.

## Documentation Index

- `README.md` — quick start, CLI commands, configuration, and current implementation status
- `as-docs-architecture.md` — full architecture, data model, implementation phases, and decisions
- `.as-docs.yaml.example` — complete configuration template with comments

## Features

- **Level 1** — Project map: task list, call graph, global variables, data types (zero AI calls, instant)
- **Level 2** — Task enrichment pipeline: AI-generated task summaries stored in the knowledge graph and reused via cache
- **Level 3** — POU enrichment pipeline: AI-generated POU descriptions, responsibilities, patterns, and notes stored in the knowledge graph
- **Level 4** — Flow diagrams: parser-first behavioral Mermaid diagrams with AI enrichment
- **AI cache** — Provider/model-separated cache for Level 2 and Level 3 enrichment
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

# Set token for Copilot/GitHub Models compatible endpoint
$env:GITHUB_TOKEN = "<token>"

# Generate Level 1 docs (no AI, instant)
as-docs generate --no-ai

# Generate docs with AI enrichment (Level 3 default)
as-docs generate

# Check freshness
as-docs status
```

## Documentation Levels

| Level | AI Calls | Time | Output |
|-------|----------|------|--------|
| 1 | 0 | seconds | overview, architecture, global vars, data types |
| 2 | 1 per task | ~45s | enriched task data in `knowledge_graph.json`, data flow diagram |
| 3 | 1 per POU | ~3min cold | enriched POU data in `knowledge_graph.json`, complete knowledge graph |
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

AI provider settings are under `ai:`:

- `provider`: `copilot` is the active Phase 2 runtime provider; `anthropic` is reserved but not enabled in this branch
- `model`: model name passed to the Copilot SDK session
- `api_base_url`: optional custom OpenAI/Azure endpoint (BYOK) passed through Copilot SDK provider config
- `api_key_env`: environment variable that stores the access token

Example:

```yaml
ai:
  enabled: true
  provider: "copilot"
  model: "gpt-4.1"
  api_base_url: ""
  api_key_env: "GITHUB_TOKEN"
  timeout_seconds: 60
  max_retries: 3
  cache_dir: ".as-docs-cache"
```

## AI Generation and Enrichment (Copilot SDK Aligned)

This project performs AI enrichment through the Copilot SDK session API and normalizes strict JSON into the knowledge graph.

After reviewing `github/copilot-sdk`, the recommended mental model for generation and enrichment is:

- **Session-based generation**: create a session with an explicit model (for example `gpt-5`/`gpt-4.1`) and stream or wait for completion
- **Tool-augmented enrichment**: expose analyzers/retrievers as tools so the model can fetch only the context it needs
- **MCP-first integrations**: attach local/remote MCP servers and scope allowed tools (`["*"]`, specific names, or `[]`)
- **Hooked post-processing**: use pre/post tool hooks to inject extra context, modify results, or suppress noisy output before final enrichment text is applied
- **Agent specialization**: separate read-only analysis from write/update actions using custom agents with scoped tool sets

How this maps to `as-docs` today:

- **Implemented now**: direct Copilot SDK session runtime, deterministic enrichment prompts, provider/model-aware cache keys, strict JSON normalization, and enrichment write-back into `knowledge_graph.json`
- **Optional compatibility mode**: set `ai.api_base_url` to route through a custom OpenAI/Azure endpoint via Copilot SDK provider config

Suggested operational pattern for reliable enrichment quality:

1. Keep Level 2/3 prompts schema-first (JSON contract first, prose second).
2. Use small, task/POU-specific prompts to reduce hallucinated cross-module assumptions.
3. Treat cache as provider+model scoped (already implemented) to avoid cross-model contamination.
4. Re-run enrichment only for changed POUs/tasks (`as-docs diff` + targeted cache clear) to keep costs and drift low.

## Current Phase 2 Status

- Implemented: config validation, provider abstraction, copilot runtime client, prompt generation, Level 2/3 enrichment pipeline, cache, CLI visibility, mocked test coverage
- Deferred: anthropic runtime client, provider override flag on CLI, Level 2/3 dedicated markdown page generation
- Current enriched output target: `knowledge_graph.json`; Level 1 markdown files remain the primary human-readable output in this branch

## Requirements

- Python 3.11+
- B&R Automation Studio 4.x project
- GitHub token for the configured endpoint (default env var: `GITHUB_TOKEN`)
