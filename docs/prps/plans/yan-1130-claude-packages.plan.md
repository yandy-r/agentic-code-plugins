# YAN-1130 implementation plan

Source: docs/plans/yan-1130-claude-packages/feature-spec.md and seven research artifacts. Target v6.0.0, PR to main. No worktree annotations: implementation already isolated.

## Decisions

- Generator mirrors in-repo Codex generator boundaries; no cross-runtime framework.
- Include all included/native Claude add-ons except canonical ycc; reject unsupported components. Deferred ycc-agents emits nothing.
- MCP copy is byte-for-byte; ${ENV} stays literal.
- Only settings-registered WorktreeCreate is emitted. herdr is unregistered and foreign-managed, so neither copied nor activated.
- Aggregate uses lockstep version/author metadata and bare dependencies from model order.
- Check compares executable bits and reports extra owned files without mutation.
- Real CLI validation optional only in local repository validator; acceptance requires executed local CLI.

## Batches

| Batch | Tasks                                                      | Depends on |
| ----- | ---------------------------------------------------------- | ---------- |
| 1     | T1 Generator and generated output; T2 validator and wiring | none       |
| 2     | T3 tests and live harness                                  | 1          |

## Tasks

### T1 Generator — BATCH: 1

Files: scripts/generate_claude_packages.py, scripts/generate-claude-packages.sh, packages/claude/**.
Implement load, selection, metadata-before-write, symlink guard, owned pruning, deterministic write, check/dry-run, error exit 2.

### T2 Integration — BATCH: 1

Files: scripts/validate-claude-packages.sh, scripts/sync.sh, scripts/validate.sh, scripts/lib/validate-scope.sh, scripts/test-validate-scope.sh, AGENTS.md command table if needed.
Add claude sync and focused validation targets. Map Claude generated and generator files narrowly; package model changes also validate claude.

### T3 Verification — BATCH: 2

Files: scripts/test_generate_claude_packages.py, scripts/test-claude-native-packages.sh.
Tests: lockstep version, literal env sentinel, exact hook rewrite and executable copy, fail-closed hook source, unsupported selection, symlink rejection, pruning, check drift classes. Live opt-in harness validates all generated packages and installs only ycc-all from isolated marketplace with canonical ycc.

## Validation

python3 scripts/generate_claude_packages.py --check; python3 scripts/test_generate_claude_packages.py; scripts/validate-claude-packages.sh; scripts/test-claude-native-packages.sh; scripts/test-validate-scope.sh; scoped lint/format; ./scripts/sync.sh and ./scripts/validate.sh as AGENTS requires for generated-source changes.

## Acceptance

Generated packages validate; installing ycc-all installs ycc, ycc-mcp and ycc-hooks; public catalog/settings/installer remain unchanged; WorktreeCreate copied hook works in disposable repo.
