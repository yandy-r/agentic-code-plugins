# Codex Install Guide (v6 native packages)

Codex installs `ycc` as two native plugins from the `ycc` marketplace in this
repository (`yandy-r/ystack`). Custom agents, `AGENTS.md`, and `config.toml`
settings stay on `install.sh` because Codex plugins cannot carry them; see
[Codex Install](../codex.md) for those steps.

## Install

Codex 0.160 or later:

```bash
codex plugin marketplace add https://github.com/yandy-r/ystack.git
codex plugin add ycc@ycc
codex plugin add ycc-mcp@ycc
```

Add `--ref <sha>` to `marketplace add` to pin a commit. Restart Codex after
installing. The `ycc` catalog replaces the legacy `local-ycc-plugins` catalog;
if you previously installed through `install.sh`, move over with the
[migration](#migration-cli) below.

From a checkout, `./install.sh install --target codex` does the same thing
(`codex plugin marketplace add <checkout>`, then `codex plugin add ycc@ycc`
and `codex plugin add ycc-mcp@ycc`) and also syncs the custom agents into
`~/.codex/agents/`. `--mode repo` registers the Git marketplace
`https://github.com/yandy-r/ystack.git` at `main` instead of the checkout.
Rerun the base step to refresh the snapshots after regenerating the bundle.
Without the Codex plugin CLI the installer copies the same snapshots into
`~/.codex/plugins/cache/ycc/` and writes `[marketplaces.ycc]` itself.

## v6 Native Package Model

`ycc/settings/packages.json` is the package truth (loaded through
`scripts/package_model.py`); the decision record is
[ADR 0001](../../internal/adr/0001-package-model-and-versioning.md). Codex
packages:

| ID            | Payload                                  | Status                                                                                                 |
| ------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `ycc@ycc`     | Skills + `shared/` (skills-only; no MCP) | Listed in the repo-root `.agents/plugins/marketplace.json` (local source `./.codex-plugin/ycc`).       |
| `ycc-mcp@ycc` | MCP-only (`mcpServers: ./.mcp.json`)     | Listed; native MCP uses Codex `env_vars`; installed on the pinned baselines below.                     |
| `ycc-hooks`   | Hooks (excluded)                         | **Excluded.** No-Go until hook trust and dispatch are verified (YAN-1149 gate); not an installable ID. |
| `ycc-agents`  | — (not a Codex package)                  | Claude-only and deferred to v7 anyway; not an installable ID.                                          |

The legacy ID `ycc@local-ycc-plugins` is what pre-v6 `install.sh` wrote
(marketplace `local-ycc-plugins`, source `./.agents/plugins/ycc`). It is not a
separate package and not an error; `install.sh install` leaves it in place and
`install.sh migrate --target codex` retires it once `ycc@ycc` and
`ycc-mcp@ycc` are installed and enabled.

Each package keeps a distinct manifest `name`; payloads live under
`.codex-plugin/ycc` and `.codex-plugin/ycc-mcp`.

## Config Shape

After installation `~/.codex/config.toml` enables both packages (a checkout
install via `install.sh` also records `[marketplaces.ycc]` with
`source_type = "local"` and the checkout path):

```toml
[plugins."ycc@ycc"]
enabled = true

[plugins."ycc-mcp@ycc"]
enabled = true
```

A pre-v6 `install.sh` install holds the legacy entry instead:

```toml
[plugins."ycc@local-ycc-plugins"]
enabled = true
```

The **repository-root** `.agents/plugins/marketplace.json` describes the native
Git marketplace named `ycc`. Its `local` sources resolve from the repository
root, where the `.codex-plugin/` payload lives:

```json
{
  "name": "ycc",
  "plugins": [
    { "name": "ycc", "source": { "source": "local", "path": "./.codex-plugin/ycc" } },
    { "name": "ycc-mcp", "source": { "source": "local", "path": "./.codex-plugin/ycc-mcp" } }
  ]
}
```

A Git marketplace catalog at `.agents/plugins/marketplace.json` wins over
`.claude-plugin/marketplace.json`, which is why the repo-level Codex catalog
lives under `.agents/plugins/`.

This is **not** a replacement snippet for the user-level
`~/.agents/plugins/marketplace.json` that pre-v6 installs used: there the
marketplace root is `$HOME`, so `./.codex-plugin/ycc` would resolve to
`~/.codex-plugin/ycc`, not this repository.

## Tested Baselines And Version Boundaries

- **codex-cli 0.160.0 and 0.163.0 (public profile, production repo):**
  anonymous public GitHub HTTPS registration of `yandy-r/ystack` at a pinned
  `main` SHA and independent installs of `ycc@ycc` and `ycc-mcp@ycc`, from
  both full and sparse checkouts, in both install orders (v6.0.0 payload).
- **codex-cli 0.160.0 (exact, public spike fixture):** the same matrix
  against a 5.3.0-payload fixture repository.
- **codex-cli 0.161.0:** the same package split installed from a local
  file-transport fixture; sparse-checkout and hook-discovery matrix verified.
- No claim is made about runtimes not listed above. Authenticated/private,
  SSH, and `owner/repo` shorthand transports are untested. MCP evidence is
  metadata only (`mcp list`); no server execution, login, session, or hook
  dispatch was exercised.

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

## Migration CLI

```bash
./install.sh migrate --target codex            # dry-run
./install.sh migrate --target codex --apply
```

Dry-run writes no config, state, build output, or CLI state. With the default
source (this checkout's `ycc` catalog) it prints that it would add the
marketplace, install `ycc@ycc` and `ycc-mcp@ycc` and verify them installed and
enabled, and then retire only proven legacy config, links, and cache with
`~/.codex/agents` retained. The migration is gated on the catalog: if the
selected source is not an eligible native `ycc` catalog (name `ycc`, both
packages listed, payloads present and unmodified), dry-run prints
`[!!] Codex native gate: <reason>` and keeps the legacy
`ycc@local-ycc-plugins` install, and `--apply` exits nonzero **before any
cleanup or CLI call**, leaving the legacy files intact. It never repurposes
`local-ycc-plugins` and never falls back to the legacy installer when a native
CLI operation fails.

`--marketplace-source <dir>` selects a different local catalog root (for
example a staged export), not a bypass. For example, create a disposable native export
with `scripts/generate_codex_plugin.py --native-output <dir>`, then preview
and apply it explicitly:

```bash
./install.sh migrate --target codex --marketplace-source /path/to/native-export
./install.sh migrate --target codex --marketplace-source /path/to/native-export --apply
```

The directory must have an eligible `.agents/plugins/marketplace.json`
named `ycc`, local sources for `ycc` and `ycc-mcp` at
`./.codex-plugin/<package>`, and matching package manifests/payloads. The
package model must also mark them included, native, and not opt-in. The same
checks apply to the default source. `--marketplace-source` requires Codex
among the selected targets.

Apply registers that marketplace, requires both packages in the available
listing, installs each, then verifies both installed and enabled. Only after
all of that succeeds does it retire recognized installer-owned legacy
enablement, links, and catalog entries. Standalone `~/.codex/skills/` entries
are retired when they exactly match the installer output. Shared helpers stay
while any skills remain. A legacy cache snapshot under
`~/.codex/plugins/cache/local-ycc-plugins/ycc` is retired when it is
byte-identical to `.codex-plugin/ycc` or to the legacy combined bundle
rendered from the current source, or when its git tree equals a committed
`.codex-plugin/ycc` tree in this checkout's history. An edited snapshot stays.
A shallow clone that does not contain that commit keeps the snapshot and
prints `git fetch --unshallow`. If git history cannot be read, the snapshot
stays.
A failure before verification keeps the legacy install intact and returns an
error. All `~/.codex/agents/` content is preserved, along with user edits,
unrelated settings, and foreign entries. Uncertain ownership is reported and
retained. Symlinked configuration files are retained with a notice rather
than replaced. Repeated apply is safe, and `--force` is rejected.

Installed/enabled metadata is not runtime session or MCP execution proof.
`install.sh install --package <ids> --target codex` is a checkout-based
delivery route (`ycc`, `ycc-mcp`; `ycc-hooks` is rejected on Codex): its
`base` step installs the same `ycc@ycc` and `ycc-mcp@ycc` pair as above, and
custom agents are always copied.

## Hooks Excluded

The `ycc-hooks` package is **excluded** from Codex. On codex-cli 0.161.0,
`WorktreeCreate` is absent from Codex's `HookEventName` schema, and plugin
`SessionStart` hooks were observed only as `trustStatus: "untrusted"` with
the `plugin_hooks` feature flag removed and no trust grant or runtime
dispatch exercised. Hooks stay out of the Codex bundle until verified
(YAN-1149 gate).

## Duplicates And Migration

- **Duplicates.** A native plugin and an install.sh file copy can both be
  installed. A stale `ycc@local-ycc-plugins` enablement left beside `ycc@ycc`
  would double-list every ycc skill (run `migrate` to retire it); Codex
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
- **Migration (implemented).** Use `migrate`, not the remove path above, to
  retire legacy entries only after the eligible native catalog is registered
  and both `ycc@ycc` and `ycc-mcp@ycc` are installed and enabled. It preserves
  all of `~/.codex/agents/` and user-owned hooks/settings; it never calls the
  name-based `remove_mirrored_entries` helper, and it does not establish
  runtime execution evidence.

## Evidence Index

- [ADR 0001: package model and versioning](../../internal/adr/0001-package-model-and-versioning.md)
- [Codex marketplace spike (YAN-1123)](../../internal/spikes/codex-marketplace.md)
- [Codex public fork install spike (YAN-1163)](../../internal/spikes/codex-public-fork-install.md)
- Package truth: `ycc/settings/packages.json` (`scripts/package_model.py`)
- Live guide: [Codex Install](../codex.md); v6 index: [v6 README](README.md)
