# Rename Repo: Engineering Practices Research

## Executive Summary

Use a small strict Bash entrypoint and a standard-library Python module, mirroring `scripts/generate-claude-packages.sh` and existing generator/helper modules. Keep the fixed allowlist and transformation logic easy to inspect; do not add a generic rename framework, traversal layer, external dependencies, ambient root hook, or duplicated parser.

Research evidence: `.claude/rules/scripts.md` requires strict Bash, stdout results/stderr errors, executable scripts, and regression coverage. `scripts/test_codex_marketplace.py` demonstrates `unittest`, `tempfile`, and subprocess fixtures. `scripts/test-worktree-roots.sh` demonstrates isolated shell regression suites. Python formatting/lint is configured in `pyproject.toml`; shell lint uses the repository's pinned shellcheck path. No checks were run for this research.

## Existing Reusable Code

Reuse the wrapper/module structure of `scripts/generate-claude-packages.sh`, managed-path guards in `scripts/generate_claude_packages.py`, and same-directory atomic replacement pattern in `scripts/merge_managed_config.py`. Existing `scripts/test_codex_marketplace.py` supplies the standard-library unittest/subprocess fixture style. The inventory dispatch and changed-path scope mapping already provide the integration points; no new runner or runtime dependency is necessary.

## Modularity Design

Tests must exercise the shipped wrapper and engine copied into temporary roots, with every allowlist file populated. This proves physical root derivation without a dangerous production `PROJECT_ROOT` override. The independent test owner must define expected transformations independently, not derive expectations by calling the implementation matcher or silently omit allowlist entries. Keep the shell `scripts/test-rename-repo.sh` as the discoverable test entrypoint; a Python unittest module may carry the detailed matrix.

Implementation and fixture tests/wiring can proceed concurrently once the public CLI, root strategy, allowlist, and no-op behavior are fixed. Their files do not overlap. The parent integrates and runs checks only after both land; workers must not run competing formatters, builds, tests, or smoke commands mid-flight.

## Validator wiring

The suite name does not match the `test-release-*.sh` discovery pattern. Wire it explicitly into the `inventory` target alongside repo-meta regressions in `scripts/validate.sh` (the inspected current anchor is `test-worktree-roots.sh` around lines 205-206). Add the wrapper, engine, and test paths to `scripts/lib/validate-scope.sh` so changed validation selects `inventory`, and mirror the mapping in `scripts/test-validate-scope.sh`. Include documentation-only paths only as existing mapping policy requires; do not widen unrelated validator behavior.

## Documentation and generated artifacts

`CONTRIBUTING.md` gets concise maintainer usage and scope. The seven research artifacts, consolidated spec, and PRP plan capture the enhanced research and decisions. Do not edit `RELEASING.md` or the changelog for this slice. Generated bundles remain untouched: source generator constants are in the future apply allowlist, with later explicit regeneration through `scripts/sync.sh`.

## Parent Verification Evidence

Parent integration reports 20 fixture tests and 50 scope tests passed. Lint and validation for inventory, scope, and practices passed. The real-checkout dry-run shows 24 replacements across all 12 allowlisted files with no protected strings in the diff; the README bare-name rewrite was removed, leaving anchored owner/repo references only. These are parent-reported results, not commands rerun by this documentation worker. Full validation and PR/CI/merge must still be reported from their actual execution, and apply against the real checkout remains forbidden during preparation.

## Resolved research differences

The initial practices suggestion to reuse `detect_project_root()` would honor ambient `PROJECT_ROOT`; that is deliberately rejected by the stricter safety contract. The standalone fixtures replace that test hook. Avoid routine Git cleanliness claims as proof: this PR legitimately adds files, and absence of real reference changes must be established from the actual patch/review evidence rather than invented clean-tree output.
