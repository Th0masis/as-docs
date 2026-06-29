# as-docs

Documentation generation tool for **B&R Automation Studio (AS) projects** written in Structured Text (IEC 61131-3 ST).

Parses AS project files, extracts structural and semantic information, optionally enriches with AI-generated descriptions, and outputs documentation in multiple formats — readable by both humans and AI agents.

## Documentation Index

- `README.md` — quick start, CLI commands, configuration, and current implementation status
- `as-docs-architecture.md` — full architecture, data model, implementation phases, and decisions
- `EXECUTION_CHECKLIST.md` — live execution tracker for prioritized remaining work
- `.as-docs.yaml.example` — complete configuration template with comments

## Features

- **Level 1** — Project map: task list, call graph, global variables, data types (zero AI calls, instant)
- **Level 2** — Task enrichment pipeline: AI-generated task summaries stored in the knowledge graph and reused via cache
- **Level 3** — POU enrichment pipeline: AI-generated POU descriptions, responsibilities, patterns, and notes stored in the knowledge graph
- **Level 4** — Flow diagrams: parser-first behavioral Mermaid diagrams with AI enrichment fallback
- **Nested packages** — Recursive AS6 Package.pkg traversal discovers POUs in hierarchical structures (Infrastructure, Charts, Wizard, etc.); identifies package_path for every POU
- **AI cache** — Provider/model-separated cache for Level 2 and Level 3 enrichment
- **MCP server** — FastMCP server for AI agent integration (Claude Code, VS Code Copilot)
- **Standalone binary** — optional PyInstaller build for a zero-Python `as-docs-server.exe`

## Installation

```bash
pipx install as-docs
```

For the optional standalone build tooling:

```bash
pip install -e .[standalone]
```

Or for development:

```bash
git clone <repo>
cd as-docs
pip install -e .
```

## How to Use

1. Run `as-docs init` inside an Automation Studio project to create `.as-docs.yaml`.
2. Run `as-docs generate --no-ai` for a fast Level 1 pass, or `as-docs generate` for the default Level 3 output.
3. Use `as-docs status` to check freshness and `as-docs serve` when connecting through MCP clients.
4. For iterative updates, use `as-docs upgrade --to 3 --pou MainProgram` or `as-docs watch`.

## Quick Start

```bash
# In your AS project directory (or any subdirectory)
as-docs init                    # detect project root, create .as-docs.yaml

# GitHub credentials are resolved automatically (see Authentication below).
# Optionally set GITHUB_TOKEN to override auto-detection:
# $env:GITHUB_TOKEN = "<token>"

# Generate Level 1 docs (no AI, instant)
# Automatically detects and recursively scans nested packages (AS6)
as-docs generate --no-ai

# Generate docs with AI enrichment (Level 3 default)
as-docs generate

# Check freshness (shows all discovered POUs, including nested)
as-docs status

# For projects with deep or circular package hierarchies, adjust:
# recursive_packages: false       (disable recursive scanning)
# max_recursion_depth: 5          (reduce depth limit)
```

## Documentation Levels

| Level | AI Calls | Time | Output |
|-------|----------|------|--------|
| 1 | 0 | seconds | overview, architecture, global vars, data types |
| 2 | 1 per task | ~45s | enriched task data in `knowledge_graph.json`, data flow diagram |
| 3 | 1 per POU | ~3min cold | enriched POU data in `knowledge_graph.json`, complete knowledge graph |
| 4 | 0–1 per POU | planned | behavioral flow diagrams (Phase 6) |

## MCP Server

```bash
as-docs serve                   # stdio (default, used by MCP clients)
as-docs serve --http --port 8765
```

## Standalone Binary (Phase 7)

The planned standalone executable uses PyInstaller and installs under the same Windows app-data convention as the sibling MCP tools:

- Windows default: `%APPDATA%\as-docs-mcp\as-docs-server.exe`
- Linux/macOS default: `~/.local/share/as-docs-mcp/as-docs-server`

Build a local binary with:

```bash
python scripts/build_standalone.py --dry-run
python scripts/build_standalone.py
```

If you only want to inspect the plan, keep `--dry-run`. The helper prints the exact PyInstaller command and output paths.

