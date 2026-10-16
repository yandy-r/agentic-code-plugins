# Plan: Codex Native Packages

## Summary

Implement YAN-1131 / GitHub #300 for v6.0.0: dormant MCP package plus a complete explicit external native distribution. Preserve legacy default output and defer production activation to YAN-1140.

## User Story

As a maintainer, I want independently installable workflow and MCP packages verified in Codex without changing current installations.

## Problem → Solution

Combined MCP/workflows and installer-only helper paths → model-driven split packages, translated credentials and cache-relative resources in an isolated export.

## Metadata

- **Complexity**: Large
- **Source PRD**: docs/plans/codex-native-packages/feature-spec.md
- **PRD Phase**: standalone
- **Estimated Files**: 10 source/test files plus two generated files and research evidence

## Batches

| Batch | Tasks    | Depends On | Parallel Width |
| ----- | -------- | ---------- | -------------- |
| B1    | 1.1, 1.2 | —          | 2              |
| B2    | 2.1, 2.2 | B1         | 2              |
| B3    | 3.1      | B2         | 1              |

- **Total tasks**: 5
- **Total batches**: 3
- **Max parallel width**: 2

## UX Design

### Before

Current legacy ycc includes skills and MCP; local-ycc-plugins catalog is discovered.

### After

Defaults remain identical. Maintainer explicitly exports a future repo-shaped tree with `--native-output DIR`; ycc@ycc and ycc-mcp@ycc install independently.

### Interaction Changes

| Touchpoint               | Before                      | After                              | Notes                              |
| ------------------------ | --------------------------- | ---------------------------------- | ---------------------------------- |
| Metadata generator       | legacy/check/dry-run        | additional external native-output  | Check read-only; dry-run no writes |
| Native helper references | installer home symlink      | containing document-relative paths | Preserve user repository cwd       |
| Native Xero credentials  | literal Claude placeholders | Codex env_vars pass-through        | Legacy bytes unchanged             |

## Mandatory Reading

| Priority | File                                               | Lines          | Why                                       |
| -------- | -------------------------------------------------- | -------------- | ----------------------------------------- |
| P0       | `docs/plans/codex-native-packages/feature-spec.md` | all            | Settled design overrides earlier research |
| P0       | `scripts/generate_codex_plugin.py`                 | 1-176          | Existing metadata generation              |
| P0       | `scripts/generate_codex_skills.py`                 | 56-249         | Resource transform and ownership          |
| P0       | `scripts/package_model.py`                         | 23-55,261-267  | Typed validated model                     |
| P1       | `scripts/generate_codex_mcp.py`                    | 41-98          | Translator/overrides                      |
| P1       | `scripts/test-codex-marketplace-spike.sh`          | 38-124,161-225 | Isolated runtime pattern                  |

## External Documentation

| Topic         | Source                                                                                         | Key Takeaway                                         |
| ------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| Native skills | <https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/ext/skills/src/catalog_prompt.rs> | Resources resolve from installed document            |
| MCP parser    | <https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/codex-mcp/src/plugin_config.rs>   | mcpServers accepts env_vars; no Claude interpolation |
| Discovery     | <https://github.com/openai/codex/blob/rust-v0.161.0/codex-rs/core-plugins/src/marketplace.rs>  | Existing preferred catalog is user-visible           |

## Patterns to Mirror

### NAMING_CONVENTION

`scripts/generate_codex_plugin.py:29-33`: snake_case builders returning JSON dictionaries. Existing legacy builders stay unchanged.

### ERROR_HANDLING

`scripts/package_model.py:261-267`: validated model loader raises PackageModelError. CLI catches validation/IO errors with concise stderr and nonzero exit, no fallback.

### REPOSITORY_PATTERN

`scripts/generate_codex_mcp.py:90-93`: build_codex_mcp_config reads authored source and overrides; native wrapper is mcpServers, not mcp_servers.

### SERVICE_PATTERN

`scripts/generate_codex_skills.py:143-217`: write_tree returns owned relative inventory; preserves executable mode and policy sidecars; prunes only skills/shared.

### TEST_STRUCTURE

`scripts/test_codex_marketplace.py:21-41`: unittest TemporaryDirectory with cleanup and subprocess CLI assertions. Critical behavior only, no source-text/wording tests.

## Files to Change

