"""Click CLI entry points for as-docs."""

from __future__ import annotations
import json
import logging
import sys
import time
from pathlib import Path

import click
from git import InvalidGitRepositoryError, Repo
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from as_docs.config import Config, find_project_root, load_config
from as_docs.scanner.as_cli_adapter import AsCliAdapter, AsCliError


@click.group()
@click.version_option()
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable DEBUG logging.",
    envvar="AS_DOCS_VERBOSE",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """as-docs — Documentation generator for B&R Automation Studio projects."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)-8s %(name)s — %(message)s",
    )


# ---------------------------------------------------------------------------
# as-docs init
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--http", is_flag=True, help="Configure for HTTP MCP transport.")
@click.option(
    "--mcp",
    is_flag=True,
    help="Create or update .vscode/mcp.json with an as-docs server entry.",
)
def init(http: bool, mcp: bool) -> None:
    """Detect AS project root, create .as-docs.yaml, update .gitignore."""
    root = find_project_root()
    if root is None:
        click.echo(
            "ERROR: Cannot find AS project root (Logical/ + Physical/ not found).\n"
            "    Run 'as-docs init' from within your AS project directory.",
            err=True,
        )
        sys.exit(1)

    click.echo(f"Found AS project root: {root}")

    config_file = root / ".as-docs.yaml"
    if config_file.exists():
        click.echo(".as-docs.yaml already exists — skipping creation.")
    else:
        example = Path(__file__).parent.parent / ".as-docs.yaml.example"
        if example.exists():
            content = example.read_text(encoding="utf-8")
        else:
            content = _default_config_content(root.name)

        if http:
            content = content.replace('mode: "stdio"', 'mode: "http"')

        config_file.write_text(content, encoding="utf-8")
        click.echo("Created .as-docs.yaml")

    # Update .gitignore
    _update_gitignore(root)
    click.echo("Updated .gitignore (.as-docs-cache/ and docs/as-docs/)")

    if mcp:
        _update_vscode_mcp(root)
        click.echo("Updated .vscode/mcp.json (as-docs MCP server)")

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
        gitignore.write_text(
            content + sep + "\n".join(additions) + "\n", encoding="utf-8"
        )


def _update_vscode_mcp(root: Path) -> Path:
    vscode_dir = root / ".vscode"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    mcp_file = vscode_dir / "mcp.json"

    try:
        payload = (
            json.loads(mcp_file.read_text(encoding="utf-8"))
            if mcp_file.exists()
            else {}
        )
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"Invalid JSON in {mcp_file}: {exc}") from exc

    if not isinstance(payload, dict):
        payload = {}

    servers = payload.get("servers")
    if not isinstance(servers, dict):
        servers = {}

    servers["as-docs"] = {
        "command": "as-docs",
        "args": ["serve"],
    }
    payload["servers"] = servers

    mcp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return mcp_file


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
  recursive_packages: true
  max_recursion_depth: 10

ai:
  enabled: true
  provider: "copilot"
  model: "gpt-4.1"
  api_base_url: ""
  api_key_env: "GITHUB_TOKEN"
  timeout_seconds: 60
  max_retries: 3
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
@click.option(
    "--level",
    default=None,
    type=int,
    help="Documentation level (1–4). Default from config.",
)
@click.option(
    "--no-ai", "no_ai", is_flag=True, help="Skip AI enrichment (Level 1 only)."
)
@click.option(
    "--use-as-cli",
    "use_as_cli",
    is_flag=True,
    help="Enable as-cli integration (if available). Overrides config.",
)
@click.option(
    "--scope",
    default="all",
    type=str,
    help="Regeneration scope: all, changed, or pou:<name>.",
)
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(),
    help="Path to .as-docs.yaml",
)
@click.pass_context
def generate(
    ctx: click.Context,
    level: int | None,
    no_ai: bool,
    use_as_cli: bool,
    scope: str,
    config_path: str | None,
) -> None:
    """Generate documentation for the AS project.

    By default, uses filesystem scanner. With --use-as-cli, attempts to merge
    as-cli data (if available). Falls back to filesystem if as-cli unavailable.

    Scoping:
      --scope all         Regenerate all POUs (default)
      --scope changed     Regenerate only POUs with changed source files
      --scope pou:NAME    Regenerate only the named POU
    """
    from as_docs.engine import run_generate

    cfg = _load_cfg(config_path)
    effective_level = (
        level if level is not None else (1 if no_ai else cfg.output.default_level)
    )
    ai_enabled = cfg.ai.enabled and not no_ai and effective_level >= 2

    click.echo(
        f"Generating Level {effective_level} docs for '{cfg.project.name or 'project'}'..."
    )
    if ai_enabled:
        click.echo(
            f"AI enrichment enabled (provider: {cfg.ai.provider}, model: {cfg.ai.model})"
        )
    if use_as_cli:
        click.echo("as-cli integration enabled (will merge if available)")
    if scope != "all":
        click.echo(f"Scope: {scope}")

    try:
        graph = run_generate(
            cfg,
            level=effective_level,
            ai_enabled=ai_enabled,
            use_as_cli=use_as_cli,
            scope=scope,
        )
        out = Path(cfg.output.docs_dir)
        click.echo(f"\nDone — {len(graph.pous)} POUs, {len(graph.tasks)} tasks")
        if ai_enabled:
            stats = getattr(graph, "_ai_stats", None)
            if stats is not None:
                click.echo(
                    f"AI cache: hits={stats.hits}, misses={stats.misses}, writes={stats.writes}"
                )

        # Show as-cli merge report if available
        meta = getattr(graph, "_regen_meta", {})
        as_cli_report = meta.get("as_cli_merge_report")
        if as_cli_report:
            click.echo("\nas-cli merge report:")
            click.echo(f"    Filesystem: {as_cli_report['pou_count_fs']} POUs")
            click.echo(f"    as-cli: {as_cli_report['pou_count_as_cli']} POUs")
            click.echo(f"    Merged: {as_cli_report['pou_count_merged']} POUs")
            if as_cli_report["conflicts"]:
                click.echo(f"    Conflicts: {len(as_cli_report['conflicts'])}")
                for conflict in as_cli_report["conflicts"][:3]:
                    click.echo(
                        f"       - {conflict['pou_name']}: {conflict['conflict_type']}"
                    )
                if len(as_cli_report["conflicts"]) > 3:
                    click.echo(
                        f"       ... and {len(as_cli_report['conflicts']) - 3} more"
                    )
            click.echo(
                f"    Full report: {out.resolve() / 'as_cli_conflict_report.json'}"
            )

        click.echo(f"Output: {out.resolve()}")
    except FileNotFoundError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# as-docs as-cli-check
# ---------------------------------------------------------------------------


@cli.command("as-cli-check")
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(),
    help="Path to .as-docs.yaml",
)
def as_cli_check(config_path: str | None) -> None:
    """Diagnose as-cli integration and availability.

    Checks if as-cli is installed, accessible, and can communicate with an
    Automation Studio project. Useful for troubleshooting integration issues.
    """
    cfg = _load_cfg(config_path)

    click.echo(" Diagnosing as-cli integration...\n")

    # Step 1: Check configuration
    click.echo("1.  Configuration:")
    click.echo(f"    Enabled: {cfg.as_cli.enabled}")
    click.echo(f"    Path: {cfg.as_cli.path}")
    click.echo(f"    Timeout: {cfg.as_cli.timeout_ms}ms")
    click.echo(f"    Strict mode: {cfg.as_cli.strict}")
    click.echo(f"    Commands: {', '.join(cfg.as_cli.use_commands)}")
    click.echo()

    # Step 2: Check availability
    click.echo("2.  Availability check:")
    adapter = AsCliAdapter(
        as_cli_path=cfg.as_cli.path,
        timeout_ms=2000,  # Quick check timeout
    )

    as_cli_available = False
    try:
        if adapter.is_available():
            click.echo("    as-cli is installed and accessible")
            as_cli_available = True
        else:
            click.echo("    as-cli is not available")
            click.echo("\n    Troubleshooting:")
            click.echo("    - Ensure as-cli is installed")
            click.echo("    - Check that as-cli is in your PATH")
            click.echo("    - Try: as-cli --version")
    except Exception as e:
        click.echo(f"    Error checking availability: {e}")

    click.echo()

    # Only proceed to steps 3-4 if as-cli is available
    if as_cli_available:
        # Step 3: Try to connect to daemon or start one
        click.echo("3.  Daemon connectivity:")
        try:
            # This will auto-start daemon if needed
            adapter._ensure_daemon()
            click.echo("    Connected to daemon (or started new one)")
        except Exception as e:
            click.echo(f"    Daemon issue: {e}")
            click.echo("    Note: This may be temporary; retry later")

        click.echo()

        # Step 4: Try basic commands
        click.echo("4.  Command availability:")

        try:
            # Try logical_list
            if "logical_list" in cfg.as_cli.use_commands:
                try:
                    result = adapter.get_logical_list()
                    modules = result.get("modules", [])
                    click.echo(f"    logical_list: {len(modules)} modules found")
                except AsCliError as e:
                    click.echo(f"    logical_list failed: {e}")

            # Try symbol_search
            if "symbol_search" in cfg.as_cli.use_commands:
                try:
                    result = adapter.get_symbol_search("*")
                    symbols = result.get("symbols", {})
                    click.echo(f"    symbol_search: {len(symbols)} symbols found")
                except AsCliError as e:
                    click.echo(f"    symbol_search failed: {e}")
        except Exception as e:
            click.echo(f"    Error running commands: {e}")

        click.echo()

    # Step 5: Configuration recommendations
    click.echo("5.  Recommendations:")
    if not cfg.as_cli.enabled:
        click.echo("    • Enable as-cli in .as-docs.yaml: as_cli.enabled: true")
    else:
        click.echo("    • as-cli is enabled in config ")

    if cfg.as_cli.strict:
        click.echo("    • Running in strict mode (will fail if as-cli unavailable)")
    else:
        click.echo("    • Running in graceful fallback mode (recommended)")

    click.echo()
    click.echo("Diagnostic complete.")


# ---------------------------------------------------------------------------
# as-docs upgrade
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--to", "to_level", required=True, type=int, help="Target level (2, 3, or 4)."
)
@click.option("--pou", default=None, help="Upgrade a single POU by name.")
@click.option("--config", "config_path", default=None, type=click.Path())
def upgrade(to_level: int, pou: str | None, config_path: str | None) -> None:
    """Upgrade documentation to a higher level."""
    from as_docs.engine import run_generate

    cfg = _load_cfg(config_path)
    if not cfg.ai.enabled:
        click.echo("ERROR: AI is disabled in config. Set ai.enabled: true", err=True)
        sys.exit(1)

    scope = f"pou:{pou}" if pou else "all"
    click.echo(f"  Upgrading to Level {to_level} (scope: {scope})...")

    ai_enabled = bool(cfg.ai.enabled and to_level >= 2)
    try:
        graph = run_generate(cfg, level=to_level, ai_enabled=ai_enabled, scope=scope)
        meta = getattr(graph, "_regen_meta", {})
        touched = ", ".join(meta.get("touched_pous", [])) or "—"
        click.echo(f"\nUpgrade complete — level {graph.level}")
        click.echo(f" Scope: {meta.get('scope', scope)}")
        click.echo(f"Touched POUs: {touched}")
        click.echo(f"  Elapsed: {meta.get('elapsed_seconds', 0.0)}s")
        if meta.get("fallback_full"):
            click.echo(
                "No prior graph found; executed full regeneration to establish baseline."
            )
    except ValueError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)


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
        click.echo("No documentation generated yet. Run: as-docs generate --no-ai")
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
            icon = "" if state == "fresh" else ("!" if state == "stale" else "?")
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
        click.echo(
            "ERROR: MCP server dependencies not installed. Install with: pip install as-docs[mcp]",
            err=True,
        )
        sys.exit(1)
    cfg = _load_cfg(config_path)
    start_server(cfg, use_http=http, port=port)


# ---------------------------------------------------------------------------
# as-docs watch
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--level", default=1, show_default=True, type=int)
@click.option("--debounce-ms", default=500, show_default=True, type=int)
@click.option("--config", "config_path", default=None, type=click.Path())
def watch(level: int, debounce_ms: int, config_path: str | None) -> None:
    """Watch for file changes and regenerate on save (daemon mode)."""
    from as_docs.engine import run_generate

    cfg = _load_cfg(config_path)
    project_root = _resolve_project_root(cfg)
    logical_root = project_root / "Logical"
    physical_root = project_root / "Physical"
    if not logical_root.exists():
        click.echo("ERROR: Logical/ directory not found for watch mode.", err=True)
        sys.exit(1)

    ai_enabled = bool(cfg.ai.enabled and level >= 2)
    known_pous = _known_pou_names(cfg, project_root)
    pending_pous: set[str] = set()
    pending_generic_change = False
    last_event_at = 0.0
    debounce_seconds = max(0.0, debounce_ms / 1000.0)

    def _on_change(changed_path: Path) -> None:
        nonlocal last_event_at, pending_generic_change
        scope = _watch_scope_for_path(changed_path, known_pous)
        if scope is None:
            return
        if scope == "changed":
            pending_generic_change = True
        else:
            pending_pous.add(scope.split(":", 1)[1])
        last_event_at = time.monotonic()

    handler = _ASDocsWatchHandler(callback=_on_change, debounce_ms=debounce_ms)
    observer = Observer()
    observer.schedule(handler, str(logical_root), recursive=True)
    if physical_root.exists():
        observer.schedule(handler, str(physical_root), recursive=True)

    click.echo(f" Watching {logical_root} (level {level}, debounce {debounce_ms}ms)")
    if physical_root.exists():
        click.echo(f" Watching {physical_root} (task/config changes)")
    click.echo("Press Ctrl+C to stop.")

    observer.start()
    try:
        while True:
            if (pending_pous or pending_generic_change) and (
                time.monotonic() - last_event_at
            ) >= debounce_seconds:
                scope = _watch_batch_scope(pending_pous, pending_generic_change)
                pending_pous.clear()
                pending_generic_change = False

                if scope:
                    graph = run_generate(
                        cfg, level=level, ai_enabled=ai_enabled, scope=scope
                    )
                    meta = getattr(graph, "_regen_meta", {})
                    touched = ", ".join(meta.get("touched_pous", [])) or "—"
                    click.echo(
                        f" Regenerated {meta.get('scope', scope)}; touched POUs: {touched}; elapsed: {meta.get('elapsed_seconds', 0.0)}s"
                    )
            time.sleep(0.25)
    except KeyboardInterrupt:
        click.echo("\nStopping watcher...")
    finally:
        observer.stop()
        observer.join(timeout=5)


# ---------------------------------------------------------------------------
# as-docs install-hook
# ---------------------------------------------------------------------------


@cli.command("install-hook")
@click.option("--yes", is_flag=True, help="Install without confirmation prompt.")
@click.option("--force", is_flag=True, help="Replace any existing as-docs hook block.")
@click.option("--config", "config_path", default=None, type=click.Path())
def install_hook(yes: bool, force: bool, config_path: str | None) -> None:
    """Install a git post-commit hook for automatic doc regeneration."""
    cfg = _load_cfg(config_path)
    project_root = _resolve_project_root(cfg)

    try:
        repo = Repo(project_root, search_parent_directories=True)
    except InvalidGitRepositoryError:
        click.echo("ERROR: Not a git repository. Initialize git first.", err=True)
        sys.exit(1)

    repo_root = Path(repo.working_tree_dir or project_root)
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_file = hooks_dir / "post-commit"

    if not yes:
        if not click.confirm(
            f"Install as-docs post-commit hook in {hook_file}?", default=True
        ):
            click.echo("Hook installation cancelled.")
            return

    marker_start = "# >>> as-docs hook start >>>"
    marker_end = "# <<< as-docs hook end <<<"
    hook_block = _build_post_commit_hook_block(cfg)

    if hook_file.exists():
        existing = hook_file.read_text(encoding="utf-8", errors="replace")
    else:
        existing = "#!/bin/sh\n"

    updated, changed = _merge_hook_block(
        existing,
        marker_start=marker_start,
        marker_end=marker_end,
        block=hook_block,
        force=force,
    )

    if not changed:
        click.echo(" Hook already installed (no changes).")
        return

    hook_file.write_text(updated, encoding="utf-8")
    try:
        hook_file.chmod(0o755)
    except OSError:
        # Windows may ignore chmod for hooks; keep going.
        pass

    click.echo(f" Installed post-commit hook: {hook_file}")


# ---------------------------------------------------------------------------
# as-docs diff
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("ref", default="HEAD~1")
@click.option("--config", "config_path", default=None, type=click.Path())
def diff(ref: str, config_path: str | None) -> None:
    """Show which POUs changed since a git ref."""
    cfg = _load_cfg(config_path)
    project_root = _resolve_project_root(cfg)

    try:
        repo = Repo(project_root, search_parent_directories=True)
    except InvalidGitRepositoryError:
        click.echo("ERROR: Not a git repository. Initialize git first.", err=True)
        sys.exit(1)

    repo_root = Path(repo.working_tree_dir or project_root)
    try:
        changed = _git_changed_files(repo, ref)
    except Exception as exc:
        click.echo(f"ERROR: Unable to diff ref '{ref}': {exc}", err=True)
        sys.exit(1)

    if not changed:
        click.echo(f"No changed files detected between {ref} and HEAD.")
        return

    known_pous = _known_pou_names(cfg, repo_root)
    changed_pous = _changed_pous_from_files(changed, repo_root, known_pous)
    click.echo(f"Changed files ({len(changed)}):")
    for path in changed:
        click.echo(f"  - {path}")

    click.echo("")
    click.echo(f"Changed POUs ({len(changed_pous)}):")
    for name in sorted(changed_pous):
        click.echo(f"  - {name}")

    if changed_pous:
        click.echo("")
        click.echo("Suggested commands:")
        for name in sorted(changed_pous):
            click.echo(f"  as-docs upgrade --to {cfg.git.auto_level} --pou {name}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_cfg(config_path: str | None) -> Config:
    p = Path(config_path) if config_path else None
    try:
        return load_config(p)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def _resolve_project_root(cfg: Config) -> Path:
    root = Path(cfg.project.root).resolve()
    if (root / "Logical").is_dir() and (root / "Physical").is_dir():
        return root
    detected = find_project_root()
    if detected:
        return detected
    raise click.ClickException(
        "Cannot locate AS project root (Logical/ + Physical/ not found)."
    )


def _git_changed_files(repo: Repo, ref: str) -> list[str]:
    output = repo.git.diff("--name-only", ref, "HEAD")
    return [line.strip() for line in output.splitlines() if line.strip()]


def _resolve_pou_name_from_path(path: Path) -> str | None:
    lower_suffix = path.suffix.lower()
    if lower_suffix not in {".st", ".prg", ".var"}:
        return None
    if path.parent.name == "GlobalVars":
        return None
    return path.parent.name


def _watch_scope_for_path(path: Path, known_pous: set[str]) -> str | None:
    if "Physical" in path.parts:
        return "changed"

    lower_suffix = path.suffix.lower()
    if lower_suffix not in {".st", ".prg", ".var", ".typ", ".per"}:
        return None

    if "Logical" not in path.parts:
        return None

    logical_idx = path.parts.index("Logical")
    if len(path.parts) <= logical_idx + 1:
        return None

    section = path.parts[logical_idx + 1]
    if section == "GlobalVars" or lower_suffix == ".typ":
        return "changed"

    pou = _resolve_pou_name_from_path(path)
    if pou and pou in known_pous:
        return f"pou:{pou}"

    if lower_suffix == ".per":
        return "changed"

    return None


def _watch_batch_scope(pous: set[str], generic_change: bool) -> str | None:
    if generic_change:
        return "changed"
    if not pous:
        return None
    if len(pous) == 1:
        return f"pou:{next(iter(pous))}"
    return "changed"


def _is_relevant_source_path(path: Path) -> bool:
    return path.suffix.lower() in {".st", ".prg", ".var", ".typ", ".per"}


def _known_pou_names(cfg: Config, project_root: Path) -> set[str]:
    from as_docs.scanner.project_scanner import scan_project

    model = scan_project(cfg, project_root=project_root)
    return set(model.pous.keys())


def _changed_pous_from_files(
    changed_files: list[str],
    repo_root: Path,
    known_pous: set[str],
) -> set[str]:
    changed_pous: set[str] = set()
    for rel in changed_files:
        path = repo_root / rel
        parts = path.parts
        if "Logical" not in parts:
            if "Physical" in parts:
                changed_pous.update(known_pous)
            continue

        logical_idx = parts.index("Logical")
        if len(parts) <= logical_idx + 1:
            continue

        section = parts[logical_idx + 1]
        suffix = path.suffix.lower()
        if section == "GlobalVars" or suffix in {".typ"}:
            changed_pous.update(known_pous)
            continue

        pou = _resolve_pou_name_from_path(path)
        if pou and pou in known_pous:
            changed_pous.add(pou)
    return changed_pous


def _build_post_commit_hook_block(cfg: Config) -> str:
    auto_level = cfg.git.auto_level
    return "\n".join(
        [
            "# >>> as-docs hook start >>>",
            "if command -v as-docs >/dev/null 2>&1; then",
            f"  as-docs generate --level {auto_level} >/dev/null 2>&1 || true",
            "fi",
            "# <<< as-docs hook end <<<",
            "",
        ]
    )


def _merge_hook_block(
    existing: str,
    *,
    marker_start: str,
    marker_end: str,
    block: str,
    force: bool,
) -> tuple[str, bool]:
    has_start = marker_start in existing
    has_end = marker_end in existing

    if has_start and has_end:
        start_idx = existing.index(marker_start)
        end_idx = existing.index(marker_end) + len(marker_end)
        before = existing[:start_idx].rstrip("\n")
        current_block = existing[start_idx:end_idx]
        after = existing[end_idx:].lstrip("\n")
        normalized_existing = current_block.strip()
        normalized_new = block.strip()
        if normalized_existing == normalized_new:
            return existing if existing.endswith("\n") else existing + "\n", False
        merged = (
            "\n".join(part for part in [before, block.rstrip("\n"), after] if part)
            + "\n"
        )
        return merged, True

    if has_start or has_end:
        if not force:
            raise click.ClickException(
                "Found partial as-docs hook markers. Re-run with --force to replace."
            )

    base = existing.rstrip("\n")
    merged = (base + "\n\n" + block).strip("\n") + "\n"
    changed = marker_start not in existing
    return merged, changed


class _ASDocsWatchHandler(FileSystemEventHandler):
    def __init__(self, callback, debounce_ms: int) -> None:
        self._callback = callback
        self._debounce_seconds = max(0.0, debounce_ms / 1000.0)
        self._last_run = 0.0

    def on_modified(self, event) -> None:
        self._handle_event(event)

    def on_created(self, event) -> None:
        self._handle_event(event)

    def on_moved(self, event) -> None:
        self._handle_event(event)

    def _handle_event(self, event) -> None:
        if getattr(event, "is_directory", False):
            return

        src = getattr(event, "dest_path", None) or getattr(event, "src_path", "")
        path = Path(src)
        if not _is_relevant_source_path(path):
            return

        now = time.monotonic()
        if now - self._last_run < self._debounce_seconds:
            return

        self._last_run = now
        self._callback(path)