The standalone build is optional. Normal development and MCP use still run through the Python package and `as-docs serve`.

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
as-docs init [--http] [--mcp]             # setup
as-docs generate [--level 1-4] [--no-ai] # generate docs
as-docs upgrade --to N [--pou NAME]       # upgrade to higher level
as-docs status                            # freshness report
as-docs cache clear [--pou NAME]          # clear AI cache
as-docs serve [--http --port 8765]        # MCP server
as-docs watch [--level N] [--debounce-ms N] # daemon mode
as-docs install-hook [--yes] [--force]     # git post-commit hook
as-docs diff HEAD~1                       # changed POUs since commit
```

Scoped behavior notes:
- `as-docs upgrade --to N --pou NAME` performs scoped regeneration for the selected POU.
- MCP `regenerate(scope)` supports `all`, `changed`, and `pou:NAME`, and returns touched POU metadata.
- `as-docs init --mcp` creates or updates `.vscode/mcp.json` with an `as-docs` MCP entry.

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

Copilot provider can authenticate via the Copilot SDK session (Copilot CLI backend). In addition, it attempts token-based GitHub preflight checks when a token is available from the first source below:

| Priority | Source | Notes |
|----------|--------|-------|
| 1 | Direct token in `ai.api_key_env` | If value looks like `ghp_...`/`github_pat_...` |
| 2 | Env var named by `ai.api_key_env` | Default: `GITHUB_TOKEN` |
| 3 | `GH_TOKEN`/`GITHUB_TOKEN` env var | Standard GitHub variables |
| 4 | `gh auth token` | GitHub CLI token |
| 5 | `git credential fill` (`https://github.com`) | Git Credential Manager / git credential helper |
| 6 | Windows Credential Manager target `vscode.github-authentication` | VS Code GitHub Authentication extension session |
| 7 | Cached device-flow token (`~/.config/as-docs/github_token`) | Reuses prior interactive login |
| 8 | Interactive OAuth device flow | Requires `ai.oauth_client_id` or `AS_DOCS_OAUTH_CLIENT_ID` |

If a token is found, `as-docs` performs a best-effort GitHub preflight (login + Copilot entitlement check). Preflight is non-blocking: failures are logged and the provider continues with SDK auth.

To inspect auth/runtime decisions, run with verbose mode:

```bash
as-docs -v generate --level 3
```

Look for `Resolved GitHub credential source: ...` in logs.

The raw token is **never stored on the provider object** — the Copilot SDK handles runtime auth discovery/session use.

Anthropic provider reads the key from `ai.api_key_env` (for example `ANTHROPIC_API_KEY`) and initializes the Anthropic SDK directly.

## Current Status (2026-06-25)

- Implemented: FastMCP server with stdio and HTTP transports (`as-docs serve`, `as-docs serve --http --port 8765`)
- Implemented read tools: `get_overview`, `get_pou_list`, `get_pou`, `get_task`, `find_variable`, `get_data_flow`, `get_call_graph`, `get_global_vars`, `search`, `get_flow_diagram`
- Implemented action tools: `regenerate`, `get_cache_status`, `upgrade`
- Implemented level-aware MCP responses with `status: partial`, `available_level`, `requested_level`, and upgrade hints when a higher level is required
- Implemented MCP payload + behavior tests for Phase 3 (`tests/test_phase3_mcp_server.py`)
- Implemented scoped regeneration for `regenerate(scope)` and scoped CLI upgrades via `upgrade --pou`
- Implemented `as-docs diff`, `as-docs install-hook`, and `as-docs watch` for Phase 4 git integration
- `as-docs watch` now batches file events and regenerates once after the debounce window settles
- Implemented Phase 5 template integration for `as-docs` MCP and GitHub Copilot assets
- Implemented Level 4 flow-diagram pipeline with parser-first extraction, Mermaid output, and AI narrative fallback
- Implemented the standalone packaging plan and build helper for a PyInstaller-based `as-docs-server` executable

See `EXECUTION_CHECKLIST.md` for the live prioritized execution tracker.

## Requirements

- Python 3.11+
- B&R Automation Studio 4.x project
- One AI provider credential path:
  - GitHub account with active Copilot subscription (token resolved automatically), or
  - Anthropic API key in the environment variable configured by `ai.api_key_env`