| File                                                     | Action | Justification                                      |
| -------------------------------------------------------- | ------ | -------------------------------------------------- |
| `scripts/generate_codex_skills.py`                       | UPDATE | Native path policy; legacy unchanged               |
| `scripts/generate_codex_plugin.py`                       | UPDATE | Model-driven split export, safety, lifecycle/check |
| `scripts/test_generate_codex_skills.py`                  | CREATE | Critical document-relative path behavior           |
| `scripts/test_generate_codex_plugin.py`                  | CREATE | Output boundary/lifecycle/selection                |
| `scripts/validate-codex-plugin.sh`                       | UPDATE | Validate dormant and explicit native output        |
| `scripts/validate.sh`                                    | UPDATE | Register scoped unit tests                         |
| `scripts/test-codex-native-packages.sh`                  | CREATE | Actual Git fixture install/cache helper proof      |
| `.codex-plugin/ycc-mcp/.codex-plugin/plugin.json`        | CREATE | Generated dormant metadata                         |
| `.codex-plugin/ycc-mcp/.mcp.json`                        | CREATE | Generated translated MCP                           |
| `docs/internal/adr/0001-package-model-and-versioning.md` | UPDATE | Post-verification implementation evidence          |

## NOT Building

- No production catalog rename, listed flags, automatic flip routing, installer migration/dedupe, hooks, new dependencies or duplicate checked-in skills tree.
- No RELEASING.md edits (user requires release-model for those); existing gates already cover explicit unwired output.
- No changes to user-level marketplace helper; preserve local-ycc-plugins.
- No full test suite or source skill edits; only affected generator verification.

## Step-by-Step Tasks

### Task 1.1: Native resource path policy — Depends on [none]

- **BATCH**: B1
- **ACTION**: Extend existing skills generator and add critical native-resource tests.
- **IMPLEMENT**: Add keyword-only `native_paths: bool = False` to write_tree; export calls it true. Native markdown resources become document-relative after existing transforms, including authored plugin-root paths, transformed ~/.codex/plugins/ycc paths and bundled ~/.codex/skills paths. Add concise SKILL instruction to resolve from expanded document and execute absolute helpers while keeping project cwd. Executable script references must use script-directory-relative shell paths, never cwd-relative fallbacks; preserve source/verbatim exceptions and legacy bytes.
- **MIRROR**: write_tree, copy_mode, prune_orphans, transform_skill_markdown.
- **GOTCHA**: shared output is shared/, not skills/_shared/. Avoid changing fallback/general user-home instructions that are not bundled-resource references. No invented runtime environment variable.
- **VALIDATE**: Focused deterministic path tests for top-level skill, nested reference, shared reference, executable fallback; cache-based smoke in Task 2.2.

### Task 1.2: Model-driven export and lifecycle — Depends on [none]

- **BATCH**: B1
- **ACTION**: Extend existing metadata generator; add critical generator unit tests.
- **IMPLEMENT**: Public `generate_native_tree(dest_root: Path, dry_run: bool = False) -> set[Path]` emits repo-relative inventory and calls skills.write_tree with native_paths=True. Use validated package model status/mechanism/components and version_source; native catalog builder filters listed by default, explicit export includes eligible unlisted candidates. Native ycc lacks MCP file/declaration; MCP-only wraps translated server map. Default write_all preserves current legacy output and adds only dormant MCP files. CLI --native-output works with mutually-exclusive check/dry-run; check renders temporary tree and compares without writes. Guard filesystem-root/checkout overlap and all managed symlinks before mutation; prune only owned package roots and catalog file, preserve neighbors.
- **MIRROR**: write_json, write_all, compare_files, package_model.load_package_model.
- **GOTCHA**: No default production flip, no hooks, no generated-source copies. Pass-through variables stay names, never generation environment values. Separate default profile versus full native profile.
- **VALIDATE**: Critical tests: split ownership/credential semantics; model excludes hooks; repeated generation removes stale native MCP/orphan and preserves neighbors; missing/drift/stale check read-only; dry-run no writes; overlap/managed symlink rejection.

### Task 2.1: Scoped validator integration — Depends on [1.1, 1.2]

- **BATCH**: B2
- **ACTION**: Extend validator and register unit tests.
- **IMPLEMENT**: Default validator checks dormant MCP JSON plus legacy drift. `--native-output DIR` validates via generator check and structural component invariants/catalog target paths/version parity; tests deliberately corrupt exported fixture and observe failure. Register both unit test files in codex group, do not require Codex binary in regular CI. Existing release discovery already includes new manifest; prove with existing scoped release command, no new release framework/tests needed.
- **MIRROR**: scripts/validate-codex-plugin.sh and validate.sh codex case.
- **VALIDATE**: Both default and exported validators pass; corrupted fixture fails. Existing marketplace helper tests pass.

### Task 2.2: Git fork-install smoke harness — Depends on [1.1, 1.2]

