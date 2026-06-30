# as-docs

Documentation generation tool for **B&R Automation Studio (AS) projects** written in Structured Text (IEC 61131-3 ST).

Parses AS project files, extracts structural and semantic information, optionally enriches with AI-generated descriptions, and outputs documentation in multiple formats — readable by both humans and AI agents.

## Documentation Index

- `README.md` — this file: quick start, CLI commands, configuration, and current implementation status
- `as-docs-architecture.md` — full architecture, data model, phases 1-7, and design decisions
- `CHANGELOG.md` — version history and release notes
- `docs/AS_CLI_INTEGRATION_ARCHITECTURE.md` — detailed as-cli integration architecture and data flow
- `docs/PHASE_2_7_VALIDATION_REPORT.md` — Phase 2.7 test coverage report and validation checklist
- `.as-docs.yaml.example` — complete configuration template with detailed comments

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

## Commands

All `as-docs` functionality is accessed via the CLI. Use `as-docs --help` for a full command list, or `as-docs <command> --help` for detailed options.

### `as-docs init`
Initialize a new as-docs project.
```bash
as-docs init                # Create .as-docs.yaml in project root
as-docs init --mcp          # Also configure MCP support in .vscode/mcp.json
as-docs init --http         # Configure HTTP transport for MCP (default: stdio)
```

**What it does:**
- Detects the AS project root (looks for `Logical/` and `Physical/` directories)
- Creates `.as-docs.yaml` with default configuration
- Updates `.gitignore` to exclude cache and generated documentation
- Optionally configures VS Code MCP integration

---

### `as-docs generate`
Generate documentation for the AS project.
```bash
as-docs generate                              # Generate with default level (from config)
as-docs generate --level 1                    # Level 1 (project map, no AI)
as-docs generate --level 3                    # Level 3 (with AI enrichment)
as-docs generate --no-ai                      # Force Level 1 (skip AI)
as-docs generate --use-as-cli                 # Enable as-cli integration
as-docs generate --scope changed              # Regenerate only changed POUs
as-docs generate --scope pou:MainProgram      # Regenerate a single POU
```

**Options:**
- `--level N` — Documentation level (1–4). Default from config (usually 3)
- `--no-ai` — Skip AI enrichment (force Level 1)
- `--use-as-cli` — Enable as-cli integration (if available)
- `--scope all|changed|pou:<name>` — Regeneration scope (default: all)
- `--config <path>` — Path to .as-docs.yaml (auto-detected by default)

**Documentation Levels:**
- **Level 1:** Project structure (tasks, POUs, variables, call graphs) — instant, no AI calls
- **Level 2:** Task descriptions and responsibilities — AI enrichment for tasks
- **Level 3:** POU descriptions, patterns, and notes — full AI enrichment
- **Level 4:** Behavioral flow diagrams (Mermaid) — AI-assisted diagram generation

---

### `as-docs status`
Show documentation freshness and POU inventory.
```bash
as-docs status              # List all POUs with freshness state
```

**Output states:**
- `fresh` — Source code matches documented version
- `stale` (!) — Source code has changed since documentation was generated
- `missing` (?) — Documentation not yet generated

Use this to identify which POUs need regeneration.

---

### `as-docs upgrade`
Upgrade documentation to a higher level.
```bash
as-docs upgrade --to 2                        # Upgrade all POUs to Level 2
as-docs upgrade --to 3 --pou MainProgram      # Upgrade one POU to Level 3
```

**Options:**
- `--to N` — Target level (2, 3, or 4)
- `--pou <name>` — Optional: upgrade only this POU (default: all)

Useful for incrementally enriching documentation with AI.

---

### `as-docs cache clear`
Clear cached AI responses.
```bash
as-docs cache clear                    # Clear entire cache
as-docs cache clear --pou MainProgram  # Clear cache for one POU
```

Use after updating AI provider/model settings or to force re-enrichment.

---

### `as-docs serve`
Start the MCP (Model Context Protocol) server.
```bash
as-docs serve                  # Start on stdio (default)
as-docs serve --http           # Start on HTTP (port 8765)
as-docs serve --http --port 9000
```

**Use with:**
- VS Code Copilot Chat (configure via `.vscode/mcp.json` or `--mcp` flag)
- Claude Desktop or other AI clients
- Custom MCP applications

