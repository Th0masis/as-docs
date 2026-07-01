# Changelog

All notable changes to as-docs are documented in this file.

## [0.3.0] - 2026-06-30

### Phase 2.5: CLI Updates - COMPLETE

#### Added
- `--use-as-cli` flag for `generate` command to enable as-cli integration on a per-run basis
- `as-cli-check` diagnostic command with 5-step troubleshooting workflow:
  - Configuration display
  - Availability check with guidance
  - Daemon connectivity verification
  - Command availability tests
  - Configuration recommendations
- Conflict report display in `generate` command output when as-cli merge produces conflicts
- 11 comprehensive CLI integration tests (100% passing)

#### Changed
- `generate` command now supports optional as-cli integration with CLI > config > default precedence
- CLI execution flow updated to show merge conflicts when as-cli is enabled

#### Documentation
- Added comprehensive "as-cli Integration" section to README.md
- Updated CLI Reference with new commands and flags
- Updated "Current Status" section with Phase 2.5 completion details
- Configuration template (`.as-docs.yaml.example`) already includes as_cli section from v0.2.0

### Phase 2.4: Engine Integration - COMPLETE

#### Added
- Engine-level integration of as-cli functionality
- Smart merge logic using union strategy with as-cli as source of truth
- Conflict reporting and save functionality
- Scope resolution for POU-level targeting
- 14 engine integration tests (100% passing)

#### Changed
- `run_generate()` now accepts `use_as_cli` parameter for optional integration

### Phase 2.3: Data Conflict Resolution - COMPLETE

#### Added
- `DataConflictResolver` class for merging filesystem and as-cli discovery results
- Conflict detection with path and type comparison
- ConflictReport generation with statistics
- 24 resolver tests (100% passing)

### Phase 2.2: as-cli Adapter - COMPLETE

#### Added
- `AsCliAdapter` class for subprocess execution and daemon lifecycle management
- Hybrid daemon mode with auto-start capability
- Windows named pipes support for as-cli communication
- Exception hierarchy for error handling
- 23 adapter tests (100% passing)

#### Features
- `is_available()` - checks if as-cli is installed
- `get_logical_list()` - retrieves module/task/program hierarchy
- `get_symbol_search()` - queries all symbols in project
- Graceful fallback on errors

### Phase 2.1: Configuration & Validation - COMPLETE

#### Added
- `AsCliConfig` dataclass with validation
  - `enabled` (bool, default: false) - opt-in design
  - `path` (str) - auto-detect from PATH
  - `timeout_ms` (int) - per-command timeout
  - `strict` (bool) - graceful fallback vs strict mode
  - `use_commands` (list) - command selection (logical_list, symbol_search)
- 23 configuration tests (100% passing)
- `.as-docs.yaml.example` updated with as_cli section and documentation

### Phase 1: Architecture Design - COMPLETE

#### Added
- Decision gates and rationale for as-cli integration
- MVP scope definition (logical_list, symbol_search)
- Merge strategy documentation
- Error handling and fallback behavior specification
- Architecture documentation in `AS_CLI_INTEGRATION_ARCHITECTURE.md`

## [0.2.0] - 2026-06-20

### Phases 0-4: Core as-docs Features - COMPLETE

#### Added
- **FastMCP Server**: stdio and HTTP transports for MCP client integration
- **Read Tools**: get_overview, get_pou_list, get_pou, get_task, find_variable, get_data_flow, get_call_graph, get_global_vars, search, get_flow_diagram
- **Action Tools**: regenerate, get_cache_status, upgrade
- **Git Integration**: as-docs diff, install-hook, watch with debouncing
- **Level 4 Flow Diagrams**: parser-first extraction with AI narrative fallback
- **Template Integration**: VS Code Copilot and MCP assets
- **Standalone Packaging**: PyInstaller build helper and configuration
- **Scoped Operations**: Regenerate by scope (all, changed, pou:NAME) and scoped upgrades

#### Features
- 4-level documentation generation (instant, task, POU, flow diagram)
- AI enrichment via Copilot SDK and Anthropic providers
- Provider/model-aware caching
- Nested package traversal (AS6+)
- Level-aware MCP responses with upgrade hints
- File event batching for watch mode

#### Tests
- 162 tests covering all phases (100% passing)
- MCP payload validation
- Scoped regeneration verification
- Git integration testing
- Level-aware response testing

## [0.1.0] - Initial Release

### Core Features
- Basic project scanning
- Markdown documentation generation
- YAML configuration support
- Initial CLI structure
