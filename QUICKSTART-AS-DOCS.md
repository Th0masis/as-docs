# as-docs Quick Start Manual

A short guide to get as-docs running and connected as an MCP server.

## 1) Install

```bash
pipx install as-docs
as-docs --version
```

If you are developing locally from source:

```bash
pip install -e .
as-docs --version
```

## 2) Initialize in your Automation Studio project

Run this inside your AS project directory (or any subdirectory).

```bash
as-docs init
```

What this does:
- Finds project root (must contain Logical and Physical folders)
- Creates .as-docs.yaml
- Adds .as-docs-cache/ and docs/as-docs/ to .gitignore

## 3) Generate documentation

Level 1 only (no AI):

```bash
as-docs generate --no-ai
```

Default generation (Level 3 with AI if enabled):

```bash
as-docs generate
```

Useful options:

```bash
as-docs generate --level 1
as-docs generate --level 2
as-docs generate --level 3
as-docs generate --level 4
```

## 4) Check status and freshness

```bash
as-docs status
```

## 5) Start MCP server

Stdio mode (recommended):

```bash
as-docs serve
```

HTTP mode:

```bash
as-docs serve --http --port 8765
```

## 6) VS Code MCP config

Add this to your user or workspace mcp.json:

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

If config auto-detection is not reliable for your setup, pass config path explicitly:

```json
{
  "mcpServers": {
    "as-docs": {
      "command": "as-docs",
      "args": ["serve", "--config", "C:/path/to/.as-docs.yaml"]
    }
  }
}
```

## 7) First MCP queries to try

- project overview
- list all POUs
- show call graph for MainProgram
- find readers and writers of gMotorSpeed
- show cross-task data flow

## 8) Troubleshooting

- "No generated docs found": run as-docs generate first.
- "Cannot find AS project root": run in a directory under the AS project containing Logical and Physical.
- MCP server not visible in chat: reload VS Code window or restart chat/MCP session after editing mcp.json.
- AI issues: run `as-docs -v generate --level 3` and check `Resolved GitHub credential source: ...`.
  - If source is `none`, set `GITHUB_TOKEN` or configure Git Credential Manager / `gh auth login`.

## Recommended daily workflow

```bash
as-docs status
as-docs generate
as-docs serve
```
