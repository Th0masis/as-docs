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

# GitHub credentials are resolved automatically (see Authentication below).
# Optionally set GITHUB_TOKEN to override:
# $env:GITHUB_TOKEN = "<token>"

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

- `provider`: `copilot` (default) or `anthropic` fallback
- `model`: provider-specific model name (for example `gpt-4.1` for Copilot, `claude-3-5-sonnet-latest` for Anthropic)
- `api_base_url`: optional provider endpoint override (Copilot SDK provider config or Anthropic-compatible gateway)
- `api_key_env`: primary environment variable name used for provider authentication

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

Provider quick examples:

```yaml
# Copilot (default)
ai:
  provider: "copilot"
  model: "gpt-4.1"
  api_key_env: "GITHUB_TOKEN"
```

```yaml
# Anthropic fallback
ai:
  provider: "anthropic"
  model: "claude-3-5-sonnet-latest"
  api_key_env: "ANTHROPIC_API_KEY"
```

## AI Generation and Enrichment (Copilot SDK Aligned)

This project performs AI enrichment through provider clients and normalizes strict JSON into the knowledge graph.

Default runtime is Copilot SDK. Anthropic is implemented as a fallback provider for users without GitHub Copilot.

After reviewing `github/copilot-sdk`, the recommended mental model for generation and enrichment is:

- **Session-based generation**: create a session with an explicit model (for example `gpt-5`/`gpt-4.1`) and stream or wait for completion
- **Tool-augmented enrichment**: expose analyzers/retrievers as tools so the model can fetch only the context it needs
- **MCP-first integrations**: attach local/remote MCP servers and scope allowed tools (`["*"]`, specific names, or `[]`)
- **Hooked post-processing**: use pre/post tool hooks to inject extra context, modify results, or suppress noisy output before final enrichment text is applied
- **Agent specialization**: separate read-only analysis from write/update actions using custom agents with scoped tool sets

How this maps to `as-docs` today:

- **Implemented now**: direct Copilot SDK runtime, Anthropic runtime fallback, deterministic enrichment prompts, provider/model-aware cache keys, strict JSON normalization, and enrichment write-back into `knowledge_graph.json`
- **Optional compatibility mode**: set `ai.api_base_url` to route through a custom endpoint for the selected provider

Suggested operational pattern for reliable enrichment quality:

1. Keep Level 2/3 prompts schema-first (JSON contract first, prose second).
2. Use small, task/POU-specific prompts to reduce hallucinated cross-module assumptions.
3. Treat cache as provider+model scoped (already implemented) to avoid cross-model contamination.
4. Re-run enrichment only for changed POUs/tasks (`as-docs diff` + targeted cache clear) to keep costs and drift low.

## Authentication

Copilot provider resolves a GitHub token automatically from the first available source:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 | Env var named by `ai.api_key_env` | Default: `GITHUB_TOKEN` |
| 2 | `GH_TOKEN` env var | Standard GitHub CLI variable |
| 3 | `gh auth token` | Token managed by VS Code GitHub extension or GitHub CLI |

After a token is found, `as-docs` calls the GitHub API to confirm the login and verify an active Copilot subscription before initializing the SDK. If none of the sources yield a token, or the account has no Copilot entitlement, startup is refused with a clear error message.

The raw token is **never stored on the provider object** — the Copilot SDK auto-discovers the VS Code session at runtime.

Anthropic provider reads the key from `ai.api_key_env` (for example `ANTHROPIC_API_KEY`) and initializes the Anthropic SDK directly.

## Current Phase 3 Status

- Implemented: FastMCP server with stdio and HTTP transports (`as-docs serve`, `as-docs serve --http --port 8765`)
- Implemented read tools: `get_overview`, `get_pou_list`, `get_pou`, `get_task`, `find_variable`, `get_data_flow`, `get_call_graph`, `get_global_vars`, `search`, `get_flow_diagram`
- Implemented action tools: `regenerate`, `get_cache_status`, `upgrade`
- Implemented level-aware MCP responses with `status: partial`, `available_level`, `requested_level`, and upgrade hints when a higher level is required
- Implemented MCP payload + behavior tests for Phase 3 (`tests/test_phase3_mcp_server.py`)
- Current limitation: scoped `regenerate` (`changed`, `pou:NAME`) and `upgrade --pou` routes are exposed but currently execute full regeneration with an explicit warning until true scoped execution is added

## Requirements

- Python 3.11+
- B&R Automation Studio 4.x project
- One AI provider credential path:
  - GitHub account with active Copilot subscription (token resolved automatically), or
  - Anthropic API key in the environment variable configured by `ai.api_key_env`
