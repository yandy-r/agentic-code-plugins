# Cursor v6 Install Draft

> **DRAFT — unwired for v6.** The native Cursor packages described here are
> generated under `packages/cursor/` but are **hidden and not installable from
> any production catalog today**: every entry is `listed: false` in
> `ycc/settings/packages.json`, there is no root `.cursor-plugin/marketplace.json`,
> and no native installer route exists. `install.sh migrate` is implemented
> as a dry-run-first cleanup command that prints the interactive install
> step; `install.sh --package` remains planned, not implemented. The live
> file-copy installer in `docs/install/` is unchanged and remains the
> supported install path.

## What exists today (baseline)

Today, and throughout v6 until the listing flip, install with the live
file-copy route:

```bash
./install.sh install --target cursor
./install.sh sync --target cursor --intent settings,rules,mcp
```

This generates and rsyncs `packages/cursor/ycc/{skills,agents}` and
`packages/cursor/ycc-rules/rules` into `~/.cursor/`, merges
`packages/cursor/installer-fallback/config/cli-config.json` into
`~/.cursor/cli-config.json`, and merges MCP servers into
`<project>/.cursor/mcp.json` (or `~/.cursor/mcp.json` with `--global`). The
`commands`, `hooks`, and `plugins` intents are no-ops for Cursor.

## Planned native packages (hidden, not installable today)

| Package     | Native ID       | Payload                                                                            | Status                                                                                                                               |
| ----------- | --------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `ycc`       | `ycc@ycc`       | `skills/`, `agents/`, `commands/` (thin files per user-invocable skill), `shared`  | Generated under `packages/cursor/ycc/`; unlisted; no root marketplace                                                                |
| `ycc-rules` | `ycc-rules@ycc` | Manifest + `rules/` from the existing Cursor rules transform (Cursor-only package) | Generated under `packages/cursor/ycc-rules/`; unlisted                                                                               |
| `ycc-mcp`   | `ycc-mcp@ycc`   | Manifest + literal `mcp.json`; `${VAR}` placeholders declared under `variables`    | Generated under `packages/cursor/ycc-mcp/`; unlisted; no secret literals ever committed                                              |
| `ycc-hooks` | `ycc-hooks@ycc` | `hooks/hooks.json` + `herdr-session-start.sh`; `sessionStart` only                 | Generated under `packages/cursor/ycc-hooks/`; unlisted; `WorktreeCreate` is not implemented for Cursor — the fallback ships no hooks |

Every generated manifest carries `minClientVersions.cursor: 3.24.12`. That is
the **tested floor** from the spike (Cursor IDE 3.24.12, agent CLI
2026.10.14-941492e); no older minimum is established or claimed.

## Planned marketplace shape (future, not current)

The future marketplace will use the repository URL valid after the owner-led
rename/reference flip. No runnable registration command is provided here:
the current repository has no Cursor marketplace, and no v6 tag or catalog
availability is implied.

The planned layout is a root `.cursor-plugin/marketplace.json` whose entries
point at the four generated package roots under `packages/cursor/` with
relative `source` paths (exact source form is finalized at the flip PR; the
spike verified string and object source forms).
The spike established:

- **Marketplace registration: Go** at user scope (`agent plugin marketplace add <github-url>`),
  without installing the Cursor GitHub App.
- **Pinning: Go** for the marketplace ref — `--git-ref <tag|sha>` stores the
  full commit SHA; a missing ref fails closed.
- **One entry per directory.** The server-side `update` collapses two entries
  pointing at the same relative directory. A future catalog must therefore
  avoid duplicate sources; no production Cursor catalog exists today.
- Relative `source` entries merge the directory's `.cursor-plugin/plugin.json`.

## Interactive install and evidence gates

There is **no non-interactive install**: the CLI has no `plugin install`
subcommand; `marketplace add` prints `Tip: use /plugins in interactive mode`.
The interactive `/add-plugin` flow in the agent TUI (or the Cursor IDE) is the
planned user install step after the flip. Do **not** claim the catalog is
available or drive it today: **interactive installation and installed-plugin
runtime verification remain open gates** and block listing.

What is proven so far (agent CLI 2026.10.14-941492e): `agent --plugin-dir
<dir>` loads a local plugin's `sessionStart` hook in that one process without
an account install. The generated `ycc-hooks` package loaded this way sent a
session identity report to a disposable socket. That is per-process load
evidence, not account-installed runtime proof.

