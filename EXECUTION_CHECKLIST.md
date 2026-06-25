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

## Verification snapshot (2026-06-25)
- [x] Checklist matches current implementation status at a high level.
- [~] Scoped regenerate/upgrade routes exist but still run full regeneration (warning path present).
- [ ] CLI Phase 4 commands (`watch`, `install-hook`, `diff`) are still placeholders.
- [ ] Level 4 flow extraction/generation pipeline files are not present yet.
- [ ] Phase 5 as-docs template/MCP integration files are not present yet.

Evidence used for verification:
- `as_docs/cli.py`: `upgrade` currently prints not implemented guidance; `watch`, `install-hook`, and `diff` print not implemented.
- `as_docs/mcp_server.py`: scope validation exists in `regenerate_payload`, but non-`all` scope still returns explicit full-regeneration warning.
- `as_docs/engine.py`: no incremental/scoped generation path yet; generation is full scan/analyze/generate pipeline.
- `agentic-engineering-in-automation-studio/copilot/mcp/as-docs/`: missing.
- `as_docs/analyzer/flow_extractor.py` and `as_docs/generator/flow_diagram_gen.py`: missing.

## Priority plan

### P0 - Finish core product behavior

#### 1) Implement scoped regeneration for CLI and MCP
- Priority: P0
- Estimate: 0.5-1 day
- Status: [x]
- Why:
  - README currently states scoped regenerate/upgrade routes are exposed but execute full regeneration.
- Tasks:
  - [x] Add real scope handling in engine for:
    - changed files
    - single POU
    - all
  - [x] Wire CLI upgrade --pou to true scoped execution.
  - [x] Wire MCP regenerate(scope) to true scoped execution.
  - [x] Return clear result metadata (scope, touched POUs, elapsed time).
- Done criteria:
  - [x] scope=changed only regenerates affected POUs.
  - [x] scope=pou:NAME only regenerates NAME.
  - [x] Existing full regeneration path remains intact.

#### 2) Implement Phase 4 git commands in CLI
- Priority: P0
- Estimate: 1-1.5 days
- Status: [x]
- Tasks:
  - [x] Implement as-docs diff <ref> using gitpython.
  - [x] Implement install-hook (post-commit) with opt-in behavior.
  - [x] Implement watch mode using watchdog and incremental regenerate.
  - [x] Ensure status output aligns with incremental workflow.
- Done criteria:
  - [x] CLI commands no longer print "not yet implemented".
  - [x] Hook file is created/updated safely and idempotently.
  - [x] Diff command outputs changed POUs reliably on sample fixture + repo tests.

### P1 - Complete roadmap integration

#### 3) Phase 5 template deliverables
- Priority: P1
- Estimate: 0.5-1 day
- Status: [x]
- Tasks:
  - [x] Add copilot/mcp/as-docs/mcp.json
  - [x] Add copilot/mcp/as-docs/README.md
  - [x] Add template/.github/skills/as-docs/SKILL.md
  - [x] Add template/.github/instructions/as-project-documentation.instructions.md
  - [x] Add template/.github/collections/as-project-documentation.collection.yml
  - [x] Register as-docs MCP in template/.github/agents/as-project.agent.md
- Done criteria:
  - [x] as-docs appears as a first-class option alongside existing MCPs.
  - [x] Template docs include setup + usage steps.

#### 4) Implement planned init MCP helper option
- Priority: P1
- Estimate: 0.25 day
- Status: [x]
- Tasks:
  - [x] Add init option to generate MCP config snippet/file as planned.
  - [x] Document in README and quickstart.
- Done criteria:
  - [x] Fresh project can configure MCP with one command + minimal edits.

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

## Execution workflow protocol (apply to each milestone)

For each major checklist item, execute this fixed cycle before moving to the next:

1. Implement
- Make only milestone-scoped code changes.
- Keep backward compatibility for existing CLI and MCP behavior unless explicitly changed in this checklist.

2. Verify functionality (manual + automated)
- Run targeted tests first (new/changed area).
- Run full regression after milestone completion:
  - `py -m pytest -q`
- Run CLI smoke checks relevant to the milestone.

3. Add/update tests
- Add unit tests for core logic changes.
- Add integration/CLI tests for exposed behavior changes.
- Prefer fixture-based tests under `tests/fixtures/SampleProject/`.

4. Update documentation
- Update `README.md` command behavior and limitations.
- Update `QUICKSTART-AS-DOCS.md` when setup/usage flow changes.
- Update this checklist status and done criteria checkboxes.

5. Commit (one commit per milestone)
- Commit only files relevant to the milestone.
- Suggested commit style:
  - `feat(as-docs): <milestone outcome>`
  - `test(as-docs): add coverage for <milestone outcome>` (optional second commit if large)
  - `docs(as-docs): update README/quickstart for <milestone outcome>` (optional squash or separate)

Release gate before starting next milestone:
- [ ] Milestone tests pass.
- [ ] CLI/MCP behavior manually validated.
- [ ] Documentation updated.
- [ ] Commit created with clear scope.
