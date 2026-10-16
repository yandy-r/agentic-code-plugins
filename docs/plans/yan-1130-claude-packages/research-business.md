# Business Research: YAN-1130 Claude Packages

## Executive Summary

YAN-1130 / [GitHub #302](https://github.com/yandy-r/claude-plugins/issues/302) prepares native Claude MCP, hooks, and aggregate packages without changing today's distribution or installation behavior. The target is **v6.0.0**, but generated versioned artifacts must use the current source version **5.3.0**, not an early v6 bump. This is a hidden-generation delivery, not approval to list packages, migrate users, or replace the installer.

## User Stories

- As a Claude user, I want independent MCP and hooks packages so I can eventually install only the components I need through the native plugin mechanism rather than file-copy installation.
- As a user wanting the complete bundle, I want `ycc-all` to install `ycc`, `ycc-mcp`, and `ycc-hooks` automatically, without copying their payloads into a second bundle.
- As an existing user, I want current `ycc@ycc`, settings, and installer-managed hooks to remain unchanged while native packages are prepared and proven.
- As a maintainer, I want reproducible packages from one model and canonical sources, avoiding independently maintained component lists or divergent versions.

## Business Rules

| Rule                                                                        | Evidence / safe default                                                                                                                                                                                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Generate hidden native Claude packages at `packages/claude/`.               | Issue #302; `ycc/settings/packages.json:65-198`. Select included/native Claude entries; `listed: false` does not mean omit their payload.                                                                                                                                                                                                                                                                                    |
| `ycc-mcp` contains MCP configuration derived from `mcp-configs/mcp.json`.   | Issue #302. Preserve `${ENV}` secret references literally; never resolve local credentials into output.                                                                                                                                                                                                                                                                                                                      |
| `ycc-hooks` contains `hooks/hooks.json` and the scripts required to run it. | Issue #302; canonical source `ycc/settings/hooks`. Document Claude Code **2.1.300 or later** for native hooks.                                                                                                                                                                                                                                                                                                               |
| `ycc-all` is a dependency-only meta package.                                | Issue #302; `packages.json:183-196`. It has no component payload. "Name + dependencies" defines the package's role, not a strict two-key JSON rule. Dependencies are exactly bare names `["ycc", "ycc-mcp", "ycc-hooks"]`, derived from model `requires`; do not qualify names with `@ycc`, add ranges, or duplicate payload. Normal manifest metadata such as version and author may remain for lockstep checks or the CLI. |
| Existing `ycc` remains the skills/agents/shared package.                    | `packages.json:10-24`; ADR 0001 Names and Package matrix. No agents split in v6; `ycc-agents` is v7 scope.                                                                                                                                                                                                                                                                                                                   |
| Product versions are lockstep.                                              | `packages.json:4`, `version_policy`; ADR 0001 Versioning. Current source `ycc/.claude-plugin/plugin.json` is 5.3.0. The coordinator chooses a versioned meta manifest, so every versioned generated manifest uses 5.3.0.                                                                                                                                                                                                     |
| No listing or user configuration changes.                                   | Issue #302; ADR 0001 Gates; `RELEASING.md:76-85`. Keep public `.claude-plugin/marketplace.json`, package listing flags, settings, `install.sh`, migration behavior, and public install-guide wiring unchanged.                                                                                                                                                                                                               |
| Generation is not rollout authorization.                                    | `packages.json` gates; ADR 0001 Dependencies and Consequences. Installer hook dedupe and later listing proof remain mandatory before native rollout.                                                                                                                                                                                                                                                                         |

### Edge Cases

- Existing installer hooks and native plugin hooks both run; do not claim automatic deduplication or advise production co-installation. Later dedupe must preserve user-owned commands (`ADR 0001:148-154`).
- Hook compatibility evidence does not prove every version between 2.1.143 and 2.1.300. Use the documented 2.1.300 minimum rather than inferring an earlier one (`ADR 0001:36-38`).
- A successful latest-client dependency probe does not establish the minimum client for `ycc-all`. Do not transfer the hooks minimum to aggregate dependency support.
- Other runtimes and deferred/excluded packages are not deliverables of this issue. No repository rename, marketplace rename, settings packaging, or npm publication is implied.

## Workflows

### Primary

1. Maintainer reads the validated package model and current version source.
2. Generator materializes hidden Claude component packages from canonical MCP/hooks sources and the dependency-only aggregate from `requires`.
3. Maintainer validates every generated package with `claude plugin validate`.
4. In an isolated test marketplace, install **only** `ycc-all` and observe that all three dependencies are automatically installed.
5. Land the hidden artifacts/tooling without changing production discovery or installer behavior. Target release remains v6.0.0; a later listing PR applies rollout gates.

### Error Recovery

Invalid model, missing required payload/scripts, or unsupported component selection should stop generation with actionable source-path feedback rather than silently emit an incomplete plugin. Failed validation or dependency installation blocks acceptance of the generated package, not a reason to bypass dependencies or list packages early. Test fixtures must stay isolated from real user settings and plugin registrations.

## Domain Model

- **Package**: distinct stable identifier and lockstep version policy.
- **Claude runtime entry**: included/native status, component selection, `requires`, target release, evidence and gates. `listed` is generator policy, not a field to leak into Claude manifests.
- **Canonical component source**: MCP configuration or hook configuration plus its runnable scripts.
- **Generated package**: build output, not a new authoritative configuration source.
- **Release gate**: separates generating/validating hidden artifacts from publicly listing and migrating users.

State transition: modeled → hidden generated → package validated and isolated install proven → eligible for a later gated listing decision. This issue ends before the final listing transition.

## Existing Codebase Integration

- `scripts/package_model.py:23-55` provides immutable package/runtime entities and `lookup`; reuse the model instead of creating a parallel business catalog.
- `scripts/generate_codex_plugin.py:101-125` demonstrates distinguishing included native payload selection from listing status. Claude should preserve that policy distinction, not copy Codex manifest fields.
- `ycc/settings/packages.json:69-82,121-138,183-196` records the hidden Claude entries, hook floor/dedupe gates, and aggregate dependency proof gate.
- `docs/internal/adr/0001-package-model-and-versioning.md:92-120,129-154` records bare dependencies, lockstep rules, public-listing gates, and duplicate-hook risks.
- `RELEASING.md:34-61,66-95` permits hidden incremental delivery on main; only maintainers cut releases. Some release-gate prose is a historical snapshot of generator availability, so use the actual model/source and issue contract rather than treating stale prose as a prohibition on generation.

## Success Criteria

1. Three complete unlisted Claude package roots are produced from the model and canonical sources under `packages/claude/`.
2. MCP references remain secret-free `${ENV}` placeholders; hook payload includes the scripts its commands require.
3. Every generated package passes Claude's validator.
4. Installing only `ycc-all` in an isolated local marketplace automatically installs all three modeled dependencies.
5. Native-hooks minimum 2.1.300 is documented without claiming an untested aggregate minimum or finished migration/dedupe.
6. Public marketplace, settings, listing flags, installer/migration behavior, and current source version remain unchanged.

Evidence status: the coordinator reports a Claude 2.1.301 **stub** aggregate validation/install probe, also recorded in the issue comment. It supports dependency-mechanism feasibility only; it is not evidence that the real generated payloads meet criteria 1–4. No builds, tests, validators, or installation probes were run for this research assignment.

## Open Questions

- The supported minimum client for aggregate dependencies remains unestablished. Safe default: report the actual tested client and leave the existing candidate-baseline/latest-client listing gate intact; do not block hidden generation on a new compatibility-policy decision.
- Public rollout still requires command-level installer dedupe, migration tests, lockstep preflight, clean-machine fork installs, and listing approval. These are existing later gates, not additional scope for YAN-1130.
- No unresolved business choice prevents the scoped hidden generator: package names, sources, dependencies, release target, version source, and no-public-change boundary are already decided.
