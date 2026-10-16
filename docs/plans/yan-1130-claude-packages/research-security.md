# Security Research: yan-1130-claude-packages

## Executive Summary

The scoped change can safely generate unlisted Claude payloads without changing user configuration or enabling new integrations. Primary controls are preserving secret references literally, rejecting managed-path symlinks before mutation, pruning only owned package roots, and keeping executable-hook proof isolated from production hooks and credentials. Native hook rollout remains gated on installer deduplication; artifact generation is not permission to activate the packages publicly.

## Findings by Severity

### CRITICAL — Hard Stops

No critical findings identified in the reviewed source configuration. No literal credential values were observed in `mcp-configs/mcp.json`; this is a scoped source review, not a repository-wide secret scan.

### WARNING — Must Address

| Finding                                   | Risk                                                                                                    | Suggested Mitigation                                                                                                                                                                                                                 | Alternatives                                                                                                                                             |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Managed output can contain symlinks       | Writes or stale-file deletion could escape owned output into user or source files                       | Reject symlinked managed ancestors, files, and directories before writes or pruning; include dangling links. Follow the preflight/guard pattern in `scripts/generate_codex_plugin.py:191-237`                                        | Fail closed with a path-only diagnostic; do not follow or replace the link                                                                               |
| Overbroad pruning                         | A generator could remove sibling runtime packages, public metadata, or unrelated files                  | Inventory expected files first; prune only the three owned roots `packages/claude/ycc-mcp`, `packages/claude/ycc-hooks`, and `packages/claude/ycc-all`. Do not recursively own `packages`, `packages/claude`, or the repository root | Report drift instead of deleting outside explicit ownership                                                                                              |
| Accidental credential interpolation       | Generation or proof logs could serialize the developer's Xero secrets                                   | Preserve `${XERO_CLIENT_ID}` and `${XERO_CLIENT_SECRET}` as literal source strings; never read the environment to render MCP JSON. Do not copy auth files or print environment values                                                | Exact source-payload comparison can detect accidental transforms without accessing credentials                                                           |
| Settings/plugin hooks execute twice       | Two WorktreeCreate handlers can mutate worktrees; two session handlers can duplicate reporting          | Keep public marketplace, installer, settings, and migration unchanged in YAN-1130. Test package hooks only with fresh isolated settings; preserve the future command-level dedupe gate                                               | Activation belongs in the later migration work, not a whole-event-array deletion here                                                                    |
| Live proof could launch real integrations | Real MCP servers can authenticate remotely; hooks can create worktrees or report session paths to Herdr | Use an ephemeral home/config/cache and scrubbed environment; use inert MCP/hook fixtures for structural install proof. Separate dependency-install evidence from actual service or hook execution                                    | If exercising the real worktree script, use only a disposable Git repository with an explicitly lab-contained worktree root and no `HERDR_*` environment |

### ADVISORY — Best Practices

| Finding                                            | Benefit                                 | Recommendation                                                                                                              | Defer Justification                                                          |
| -------------------------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Source includes mutable `@latest` npm MCP commands | Reproducibility and supply-chain review | Preserve source semantics in this ticket; evaluate pinning centrally in a separate source-policy change                     | Package generation must not silently alter the existing integration contract |
| Local marketplace proof is not remote/cache proof  | Accurate release confidence             | Record CLI version, commands, enabled plugin IDs, actual loaded paths, and isolation controls; state what was not exercised | Remote-source rollout is outside the unlisted artifact scope                 |
| Herdr hook handles session metadata                | Limits disclosure                       | Do not run it against a production socket during proof; avoid logging session IDs/transcript paths                          | Existing script is preserved, not redesigned                                 |

## Authentication and Authorization

`mcp-configs/mcp.json` is the authoritative Claude-shaped payload: GitHub is a local `github-mcp-server stdio` command; Xero uses environment references; the HTTP services use HTTPS endpoints. Generating their declarations does not establish authentication, tool availability, authorization scopes, or service connectivity. The Claude package should retain this source payload rather than the Codex-specific `env_vars` and approval-mode translation in `scripts/generate_codex_mcp.py` and `.codex-plugin/ycc-mcp/.mcp.json`.

The current `ycc/settings/settings.json` contains permission policy, enabled plugins, marketplace configuration, environment controls, and status-line registration. None belongs in `ycc-hooks` or `ycc-all`; avoid implicitly changing permission prompts or authorizing tools. `ycc-all` should remain a manifest-only dependency carrier with exactly `[ycc, ycc-mcp, ycc-hooks]`, not duplicated executable content.

## Data Protection

Copy only the source-controlled MCP configuration and hook scripts required by the package inventory. Never package home-directory credentials, `.env` files, settings snapshots, transcripts, sockets, or local install state. The Herdr script (`ycc/settings/hooks/herdr-agent-state.sh`) captures stdin in a temporary file, removes it with a trap, requires `HERDR_ENV=1`, `HERDR_SOCKET_PATH`, and `HERDR_PANE_ID`, and reports session identity/path to a Unix socket. Those gates make its ordinary no-Herdr execution inert but do not justify inheriting production environment into tests.

## Dependency Security

