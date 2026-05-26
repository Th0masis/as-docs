"""Click CLI entry points for as-docs."""
from __future__ import annotations
import sys
from pathlib import Path

import click

from as_docs.config import Config, find_project_root, load_config


@click.group()
@click.version_option()
def cli() -> None:
    """as-docs — Documentation generator for B&R Automation Studio projects."""


# ---------------------------------------------------------------------------
# as-docs init
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--http", is_flag=True, help="Configure for HTTP MCP transport.")
def init(http: bool) -> None:
    """Detect AS project root, create .as-docs.yaml, update .gitignore."""
    root = find_project_root()
    if root is None:
        click.echo(
            "❌  Cannot find AS project root (Logical/ + Physical/ not found).\n"
            "    Run 'as-docs init' from within your AS project directory.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"✓  Found AS project root: {root}")

    config_file = root / ".as-docs.yaml"
    if config_file.exists():
        click.echo(f"ℹ  .as-docs.yaml already exists — skipping creation.")
    else:
        example = Path(__file__).parent.parent / ".as-docs.yaml.example"
        if example.exists():
            content = example.read_text(encoding="utf-8")
        else:
            content = _default_config_content(root.name)

        if http:
            content = content.replace('mode: "stdio"', 'mode: "http"')

        config_file.write_text(content, encoding="utf-8")
        click.echo(f"✓  Created .as-docs.yaml")

    # Update .gitignore
    _update_gitignore(root)
    click.echo("✓  Updated .gitignore (.as-docs-cache/ and docs/as-docs/)")
    click.echo("\nNext: as-docs generate --no-ai")


def _update_gitignore(root: Path) -> None:
    gitignore = root / ".gitignore"
    entries = [".as-docs-cache/", "docs/as-docs/"]
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
    else:
        content = ""
    additions = [e for e in entries if e not in content]
    if additions:
        sep = "\n" if content and not content.endswith("\n") else ""
        gitignore.write_text(content + sep + "\n".join(additions) + "\n", encoding="utf-8")


def _default_config_content(project_name: str) -> str:
    return f"""\
project:
  name: "{project_name}"
  as_version: ""
  root: "."
  language: "en"

scanner:
  active_configuration: ""
  ignore_dirs: [Temp, Binaries, Diagnosis]
  scan_libraries: true
  external_lib_prefixes: [Mp, Mc, ACP10, Ar]

ai:
  enabled: true
  model: "claude-sonnet-4-20250514"
  cache_dir: ".as-docs-cache"

server:
  mode: "stdio"
  port: 8765
  host: "127.0.0.1"

output:
  docs_dir: "docs/as-docs"
  formats: [markdown, json, llms.txt]
  mermaid: true
  default_level: 3

git:
  hook_enabled: false
  auto_level: 2
"""


# ---------------------------------------------------------------------------
# as-docs generate
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--level", default=None, type=int, help="Documentation level (1–4). Default from config.")
@click.option("--no-ai", "no_ai", is_flag=True, help="Skip AI enrichment (Level 1 only).")
@click.option("--config", "config_path", default=None, type=click.Path(), help="Path to .as-docs.yaml")
def generate(level: int | None, no_ai: bool, config_path: str | None) -> None:
    """Generate documentation for the AS project."""
    from as_docs.engine import run_generate

    cfg = _load_cfg(config_path)
    effective_level = level if level is not None else (1 if no_ai else cfg.output.default_level)
    ai_enabled = cfg.ai.enabled and not no_ai and effective_level >= 2

    click.echo(f"📖  Generating Level {effective_level} docs for '{cfg.project.name or 'project'}'...")
    if ai_enabled:
        click.echo(f"🤖  AI enrichment enabled (model: {cfg.ai.model})")

    try:
        graph = run_generate(cfg, level=effective_level, ai_enabled=ai_enabled)
        out = Path(cfg.output.docs_dir)
        click.echo(f"\n✅  Done — {len(graph.pous)} POUs, {len(graph.tasks)} tasks")
        click.echo(f"📁  Output: {out.resolve()}")
    except FileNotFoundError as e:
        click.echo(f"❌  {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# as-docs upgrade
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--to", "to_level", required=True, type=int, help="Target level (2, 3, or 4).")
@click.option("--pou", default=None, help="Upgrade a single POU by name.")
@click.option("--config", "config_path", default=None, type=click.Path())
def upgrade(to_level: int, pou: str | None, config_path: str | None) -> None:
    """Upgrade documentation to a higher level."""
    import os
    cfg = _load_cfg(config_path)
    if not cfg.ai.enabled:
        click.echo("❌  AI is disabled in config. Set ai.enabled: true", err=True)
        sys.exit(1)
    if "ANTHROPIC_API_KEY" not in os.environ:
        click.echo("❌  ANTHROPIC_API_KEY environment variable not set.", err=True)
        sys.exit(1)

    scope = f"pou:{pou}" if pou else "all"
    click.echo(f"⬆️   Upgrading to Level {to_level} (scope: {scope})...")
    click.echo("ℹ️   AI enrichment not yet implemented — run 'as-docs generate' for now.")


# ---------------------------------------------------------------------------
# as-docs status
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--config", "config_path", default=None, type=click.Path())
def status(config_path: str | None) -> None:
    """Show current documentation level and per-POU freshness."""
    from as_docs.engine import load_graph, get_staleness

    cfg = _load_cfg(config_path)
    graph = load_graph(cfg)

    if graph is None:
        click.echo("ℹ️   No documentation generated yet. Run: as-docs generate --no-ai")
        return

    click.echo(f"Project: {graph.project_name}")
    click.echo(f"Level:   {graph.level}")
    click.echo(f"Generated: {graph.generated_at[:19].replace('T', ' ')}")
    click.echo(f"POUs:    {len(graph.pous)}")
    click.echo(f"Tasks:   {len(graph.tasks)}")

    staleness = get_staleness(cfg)
    if staleness:
        click.echo("\nPOU freshness:")
        for pou_name, state in sorted(staleness.items()):
            icon = "✓" if state == "fresh" else ("⚠" if state == "stale" else "?")
            click.echo(f"  {icon} {pou_name}: {state}")


# ---------------------------------------------------------------------------
# as-docs cache
# ---------------------------------------------------------------------------

@cli.group()
def cache() -> None:
    """Manage the AI response cache."""


@cache.command("clear")
@click.option("--pou", default=None, help="Clear cache for a single POU.")
@click.option("--config", "config_path", default=None, type=click.Path())
def cache_clear(pou: str | None, config_path: str | None) -> None:
    """Clear cached AI responses."""
    cfg = _load_cfg(config_path)
    cache_dir = Path(cfg.ai.cache_dir)
    if not cache_dir.exists():
        click.echo("Cache directory does not exist — nothing to clear.")
        return
    if pou:
        cleared = 0
        for f in cache_dir.glob(f"{pou}.*"):
            f.unlink()
            cleared += 1
        click.echo(f"Cleared {cleared} cache file(s) for '{pou}'.")
    else:
        import shutil
        shutil.rmtree(cache_dir)
        click.echo("Cache cleared.")


# ---------------------------------------------------------------------------
# as-docs serve
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--http", is_flag=True, help="Use HTTP transport instead of stdio.")
@click.option("--port", default=8765, show_default=True, help="HTTP port.")
@click.option("--config", "config_path", default=None, type=click.Path())
def serve(http: bool, port: int, config_path: str | None) -> None:
    """Start the MCP server (stdio by default, --http for HTTP transport)."""
    try:
        from as_docs.mcp_server import start_server
    except ImportError:
        click.echo("❌  MCP server dependencies not installed. Install with: pip install as-docs[mcp]", err=True)
        sys.exit(1)
    cfg = _load_cfg(config_path)
    start_server(cfg, use_http=http, port=port)


# ---------------------------------------------------------------------------
# as-docs watch
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--level", default=1, show_default=True, type=int)
@click.option("--config", "config_path", default=None, type=click.Path())
def watch(level: int, config_path: str | None) -> None:
    """Watch for file changes and regenerate on save (daemon mode)."""
    click.echo("⚠️   Watch mode not yet implemented.")


# ---------------------------------------------------------------------------
# as-docs install-hook
# ---------------------------------------------------------------------------

@cli.command("install-hook")
@click.option("--config", "config_path", default=None, type=click.Path())
def install_hook(config_path: str | None) -> None:
    """Install a git post-commit hook for automatic doc regeneration."""
    click.echo("⚠️   Git hook installation not yet implemented.")


# ---------------------------------------------------------------------------
# as-docs diff
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("ref", default="HEAD~1")
@click.option("--config", "config_path", default=None, type=click.Path())
def diff(ref: str, config_path: str | None) -> None:
    """Show which POUs changed since a git ref."""
    click.echo("⚠️   Git diff integration not yet implemented.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_cfg(config_path: str | None) -> Config:
    p = Path(config_path) if config_path else None
    return load_config(p)
