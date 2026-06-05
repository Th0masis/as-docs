# as-docs — Project Architecture & Development Guide

> **Purpose of this document:** Complete reference for AI agents and developers cooperating on the `as-docs` project. Contains all architectural decisions, data models, file structures, and implementation phases. Do not contradict decisions documented here without explicit confirmation from the project owner.

---

## 1. Project Overview

`as-docs` is a documentation generation tool for **B&R Automation Studio (AS) projects** written primarily in Structured Text (IEC 61131-3 ST). It parses AS project files, extracts structural and semantic information, optionally enriches it with AI-generated descriptions, and outputs documentation in multiple formats readable by both humans and AI agents.

### Goals
- Help engineers understand unfamiliar AS projects quickly
- Document connections between tasks, programs, function blocks, and variables
- Produce output consumable by AI agents (MCP tools, `llms.txt`, JSON graph)
- Stay in sync with the project via git hooks and incremental cache updates

### Target Users
- Human engineers (onboarding, code review, debugging)
- AI agents (Claude Code, claude.ai, VS Code Copilot/Claude extension)

### Project Scale Target
- ~40 POUs
- ~30,000–50,000 lines of ST code
- Small to mid-large AS projects

---

## 2. Repository Structure

```
as-docs/                              monorepo — one version number
│
├── as_docs/                          Python package (the engine)
│   ├── scanner/                      Layer 1: deterministic file parsers
│   │   ├── project_scanner.py        walks project dir, discovers all files
│   │   ├── pkg_parser.py             .pkg/.prg → POU metadata
│   │   ├── var_parser.py             .var → variable declarations
│   │   ├── typ_parser.py             .typ → STRUCT/ENUM/ALIAS definitions
│   │   └── per_parser.py             .per XML → task config
│   │
│   ├── analyzer/                     Layer 2: heuristic ST analysis
│   │   ├── st_analyzer.py            regex-based ST code analysis
│   │   ├── call_graph.py             builds POU call hierarchy
│   │   ├── xref_builder.py           variable cross-references (read/write)
│   │   └── flow_extractor.py         CASE/IF/loop → control flow structure (Level 4)
│   │
│   ├── model/                        core data model
│   │   ├── project.py                ProjectModel dataclass tree
│   │   └── graph.py                  KnowledgeGraph (nodes + edges)
│   │
│   ├── enricher/                     Layer 3: AI enrichment
│   │   ├── ai_enricher.py            AI provider calls per POU/task (Copilot-first with Anthropic fallback)
│   │   ├── cache.py                  SHA256 hash-based cache
│   │   └── prompts.py                prompt templates per level
│   │
│   ├── generator/                    Layer 4: output rendering
│   │   ├── markdown_gen.py           per-POU and per-task .md files
│   │   ├── diagram_gen.py            Mermaid structural diagrams
│   │   ├── flow_diagram_gen.py       Mermaid behavioral flow diagrams (Level 4)
│   │   ├── json_gen.py               knowledge_graph.json
│   │   └── llms_txt_gen.py           llms.txt index
│   │
│   ├── mcp_server.py                 FastMCP server (stdio + HTTP transport)
│   ├── cli.py                        Click CLI entry points
│   └── config.py                     .as-docs.yaml loader/validator
│
├── tests/
│   └── fixtures/                     small synthetic AS project samples
│
├── pyproject.toml
├── .as-docs.yaml.example             template config for new projects
└── README.md
```

---

## 3. B&R AS Project File Structure

The tool parses standard AS 4.x project layout:

```
MyProject/
├── Logical/
│   ├── Libraries/
│   ├── MyProgram/
│   │   ├── MyProgram.prg             package descriptor (XML-like)
│   │   ├── Main.st                   ST source code
│   │   ├── Local.var                 local variable declarations
│   │   └── Types.typ                 local type definitions
│   ├── GlobalVars.var                global variable list (GVL)
│   └── GlobalTypes.typ
├── Physical/
│   └── Config1/
│       └── X20CP.../
│           ├── Cpu.per               task config (cyclic/init/exit, cycle times)
│           └── ...                   IO mappings
├── Binaries/                         compiled output — IGNORED by scanner
├── Diagnosis/                        runtime diagnostics — IGNORED by scanner
└── Temp/                             build artifacts — IGNORED by scanner
```

`Temp/`, `Binaries/`, and `Diagnosis/` are always excluded from scanning.

### Multiple Physical Configurations

AS projects often have multiple configurations under `Physical/` (e.g., `Config1/` for production hardware, `Config2/` for simulation). Each has its own `Cpu.per` with potentially different task assignments. The scanner parses only the **active configuration**, controlled by `.as-docs.yaml`:

```yaml
scanner:
  active_configuration: "Config1"    # default: first found alphabetically
```

The active configuration name is stored in `KnowledgeGraph.active_configuration` and included in `overview.md` so readers know which hardware context the docs describe.

### Library Handling

`Logical/Libraries/` contains two categories that must be handled differently:

| Library type | Example | Scanner behaviour |
|---|---|---|
| **B&R / third-party precompiled** | `MpAxis`, `ACP10`, `ArSsl` | Excluded from source scan. FBs appear in `.var` declarations as types — recognized as external, marked `is_external_library: True` in `POUNode`, not documented internally. |
| **Custom in-project libraries** | Project-specific ST code in `Libraries/` | Scanned like any other POU folder. |

