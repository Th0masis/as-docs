# Milestone 1 Short Spec: Scoped Regeneration

Date: 2026-06-25
Scope: P0 item 1 from EXECUTION_CHECKLIST.md

## Goal
Implement true scoped regeneration paths so that non-all operations process only target POUs while preserving full regeneration behavior.

## Scope Semantics
- all:
  - Full scan, full ST analysis, full edge rebuild, full output generation.
- changed:
  - Resolve stale/missing POUs via current staleness mechanism.
  - Re-analyze only changed POUs.
  - Merge updated POUs and edges into existing graph.
  - If no prior graph exists, fallback to full baseline generation.
- pou:NAME:
  - Validate NAME exists in scanned model.
  - Re-analyze only NAME.
  - Merge NAME updates into existing graph.
  - If no prior graph exists, fallback to full baseline generation.

## Engine Design
- Extend run_generate with scope argument (default all).
- Add scope resolver that maps scope to target POUs.
- Add scoped merge strategy:
  - Replace touched POU nodes.
  - Rebuild edges only for touched sources.
  - Keep unrelated edges untouched.
  - De-duplicate merged edges by (source, target, edge_type).
- Emit execution metadata on graph:
  - scope
  - touched_pous
  - scanned_pous
  - elapsed_seconds
  - fallback_full

## CLI Design
- upgrade --pou NAME:
  - Call run_generate with scope pou:NAME.
  - Print scope result metadata (touched_pous, elapsed_seconds).
  - Keep full-scope upgrade behavior unchanged.

## MCP Design
- regenerate(scope):
  - Call run_generate with requested scope.
  - Return scope metadata and touched_pous.
  - Remove old warning that claimed full regeneration for scoped calls.
- upgrade(to_level, pou):
  - Route pou to scope pou:NAME.
  - Return touched_pous and elapsed_seconds.

## Test Plan (Milestone 1)
- Unit/integration tests:
  - Engine validates pou scope and returns touched metadata.
  - MCP regenerate returns touched_pous for pou/changed/all.
  - CLI upgrade --pou executes and prints scoped metadata.
- Regression:
  - Existing Phase 1 and Phase 3 tests remain green.

## Non-Goals
- Git diff/watch/hook features (Milestone 2).
- Level 4 flow extraction and generation (Milestone 5).
- Full task-level incremental enrichment optimization.