---

### `as-docs watch`
Watch for source changes and regenerate automatically.
```bash
as-docs watch                   # Watch Level 1 docs (default)
as-docs watch --level 2         # Watch with AI enrichment
as-docs watch --debounce-ms 1000
```

**Options:**
- `--level N` — Documentation level to maintain (default: 1)
- `--debounce-ms MS` — Wait time before regenerating after file change (default: 500)

Runs as a daemon. Press `Ctrl+C` to stop. Useful during development.

---

### `as-docs diff`
Show which POUs changed since a git reference.
```bash
as-docs diff                         # Changes since HEAD~1
as-docs diff HEAD~2                  # Changes since 2 commits ago
as-docs diff main                    # Changes since main branch
```

**Output:**
- List of changed files
- List of affected POUs
- Suggested commands to upgrade just those POUs

Useful for CI/CD and selective documentation updates.

---

### `as-docs install-hook`
Install a git post-commit hook for automatic documentation regeneration.
```bash
as-docs install-hook            # Install with confirmation
as-docs install-hook --yes      # Install without prompt
as-docs install-hook --force    # Replace any existing hook
```

**What it does:**
- Installs a `.git/hooks/post-commit` script
- Automatically regenerates documentation after each commit
- Level is determined by `git.auto_level` in config (default: 2)
- Gracefully skips if as-docs is not available

---

### `as-docs as-cli-check`
Diagnose as-cli integration status.
```bash
as-docs as-cli-check
```

**Checks:**
1. Configuration display
2. as-cli availability (installed, in PATH)
3. Daemon connectivity
4. Command availability (logical_list, symbol_search)
5. Configuration recommendations

Use when troubleshooting as-cli integration issues.

---

## as-cli Integration

**Automation Studio Project Discovery via as-cli**