Controlled by `.as-docs.yaml`:
```yaml
scanner:
  scan_libraries: true                # scan Logical/Libraries/ for custom lib ST code
  external_lib_prefixes:              # known precompiled prefixes → skip as external
    - "Mp"
    - "Mc"
    - "ACP10"
    - "Ar"
```

### File Types and Parser Responsibility

| File | Parser | What is extracted |
|---|---|---|
| `.pkg` / `.prg` | `pkg_parser.py` | POU names, types (PROGRAM/FB/FN), parent package |
| `.per` | `per_parser.py` | Task name, task type, cycle time, assigned programs. **Note:** `Cpu.sw` `<Task Name>` attribute is limited to 10 characters — match tasks↔programs by `Source` path attribute, not by name equality. |
| `.var` | `var_parser.py` | Variable name, type, initial value, scope (LOCAL/GLOBAL/GVL name) |
| `.typ` | `typ_parser.py` | STRUCT members, ENUM values, ALIAS targets |
| `.st` | `st_analyzer.py` + `flow_extractor.py` | Calls, variable usage (read/write), control flow structure |

`Temp/`, `Binaries/`, and `Diagnosis/` directories are always excluded from scanning.

---

## 4. Core Data Model

All layers produce and consume this model. It is the single source of truth.

```python
# model/graph.py

from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Variable:
    name: str
    var_type: str                          # REAL, BOOL, custom STRUCT, etc.
    scope: Literal["LOCAL", "GLOBAL"]
    gvl_name: str | None                   # if GLOBAL: which GVL
    initial_value: str | None
    var_class: Literal["VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"] = "VAR"
    description: str = ""                 # from trailing (* comment *) in .var/.typ
    unit: str | None = None               # engineering unit from [unit] in description

@dataclass
class DataTypeMember:
    name: str
    member_type: str
    initial_value: str | None
    description: str = ""
    unit: str | None = None

@dataclass
class DataType:
    name: str
    kind: Literal["STRUCT", "ENUM", "ALIAS"]
    members: list[DataTypeMember]          # STRUCT fields or ENUM values
    alias_target: str | None               # only for ALIAS
    source_file: str

@dataclass
class POUNode:
    name: str
    pou_type: Literal["PROGRAM", "FUNCTION_BLOCK", "FUNCTION"]
    source_file: str
    description: str = ""                  # AI generated (Level 3)
    patterns: list[str] = field(default_factory=list)   # AI detected patterns
    responsibilities: list[str] = field(default_factory=list)
    notes: str = ""
    local_vars: list[Variable] = field(default_factory=list)
    instances: list[str] = field(default_factory=list)  # instance names in parents
    is_external_library: bool = False      # True for FBs from precompiled libs (Mp*, Mc*, ACP10*)

@dataclass
class TaskConfig:
    name: str
    task_type: Literal["cyclic", "init", "exit"]
    cycle_time_ms: int | None
    programs: list[str]
    configuration: str = ""               # which Physical config this task belongs to
    description: str = ""                  # AI generated (Level 2)
    responsibilities: list[str] = field(default_factory=list)

@dataclass
class Edge:
    source: str                            # POU name or task name
    target: str                            # POU name or variable name
    edge_type: Literal["CALLS", "READS", "WRITES", "INSTANCE_OF", "OWNS"]

@dataclass
class FlowNode:
    node_id: str
    label: str                             # plain English label (AI enriched)
    raw_condition: str | None              # original ST condition text
    node_type: Literal["state", "branch", "action", "start", "end"]

@dataclass
class FlowDiagram:
    pou_name: str
    diagram_type: Literal["stateDiagram-v2", "flowchart", "sequenceDiagram"]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    source: Literal["parsed", "parsed+ai", "ai-generated"]
    mermaid_code: str
    narrative: str = ""                    # AI generated flow description

@dataclass
class KnowledgeGraph:
    schema_version: str                    # bump when model changes; triggers full regen if mismatch
    project_name: str
    as_version: str
    generated_at: str
    level: int                             # 1-4: which level was generated
    active_configuration: str             # which Physical config was parsed
    pous: dict[str, POUNode]
    tasks: dict[str, TaskConfig]
    global_vars: dict[str, Variable]
    data_types: dict[str, DataType]        # STRUCT/ENUM/ALIAS definitions
    edges: list[Edge]
    flow_diagrams: dict[str, FlowDiagram]  # keyed by POU name, Level 4 only
```

---

## 5. Documentation Levels

Levels are **strict supersets** — Level N always includes everything from Level N-1.

### Level 1 — Project Map
- **AI calls:** 0
- **Time:** seconds
- **Purpose:** orientation, onboarding, AI agent routing

Output files:
```
overview.md           project metadata, AS version, CPU, task list, GVL list
architecture.md       Mermaid: Task→Program→FB structural call graph
global_vars.md        GVL tables (name, type, initial value) — no cross-refs
data_types.md         all STRUCTs, ENUMs, ALIASes with member definitions
knowledge_graph.json  all nodes, structural edges only (CALLS, INSTANCE_OF)
llms.txt              file index with one-line descriptions
```

### Level 2 — Task Overview
- **AI calls:** 1 per task (task-scoped prompt, NO source code sent)
- **Time:** ~45 seconds for typical project
- **Purpose:** architecture review, PR descriptions, understanding task responsibilities

Additional output:
```
tasks/{TaskName}.md   description, responsibilities, GVL usage table,
                      cross-task variable coupling, program list
data_flow.md          Mermaid: inter-task data coupling via shared globals
global_vars.md        enriched: task-level read/write ownership per variable
knowledge_graph.json  + task→program edges, GVL ownership, AI task descriptions
```