- **BATCH**: B2
- **ACTION**: Add opt-in real Codex runtime harness.
- **IMPLEMENT**: Generate full export from source, create isolated local Git fork/bare fixture pinned to commit, register HTTPS-shaped URL rewritten to file-only transport. Isolate HOME/CODEX_HOME/XDG/Git config, use clean cwd, install ycc@ycc and ycc-mcp@ycc, verify complete cache inventory and no hooks/MCP in skills package. Run a real harmless bundled helper resolved from installed SKILL resource path with user project cwd unchanged. Inspect MCP loading via CLI metadata without starting credentialed servers; use no inference. Cover full and sparse catalog+both payloads.
- **MIRROR**: scripts/test-codex-marketplace-spike.sh env-i, run/assert_rc and fixture commit patterns.
- **GOTCHA**: No public GitHub/0.160 execution claim unless actually run. File-only Git is not OS egress isolation. Keep transcript/sandbox opt-in --keep and remove otherwise.
- **VALIDATE**: Run harness on installed Codex 0.161.0; both installs/cache helper succeed with no legacy symlink.

### Task 3.1: Verify, document and review — Depends on [2.1, 2.2]

- **BATCH**: B3
- **ACTION**: Integration owner runs scoped checks, smoke, updates existing ADR and fixes adversarial findings.
- **IMPLEMENT**: Regenerate codex, run scoped static/unit/validator/release checks and live harness; preserve default legacy bytes. Record observed evidence and decisions in ADR/internal report, not public install guides. Run adversarial parallel review before PR then PR review/autofix workflow; ship only green CI.
- **MIRROR**: AGENTS.md, .github PR template and labels.
- **VALIDATE**: Acceptance criteria below plus merged green PR and owned cleanup.

## Testing Strategy

### Unit Tests

| Boundary         | Input                                            | Expected Output                                    |
| ---------------- | ------------------------------------------------ | -------------------------------------------------- |
| Native resources | skill/shared/nested documents + script fallbacks | installed-root-relative resources, independent cwd |
| Output ownership | stale MCP/orphan + unrelated neighbor            | only owned stale paths removed                     |
| Safety           | overlapping destination / managed symlink        | rejection before mutation                          |
| Read-only modes  | drift/missing/stale files                        | check failure, unchanged target; dry-run no create |
| Package policy   | current model + excluded native entries          | only supported included payloads, no hooks         |

## Validation Commands

### Static Analysis

`ruff check <changed Python files>`; `black --check <changed Python files>`; `shellcheck <changed shell files>`; `python3 -m compileall -q <changed Python files>`.

### Unit Tests

`python3 scripts/test_generate_codex_plugin.py`; `python3 scripts/test_generate_codex_skills.py`; `python3 scripts/test_generate_codex_mcp.py`; `python3 scripts/test_codex_marketplace.py`.

### Scoped Build and Validation

`./scripts/sync.sh --only codex`; `./scripts/validate.sh --only codex,packages,release`; explicit native export then native validator. No full suite for this non-app change.

### Manual Validation

`./scripts/test-codex-native-packages.sh --keep` exercises actual runtime install/cache/helper paths.

## Acceptance Criteria

- Both package IDs install from the generated Git fork fixture on Codex >=0.160 (actual installed version recorded).
- Default and native Codex validators pass; broken native fixture fails.
- Legacy default manifest/MCP/catalog and skills remain byte-identical.
- Complete native tree derives from authored source, no hooks, no MCP in ycc, no skills in ycc-mcp.
- Native credentials use pass-through names; helper executes from installed cache without installer symlink.
- Output guards/check/dry-run/prune obey boundaries.
- PR and issues shipped/closed only on green CI.

## Completion Checklist

- Model and canonical version reused; no new runtime/listing fields.
- Only critical deterministic permanent tests; smoke not substituted by tests.
- Existing ADR updated after proof; public guides and release gates unchanged.
- Research/spec/plan/report retained under internal docs with docs(internal) commit.
- Code review findings resolved before merge.

## Risks

| Risk                                           | Likelihood | Impact | Mitigation                                                  |
| ---------------------------------------------- | ---------- | ------ | ----------------------------------------------------------- |
| Native path rewriting corrupts source examples | Medium     | Medium | Context-aware document/script handling, verbatim exceptions |
| Export lifecycle touches neighbors             | Low        | High   | Owned paths and preflight symlink guard                     |
| Catalog activated early                        | Low        | High   | Default legacy builders unchanged                           |

## Notes

Seven feature researchers and seven enhanced-plan researchers completed. Some early research suggested automatic flip or forbidding native check; settled feature spec and this plan override those suggestions. Enhanced preflight helper expects unavailable ~/.agents/agents; equivalent actual task agents completed successfully. Spec structural validator passes headings/content but exits at a broken Markdown-link regex; do not modify unrelated tooling.