For improved project discovery and more accurate POU detection (especially with nested packages), `as-docs` can optionally use [as-cli](https://github.com/br-automation-com/as-cli), a C# CLI tool for B&R Automation Studio.

### What is as-cli?

- Windows-only command-line tool for Automation Studio project inspection
- Daemon-based architecture using Windows named pipes
- Provides accurate `logical_list` (modules, tasks, programs) and `symbol_search` (all symbols)
- Catches implicit programs and nested package hierarchies that filesystem scanning may miss

### Setup

1. **Install as-cli** from the [official repository](https://github.com/br-automation-com/as-cli)
2. **Enable in config** (`.as-docs.yaml`):
   ```yaml
   as_cli:
     enabled: true
     path: "as-cli"           # auto-detect from PATH
     timeout_ms: 30000        # per-command timeout
     strict: false            # graceful fallback (recommended)
     use_commands:
       - logical_list
       - symbol_search
   ```
3. **Test availability** with the diagnostic command:
   ```bash
   as-docs as-cli-check
   ```

### Usage

**Option 1: Enable in config (persistent)**
```bash
as-docs generate              # uses as-cli if enabled in .as-docs.yaml
```

**Option 2: CLI flag (one-time override)**
```bash
as-docs generate --use-as-cli  # enable for this run, regardless of config
```

### Merge Strategy

When as-cli is enabled and available:
- `as-docs` scans the filesystem *and* queries as-cli independently
- Results are merged using a **union strategy**: all POUs from both sources are included
- **as-cli is the source of truth** for conflicts (e.g., POU path or type differs)
- A **conflict report** is generated and saved to `docs/as-docs/as_cli_conflicts.json`
- Conflict report is also displayed in the CLI output under `[as-cli Merge Report]`

### Graceful Fallback (Recommended)

Default configuration uses **graceful fallback mode** (`strict: false`):
- If as-cli is unavailable or errors occur, `as-docs` automatically falls back to filesystem scanning
- No errors or warnings — documentation generation completes successfully
- **Zero changes to existing workflows** if as-cli is not installed

### Strict Mode (Optional)

For strict validation, set `strict: true`:
```yaml
as_cli:
  enabled: true
  strict: true    # fail if as-cli is unavailable or errors occur
```

This is useful in CI/CD pipelines where you want to guarantee accurate discovery.

### Troubleshooting

Run the diagnostic command to check as-cli integration status:
```bash
as-docs as-cli-check
```

This performs 5 checks:
1. **Configuration Display** — shows current as_cli settings
2. **Availability Check** — verifies as-cli is installed and in PATH
3. **Daemon Connectivity** — confirms connection or auto-start
4. **Command Availability** — tests logical_list and symbol_search
5. **Recommendations** — suggests next steps based on config state

Example output:
```
🔧  Diagnosing as-cli integration...

1️⃣   Configuration:
    Enabled: True
    Path: as-cli
    Timeout: 30000ms
    Strict mode: False
    Commands: logical_list, symbol_search

2️⃣   Availability check:
    ✅  as-cli is installed and accessible

3️⃣   Daemon connectivity:
    ✅  Connected to daemon (or started new one)

4️⃣   Command availability:
    ✅  logical_list: 5 modules found
    ✅  symbol_search: 142 symbols found

5️⃣   Recommendations:
    • as-cli is enabled in config ✓
    • Running in graceful fallback mode (recommended)

✅  Diagnostic complete!
```

### When to Use as-cli

- **Recommended:** Projects with nested packages (AS6+) or complex hierarchies
- **Optional:** Small projects where filesystem scanning is sufficient
- **Required:** If you need guaranteed detection of implicit programs

For most users, **filesystem scanning is sufficient**. Enable as-cli only if you encounter missed POUs.

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
as-docs init [--http] [--mcp]                    # setup
as-docs generate [--level 1-4] [--no-ai] [--use-as-cli] # generate docs (optionally with as-cli)
as-docs as-cli-check                             # diagnose as-cli integration
as-docs upgrade --to N [--pou NAME]              # upgrade to higher level
as-docs status                                   # freshness report
as-docs cache clear [--pou NAME]                 # clear AI cache
as-docs serve [--http --port 8765]               # MCP server
as-docs watch [--level N] [--debounce-ms N]      # daemon mode
as-docs install-hook [--yes] [--force]           # git post-commit hook
as-docs diff HEAD~1                              # changed POUs since commit
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

## Current Status (2026-06-30)

**Phase 2.5 - CLI Updates (COMPLETE)**
- ✅ `--use-as-cli` flag for `generate` command with CLI > config > default precedence
- ✅ `as-cli-check` diagnostic command with 5-step troubleshooting workflow
- ✅ 11 comprehensive CLI integration tests (100% passing)
- ✅ Backward compatibility maintained (default: as_cli.enabled=false)

**Phases 1-2.4 - as-cli Integration (COMPLETE)**
- ✅ Config system with AsCliConfig validation
- ✅ AsCliAdapter for subprocess execution and daemon lifecycle
- ✅ DataConflictResolver for smart merge and conflict reporting
- ✅ Engine integration with graceful fallback and strict mode
- ✅ 84 unit tests (100% passing)

**Phases 0-4 - Core as-docs (COMPLETE)**
- Implemented: FastMCP server with stdio and HTTP transports (`as-docs serve`, `as-docs serve --http --port 8765`)
- Implemented read tools: `get_overview`, `get_pou_list`, `get_pou`, `get_task`, `find_variable`, `get_data_flow`, `get_call_graph`, `get_global_vars`, `search`, `get_flow_diagram`
- Implemented action tools: `regenerate`, `get_cache_status`, `upgrade`
- Implemented level-aware MCP responses with `status: partial`, `available_level`, `requested_level`, and upgrade hints
- Implemented scoped regeneration for `regenerate(scope)` and scoped CLI upgrades via `upgrade --pou`
- Implemented `as-docs diff`, `as-docs install-hook`, and `as-docs watch` for git integration
- `as-docs watch` batches file events and regenerates once after debounce window
- Implemented Phase 5 template integration for `as-docs` MCP and GitHub Copilot assets
- Implemented Level 4 flow-diagram pipeline with parser-first extraction and AI narrative fallback
- Implemented standalone packaging plan and build helper for PyInstaller-based `as-docs-server` executable

**Total: 173 tests passing** (11 CLI + 162 existing)

See `EXECUTION_CHECKLIST.md` for the live prioritized execution tracker.

## Requirements

- Python 3.11+
- B&R Automation Studio 4.x project
- One AI provider credential path:
  - GitHub account with active Copilot subscription (token resolved automatically), or
  - Anthropic API key in the environment variable configured by `ai.api_key_env`
