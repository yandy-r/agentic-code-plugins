# YAN-1130: hidden Claude native packages

Target release: v6.0.0. GitHub: #302. Base and PR target: main. No backport under trunk-only release model.

## Requirements

Generate packages/claude/ycc-mcp, ycc-hooks and ycc-all using the validated package model. Keep the shipping marketplace, listing flags, product version, settings and installer behavior unchanged. Existing ycc remains the canonical skills/agents package; do not duplicate it in the generated tree.

- MCP: preserve the Claude-shaped mcp-configs/mcp.json and literal ${ENV} references; never expand environment values.
- Hooks: derive event registrations from committed ycc/settings/settings.json. Currently only WorktreeCreate is registered. Rewrite only its known installer command to a quoted ${CLAUDE_PLUGIN_ROOT}/hooks/worktree-create.sh path and copy its source script without changing behavior. Do not activate the unregistered herdr script: a successful spike is evidence, not production registration policy. Fail closed on unsupported registered commands rather than silently dropping them.
- Aggregate: derive bare dependencies from requires. No duplicated components; name, version, description/author metadata and dependencies are acceptable. Version is read from model.version_source, not hardcoded.
- Selection: included/native Claude add-ons are generated independently of listed. Deferred/excluded entries are not emitted. Reject unsupported component combinations.
- Ownership: prune/check only modeled generated add-on roots, preserve neighbors and canonical ycc. Reject managed symlinks before writing; precompute payloads before mutation. --check reports missing, changed, extra files and executable drift without mutation; --dry-run does not mutate.

## Integration

Add a claude sync target and a focused claude validation target, generation wrapper and validator consistent with existing patterns. Generator checks and critical boundary tests are always available; real claude plugin validation is optional with explicit missing-CLI warning. Update scoped validator mapping and its behavior regressions. Native validator expansion for every runtime remains YAN-1137, not this change.

## Acceptance evidence

1. CLI validate each actual generated package.
2. Isolated temporary HOME/config marketplace containing canonical ycc and all three generated packages; install only ycc-all and assert all dependencies appear enabled. No inference or MCP/hook activation is needed for installation proof.
3. Generator/check behavior, credential sentinel, ownership/symlink protection and executable drift tests.
4. Exercise copied WorktreeCreate script in a disposable Git repo; observe actual returned worktree path. Never run production hooks against this checkout.
5. Focused lint/type checks and relevant validation targets; use `./scripts/sync.sh --only claude` and `./scripts/validate.sh --only claude` during iteration. Before declaring done, run the required final checks `./scripts/sync.sh` and `./scripts/validate.sh`; scoped iteration does not replace them. Do not run unrelated local suites beyond these required gates.

## Compatibility and remaining gates

Document hook minimum Claude Code 2.1.300. Dependency auto-install stub probe succeeded on 2.1.301; prove actual generated packages separately. Do not claim candidate-baseline compatibility or clean-machine remote fork installs. Existing listing and migration/dedupe gates remain closed. Plugin/settings hooks execute twice; do not recommend production co-installation.

## Research

Seven research perspectives live beside this spec. Coordinator decisions above resolve recommendations; source configuration takes precedence over hypothetical SessionStart activation. Reuse existing package_model and generator/script conventions. No new dependency or generalized generator framework is required.