Per-task Markdown structure:
```markdown
# {TaskName}
**Type:** Cyclic  **Interval:** {N}ms
**Programs:** Program1, Program2

## Description
{AI: 2-3 sentence summary}

## Responsibilities
{AI: bullet list 3-5 items}

## Global Variables Used
| Variable | GVL | Direction |
|---|---|---|
| gMotorSpeed | GVL_Drive | WRITE |

## Data Coupling
{which other tasks share variables with this task}

## Programs In This Task
- Program1 — [detail available at Level 3]
```

### Level 3 — POU Detail
- **AI calls:** 1 per POU (full source code, rich JSON schema)
- **Time:** ~3 min cold / instant if cached
- **Purpose:** deep debugging, code review, full agent context

Additional output:
```
pou/{POUName}.md      description, interface table, global var usage,
                      call graph (Mermaid), detected patterns, notes
global_vars.md        full cross-reference down to POU level
knowledge_graph.json  complete graph — all READS/WRITES edges at POU level,
                      AI descriptions on every node
```

AI response schema for Level 3 (JSON):
```json
{
  "description": "2-3 sentence description of what the block does",
  "responsibilities": ["bullet 1", "bullet 2"],
  "inputs": "description of input variables and their effect",
  "outputs": "description of output variables",
  "side_effects": ["writes gMotorSpeed", "reads gFault"],
  "patterns": ["PID control loop", "state machine", "fault interlock"],
  "notes": "important behavioral observations, edge cases"
}
```

### Level 4 — Flow Diagrams
- **AI calls:** 0–1 per POU (depends on parser confidence)
- **Time:** ~6 min cold / incremental on file changes
- **Purpose:** behavioral understanding — HOW a block works step by step

Additional output:
```
pou/{POUName}.flow.md   behavioral diagram + narrative + confidence tag
flows/                  cross-POU sequence diagrams
```

#### Level 4 Parser-First Strategy

```
For each POU:

1. Check Level 3 patterns[] — does it suggest complex control flow?
   If simple linear logic (<3 branches, no CASE, no loop) → SKIP (note in .md)

2. Static parse attempt:
   CASE statement found?         → stateDiagram-v2    confidence: HIGH
   IF/ELSIF chain (>3 branches)? → flowchart           confidence: MEDIUM
   FOR/WHILE loop?               → flowchart           confidence: MEDIUM
   None / too complex?           → AI FALLBACK         confidence: LOW

3. Enrichment:
   HIGH or MEDIUM confidence:
     → send parsed skeleton + source to AI
     → AI contributes: plain-English condition labels, flow narrative
     → tagged: 🟢 Parsed + AI-enriched

   LOW confidence (AI fallback):
     → send full source to AI
     → AI generates complete Mermaid diagram
     → tagged: 🔴 AI-generated ⚠ verify against source
```

#### Confidence Tags in Output
Every Level 4 diagram includes a visible trust indicator:
```
🟢 Parsed + AI-enriched — Structure from source, labels by AI. High confidence.
🟡 Parsed + AI-enriched — Partial parse, complex branches simplified. Verify.
🔴 AI-generated — Parser could not extract structure. Verify before trusting.
```

#### Diagram Type Selection
| Detected Pattern | Mermaid Diagram Type |
|---|---|
| CASE-based state machine | `stateDiagram-v2` |
| IF/ELSIF sequential logic | `flowchart TD` |
| FOR/WHILE iteration | `flowchart TD` |
| Inter-task data timing | `sequenceDiagram` |
| Linear / simple | skipped |

---

## 6. ST Analyzer Strategy

**No full grammar parser.** Targeted regex + heuristics for documentation purposes. Covers ~85–90% of cases — sufficient for docs, not suitable for a linter or compiler.

### ST Analyzer targets (`st_analyzer.py`)
```
Left side of :=        → WRITE to variable
Right side / conditions → READ of variable
Pattern: identifier(   → function/FB call
Pattern: identifier.   → FB method/property access
VAR block in .st       → local instance declarations
```

### Flow Extractor targets (`flow_extractor.py`)
```
CASE {expr} OF
  {value}: {body}       → state node + body actions
  ...
END_CASE

IF {cond} THEN          → branch node, condition captured as raw text
  ...
ELSIF {cond} THEN
  ...
END_IF

FOR / WHILE             → loop node
```

The flow extractor produces `FlowNode` objects and transition lists, not Mermaid directly. `flow_diagram_gen.py` renders FlowNodes to Mermaid strings.

**Scoping:** Each `.st` file contains `_INIT`, `_CYCLIC`, and `_EXIT` sections. The flow extractor must scope analysis per section — do not merge control flow across sections.

**High-confidence trigger:** `CASE` operating on a variable whose type ends in `Enum` (e.g., `Local.State : MyStateEnum`) → always produce `stateDiagram-v2` with HIGH confidence.

### B&R Naming Conventions as Analyzer Heuristics

Source: `agentic-engineering-in-automation-studio/copilot/template/.github/instructions/as-project-code.instructions.md`

These conventions are deterministic (no AI needed) and improve edge classification accuracy:

