# Recommendations: YAN-1130 Claude Packages

## Executive Summary

Generate three hidden, unlisted Claude packages under `packages/claude/` from the validated package model and canonical sources, without changing any shipping behavior: `ycc-mcp` (verbatim `.mcp.json`), `ycc-hooks` (`hooks/hooks.json` + runnable scripts, floor 2.1.300), and dependency-only `ycc-all` (`["ycc","ycc-mcp","ycc-hooks"]`). Reuse the Codex generator policy shape (`scripts/generate_codex_plugin.py:101-152,179-289`), read lockstep version `5.3.0` from `model.version_source` (`ycc/.claude-plugin/plugin.json`), keep `listed:false` as generator input only, and gate acceptance on `claude plugin validate` per package plus an isolated install-only-`ycc-all` auto-install probe. Listing, migration, installer dedupe, `ycc-agents`, renames, and all other runtimes are explicitly later work.

## Implementation Recommendations

### Recommended Implementation Strategy

Mirror the proven Codex native pattern; do not invent a second convention:

1. **Model-first selection.** Load `ycc/settings/packages.json` via `scripts/package_model.py` (`load_package_model`, `lookup`). Select Claude `status==included` + `mechanism==native` entries independent of `listed` — the same distinction as `native_packages()` (`generate_codex_plugin.py:113-125`). `listed:false` means "generate hidden", never "omit payload".
2. **Reuse the metadata-before-writes shape.** Resolve all manifests first (`native_metadata` pattern, `:179-189`), then write trees, then prune owned roots (`prune_native_output`, `:251-263`). Add the same guards: unsafe package names (`{".",".."}` / path separators), symlink rejection on managed/owned paths (`guard_managed_paths`, `:192-213`), destination preflight (must not overlap the checkout for export verification; checked-in `packages/claude/` roots are the landed output), executable-bit preservation only where Git tracks it.
3. **Lockstep version only.** Resolve every versioned generated manifest through `native_version(model)` (`:146-152`) reading `version_source` (`ycc/.claude-plugin/plugin.json`, today `5.3.0`). Do not bump to v6 early; `bump-version.sh` / `preflight.sh` ownership stays as documented in ADR 0001 Versioning.
4. **Keep the no-public-change boundary.** Do not touch `.claude-plugin/marketplace.json`, `ycc/settings/settings.json`, `install.sh`, install guides, `listed` flags, or the current `5.3.0` source version. New roots stay uncataloged until the v6 listing PR (RELEASING.md gates; ADR 0001 Gates).

### Technology Choices

