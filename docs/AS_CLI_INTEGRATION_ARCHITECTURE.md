# as-cli Integration — Phase 1 Architecture Design

**Status:** ARCHITECTURE PHASE  
**Branch:** `feature/as-cli-integration`  
**Decisions Reference:** Phase 0 (all confirmed)  
**Date:** 2026-06-30

---

## Table of Contents

1. [Data Flow](#data-flow)
2. [Module Design](#module-design)
3. [Class Interfaces](#class-interfaces)
4. [Configuration Schema](#configuration-schema)
5. [Error Handling Strategy](#error-handling-strategy)
6. [Integration Points](#integration-points)
7. [Testing Strategy](#testing-strategy)

---

## Data Flow

### High-Level Flow Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                       User Command                             │
│              as-docs generate --use-as-cli                     │
└────────────────────────────────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────┐
        │  cli.py (click command handler)      │
        │  - Parse --use-as-cli flag           │
        │  - Load config                       │
        │  - Resolve: CLI > config > default   │
        └──────────────────────────────────────┘
                           ↓
        ┌──────────────────────────────────────┐
        │  engine.py: run_generate()           │
        │  - Decide: as_cli_enabled?           │
        │  - Call appropriate data source      │
        └──────────────────────────────────────┘
                           ↓
            ┌──────────────┬─────────────────┐
            ↓              ↓                 ↓
        YES: use_as_cli    NO: fs_only    MAYBE: hybrid
            ↓                              ↓
    ┌──────────────────┐        ┌─────────────────────┐
    │  AsCliAdapter    │        │ filesystem scanner  │
    │                  │        │ (existing code)     │
    │ get_logical_list │        └─────────────────────┘
    │ get_symbol_search│                  ↓
    │ + hybrid daemon  │              fs_project
    │ management       │                  
    └──────────────────┘                  
            ↓                              
      as_cli_project                      
            ↓                              
    ┌──────────────────────────────────────┐
    │  DataConflictResolver.merge()        │
    │  - Union both POUs                   │
    │  - Detect conflicts                  │
    │  - Generate ConflictReport           │
    └──────────────────────────────────────┘
            ↓
    ┌──────────────────────────────────────┐
    │  Merged ProjectData                  │
    │  (union of fs + as-cli POUs)         │
    └──────────────────────────────────────┘
            ↓
    ┌──────────────────────────────────────┐
    │  Continue as-docs pipeline           │
    │  - analyzer (call graph, xref, etc)  │
    │  - enricher (AI if enabled)          │
    │  - generator (markdown, json, etc)   │
    └──────────────────────────────────────┘
            ↓
    ┌──────────────────────────────────────┐
    │  Output Files                        │
    │  - knowledge_graph.json              │
    │  - as_cli_merge_report.json (NEW)    │
    │  - [other output files]              │
    └──────────────────────────────────────┘
```

### Decision Point: When to Use as-cli?

```python
def should_use_as_cli(config, cli_override):
    """
    Precedence:
    1. CLI flag (if specified) > config file > default
    2. Return True/False
    """
    if cli_override is not None:
        return cli_override  # CLI flag wins
    return config.as_cli.enabled  # Config file default
```

---

## Module Design

### New Modules to Create

#### 1. `as_docs/scanner/as_cli_adapter.py`

**Purpose:** Encapsulate all as-cli interactions (spawn, command execution, JSON parsing)

**Responsibilities:**
- Spawn and manage as-cli daemon (hybrid lifecycle)
- Execute `logical_list` and `symbol_search` commands
- Parse JSON output from as-cli
- Handle timeouts and errors
- Check daemon availability

**Key Classes:**

```python
class AsCliError(Exception):
    """Base exception for as-cli errors."""
    pass

class AsCliNotAvailableError(AsCliError):
    """as-cli not found or not working."""
    pass

class AsCliTimeoutError(AsCliError):
    """as-cli command timed out."""
    pass

class AsCliAdapter:
    """
    Wrapper around as-cli CLI.
    Manages daemon lifecycle (hybrid: auto-start on demand, persist).
    """
    
    def __init__(self, 
                 as_cli_path: str = "as-cli",
                 project_path: str = None,
                 timeout_ms: int = 30000):
        """
        Args:
            as_cli_path: Path to as-cli executable (auto-detect from PATH by default)
            project_path: Path to Automation Studio project (.apj file or containing dir)
            timeout_ms: Timeout per command (default 30s)
        """
        self.as_cli_path = as_cli_path
        self.project_path = project_path
        self.timeout_ms = timeout_ms
        self._daemon_started = False
    
    def is_available(self) -> bool:
        """
        Check if as-cli is available (installed, in PATH, and working).
        
        Returns:
            True if as-cli --version succeeds, False otherwise
        """
        # Try: shutil.which(self.as_cli_path) + version check
        pass
    
    def _ensure_daemon(self) -> bool:
        """
        Ensure as-cli daemon is running for the project.
        
        Hybrid lifecycle:
        1. Try to connect to existing daemon (fast check)
        2. If daemon not running, spawn it (one-time cost)
        3. Subsequent commands reuse daemon
        
        Returns:
            True if daemon is running/started, False if cannot start
        """
        if self._daemon_started:
            return True  # Already started in this session
        
        try:
            # Lightweight check: run as-cli project status (fast)
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path, "project", "status"],
                timeout=2,  # Fast timeout for connectivity check
                capture_output=True
            )
            if result.returncode == 0:
                self._daemon_started = True
                return True  # Daemon already running
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        # Daemon not running; try to start it (will start as side effect of any command)
        try:
            subprocess.run(
                [self.as_cli_path, "--project", self.project_path, "project", "status"],
                timeout=self.timeout_ms / 1000,  # Use full timeout for startup
                capture_output=True,
                check=False
            )
            self._daemon_started = True
            return True
        except Exception as e:
            raise AsCliNotAvailableError(f"Failed to start as-cli daemon: {e}")
    
    def get_logical_list(self) -> dict:
        """
        Execute: as-cli logical list --format json
        
        Returns:
            {
                "modules": [...],
                "tasks": [...],
                "programs": [...]
            }
        
        Raises:
            AsCliNotAvailableError: as-cli not available or daemon failed to start
            AsCliTimeoutError: Command timed out
            AsCliError: JSON parsing failed or as-cli returned error
        """
        self._ensure_daemon()
        
        try:
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path, 
                 "logical", "list", "--format", "json"],
                timeout=self.timeout_ms / 1000,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise AsCliError(f"as-cli logical list failed: {result.stderr}")
            
            data = json.loads(result.stdout)
            return data
        
        except subprocess.TimeoutExpired:
            raise AsCliTimeoutError(f"as-cli logical list timed out ({self.timeout_ms}ms)")
        except json.JSONDecodeError as e:
            raise AsCliError(f"Failed to parse as-cli output: {e}")
    
    def get_symbol_search(self, query: str = "*") -> dict:
        """
        Execute: as-cli symbol search --format json
        
        Args:
            query: Symbol search query (default "*" = all symbols)
        
        Returns:
            {
                "symbols": [
                    {"name": "...", "type": "...", "scope": "...", ...},
                    ...
                ]
            }
        
        Raises:
            AsCliNotAvailableError, AsCliTimeoutError, AsCliError
        """
        self._ensure_daemon()
        
        try:
            result = subprocess.run(
                [self.as_cli_path, "--project", self.project_path,
                 "symbol", "search", query, "--format", "json"],
                timeout=self.timeout_ms / 1000,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise AsCliError(f"as-cli symbol search failed: {result.stderr}")
            
            data = json.loads(result.stdout)
            return data
        
        except subprocess.TimeoutExpired:
            raise AsCliTimeoutError(f"as-cli symbol search timed out ({self.timeout_ms}ms)")
        except json.JSONDecodeError as e:
            raise AsCliError(f"Failed to parse as-cli output: {e}")
```

---

#### 2. `as_docs/scanner/as_cli_models.py`

**Purpose:** Data models for as-cli output (AsCliProjectData, AsCliModule, AsCliSymbol)

**Key Classes:**

```python
@dataclass
class AsCliModule:
    """Represents an AS module (from logical list)."""
    name: str
    path: str  # Package path (e.g., "MainPackage/SubModule")
    type: str  # "module", "task", "program"

@dataclass
class AsCliSymbol:
    """Represents an AS symbol (from symbol search)."""
    name: str
    type: str  # "function", "program", "global", etc.
    scope: str  # Full scope path
    module: str = None  # Module it belongs to

@dataclass
class AsCliProjectData:
    """
    Parsed result from as-cli logical_list + symbol_search commands.
    
    This is the "raw" data from as-cli; later converted to as-docs ProjectData.
    """
    modules: list[AsCliModule]
    symbols: dict[str, AsCliSymbol]  # symbol_name -> AsCliSymbol
    raw_logical_list: dict = None  # Raw JSON for debugging
    raw_symbol_search: dict = None  # Raw JSON for debugging
```

---

#### 3. `as_docs/scanner/data_conflict_resolver.py`

**Purpose:** Merge filesystem and as-cli data, detect conflicts, report discrepancies

**Key Classes:**

```python
@dataclass
class Conflict:
    """Represents a single conflict between fs and as-cli data."""
    conflict_type: str  # "path_mismatch", "type_mismatch", "scope_mismatch"
    pou_name: str
    fs_value: str = None
    as_cli_value: str = None
    severity: str = "warning"  # "warning", "error"

@dataclass
class ConflictReport:
    """Summary of merge results and conflicts."""
    conflicts: list[Conflict]
    pou_count_fs: int
    pou_count_as_cli: int
    pou_count_merged: int
    fs_only_pous: list[str]  # POUs found in fs only
    as_cli_only_pous: list[str]  # POUs found in as-cli only
    agreed_pous: list[str]  # POUs where both sources agree
    merge_timestamp: str  # ISO 8601 timestamp
    
    @property
    def has_conflicts(self) -> bool:
        return len(self.conflicts) > 0
    
    @property
    def summary(self) -> str:
        """Human-readable summary."""
        return f"""
Merge Summary:
  Filesystem POUs: {self.pou_count_fs}
  as-cli POUs: {self.pou_count_as_cli}
  Merged (union): {self.pou_count_merged}
  
  Agreed: {len(self.agreed_pous)}
  Filesystem only: {len(self.fs_only_pous)} {self.fs_only_pous[:3]}...
  as-cli only: {len(self.as_cli_only_pous)} {self.as_cli_only_pous[:3]}...
  
  Conflicts: {len(self.conflicts)}
  - Path mismatches: {len([c for c in self.conflicts if c.conflict_type == 'path_mismatch'])}
  - Type mismatches: {len([c for c in self.conflicts if c.conflict_type == 'type_mismatch'])}
"""

class DataConflictResolver:
    """
    Merges filesystem and as-cli project data.
    
    Strategy (Phase 0 Decision 0.5 — Smart Union):
    1. Union all POUs from both sources
    2. For POUs in both: compare paths/types, flag conflicts
    3. Mark source for each POU (fs_only, as_cli_only, both)
    4. Return merged ProjectData + ConflictReport
    """
    
    def merge(self,
              fs_project: ProjectData,
              as_cli_project: AsCliProjectData) -> tuple[ProjectData, ConflictReport]:
        """
        Merge filesystem and as-cli data.
        
        Args:
            fs_project: Project data from filesystem scanner
            as_cli_project: Project data from as-cli adapter
        
        Returns:
            (merged_project, conflict_report)
        """
        conflicts = []
        merged_pous = {}
        agreed_pous = []
        fs_only_pous = []
        as_cli_only_pous = []
        
        # Step 1: Add all filesystem POUs
        for pou_name, pou in fs_project.pous.items():
            merged_pous[pou_name] = pou
            pou.metadata = pou.metadata or {}
            pou.metadata["source"] = "filesystem"
        
        # Step 2: Add as-cli POUs, check for conflicts
        for as_cli_pou in as_cli_project.modules:  # as_cli_project.modules are POUs
            pou_name = as_cli_pou.name
            
            if pou_name in merged_pous:
                # Conflict: both sources have this POU
                fs_pou = merged_pous[pou_name]
                
                # Check path agreement
                if fs_pou.source_file != as_cli_pou.path:
                    conflicts.append(Conflict(
                        conflict_type="path_mismatch",
                        pou_name=pou_name,
                        fs_value=fs_pou.source_file,
                        as_cli_value=as_cli_pou.path,
                        severity="warning"
                    ))
                
                # Check type agreement
                if fs_pou.pou_type != as_cli_pou.type:
                    conflicts.append(Conflict(
                        conflict_type="type_mismatch",
                        pou_name=pou_name,
                        fs_value=fs_pou.pou_type,
                        as_cli_value=as_cli_pou.type,
                        severity="warning"
                    ))
                
                # Use as-cli data as source of truth (it's more authoritative)
                merged_pous[pou_name] = self._convert_as_cli_pou(as_cli_pou)
                merged_pous[pou_name].metadata["source"] = "both"
                agreed_pous.append(pou_name)
            
            else:
                # New POU from as-cli (fs missed it)
                merged_pous[pou_name] = self._convert_as_cli_pou(as_cli_pou)
                merged_pous[pou_name].metadata["source"] = "as_cli_only"
                as_cli_only_pous.append(pou_name)
        
        # Step 3: Identify fs-only POUs
        for pou_name in fs_project.pous.keys():
            if pou_name not in agreed_pous and pou_name not in as_cli_only_pous:
                fs_only_pous.append(pou_name)
        
        # Step 4: Create merged project
        merged_project = ProjectData(
            pous=merged_pous,
            # ... copy other fields from fs_project ...
        )
        
        # Step 5: Create conflict report
        report = ConflictReport(
            conflicts=conflicts,
            pou_count_fs=len(fs_project.pous),
            pou_count_as_cli=len(as_cli_project.modules),
            pou_count_merged=len(merged_pous),
            fs_only_pous=fs_only_pous,
            as_cli_only_pous=as_cli_only_pous,
            agreed_pous=agreed_pous,
            merge_timestamp=datetime.now().isoformat()
        )
        
        return merged_project, report
    
    def _convert_as_cli_pou(self, as_cli_pou: AsCliModule) -> POUNode:
        """
        Convert as-cli module to as-docs POUNode.
        """
        # ... implementation ...
        pass
```

---

### Updated Existing Modules

#### 1. `as_docs/config.py` — Add AsCliConfig

**New dataclass:**

```python
@dataclass
class AsCliConfig:
    """Configuration for as-cli integration."""
    
    enabled: bool = False
    """Enable as-cli data source. Default: False (opt-in)."""
    
    path: str = "as-cli"
    """Path to as-cli executable. Default: auto-detect from PATH."""
    
    timeout_ms: int = 30000
    """Timeout per as-cli command (milliseconds). Default: 30s."""
    
    strict: bool = False
    """
    If True: fail hard on as-cli errors.
    If False: gracefully fall back to filesystem scanning.
    Default: False (graceful fallback).
    """
    
    use_commands: list[str] = field(default_factory=lambda: [
        "logical_list",
        "symbol_search"
    ])
    """Which as-cli commands to use. Default: both."""

@dataclass
class Config:
    # ... existing fields ...
    
    as_cli: AsCliConfig = field(default_factory=AsCliConfig)
    """as-cli integration configuration."""
```

**Validation function (in config.py):**

```python
def validate_as_cli_config(config: Config) -> list[str]:
    """
    Validate as-cli configuration.
    
    Returns:
        List of error messages (empty if valid)
    """
    errors = []
    
    if config.as_cli.enabled:
        if config.as_cli.timeout_ms <= 0:
            errors.append("as_cli.timeout_ms must be positive")
        
        if not config.as_cli.path:
            errors.append("as_cli.path cannot be empty")
        
        if not isinstance(config.as_cli.use_commands, list):
            errors.append("as_cli.use_commands must be a list")
        
        valid_commands = {"logical_list", "symbol_search"}
        for cmd in config.as_cli.use_commands:
            if cmd not in valid_commands:
                errors.append(f"Unknown as-cli command: {cmd}")
    
    return errors
```

---

#### 2. `as_docs/engine.py` — Add as_cli Branch

**Updated `run_generate()` function signature:**

```python
def run_generate(
    project_path: str,
    level: int = 3,
    ai_enabled: bool = True,
    use_as_cli: bool | None = None,  # NEW: None = read from config
    output_dir: str = ".as-docs",
    **kwargs
) -> ProjectData:
    """
    Generate documentation for an AS project.
    
    Args:
        project_path: Path to project (.apj or containing directory)
        level: Documentation level (1-4)
        ai_enabled: Enable AI enrichment
        use_as_cli: Override config.as_cli.enabled (None = read from config)
        output_dir: Output directory for generated docs
    
    Returns:
        ProjectData: Knowledge graph with POUs, tasks, xref, etc.
    """
    # Load config
    config = load_config(project_path)
    
    # Validate config
    config_errors = validate_as_cli_config(config)
    if config_errors:
        logger.warning(f"Config validation warnings: {config_errors}")
    
    # Resolve use_as_cli decision (CLI override > config > default)
    if use_as_cli is None:
        use_as_cli = config.as_cli.enabled
    
    # Step 1: Get project data from appropriate source(s)
    if use_as_cli:
        try:
            # Try as-cli data source
            adapter = AsCliAdapter(
                as_cli_path=config.as_cli.path,
                project_path=project_path,
                timeout_ms=config.as_cli.timeout_ms
            )
            
            if not adapter.is_available():
                raise AsCliNotAvailableError("as-cli not found in PATH")
            
            # Get as-cli data
            as_cli_logical = adapter.get_logical_list()
            as_cli_symbols = adapter.get_symbol_search()
            as_cli_project = AsCliProjectData(
                modules=parse_logical_list(as_cli_logical),
                symbols=parse_symbol_search(as_cli_symbols)
            )
            
            # Get filesystem data (always)
            fs_project = run_filesystem_scan(project_path, config)
            
            # Merge data
            resolver = DataConflictResolver()
            project, conflicts = resolver.merge(fs_project, as_cli_project)
            
            # Log conflicts
            if conflicts.has_conflicts:
                logger.warning(f"Merge conflicts detected:\n{conflicts.summary}")
            
            # Save conflict report
            conflict_report_path = os.path.join(output_dir, "as_cli_merge_report.json")
            with open(conflict_report_path, "w") as f:
                json.dump(asdict(conflicts), f, indent=2)
            
            logger.info(f"Conflict report saved to {conflict_report_path}")
        
        except (AsCliNotAvailableError, AsCliError) as e:
            if config.as_cli.strict:
                raise  # Hard fail
            else:
                # Graceful fallback
                logger.warning(f"as-cli unavailable, falling back to filesystem scanning: {e}")
                project = run_filesystem_scan(project_path, config)
    
    else:
        # Use filesystem scanning only (existing behavior)
        project = run_filesystem_scan(project_path, config)
    
    # Step 2: Run analysis (unchanged)
    run_analyzer(project, config, level)
    
    # Step 3: Enrich with AI (unchanged)
    if ai_enabled and level >= 2:
        enrich_graph(project, level, config)
    
    # Step 4: Generate output (unchanged)
    run_generators(project, output_dir, level)
    
    return project
```

---

#### 3. `as_docs/cli.py` — Add --use-as-cli Flag

**Updated `generate` command:**

```python
@click.command()
@click.option(
    "--no-ai",
    is_flag=True,
    help="Disable AI enrichment (generates Level 1 only)"
)
@click.option(
    "--use-as-cli",
    type=bool,
    default=None,
    help="Enable as-cli data source (overrides config). Use --use-as-cli=true or --no-use-as-cli"
)
@click.option(
    "--level",
    type=int,
    default=3,
    help="Documentation level (1-4)"
)
@click.option(
    "--output",
    type=str,
    default=".as-docs",
    help="Output directory"
)
def generate(no_ai, use_as_cli, level, output):
    """Generate documentation for the AS project."""
    try:
        ai_enabled = not no_ai
        project = run_generate(
            project_path=".",
            level=level,
            ai_enabled=ai_enabled,
            use_as_cli=use_as_cli,
            output_dir=output
        )
        click.echo(f"✓ Documentation generated at {output}")
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Exit(1)
```

**New command: `as-cli-check`:**

```python
@click.command()
def as_cli_check():
    """Check if as-cli is installed and working."""
    try:
        adapter = AsCliAdapter()
        if adapter.is_available():
            click.echo("✓ as-cli is installed and working")
            # Run version to get more info
            result = subprocess.run(
                ["as-cli", "--version"],
                capture_output=True,
                text=True
            )
            click.echo(result.stdout)
        else:
            click.echo("✗ as-cli not found or not working")
            raise click.Exit(1)
    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        raise click.Exit(1)
```

---

## Configuration Schema

### `.as-docs.yaml.example` Updates

**New section (Phase 1 deliverable):**

```yaml
project:
  root_dir: .

analysis:
  level: 3
  ai_enabled: true

ai:
  provider: anthropic
  model: claude-sonnet-4-20250514
  cache_dir: .as-docs-cache

# NEW: as-cli Integration Configuration
as_cli:
  # Enable/disable as-cli data source
  # When enabled: as-docs uses as-cli logical_list + symbol_search
  # When disabled: uses filesystem scanning only (default behavior)
  enabled: false
  
  # Path to as-cli executable
  # - Auto-detected from PATH if omitted or set to "as-cli"
  # - Set to full path if as-cli is not in PATH
  path: "as-cli"
  
  # Timeout per as-cli command (milliseconds)
  # Commands: logical_list, symbol_search
  timeout_ms: 30000
  
  # Error handling strategy
  # - false (default): Gracefully fall back to filesystem if as-cli fails
  # - true: Hard fail if as-cli unavailable (suitable for strict CI/CD)
  strict: false
  
  # Which as-cli commands to use (future extensibility)
  use_commands:
    - logical_list      # Module/task/program hierarchy
    - symbol_search     # All symbols in project
```

---

## Error Handling Strategy

### Exception Hierarchy

```python
# as_docs/scanner/as_cli_adapter.py

class AsCliError(Exception):
    """Base exception for all as-cli errors."""
    pass

class AsCliNotAvailableError(AsCliError):
    """as-cli executable not found or not executable."""
    pass

class AsCliCommandError(AsCliError):
    """as-cli command returned non-zero exit code."""
    pass

class AsCliTimeoutError(AsCliError):
    """as-cli command timed out."""
    pass

class AsCliParseError(AsCliError):
    """Failed to parse as-cli JSON output."""
    pass
```

### Error Handling Flow

```
┌─────────────────────────────────────┐
│  as_cli adapter executes command    │
└─────────────────────────────────────┘
            ↓
    ┌──────────────────────────────┐
    │  Success?                    │
    └──────────────────────────────┘
         ↙          ↘
       YES           NO
        ↓             ↓
   Return data    Check error type
        ↓             ↓
   [Good]        ┌────────────────────────┐
              → │ engine.py: catch error │
                └────────────────────────┘
                        ↓
                   ┌─────────────┐
                   │ strict mode?│
                   └─────────────┘
                      ↙      ↘
                    YES      NO
                     ↓         ↓
                  Raise    Log warn
                         Fallback
                           ↓
                       Filesystem
```

### Logging Strategy

```python
import logging

logger = logging.getLogger(__name__)

# In adapter
logger.debug(f"Executing: {' '.join(cmd)}")
logger.debug(f"as-cli logical_list returned {len(data)} modules")

# In engine
logger.warning(f"as-cli not available, falling back to filesystem: {error}")
logger.info(f"Merge complete: {conflicts.summary}")

# In conflict resolver
logger.warning(f"Path mismatch for {pou_name}: fs={fs_path}, as_cli={as_cli_path}")
```

---

## Integration Points

### How as_docs Finds the Project

**Current behavior (unchanged):**
- User runs: `as-docs generate` in any subdirectory of the AS project
- engine.py walks up directories to find `.apj` file
- scanner finds project root

**With as-cli:**
- Same project detection
- AsCliAdapter uses same project_path for `as-cli --project`

### Backward Compatibility

**Guarantee:** All existing as-docs functionality works unchanged when `as_cli.enabled: false` (default)

**Test matrix:**
| as_cli.enabled | as-cli installed | Behavior |
|---|---|---|
| false | YES | Filesystem scan (as-cli ignored) |
| false | NO | Filesystem scan (normal) |
| true | YES | as-cli + filesystem merge |
| true | NO | Graceful fallback to filesystem (if strict=false) |

---

## Testing Strategy

### Unit Tests

**`tests/test_as_cli_adapter.py`** (mock as-cli)
- `test_is_available_success()` — as-cli in PATH
- `test_is_available_not_found()` — as-cli not found
- `test_ensure_daemon_already_running()` — daemon exists, reuse it
- `test_ensure_daemon_start()` — daemon doesn't exist, start it
- `test_get_logical_list_success()` — parse JSON, return data
- `test_get_logical_list_malformed_json()` — catch JSONDecodeError
- `test_get_logical_list_timeout()` — handle subprocess.TimeoutExpired
- `test_get_symbol_search_success()` — parse JSON, return data

**`tests/test_data_conflict_resolver.py`**
- `test_merge_no_conflicts()` — both agree, clean merge
- `test_merge_fs_only_pou()` — fs has POU as-cli missed
- `test_merge_as_cli_only_pou()` — as-cli has POU fs missed
- `test_merge_path_mismatch()` — conflict detected, logged
- `test_merge_type_mismatch()` — conflict detected, logged
- `test_conflict_report_generation()` — report has correct summary
- `test_merge_uses_as_cli_as_source_of_truth()` — as-cli value preferred

**`tests/test_as_cli_config.py`**
- `test_config_load_defaults()` — as_cli section populated
- `test_config_validate_enabled_true()` — passes validation
- `test_config_validate_timeout_negative()` — fails validation
- `test_config_validate_unknown_command()` — fails validation
- `test_config_backward_compat()` — old config without as_cli section → defaults

### Integration Tests

**`tests/test_as_cli_engine_integration.py`**
- `test_run_generate_without_as_cli()` — uses filesystem (existing behavior)
- `test_run_generate_with_as_cli_success()` — uses as-cli, merges, continues
- `test_run_generate_with_as_cli_not_available_graceful()` — falls back
- `test_run_generate_with_as_cli_not_available_strict()` — raises exception
- `test_run_generate_cli_flag_overrides_config()` — precedence correct

### Test Fixtures

**Mocked as-cli output samples:**
- `fixtures/as_cli_logical_list.json` — sample output
- `fixtures/as_cli_symbol_search.json` — sample output

**Real as-cli tests (conditional):**
- Marked with `@pytest.mark.as_cli` (skip if as-cli not installed)
- Can be run manually with `pytest -m as_cli`

---

## Summary of Phase 1 Deliverables

- [ ] **Architecture Document** (this file)
- [ ] **New Modules** (code stubs):
  - [ ] `as_docs/scanner/as_cli_adapter.py`
  - [ ] `as_docs/scanner/as_cli_models.py`
  - [ ] `as_docs/scanner/data_conflict_resolver.py`
- [ ] **Config Updates**:
  - [ ] Add `AsCliConfig` to `as_docs/config.py`
  - [ ] Add validation function
  - [ ] Update `.as-docs.yaml.example`
- [ ] **Engine Updates**:
  - [ ] Update `as_docs/engine.py` with as_cli branch
- [ ] **CLI Updates**:
  - [ ] Add `--use-as-cli` flag to generate command
  - [ ] Add `as-cli-check` command
- [ ] **Test Plan** (written, not implemented):
  - [ ] Unit test files sketched
  - [ ] Integration test files sketched
  - [ ] Fixtures identified

**Status:** Phase 1 architecture finalized. Ready for Phase 2 (Implementation) review.