| Prefix / Pattern | Meaning | Analyzer use |
|---|---|---|
| `g…` | Global variable | Cross-check scope classification against GVL list |
| `di…` / `si…` | Digital/Safety Input | Direction hint → always READ, never WRITE target |
| `do…` | Digital Output | Direction hint → WRITE target in POU that owns it |
| `ai…` / `ao…` / `at…` | Analog I/O / Temperature | Same directional hints as digital |
| `p…` | Pointer | Handle `p^.Field` dereference as a separate read target; `p^.Field :=` as WRITE |
| `SCREAMING_SNAKE_CASE` | Constant | Never appears as WRITE target — skip if seen on left side of `:=` |
| `*Type` suffix | User-defined type | Suppress from variable cross-ref; it's a type reference, not a value |
| `*Enum` type / `ENUMNAME_VALUE` members | Enum literal | Enum members on right side of `:=` are READ of a literal, not a variable |
| `<FBType>_<suffix>` (e.g., `TON_delay`, `TON_0`) | FB instance | Improve `INSTANCE_OF` edge detection from VAR block declarations |

**FB call idiom — assign-then-call pattern:**
```
TON_delay.PT := config.delayTime;   ← input binding (treat as: writes INTO instance)
TON_delay.IN := TRUE;               ← input binding
TON_delay();                        ← the actual CALLS edge
```
Group all `Instance.Field :=` statements immediately preceding `Instance()` as input bindings of the same call site. Do not emit them as standalone WRITE edges to the parent POU's variables.

**Well-known library FBs to recognize in `patterns[]`:**
- `R_TRIG` / `F_TRIG` → pattern: `"edge detection"`
- `TON` / `TOF` / `TP` → pattern: `"timer"`
- `MpAlarmX*` → pattern: `"mapp AlarmX alarm handling"`
- `MpAxis*` / `MC_*` → pattern: `"motion control"`

---

## 7. AI Enrichment & Caching

### Cache Strategy
- Cache stored in `.as-docs-cache/` (gitignored)
- Key: `SHA256(file_content)` per `.st` file
- Level-aware: separate cache entries for Level 2 (task), Level 3 (POU), Level 4 (flow)
- On `generate`: compute hash, compare to cache, skip API call if match
- On `upgrade --to N`: only process POUs not yet cached at level N

### AI Model
- Current branch default provider/model: Copilot-compatible chat completions + `gpt-4.1`
- Anthropic provider is available as a fallback runtime for users without Copilot
- `max_tokens: 1024` for Level 2/3, `2048` for Level 4 (Mermaid can be verbose)

### Level 2 Prompt (task-scoped, no source code)
```
You are documenting a B&R Automation Studio project.

Task: {task_name}
Type: {task_type}, interval: {cycle_time}ms
Programs assigned: {program_list}
Global variables accessed: {gvl_usage_table}
Cross-task variable sharing: {coupling_summary}

Return JSON only with keys:
  description, responsibilities (array), notes
```

### Level 3 Prompt (full source)
```
You are documenting a B&R Automation Studio FUNCTION_BLOCK / PROGRAM.

B&R naming conventions (use these to interpret code correctly):
- Local variables: CamelCase (e.g., ActPressure, CommandCount)
- Global variables: g-prefix CamelCase (e.g., gMotorSpeed)
- IO variables: di/do/ai/ao/at/si prefix (e.g., diStartButton, doLampGreen)
- Constants: SCREAMING_SNAKE_CASE (e.g., MAX_RETRY_COUNT)
- Pointers: p-prefix (e.g., pAxisStatus)
- FB instances: <FBType>_<suffix> (e.g., TON_delay, TON_0)
- User types: CamelCase ending in Type (e.g., RecipeType)
- Enums: ending in Enum, members as ENUMNAME_VALUE (e.g., MYSTATE_IDLE)
- Task sections: _INIT (one-time init), _CYCLIC (recurring), _EXIT (cleanup)
- FB call idiom: assign inputs before call (FB.PT := x; FB.IN := y; FB();)

POU: {name}  Type: {pou_type}
Local vars: {var_summary}
Global vars used: {gvl_usage_with_direction}
Called by: {callers}
Calls: {callees}

[full ST source code]

Return JSON only with keys:
  description, responsibilities, inputs, outputs,
  side_effects, patterns, notes

For patterns[], prefer B&R vocabulary: "state machine", "edge detection",
"timer", "fault interlock", "mapp AlarmX alarm handling", "motion control",
"PID control loop", "data acquisition", "sequence control".
```

### Level 4 Prompt — AI Enrichment (parsed skeleton available)
```
You are enriching a parsed control flow diagram for a B&R ST function block.

POU: {name}
Parsed structure: {flow_nodes_json}
Raw ST conditions: {conditions_list}

[full ST source code]

Enrich each node label to plain English.
Write a flow_narrative (3-5 sentences describing the behavior).
Return JSON only with keys:
  enriched_nodes (array: {node_id, plain_label}),
  flow_narrative
```

### Level 4 Prompt — AI Fallback (no parsed skeleton)
```
You are generating a behavioral flow diagram for a B&R ST function block.

POU: {name}
Detected patterns: {patterns_from_level3}

[full ST source code]

Select the most appropriate Mermaid diagram type:
  stateDiagram-v2, flowchart TD, or sequenceDiagram

Return JSON only with keys:
  diagram_type, mermaid_code, flow_narrative
```

---

## 8. Output File Reference

### `knowledge_graph.json` — machine-readable backbone
All other outputs are rendered views of this file. AI agents should prefer querying this directly.