| Choice              | Recommendation                                                                                                                                                                                                                                            | Evidence                                                                                                                                                                |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc-mcp` payload   | Verbatim `mcpServers` from `mcp-configs/mcp.json` into `<root>/.mcp.json`; preserve `${XERO_CLIENT_ID}` / `${XERO_CLIENT_SECRET}` literally, never resolve                                                                                                | `mcp-configs/mcp.json:18-21`; business rule secret-free placeholders; contrast Codex `translate_env` (`generate_codex_mcp.py`) which reshapes — Claude needs no reshape |
| `ycc-hooks` payload | `hooks/hooks.json` + the settings-registered `ycc/settings/hooks/worktree-create.sh` only; commands via `${CLAUDE_PLUGIN_ROOT}`. Do not copy or activate the unregistered herdr script.                                                                   | `ycc/settings/hooks/worktree-create.sh`; `ycc/settings/settings.json:14-25`; hooks spike Go on 2.1.300                                                                  |
| `ycc-hooks` floor   | Document **Claude Code 2.1.300 or later** in package notes/README; do not infer earlier support                                                                                                                                                           | Spike: `WorktreeCreate` 0 executions on 2.1.143, Go on 2.1.300; ADR 0001:36-38 test-versions-are-data-points                                                            |
| `ycc-all` shape     | Dependency-only meta: distinct manifest name `ycc-all`, bare `dependencies: ["ycc","ycc-mcp","ycc-hooks"]` from model `requires`; no version ranges, no `@ycc` qualifiers, no component payload; keep normal `version`/`author` metadata for lockstep/CLI | `packages.json:183-196`; ADR Dependencies 94-100; 2.1.301 stub probe proves bare-name mechanism only                                                                    |
| Manifest names      | Every package keeps its own distinct `.claude-plugin/plugin.json` `name` (`ycc`, `ycc-mcp`, `ycc-hooks`, `ycc-all`); never reuse `ycc`                                                                                                                    | Namespace spike No-Go: shared manifest name silently splits Skill (first-installed) vs Agent (last-installed) resolution                                                |
| `ycc` package       | Leave as-is (skills/agents/shared); no agents split                                                                                                                                                                                                       | `packages.json:10-24`; `ycc-agents` deferred to v7 (ADR matrix)                                                                                                         |
| Generator language  | Python stdlib-only, mirroring `package_model.py` / `generate_codex_plugin.py`; add `test_generate_claude_*` + `validate-claude-*.sh` mirroring `validate-codex-plugin.sh` / `sync.sh` / `validate.sh packages` wiring                                     | `scripts/sync.sh:85-87`, `scripts/validate.sh:261-265,228-230` patterns                                                                                                 |

> **Coordinator resolution:** This synthesis originally contemplated the full hook
> directory and spike-backed herdr `SessionStart` activation. The feature spec
> supersedes both: spike success is evidence, not production registration policy;
> only settings-registered WorktreeCreate is copied and activated.

### Phasing

1. Generator + unit tests (model selection, MCP verbatim incl. `${ENV}`, hooks file set, `ycc-all` bare deps, lockstep version, fail-closed on missing payload/scripts).
2. `claude plugin validate` per generated root.
3. Isolated local-marketplace probe: install **only** `ycc-all`, observe all three dependencies auto-install (repeat of the 2.1.301 stub shape, now against real payloads).
4. Land hidden `packages/claude/` + tooling; no catalog, settings, or installer diff.

### Quick Wins

- Copy `native_package_roots` / `native_packages` / `native_version` / `guard_managed_paths` / `write_json` structure directly; only the component allow-list changes (`{mcp}`, `{hooks}`, `{}` meta).
- Reuse `package_model.py --check` and `test_package_model.py` as the first gate before any generation.
- Reuse the hooks-spike harness (`test-claude-hooks-spike.sh`) as documentation evidence; do not re-prove hooks in this issue.

## Improvement Ideas

In scope adjacent (do only if free, never as scope creep):

- `--native-output DIR` style export + `--check` parity mode mirroring `generate-codex-plugin.sh --native-output` / `run_check`, so CI can diff hidden output without touching the checkout.
- Lockstep preflight extension covering `packages/claude/` manifests (ADR notes discovery-driven preflight as planned).

Explicitly later (do not start):

- v6 listing flip, `ycc-all` baseline/latest dependency proof matrix, command-level installer hook dedupe (`merge_managed_config.py` `map-entries` cannot do selective removal today), migration tests, clean-machine fork installs, package-install/migration docs wiring, repo rename, `ycc-agents` v7 split, Codex/Cursor/opencode work, npm publication.

## Risk Assessment

| Risk                                                                                     | Severity | Mitigation                                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Duplicate hook execution if native + installer hooks coexist                             | High     | Do not claim dedupe; do not advise co-installation; leave dedupe to the later gated migration (spike: both copies run on 2.1.300, exact-command copies also both run) |
| Silent no-op `WorktreeCreate` on <2.1.300                                                | High     | Hard floor 2.1.300 for `ycc-hooks`; below floor users keep installer hooks (spike plugin-only floor falls back to Git default)                                        |
| Shared manifest name collision                                                           | High     | Distinct manifest names per package (namespace spike split-winner finding)                                                                                            |
| Credential bake-in via `${ENV}` resolution                                               | High     | Byte-preserving copy + test asserting `${XERO_CLIENT_ID}` / `${XERO_CLIENT_SECRET}` survive; fail generation on non-verbatim env                                      |
| Version drift (early v6 bump / per-package tags)                                         | Medium   | Single `native_version(model)` source; one tag policy; no per-plugin tags (ADR Versioning)                                                                            |
| `ycc-all` payload duplication (vendoring skills/MCP/hooks into the meta)                 | Medium   | Meta has empty components; deps only; closure test asserts no payload overlap (cf. `build_package_graph.py` duplicates group)                                         |
| Leaking `listed` into Claude manifests / editing the public catalog                      | Medium   | `listed` is generator input only; public `marketplace.json` unchanged; validator asserts new roots uncataloged                                                        |
| Over-generalizing client support (hooks floor → aggregate floor; stub 2.1.301 → minimum) | Medium   | Report tested client only; keep the candidate-baseline/latest-client dependency gate intact for the listing PR                                                        |
| Herdr-managed script drift (`herdr-agent-state.sh` header: managed by herdr)             | Low      | Resolved by not copying or activating the unregistered herdr script; only settings-registered hook sources are generated                                              |

### Risk Mitigations

Generation fail-closed (actionable source-path error, no partial plugin) on: invalid model, unsupported Claude component set, missing MCP source/servers, missing hooks scripts referenced by `hooks.json`, or unresolvable version source. Validation or isolated-install failure blocks acceptance — never bypass by vendoring payload, qualifying deps, or listing early. Fixtures stay in disposable labs (`env -i`, isolated `HOME`/`CLAUDE_CONFIG_DIR`, no `~/.claude` reads), following both spike harnesses.

## Alternative Approaches

| Option                                                  | Pros                                                                     | Cons                                                                                         | Effort         |
| ------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | -------------- |
| **Recommended: model-driven generator mirroring Codex** | Single source of truth; lockstep-safe; testable; consistent guards/prune | Small upfront generator + tests                                                              | S–M            |
| Hand-maintained `packages/claude/` copies               | No tooling                                                               | Divergent lists/versions; secret-drift risk; violates maintainer-reproducibility rule        | S now, L later |
| Monolithic second bundle instead of `ycc-all` deps      | Fewer manifests                                                          | Duplicates payload; breaks dependency-proof acceptance; multi-handler/duplicate-loading risk | M              |
| Qualified/ranged deps (`ycc-mcp@ycc`, semver ranges)    | Looks precise                                                            | Contradicts ADR bare-name decision; unverified on the dependency path actually probed        | S but wrong    |
| Early v6 version bump in generated manifests            | Signals "v6 content"                                                     | Breaks lockstep parity checks; business research explicitly requires 5.3.0                   | S but wrong    |
| Include `ycc-agents` split now                          | Fewer future moves                                                       | Breaking qualified-reference change scoped to v7; unrequested scope                          | L              |

## Task Breakdown Preview

- **Phase 1 — Generator:** Claude selection (`included`/`native`, components `{mcp}`/`{hooks}`/`{}`), MCP verbatim writer, settings-derived hooks writer with `${CLAUDE_PLUGIN_ROOT}` commands, `ycc-all` bare-deps writer, lockstep versioning, guards/preflight/prune, unit tests. Complexity: M.
- **Phase 2 — Validation wiring:** per-package `claude plugin validate` + `validate.sh`/`sync.sh` entries mirroring the Codex group; no public-catalog diff assertion. Complexity: S.
- **Phase 3 — Isolated proof:** local-marketplace install-only-`ycc-all` probe on a pinned client; record client version actually tested. Complexity: S.
- Dependencies: Phase 2–3 depend on Phase 1; nothing depends on listing/migration/dedupe work.

## Key Decisions Needed

None blocking — names, sources, bare deps, lockstep source, hidden status, and no-public-change boundary are already decided (issue #302, `packages.json`, ADR 0001, business research). Confirm only: (1) generated version stays `5.3.0`; (2) `ycc-all` keeps standard manifest metadata alongside bare deps; (3) hooks floor is stated as 2.1.300 without claiming an aggregate minimum.

Decisions raised by the practices research (`research-practices.md`), with recommended safe defaults:

- **Generator structure:** a standalone stdlib-only Claude generator that mirrors, but does not import from, `generate_codex_plugin.py` (Codex common modules pull in non-stdlib YAML). No shared runtime framework and no generated copy of `ycc`. Add a dedicated claude sync/validate/scope target mirroring the Codex wiring in `sync.sh`/`validate.sh`.
- **Hook activation set:** register only the settings-declared `WorktreeCreate` (`worktree-create.sh`). The previously considered herdr `SessionStart` activation is rejected: do not copy `herdr-agent-state.sh`, do not activate it from the spike, and continue not advising co-installation because native and installer hooks both run.
- **Validation split:** a standalone validator script plus direct unittest coverage (negative cases: missing scripts, non-verbatim `${ENV}`, wrong deps, version drift; drift check against checked-in output) is preferred over structural-only test assertions, matching `validate-codex-plugin.sh` + `test_generate_codex_plugin.py`.

## Open Questions

- Supported minimum client for aggregate `dependencies` is unestablished; the 2.1.301 stub proves mechanism feasibility only. Safe default: report the probe client, leave the baseline/latest proof gate for the listing PR.
- Later rollout gates (command-level installer dedupe preserving user hooks, migration tests, lockstep preflight, clean-machine fork installs, listing approval) remain required but out of scope.
- Cache-copy vs source-directory `${CLAUDE_PLUGIN_ROOT}` execution for remote-source marketplaces is unproven by the hooks spike (local directory marketplace only); hidden generation does not depend on it.

## Sources

- `ycc/settings/packages.json:65-198` (hidden Claude entries, hook/dedupe/dependency gates); `ycc/settings/packages.schema.json`; `scripts/package_model.py:23-55,261-267`
- `docs/internal/adr/0001-package-model-and-versioning.md:23-38,42-107,129-154` (spike verdicts, names, matrix, bare deps, gates)
- `mcp-configs/mcp.json` (verbatim source incl. `${XERO_*}`); `scripts/generate_codex_mcp.py:1-60` (contrast: Codex reshapes, Claude must not)
- `scripts/generate_codex_plugin.py:101-152,179-289` (selection/version/guards/prune pattern to mirror)
- `docs/internal/spikes/claude-hooks.md` (2.1.300 Go, floor No-Go, both-copies-run, merge-engine `map-entries` constraint); `docs/internal/spikes/claude-namespace.md` (shared-name No-Go, distinct-name Go)
- `ycc/settings/hooks/worktree-create.sh`, `ycc/settings/hooks/herdr-agent-state.sh`; `ycc/settings/settings.json:14-25`
- `ycc/.claude-plugin/plugin.json` (5.3.0 source); `.claude-plugin/marketplace.json` (must stay unchanged)
- `RELEASING.md:66-95` (v6 gates policy); `scripts/sync.sh`, `scripts/validate.sh`, `scripts/validate-codex-plugin.sh`
- `docs/plans/yan-1130-claude-packages/research-business.md` (scope, rules 1–8, success criteria, edge cases)
