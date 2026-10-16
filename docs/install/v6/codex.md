# Codex Install Guide (v6 native packages)

> **DRAFT — unwired for v6: hidden native packages are not installable from
> production catalogs today.** Everything under `docs/install/v6/` is planned
> behavior, not current install instructions. For the guide that works now,
> use [Codex Install](../codex.md).

## Current Install (unchanged today)

The shipping Codex flow stays exactly as documented in the live guide:

```bash
./install.sh install --target codex
```

The `base` step registers `local-ycc-plugins` in
`~/.agents/plugins/marketplace.json` with the local source
`./.agents/plugins/ycc`, then runs
`codex plugin add ycc@local-ycc-plugins` (Codex 0.160+), which snapshots the
plugin under `~/.codex/plugins/cache/local-ycc-plugins/ycc/<version>/`. Custom
agents (`~/.codex/agents/`), `AGENTS.md`, and `config.toml` settings remain
`install.sh`-only: Codex plugins cannot carry them. The v6 work below changes
catalog identity only; it does not ship any of that until the flip.

The install selector stays `ycc@local-ycc-plugins` until the catalog rename —
`ycc@ycc` on Codex refers to the planned post-flip catalog and is not
installable today.

## v6 Native Package Model

`ycc/settings/packages.json` is the package truth (loaded through
`scripts/package_model.py`); the decision record is
[ADR 0001](../../internal/adr/0001-package-model-and-versioning.md). Codex v6
packages, after the flip:

| ID            | Payload                                  | v6.0.0 status                                                                                                                                                 |
| ------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ycc@ycc`     | Skills + `shared/` (skills-only; no MCP) | Current catalog `local-ycc-plugins`; planned Git marketplace listing is repo-root `.agents/plugins/marketplace.json` with local source `./.codex-plugin/ycc`. |
| `ycc-mcp@ycc` | MCP-only (`mcpServers: ./.mcp.json`)     | Hidden; native MCP uses Codex `env_vars`; installed on the pinned baselines below.                                                                            |
| `ycc-hooks`   | Hooks (excluded)                         | **Excluded.** No-Go until hook trust and dispatch are verified (YAN-1149 gate); not an installable ID.                                                        |
| `ycc-agents`  | — (not a Codex package)                  | Claude-only and deferred to v7 anyway; not an installable ID.                                                                                                 |

The legacy ID `ycc@local-ycc-plugins` is the current-catalog install selector
owned by `install.sh` — not a separate package and not an error. At the flip,
the repository catalog's marketplace name becomes `ycc`, which makes the
native Git marketplace ID `ycc@ycc`. Migration from the legacy user-level
entry is planned (below), not implemented.

Each package keeps a distinct manifest `name`; hidden payloads live under
`.codex-plugin/ycc` and `.codex-plugin/ycc-mcp`.

## Planned Post-Listing Config (not runnable today)

The snippet below shows the shape of `~/.codex/config.toml` **after** the v6
listing flip. It is an example only — these keys are not written by any
current installer command, and the packages are not installable from
production catalogs today:

```toml
[plugins."ycc@ycc"]
enabled = true