```json
{
  "schema_version": "1.0",
  "project_name": "MyProject",
  "as_version": "4.10",
  "generated_at": "2026-05-15T10:00:00",
  "level": 3,
  "active_configuration": "Config1",
  "tasks": {
    "CyclicTask_10ms": {
      "task_type": "cyclic",
      "cycle_time_ms": 10,
      "configuration": "Config1",
      "programs": ["MainControl"],
      "description": "..."
    }
  },
  "pous": {
    "MotorControl_FB": {
      "pou_type": "FUNCTION_BLOCK",
      "source_file": "Logical/MainControl/MotorControl.st",
      "description": "...",
      "patterns": ["PID control loop", "fault interlock"],
      "local_vars": [...],
      "instances": ["fbMotor"],
      "is_external_library": false
    }
  },
  "global_vars": {
    "gMotorSpeed": {
      "var_type": "REAL",
      "scope": "GLOBAL",
      "gvl_name": "GVL_Drive",
      "initial_value": "0.0",
      "description": "Actual motor speed",
      "unit": "rpm"
    }
  },
  "data_types": {
    "MotorConfigType": {
      "name": "MotorConfigType",
      "kind": "STRUCT",
      "source_file": "Logical/GlobalTypes.typ",
      "members": [
        { "name": "MaxSpeed", "member_type": "REAL", "initial_value": "3000.0", "unit": "rpm" },
        { "name": "RampTime", "member_type": "TIME",  "initial_value": "T#2s" }
      ],
      "alias_target": null
    }
  },
  "edges": [
    { "source": "CyclicTask_10ms", "target": "MainControl", "edge_type": "OWNS" },
    { "source": "MainControl", "target": "MotorControl_FB", "edge_type": "CALLS" },
    { "source": "MotorControl_FB", "target": "gMotorSpeed", "edge_type": "WRITES" },
    { "source": "MotorControl_FB", "target": "gFault", "edge_type": "READS" }
  ],
  "flow_diagrams": {
    "MotorControl_FB": {
      "diagram_type": "stateDiagram-v2",
      "confidence": "HIGH",
      "source": "parsed+ai",
      "mermaid_code": "stateDiagram-v2\n  ...",
      "narrative": "..."
    }
  }
}
```

### `llms.txt` — AI agent entry point
```
# MyProject — AS Documentation Index
Generated: 2026-05-15  Level: 3

## Entry points
overview.md             Project summary, task list, hardware config
architecture.md         Full call graph: Task → Program → FB
data_flow.md            Cross-task data coupling via global variables
global_vars.md          All global variables with cross-references
knowledge_graph.json    Machine-readable full project graph

## Tasks
tasks/CyclicTask_10ms.md    Real-time motion control, 10ms, 1 program
tasks/CyclicTask_100ms.md   Safety monitoring, 100ms, 2 programs

## POUs
pou/MainControl.md          Main sequencing program
pou/MotorControl_FB.md      PID motor speed control with fault interlock
pou/ValveSequencer_FB.md    Valve open/close sequence with position feedback
...

## Flow diagrams (Level 4)
pou/MotorControl_FB.flow.md     State machine — 🟢 parsed+AI
pou/ValveSequencer_FB.flow.md   Sequential flow — 🟡 parsed+AI
```

---

## 9. MCP Server

### Transport
```
stdio (default)    started by MCP client, zero config, local only
HTTP (opt-in)      as-docs serve --http --port 8765
                   compatible with mcp-remote proxy
                   same server code, different FastMCP transport
```

### MCP Tools

Read-only tools (always available):
```python
get_overview()
  # returns project summary, task list, generation level and timestamp

get_pou_list()
  # returns all POUs with type, brief description, source file

get_pou(name: str)
  # returns full POU doc at highest available level
  # if Level 3 not generated: returns structural info + upgrade hint

get_task(name: str)
  # returns full task doc at highest available level
  # Level 1: structural info (programs, cycle time, configuration)
  # Level 2+: + description, responsibilities, GVL usage, cross-task coupling

find_variable(name: str)
  # returns all POUs that READ or WRITE this variable, with task context

get_data_flow()
  # returns cross-task coupling Mermaid diagram + coupling summary

get_call_graph(root: str | None = None)
  # returns call hierarchy from project root or specific POU

get_global_vars(gvl: str | None = None)
  # returns GVL contents, optionally filtered to one GVL

search(query: str)
  # text search across POU descriptions, variable names, patterns

get_flow_diagram(name: str)
  # returns Level 4 flow diagram for a POU (if generated)
  # includes confidence tag and narrative
```

Action tools:
```python
regenerate(scope: Literal["all", "changed", "pou:{name}"])
  # triggers re-parse and AI enrichment
  # "changed": only files modified since last run (uses git diff)
  # returns summary: N files scanned, M AI calls made, K cached

get_cache_status()
  # returns per-POU cache state: level cached, last updated, stale flag

upgrade(to_level: int, pou: str | None = None)
  # upgrades docs to higher level
  # --pou: upgrade single POU to Level 3/4 on demand
```

### Level-Aware Tool Responses
If requested data is not yet generated at sufficient level:
```json
{
  "status": "partial",
  "available_level": 1,
  "requested_level": 3,
  "data": { "...structural info..." },
  "hint": "Run: as-docs upgrade --to 3 --pou MotorControl_FB"
}
```

### Distribution

- **Phase 3 (current):** installed via `pipx install as-docs` (Python package on PyPI). Invoked as a subprocess by MCP clients.
- **Phase 7 (later):** prebuilt standalone `.exe` placed under `%APPDATA%\as-docs-mcp\as-docs-server.exe` for parity with sibling MCPs (`as-help-mcp`, `br-community-mcp`).

