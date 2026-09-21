# as-docs

`as-docs` generates searchable documentation for B&R Automation Studio projects written in Structured Text (IEC 61131-3). It scans the project structure, POUs, tasks, variables, data types, call graph, and data flow, then writes Markdown, JSON, `llms.txt`, and Mermaid output.

It can also enrich the generated documentation with GitHub Copilot or Anthropic, expose the result through an MCP server, and watch a project for changes.

## What You Need

- Python 3.11 or newer
- A B&R Automation Studio 4.x project
- For AI enrichment: either a GitHub account with an active Copilot subscription or an Anthropic API key

## Install

### Recommended: install with `pipx`

`pipx` keeps the CLI isolated while making the `as-docs` command available everywhere.

```bash
python -m pip install --user pipx
python -m pipx ensurepath
pipx install as-docs
```

Restart the terminal after `ensurepath` if the `as-docs` command is not found.

### Install from a checkout

Use this for development or when working on this repository:

```bash
git clone <repository-url>
cd as-docs
python -m pip install -e .
```

The optional standalone build tools are installed with:

```bash
python -m pip install -e ".[standalone]"
```

Check the installation:

```bash
as-docs --version
as-docs --help
```

## GitHub Copilot Authentication

Copilot is the default provider. The simplest setup is to authenticate GitHub once with the GitHub CLI:

```bash
gh auth login
gh auth status
```

Choose `GitHub.com`, HTTPS, and the browser login flow when prompted. `as-docs` can then use the token returned by `gh auth token`.

Other supported credential sources, checked in this order, are:

1. The environment variable named by `ai.api_key_env` (default: `GITHUB_TOKEN`)
2. `GH_TOKEN` or `GITHUB_TOKEN`
3. The GitHub CLI login (`gh auth token`)
4. Git Credential Manager for `https://github.com`
5. The GitHub session already signed in through VS Code on Windows
6. A cached token from a previous device login
7. Optional GitHub OAuth device flow

To use an environment variable instead of the GitHub CLI:

PowerShell:

```powershell
$env:GITHUB_TOKEN = "<your GitHub token>"
as-docs generate --level 3
```

Command Prompt:

```bat
set GITHUB_TOKEN=<your GitHub token>
as-docs generate --level 3
```

The token must belong to a GitHub account with Copilot access. Do not commit tokens to `.as-docs.yaml`, `.env` files, or the repository. Prefer `gh auth login` or a session-only environment variable.

To see which credential source was selected without printing the token:

```bash
as-docs -v generate --level 3
```

Look for `Resolved GitHub credential source` in the log. If authentication fails, run `gh auth status`, confirm that the account has Copilot access, and retry.

### Optional device flow

Device flow requires a GitHub OAuth app client ID. Set it in the config or environment, then run a Copilot generation:

```powershell
$env:AS_DOCS_OAUTH_CLIENT_ID = "<your OAuth app client ID>"
as-docs generate --level 3
```

The prompt will provide a one-time code and GitHub URL. The resulting token is cached under the user's configuration directory.

## Quick Start

Run these commands from an Automation Studio project directory, or one of its subdirectories:

```bash
# Create .as-docs.yaml and update .gitignore
as-docs init

# Fast project map; no AI credentials required
as-docs generate --no-ai

# AI-enriched documentation (Copilot by default)
as-docs generate

# Check generated-documentation freshness
as-docs status
```

`as-docs init` searches upward for the AS project root by looking for `Logical/` and `Physical/`. Generated files are written to `docs/as-docs` and the AI cache is written to `.as-docs-cache`.

If you only want to verify scanning before setting up credentials, use `--no-ai`. Level 1 works without an AI provider.

## Configuration

`as-docs init` creates `.as-docs.yaml`. To create it manually, copy `.as-docs.yaml.example` into the AS project root:

```powershell
Copy-Item .as-docs.yaml.example .as-docs.yaml
```

The default Copilot configuration is:

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

To use Anthropic instead:

```yaml
ai:
  provider: "anthropic"
  model: "claude-3-5-sonnet-latest"
  api_key_env: "ANTHROPIC_API_KEY"
```

Then set the key in the current shell before generating:

```powershell
$env:ANTHROPIC_API_KEY = "<your Anthropic API key>"
as-docs generate --level 3
```

Keep `.as-docs.yaml` project-specific settings in source control, but keep credentials out of it.

## Common Commands

```bash
as-docs generate --level 1                 # project map, no AI
as-docs generate --level 3                 # AI-enriched POU documentation
as-docs generate --scope changed           # regenerate changed POUs
as-docs generate --scope pou:MainProgram  # regenerate one POU
as-docs upgrade --to 3 --pou MainProgram   # upgrade one POU
as-docs status                             # show fresh, stale, and missing docs
as-docs diff HEAD~1                        # show POUs affected by a git change
as-docs cache clear                        # clear all cached AI responses
as-docs cache clear --pou MainProgram      # clear one POU's cache
as-docs watch                              # regenerate after source changes
as-docs install-hook --yes                 # install a post-commit hook
```

Run `as-docs <command> --help` for all options.

## Documentation Levels

| Level | AI calls | Output |
| --- | ---: | --- |
| 1 | 0 | Project structure, tasks, POUs, variables, data types, and call graphs |
| 2 | 1 per task | AI-generated task descriptions and responsibilities |
| 3 | 1 per POU | AI-generated POU descriptions, patterns, responsibilities, and notes |
| 4 | 0-1 per POU | Behavioral flow diagrams with parser-first extraction and AI fallback |

The default level is configured by `output.default_level` and is normally 3. Use `--no-ai` when you need a guaranteed local, credential-free run.

## MCP Server and VS Code

Start the server over stdio for MCP clients:

```bash
as-docs serve
```

Or use HTTP:

```bash
as-docs serve --http --port 8765
```

The easiest VS Code setup is:

```bash
as-docs init --mcp
```

This creates or updates `.vscode/mcp.json` with:

```json
{
  "servers": {
    "as-docs": {
      "command": "as-docs",
      "args": ["serve"]
    }
  }
}
```

Restart or reload the MCP client after changing its configuration.

## Troubleshooting

**`as-docs` is not recognized**

Restart the terminal after installing with `pipx`, or run `python -m pipx ensurepath` again.

**`as-docs init` cannot find the project**

Run it inside an Automation Studio project or a child directory containing `Logical/` and `Physical/`.

**Copilot authentication fails**

Run `gh auth status`, verify the account has an active Copilot subscription, and retry with `as-docs -v generate --level 3`. For a token-based setup, confirm that `GITHUB_TOKEN` or `GH_TOKEN` is set in the same terminal where `as-docs` runs.

**Generation is slow or repeats AI calls**

AI responses are cached by provider, model, and source content. Use `as-docs status` to inspect freshness and `as-docs cache clear --pou NAME` after changing provider or model settings.

**Nested POUs are missing**

Confirm `scanner.recursive_packages: true` and run `as-docs status` to check whether the generated documentation is current.

## Development

Run the test suite from the repository root:

```bash
python -m pip install -e ".[standalone]"
python -m pytest
```

Build the optional standalone executable:

```bash
python scripts/build_standalone.py --dry-run
python scripts/build_standalone.py
```

## Project Documentation

- [Architecture](as-docs-architecture.md)
- [Changelog](CHANGELOG.md)
- [.as-docs.yaml.example](.as-docs.yaml.example)

## License

MIT