| Dependency                         | Version                                                                             | Known Issues                                                                                                               | Risk Level | Alternative                                             |
| ---------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------- |
| Claude Code proof runtime          | Existing hook dossier: 2.1.300; coordinator-reported dependency stub proof: 2.1.301 | Plugin WorktreeCreate silently absent on 2.1.143; minimum 2.1.300 remains required                                         | WARNING    | Keep settings-based rollout until migration gates pass  |
| `@xeroapi/xero-mcp-server`         | `@latest` in source                                                                 | Mutable execution target; no CVE assessment performed                                                                      | ADVISORY   | Separate centrally reviewed pinning change              |
| `@playwright/mcp`                  | `@latest` in source                                                                 | Mutable execution target; no CVE assessment performed                                                                      | ADVISORY   | Separate centrally reviewed pinning change              |
| `github-mcp-server`                | Resolved through user PATH                                                          | Package generation does not prove binary provenance or OAuth behavior                                                      | ADVISORY   | Do not invoke it for structural proof                   |
| Hook shell/Python/Git/jq utilities | User runtime                                                                        | Worktree hook deliberately creates branches/worktrees; jq fallback is simpler string extraction, not a general JSON parser | ADVISORY   | Preserve scripts verbatim; no new parser/refactor scope |

No new runtime library dependency is necessary for generation. No vulnerability scanning was performed as part of this research.

## Input Validation

Load and validate the existing package model before writing (`scripts/package_model.py` rejects duplicate JSON keys and validates schema/semantic constraints). Package selection and destination paths should derive from validated model entries, not arbitrary manifest strings joined into paths. Reject absolute paths, traversal, and managed symlinks before mutation; resolve payload metadata before partial writes. For a caller-selected external output destination, reject filesystem-root and checkout-overlap destinations, matching the native Codex precedent; the intentional repository output path needs its own explicit allowed destination rather than bypassing all guards.

Hook commands must anchor quoted script paths to `${CLAUDE_PLUGIN_ROOT}`, never `~/.claude/hooks`, the generator's working directory, or an absolute checkout path. Preserve source script bytes and executable mode. `worktree-create.sh` sanitizes names and validates Git branch syntax but intentionally supports `YCC_WORKTREE_ROOT`; a proof must control that variable rather than assume paths are always inside the fixture repository.

## Infrastructure Security

Safe defaults: all new packages remain `listed: false`; public `.claude-plugin/marketplace.json`, `ycc/settings/settings.json`, and `install.sh` remain unchanged; all generated manifests use canonical source version `5.3.0`; `ycc-hooks` carries only hook registration plus copied scripts; `ycc-mcp` carries only its manifest and MCP declaration; `ycc-all` carries only its dependency manifest.

The existing hooks dossier proves settings and plugin copies both execute even with identical expanded command strings. It documents a 2.1.300 minimum and a separate installer-dedupe gate. Neither gate should be marked satisfied merely by creating unlisted files.

## Isolated Live Install Proof

Coordinator-provided evidence states that a stub `ycc-all` validated on Claude 2.1.301 and installing only it from an isolated marketplace installed all dependencies. This supports the dependency syntax and installation mechanism, not authentication, actual generated payload correctness, cache-root hook execution, or production hook safety. Retain the exact proof commands/results in the implementation evidence before claiming those additional properties.

Reuse controls documented in `docs/internal/spikes/claude-hooks.md:22-38` and `docs/internal/spikes/claude-namespace.md`:

- `mktemp` lab outside the repository with restrictive permissions; isolated `HOME`, `CLAUDE_CONFIG_DIR`, `XDG_*`, npm config/cache, and Git global/system configuration.
- `env -i` allowlist, no copied user settings/plugins/authentication, no inherited `HERDR_*`, no production socket or integration execution.
- Install from a lab-local marketplace through real CLI commands; assert that installing only `ycc-all` results in exactly the intended enabled dependencies and expected manifest versions.
- Record fixture/source immutability and real-user configuration invariance without storing credential contents.
- For hook runtime proof, use bounded inert recording fixtures, assert `${CLAUDE_PLUGIN_ROOT}` resolves to the executed script directory, and keep all returned worktree paths under the lab. Do not confuse fixture behavior with execution of real shipped helpers.
- Environment scrubbing is not an OS network sandbox. A successful structural install is not an offline/egress-security claim.

## Evidence and Open Questions

Evidence paths are repository-relative: `mcp-configs/mcp.json`; `ycc/settings/hooks/herdr-agent-state.sh`; `ycc/settings/hooks/worktree-create.sh`; `ycc/settings/settings.json`; `ycc/settings/packages.json:117-138`; `scripts/package_model.py`; `scripts/generate_codex_plugin.py:191-266`; `scripts/claude_hooks_spike.py:183-275`; `scripts/claude_hooks_checks.py`; `docs/internal/spikes/claude-hooks.md`; `docs/internal/spikes/claude-namespace.md`.

The existing local-directory hook spike explicitly did not establish remote-source or cache-copy execution. That uncertainty is not a blocker to generating unlisted local payloads, but must remain visible for the later public rollout. `docs/internal/adr/0001-package-model-and-versioning.md:97-100` also distinguishes the hook minimum from the unverified minimum runtime for plugin `dependencies`; do not transfer either version floor without direct proof. No implementation, tests, builds, linters, or live integrations were run for this research artifact.