**`mcp.json` shape** (mirrors the agentic-engineering template convention):
```json
{
  "mcpServers": {
    "as-docs": {
      "command": "as-docs",
      "args": ["serve"],
      "env": {}
    }
  }
}
```
HTTP mode: replace `args` with `["serve", "--http", "--port", "8765"]` and point MCP client to `http://127.0.0.1:8765/mcp`.

---

## 10. CLI Reference

```bash
# Initial setup
as-docs init                          # detect project root, create .as-docs.yaml
                                      # validates presence of Logical/ and Physical/
                                      # walks up directory tree if not found in cwd
                                      # adds .as-docs-cache/ and docs/as-docs/ to .gitignore
as-docs init --http                   # init with HTTP transport mode

# Generation
as-docs generate                      # Level 3 (default)
as-docs generate --level 1            # project map only
as-docs generate --level 2            # + task overviews
as-docs generate --level 4            # full including flow diagrams
as-docs generate --no-ai              # Level 1 only, no API calls

# Incremental upgrades
as-docs upgrade --to 2                # add Level 2 on top of existing Level 1
as-docs upgrade --to 3                # add Level 3
as-docs upgrade --to 3 --pou MotorControl_FB   # single POU upgrade

# Status and cache
as-docs status                        # current level, staleness per POU
as-docs cache clear                   # clear all cached AI responses
as-docs cache clear --pou MotorControl_FB

# MCP server
as-docs serve                         # stdio mode (used by MCP clients)
as-docs serve --http --port 8765      # HTTP mode

# Watch mode (daemon)
as-docs watch                         # watch for file changes, regenerate on save
as-docs watch --level 2               # only regenerate up to Level 2 on change

# Git integration
as-docs install-hook                  # install post-commit hook (opt-in)
as-docs diff HEAD~1                   # show which POUs changed since last commit
```

---

## 11. Configuration File

`.as-docs.yaml` — committed to the AS project repository root.

```yaml
project:
  name: "MyMachineProject"
  as_version: "4.10"
  root: "."                         # relative to this config file
  language: "en"                    # documentation output language

scanner:
  active_configuration: "Config1"   # which Physical config to parse
                                    # default: first found alphabetically
  ignore_dirs:                      # always excluded from scanning
    - Temp
    - Binaries
    - Diagnosis
  scan_libraries: true              # scan Logical/Libraries/ for custom lib ST code
  external_lib_prefixes:            # known precompiled prefixes → skip as external
    - "Mp"
    - "Mc"
    - "ACP10"
    - "Ar"

ai:
  enabled: true
  provider: "copilot"               # copilot | anthropic
  model: "gpt-4.1"
  api_base_url: "https://models.inference.ai.azure.com/chat/completions"
  api_key_env: "GITHUB_TOKEN"
  timeout_seconds: 60
  max_retries: 3
  cache_dir: ".as-docs-cache"       # gitignored

server:
  mode: "stdio"                     # stdio | http
  port: 8765
  host: "127.0.0.1"                 # use 0.0.0.0 for team-shared remote

output:
  docs_dir: "docs/as-docs"
  formats:
    - markdown
    - json
    - llms.txt
  mermaid: true
  default_level: 3

git:
  hook_enabled: false               # set true after as-docs install-hook
  auto_level: 2                     # level to regenerate on commit
```

---

## 12. IDE Integration

`as-docs` integrates into VS Code through the **agentic-engineering-in-automation-studio** template — the same mechanism used by the `as-help` and `br-community` MCP servers. There is no custom VS Code extension.

### Deliverables (Phase 5)
The following files are contributed to the `agentic-engineering-in-automation-studio` repository:

| File | Purpose |
|---|---|
| `copilot/mcp/as-docs/mcp.json` | MCP server registration (mirrors `as-help/mcp.json` shape) |
| `copilot/mcp/as-docs/README.md` | Setup and usage guide |
| `template/.github/skills/as-docs/SKILL.md` | Skill wrapping `as-docs generate`, `upgrade`, `status` |
| `template/.github/instructions/as-project-documentation.instructions.md` | Tells Copilot to keep docs fresh after ST/var/typ changes |
| `template/.github/collections/as-project-documentation.collection.yml` | Bundles the skill + instruction as an opt-in collection |

### Agent Registration
The as-docs MCP is registered in `template/.github/agents/as-project.agent.md` alongside `as-help` and `br-community`, enabling the default AS agent to answer call-graph and data-flow questions directly from Copilot chat.

---

## 13. Tech Stack

```
Python 3.11+
├── click / typer         CLI interface
├── urllib / json         current Copilot-compatible chat completions client path
├── anthropic             fallback AI analyzer provider path
├── copilot integration   default AI analyzer provider path
├── fastmcp               MCP server (stdio + HTTP)
├── jinja2                documentation templating
├── gitpython             git diff integration for incremental updates
├── watchdog              daemon / file watch mode
└── dataclasses + json    internal model (no heavy ORM dependencies)

No ANTLR, no matiec — targeted regex covers documentation use case.
No external database — knowledge_graph.json is the store.
No custom VS Code extension — IDE integration via agentic-engineering template + MCP.
```

---

## 14. Implementation Phases