## Hooks: sessionStart only

Cursor `hooks.json` runs `sessionStart` (payload `hook_event_name:
"sessionStart"`). `WorktreeCreate` does not exist in the CLI bundle, and the
Claude-style `SessionStart` spelling is not a Cursor hook event — a hooks file
naming unknown events silenced the whole file in the spike. Release gate:
`ycc-hooks@ycc` ships `sessionStart` only. `WorktreeCreate` is unavailable — not implemented anywhere for Cursor: not in the native package and not in the file-copy installer (the `hooks` intent is a no-op; the fallback `cli-config.json` registers no hooks).

## Duplicates and migration

`~/.cursor/skills/<name>` file copies and plugin skills
(`~/.cursor/plugins/.../skills/<name>`) do **not** share a dedupe key — both
stay, and the runtime will not collapse them. Migration handles confirmed
installer copies explicitly:

```bash
./install.sh migrate --target cursor           # dry-run
./install.sh migrate --target cursor --apply
```

Dry-run writes no config, state, build output, or CLI state. Apply removes
entries under `~/.cursor/{skills,agents,rules}` only when byte-identical to
the canonical packaged source or staged installer projection, or when they
are exactly owned symlinks. The projection covers installer-specific skill
paths, `init`, and `_shared` helpers as actually installed; shared helpers
stay while any skills remain. Recorded names alone never authorize deletion.
Edited, differing, or unknown entries and foreign links stay and are
reported, even if earlier ownership state names them. Symlinked configuration
files are retained with a notice rather than replaced. Migration preserves
user data, is safe to repeat, and rejects `--force`.

Migration prints the interactive `/add-plugin` step; it does **not** install
the Cursor plugin, make the hidden catalog available, or verify a native
installed plugin at runtime. Keep using the live install route until the
listing and runtime gates above are complete.

**WARNING — name-based deletion hazard in the live installer.** The bundle branch of `install.sh remove --target cursor` (`--intent base` or `--only base`) deletes by name: `remove_mirrored_entries` (`scripts/lib/install/bundle.sh`) removes every same-named entry from `~/.cursor/{skills,agents,rules}` for each top-level entry the generated bundle ships, regardless of ownership. Your own same-named skill, agent, or rule entry would be destroyed. Do NOT treat it as a safe migration step.

**How live `remove` behaves by intent (so the hazard is understood):**

- `./install.sh remove --target cursor --intent skills,agents` removes slice entries with an ownership check (entries the installer cannot recognize as its own are kept) but never touches `~/.cursor/rules/`.
- `./install.sh remove --target cursor --intent rules` only unlinks legacy `~/.cursor/{CLAUDE.md,AGENTS.md}` symlinks that point into this repo — never `~/.cursor/rules/`.
- Only the name-based `base` branch above touches the `~/.cursor/rules/` bundle generated by the base install.

**Migration after the listing flip:** Preview with `migrate --target cursor`
and review every retained conflict. Back up your Cursor config before
applying. Use `migrate --target cursor --apply` for the confirmed-copy cleanup,
then follow `/add-plugin` interactively once the native plugin is actually
available. Handle any edited/foreign entries manually; do not substitute the
name-based `remove --intent base` path for safe migration.

## Secrets

`ycc-mcp@ycc` declares `${VAR}` placeholders under manifest `variables`; the
generator rejects credential-shaped literals. No secret values appear in any
package or this document.

## Evidence

- `docs/internal/spikes/cursor-plugin.md` (YAN-1124: IDE 3.24.12, agent 2026.10.14-941492e)
- `docs/internal/cursor-native-packages.md` (YAN-1132 generator + gates)
- `docs/internal/adr/0001-package-model-and-versioning.md` (package matrix)
- `scripts/lib/install/targets/cursor.sh` (intent mapping; `rules` removal unlinks legacy instruction symlinks, while only `base` removes generated rules)
- `scripts/lib/install/bundle.sh` (`remove_mirrored_entries`: name-based deletion without ownership checks)
- `scripts/install_slices.py` (standalone slice ownership/content checks)
- `packages/cursor/installer-fallback/config/cli-config.json` (settings only; no registered hooks)
