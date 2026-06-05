# Phase 2 TODO - AI Enrichment

Scope: implement Phase 2 AI enrichment while preserving the existing architecture.

Current implementation scope in this branch:
- GitHub Copilot / GitHub Models compatible runtime is the active provider path.
- Anthropic is available as fallback provider runtime.

## 1) Config and Provider Abstraction

- [x] Add `ai.provider` to config with allowed values: `anthropic`, `copilot`.
- [x] Keep `ai.model` in config, interpreted per selected provider.
- [x] Set current branch default to copilot-first runtime (`copilot` + `gpt-4.1`).
- [x] Add config validation with clear error messages for unsupported provider/model combos.
- [x] Add provider docs to `.as-docs.yaml.example` and `README.md`.

## 2) AI Enricher Implementation

- [x] Replace placeholder in `as_docs/enricher/ai_enricher.py` with real enrichment pipeline.
- [x] Implement Level 2 enrichment: one task-scoped AI call per task, no source code.
- [x] Implement Level 3 enrichment: one POU-scoped AI call per POU with full source and B&R conventions.
- [x] Parse and validate JSON responses against expected keys.
- [x] Write normalized enrichment data back into `KnowledgeGraph` nodes.

## 3) Provider Clients

- [x] Create provider interface (single request contract for task and POU prompts).
- [x] Implement Anthropic client using existing SDK path.
- [x] Implement Copilot-backed client path for analyzer calls.
- [x] Ensure both providers return the same normalized response schema.
- [x] Add deterministic retry/backoff and timeout handling.

## 4) Caching

- [x] Add level-aware cache entries for Level 2 and Level 3.
- [x] Include provider + model in cache key metadata to avoid cross-provider cache pollution.
- [x] Skip AI calls on cache hit.
- [x] Expose cache hit/miss counts in generation summary.

## 5) CLI and UX

- [x] Ensure `as-docs generate` still defaults to Level 3.
- [x] Preserve `--no-ai` behavior (Level 1 only).
- [x] Print active AI provider/model in CLI output for traceability.
- [x] Keep error output actionable (missing credentials, provider unavailable, invalid response).

## 6) Tests

- [x] Unit tests for config validation (`anthropic` and `copilot` providers).
- [x] Unit tests for response parsing and schema guardrails.
- [x] Unit tests for cache key behavior including provider/model.
- [x] Integration-style tests with mocked provider clients for Level 2 and Level 3.
- [x] Confirm no test performs real external AI calls.

## 7) Done Criteria

- [x] Level 2 and Level 3 enrichment runs end-to-end with either provider.
- [x] Cached rerun performs zero new AI calls when inputs are unchanged.
- [x] `knowledge_graph.json` contains enriched descriptions/patterns as designed.
- [x] README and config example fully document provider selection.

## Remaining Gaps

- None for Phase 2 scope.