```
Phase 1 — Foundation                              ~1.5 weeks
  ├── ProjectModel + KnowledgeGraph dataclasses
  ├── Project scanner (pkg, var, typ, per parsers)
  ├── ST analyzer (call graph + xref, regex + B&R heuristics)
  ├── CLI: as-docs generate --no-ai
  └── Output: basic Markdown + knowledge_graph.json
  ✓ Milestone: run on real AS project, get structural docs

Phase 2 — AI Enrichment                           ~1 week
  ├── AI provider abstraction (`copilot` runtime implemented, `anthropic` reserved)
  ├── Copilot-compatible client integration (implemented)
  ├── Auto token discovery: env var → GH_TOKEN → `gh auth token` (VS Code/CLI)
  ├── GitHub API pre-flight: login resolution + Copilot entitlement check
  ├── Anthropic client integration (deferred)
  ├── Hash-based cache (.as-docs-cache/, gitignored)
  ├── Per-POU description + pattern detection (Level 2 + Level 3)
  ├── Diagram generator (Mermaid structural diagrams)
  └── llms.txt generator
  ✓ Milestone: full docs with semantic descriptions and diagrams

Phase 3 — MCP Server + Distribution              ~1 week
  ├── FastMCP server wrapping the engine
  ├── All read tools + regenerate / upgrade tools
  ├── stdio transport (default)
  ├── HTTP transport (--http flag)
  ├── Level-aware partial responses with upgrade hints
  ├── Claude Code config snippet generator (as-docs init --mcp-config)
  └── pipx distribution (publish to PyPI)
  ✓ Milestone: Claude can answer questions about AS project via MCP

Phase 4 — Git Integration                         ~0.5 weeks
  ├── gitpython: detect changed .st/.var files since last commit
  ├── as-docs diff → only regenerate stale POUs
  ├── post-commit hook installer (opt-in)
  └── as-docs status → freshness report per POU
  ✓ Milestone: automatic incremental updates on commit

Phase 5 — Template Integration                    ~0.5 weeks
  ├── copilot/mcp/as-docs/{mcp.json, README.md}
  ├── template/.github/skills/as-docs/SKILL.md
  ├── template/.github/instructions/as-project-documentation.instructions.md
  ├── template/.github/collections/as-project-documentation.collection.yml
  └── Register as-docs MCP in template/.github/agents/as-project.agent.md
  ✓ Milestone: as-docs ships as a first-class MCP in the agentic-engineering template

Phase 6 — Level 4 Flow Diagrams                   ~1.5 weeks
  ├── flow_extractor.py (CASE → states, IF/ELSIF → branches, FOR/WHILE → loops)
  ├── Parser confidence scoring (HIGH / MEDIUM / LOW)
  ├── flow_diagram_gen.py (FlowNodes → Mermaid strings)
  ├── AI enrichment (label enrichment + narrative) + AI fallback
  ├── Confidence tagging in output (🟢 🟡 🔴)
  └── Cross-POU sequence diagram generator
  ✓ Milestone: behavioral flow diagrams for all non-trivial POUs

Phase 7 — Prebuilt MCP Binary (optional)          ~0.5 weeks
  └── Package as standalone .exe under %APPDATA%\as-docs-mcp\ for parity
      with as-help-mcp / br-community-mcp
  ✓ Milestone: zero-Python install for teams already using sibling MCPs
```

---

## 15. Key Architectural Decisions (do not reverse without discussion)

| Decision | Choice | Rationale |
|---|---|---|
| Package structure | Monorepo: Python engine only | Single version, clean Python package |
| Engine interfaces | CLI + MCP server | All clients use same engine, no duplication |
| IDE integration | agentic-engineering template MCP + skill + collection | No custom extension; reuses existing template infrastructure |
| Distribution | pipx first; prebuilt `.exe` later (Phase 7) | Matches sibling MCPs once stable |
| MCP transport | stdio default, HTTP opt-in | Local-first, remote when needed |
| MCP config shape | Mirrors `as-help-mcp` / `br-community-mcp` `mcp.json` | Consistent with agentic-engineering template |
| Config file | `.as-docs.yaml` per project | Committed to repo, team-shared |
| Excluded dirs | `Temp/`, `Binaries/`, `Diagnosis/` | Build artifacts / diagnostics mirror Logical/ and cause duplicates |
| Multiple Physical configs | `active_configuration` in config, single config parsed | Avoids task duplication; team picks relevant config |
| Library handling | Precompiled libs marked external; custom libs scanned | Preserves call-graph accuracy without documenting vendor internals |
| ST parsing approach | Targeted regex + B&R naming heuristics, no full grammar | Sufficient for docs, far simpler |
| AI provider/model | Current branch default `copilot` + `gpt-4.1`; `anthropic` reserved but not runtime-enabled | Match company Copilot-only environment while preserving future extension point |
| Cache strategy | SHA256 per file, level-aware | Incremental updates, API cost control |
| Schema versioning | `schema_version` field in `knowledge_graph.json` | Prevents silent model mismatch after upgrades |
| `DataType` model | Proper `DataType` + `DataTypeMember` dataclasses | Type-safe, consistent across all generators and MCP tools |
| Level architecture | 4 levels, strict superset | Flexible depth vs. cost tradeoff |
| Level 1 AI | None | Pure parsing, always fast |
| Level 2 AI | 1 call per task, no source sent | Task context only, cheap and fast |
| Level 3 AI | 1 call per POU, full source + B&R style guide | Rich descriptions aligned with B&R conventions |
| Level 4 strategy | Parser-first, AI-fallback | Deterministic where possible |
| Level 4 skip logic | Linear POUs (<3 branches) skipped | No noise in output |
| Diagram trust tags | 🟢 🟡 🔴 on every Level 4 diagram | Readers know what to trust |
| Knowledge graph | Central JSON, all outputs rendered from it | Single source of truth |
| Variable metadata | `description` + `unit` parsed from `(* comment [unit] *)` | Preserves engineer intent from .var/.typ files |
| Task name matching | Match by `Source` path, not by `Task Name` (10-char limit) | Prevents task↔program linking failures |
| Single POU upgrade | `--pou` flag on upgrade | On-demand depth without full project cost |
| Watch mode | `as-docs watch` via `watchdog` | Daemon-style incremental regen on file save |
| `as-docs init` validation | Check for `Logical/` + `Physical/`, walk up tree | Prevents running in wrong directory |
| `.gitignore` management | `init` adds `.as-docs-cache/` and `docs/as-docs/` | Developer never forgets to gitignore cache |
| as-cli dependency | Deferred | Parser-only approach sufficient; adopt when as-cli is GA |

