# as-docs Live Execution Checklist

Date: 2026-06-25
Purpose: Active execution tracker for remaining implementation work (not historical notes).
Source baseline: as-docs-architecture.md roadmap + current implementation scan

## Tracking legend
- [ ] Not started
- [~] In progress / partial
- [x] Complete

## Phase status snapshot
- [x] Phase 1: Foundation
- [x] Phase 2: AI enrichment
- [~] Phase 3: MCP server + distribution (core done, one planned CLI helper missing)
- [ ] Phase 4: Git integration
- [ ] Phase 5: Template integration
- [ ] Phase 6: Level 4 flow diagrams (parser-first pipeline)
- [ ] Phase 7: Prebuilt MCP binary (optional)

## Priority plan

### P0 - Finish core product behavior

#### 1) Implement scoped regeneration for CLI and MCP
- Priority: P0
- Estimate: 0.5-1 day
- Status: [ ]
- Why:
  - README currently states scoped regenerate/upgrade routes are exposed but execute full regeneration.
- Tasks:
  - [ ] Add real scope handling in engine for:
    - changed files
    - single POU
    - all
  - [ ] Wire CLI upgrade --pou to true scoped execution.
  - [ ] Wire MCP regenerate(scope) to true scoped execution.
  - [ ] Return clear result metadata (scope, touched POUs, elapsed time).
- Done criteria:
  - [ ] scope=changed only regenerates affected POUs.
  - [ ] scope=pou:NAME only regenerates NAME.
  - [ ] Existing full regeneration path remains intact.

#### 2) Implement Phase 4 git commands in CLI
- Priority: P0
- Estimate: 1-1.5 days
- Status: [ ]
- Tasks:
  - [ ] Implement as-docs diff <ref> using gitpython.
  - [ ] Implement install-hook (post-commit) with opt-in behavior.
  - [ ] Implement watch mode using watchdog and incremental regenerate.
  - [ ] Ensure status output aligns with incremental workflow.
- Done criteria:
  - [ ] CLI commands no longer print "not yet implemented".
  - [ ] Hook file is created/updated safely and idempotently.
  - [ ] Diff command outputs changed POUs reliably on sample fixture + repo tests.

### P1 - Complete roadmap integration

#### 3) Phase 5 template deliverables
- Priority: P1
- Estimate: 0.5-1 day
- Status: [ ]
- Tasks:
  - [ ] Add copilot/mcp/as-docs/mcp.json
  - [ ] Add copilot/mcp/as-docs/README.md
  - [ ] Add template/.github/skills/as-docs/SKILL.md
  - [ ] Add template/.github/instructions/as-project-documentation.instructions.md
  - [ ] Add template/.github/collections/as-project-documentation.collection.yml
  - [ ] Register as-docs MCP in template/.github/agents/as-project.agent.md
- Done criteria:
  - [ ] as-docs appears as a first-class option alongside existing MCPs.
  - [ ] Template docs include setup + usage steps.

#### 4) Implement planned init MCP helper option
- Priority: P1
- Estimate: 0.25 day
- Status: [ ]
- Tasks:
  - [ ] Add init option to generate MCP config snippet/file as planned.
  - [ ] Document in README and quickstart.
- Done criteria:
  - [ ] Fresh project can configure MCP with one command + minimal edits.

### P2 - Level 4 completion

#### 5) Build Level 4 parser-first flow pipeline
- Priority: P2
- Estimate: 2-3 days
- Status: [ ]
- Tasks:
  - [ ] Add analyzer/flow_extractor.py (CASE/IF/loop extraction).
  - [ ] Add generator/flow_diagram_gen.py (Mermaid generation from FlowNodes).
  - [ ] Add confidence scoring (HIGH/MEDIUM/LOW).
  - [ ] Add AI enrichment fallback for labels/narratives.
  - [ ] Populate graph.flow_diagrams during level 4 generate.
  - [ ] Ensure MCP get_flow_diagram returns real diagrams when level=4 docs exist.
- Done criteria:
  - [ ] Non-trivial POUs at level 4 produce stored flow diagrams.
  - [ ] flow diagram output includes confidence + source.

### P3 - Optional distribution hardening

#### 6) Phase 7 prebuilt executable packaging
- Priority: P3
- Estimate: 0.5-1 day
- Status: [ ]
- Tasks:
  - [ ] Define packaging approach for standalone executable.
  - [ ] Add install path and update instructions.
  - [ ] Validate parity with pipx behavior.
- Done criteria:
  - [ ] Team can run MCP server without local Python setup.

## Testing checklist to run after each milestone
- [ ] py -m pytest -q
- [ ] CLI smoke tests:
  - [ ] as-docs init
  - [ ] as-docs generate --no-ai
  - [ ] as-docs generate --level 3
  - [ ] as-docs status
  - [ ] as-docs serve
- [ ] MCP payload checks for overview, pou, task, variable, flow diagram
- [ ] README and quickstart updated for any new CLI behavior

## Suggested implementation order
1. Scoped regeneration + upgrade --pou true behavior
2. Git diff + install-hook + watch
3. Template integration files
4. init MCP helper option
5. Level 4 extraction/generation pipeline
6. Optional executable packaging