[plugins."ycc-mcp@ycc"]
enabled = true
```

Today the same mechanism holds the legacy entry written by `install.sh`:

```toml
[plugins."ycc@local-ycc-plugins"]
enabled = true
```

After the flip, the **repository-root** `.agents/plugins/marketplace.json`
will describe the native Git marketplace named `ycc`. Its `local` sources
resolve from the repository root, where the `.codex-plugin/` payload lives;
the shape verified by the spike is:

```json
{
  "name": "ycc",
  "plugins": [{ "name": "ycc", "source": { "source": "local", "path": "./.codex-plugin/ycc" } }]
}
```

A Git marketplace catalog at `.agents/plugins/marketplace.json` wins over
`.claude-plugin/marketplace.json`, which is why the repo-level Codex catalog
must live under `.agents/plugins/`.

This is **not** a replacement snippet for
`~/.agents/plugins/marketplace.json`: there, the marketplace root is `$HOME`,
so `./.codex-plugin/ycc` would resolve to `~/.codex-plugin/ycc`, not this
repository. Today's user-level `local-ycc-plugins` catalog and symlink flow
remain unchanged: local mode uses `./.agents/plugins/ycc`, pointing through
`~/.agents/plugins/ycc` to the checkout's `.codex-plugin/ycc`; repo mode uses
a `git-subdir` source for `./.codex-plugin/ycc` at `main`.

## Tested Baselines And Version Boundaries

- **codex-cli 0.160.0 (exact, public profile):** anonymous public GitHub HTTPS
  registration and independent installs of `ycc@ycc` and `ycc-mcp@ycc`
  verified, from both full and sparse checkouts, in both install orders.
  Payload version was 5.3.0 bytes, not the final v6.0.0 payload.
- **codex-cli 0.161.0:** the same package split installed from a local
  file-transport fixture; sparse-checkout and hook-discovery matrix verified.
- No version other than exact 0.160.0 was run in the public profile, and no
  claim is made about later runtimes. Authenticated/private, SSH, and
  `owner/repo` shorthand transports are untested. MCP evidence is metadata
  only (`mcp list`); no server execution, login, session, or hook dispatch
  was exercised.

## Native Vs Fallback

- **Native (plugin) layer:** skills + `shared/` in `ycc@ycc`; MCP server
  connections in `ycc-mcp@ycc` (with `env_vars`, e.g. Xero's
  `XERO_CLIENT_ID`/`XERO_CLIENT_SECRET`, never secret literals).
- **Fallback (`install.sh`) layer:** custom agent TOMLs, `AGENTS.md`, and
  `config.toml` settings stay on `install.sh` — Codex plugins cannot carry
  them. `installer-fallback` in `packages.json` is an internal modeling key,
  never an installable ID.

Sparse installs from a Git marketplace must include both
`.agents/plugins` (catalog) and `.codex-plugin/ycc` (payload) in
`--sparse` selections — catalog-only sparse checkouts fail `plugin add`
with `missing plugin.json`. Add `.codex-plugin/ycc-mcp` to install the MCP
package from a sparse checkout.

`install.sh migrate` and `install.sh --package` are **planned and not
implemented**. They are never runnable commands; do not document or run them
as if they exist.

## Hooks Excluded

The `ycc-hooks` package is **excluded** from Codex. On codex-cli 0.161.0,
`WorktreeCreate` is absent from Codex's `HookEventName` schema, and plugin
`SessionStart` hooks were observed only as `trustStatus: "untrusted"` with
the `plugin_hooks` feature flag removed and no trust grant or runtime
dispatch exercised. Hooks stay out of the Codex bundle until verified
(YAN-1149 gate).

## Duplicates And Planned Migration

- **Duplicates.** A native plugin and an install.sh file copy can both be
  installed. On the legacy→native flip, a stale `ycc@local-ycc-plugins`
  enablement left beside `ycc@ycc` would double-list every ycc skill; Codex
  also reads `~/.agents/skills`, so installing the `agents` target alongside
  the plugin duplicates skills again (the installer warns and offers
  `--skills-home agents`).
- **Current agent-file hazard (implemented behavior).** `install.sh install`'s
  agents slice is ownership-tracked: it replaces an existing
  `~/.codex/agents/<name>.toml` only if the name is recorded in
  `~/.config/ycc/installed-units.json` or the file is byte-identical, unless
  `--force` is passed. The full `install.sh remove --target codex` (the
  `base` step) is **not** that safe: after the tracked removal it runs
  `remove_mirrored_entries`, which `rm -rf`s every `~/.codex/agents/<name>`
  whose name matches an agent ycc ships, **by name only** — including a
  same-named file you wrote yourself and anything unrecorded. Back up or
  rename any custom agent that shares a ycc agent name before running that
  command. `remove --only agents` uses the tracked slice and keeps
  unrecorded files without `--force`.
- **Planned migration (not implemented).** The future migration must swap the
  catalog entry and enablement to `ycc@ycc`, remove only installer-owned
  legacy entries (`local-ycc-plugins`, `./plugins/ycc`), and preserve user
  content, including user-owned files in `~/.codex/agents/` — that
  preservation is a **requirement for the migration, not a property of the
  current remove path above**. User-owned hooks and settings keys must merge
  and never be overwritten. Existing-user migration/dedupe is tracked as a
  closed gate (YAN-1139); no migration command exists today.

## Evidence Index

- [ADR 0001: package model and versioning](../../internal/adr/0001-package-model-and-versioning.md)
- [Codex marketplace spike (YAN-1123)](../../internal/spikes/codex-marketplace.md)
- [Codex public fork install spike (YAN-1163)](../../internal/spikes/codex-public-fork-install.md)
- Package truth: `ycc/settings/packages.json` (`scripts/package_model.py`)
- Live guide: [Codex Install](../codex.md); draft index: [v6 README](README.md)