---

## 16. Development Notes for AI Agents

- **Start implementation from the data model** (`model/project.py`, `model/graph.py`) — all other code depends on it
- **Use real AS project fixtures** in `tests/fixtures/` for all parser development — synthetic test data misses B&R-specific patterns
- **Never call external AI providers in tests** — use cached fixtures or mocked responses
- **Layer 1 and Layer 2 parsers must be deterministic** — same input always produces same output, no AI involvement
- **The `knowledge_graph.json` schema is stable after Phase 1** — do not change field names without bumping `schema_version` and updating all generators and MCP tools
- **On load, always validate `schema_version`** — if the file's version does not match the current tool version, force full regeneration and log a warning
- **MCP tool responses must always include `level`, `active_configuration`, and `generated_at`** — agents need to know freshness and scope of data
- **`get_task()` and `get_pou()` must both handle the partial-level case** — return structural info + upgrade hint when the requested level is not yet generated
- **Confidence tags are mandatory on all Level 4 diagrams** — never omit them for readability
- **`.as-docs-cache/` and `docs/as-docs/` must be added to `.gitignore` by `as-docs init`** — verify this during init, not just in documentation
- **`as-docs init` must validate AS project root** — check for `Logical/` and `Physical/` directories; walk up the tree if not found in cwd; exit with a clear error if not found
- **`Temp/`, `Binaries/`, `Diagnosis/` must always be excluded** — they contain build artifacts and diagnostics that mirror `Logical/` and cause duplicate POU detection
- **`scanner.external_lib_prefixes` controls external library detection** — FBs matching these prefixes get `is_external_library: True` and are excluded from AI enrichment but retained as nodes in the graph for call-graph accuracy
- **Never scan `Logical/Libraries/` precompiled content as ST source** — only scan subdirectories that contain `.st` files and are not matched by `external_lib_prefixes`
- **`active_configuration` must be stored in `knowledge_graph.json`** — readers and agents must know which Physical config the task topology reflects
- **Level 3 enrichment prompts must include the B&R style-guide excerpt** (see Section 7) — never produce descriptions that use generic variable naming inconsistent with B&R conventions
- **Task↔program linking must use `Source` path, not `Task Name`** — `Cpu.sw` task names are truncated to 10 characters; logical folder names are not
- **FB assign-then-call groups must be resolved before emitting edges** — `Inst.Field :=` lines immediately before `Inst()` are input bindings, not standalone WRITEs
- **B&R naming heuristics in `st_analyzer.py` are deterministic** — apply prefix table (Sec 6) before falling back to positional `:=` analysis
- **`DataType` must use the proper dataclass model** — never use raw `dict` for data types; `DataTypeMember` carries `unit` and `description` just like `Variable`

---

## 17. Known Limitations (v1)

These are documented constraints of the initial release. They are known and accepted — do not attempt to work around them without explicit discussion.

| Limitation | Detail |
|---|---|
| **Single Physical configuration** | Only the `active_configuration` from `.as-docs.yaml` is parsed. Other configs (e.g., simulation, test bench) are ignored. |
| **Precompiled library internals** | FBs from `Mp*`, `Mc*`, `ACP10*`, `Ar*` etc. appear as external nodes in the call graph but are not documented internally — no source available. |
| **ST only** | Ladder Diagram (LD), Function Block Diagram (FBD), and Sequential Function Chart (SFC) source files are not analyzed. Only `.st` files are processed. |
| **Conditional compilation not evaluated** | `#IF` / `#ELSE` / `#END_IF` preprocessor blocks are parsed as-is. The analyzer does not evaluate which branch is active. |
| **Very large POUs (>2000 lines)** | May approach AI context limits at Level 3/4. The enricher will split into chunks and note this with a `⚠ chunked` flag in the output. |
| **Cross-project library references** | Libraries from separate AS projects referenced via project references are not followed. |
| **Multi-POU `.st` files** | B&R AS normally puts one POU per `.st` file. If multiple `PROGRAM` / `FUNCTION_BLOCK` blocks exist in one file, each is extracted as a separate POU node. Edge case — not a primary target. |
| **IO mapping not parsed** | Physical IO channel assignments in the hardware tree are not extracted. Variable directionality is inferred from naming conventions (di/do/ai/ao) only. |
| **`as-docs diff` granularity** | Tracks changes at file level, not POU level. A `.st` file change marks the entire POU stale even if only a comment changed. |
