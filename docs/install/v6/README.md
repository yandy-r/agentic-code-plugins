# ycc v6 Install Drafts

> **DRAFT — unwired for v6.** These pages describe the planned native-package
> install surface targeted at v6.0.0. The hidden native packages under
> `packages/` are **not installable from any production catalog today**:
> nothing new is listed in a marketplace (Claude `ycc@ycc` stays the only
> listed, shipping entry), the opencode npm package is unpublished, and the
> commands shown in these drafts (`install.sh migrate`, `install.sh --package`)
> are planned v6 commands, not implemented today. The live, working install
> commands are the `install.sh` file-copy path documented in `docs/install/` —
> they are unchanged and remain the supported route. The repository name is
> also unchanged today: `yandy-r/claude-plugins`.

This directory is a draft tree only. It is not linked from the root README or
the live `docs/install/README.md`; nothing here affects production navigation.

| Runtime  | Guide                      |
| -------- | -------------------------- |
| Claude   | [claude.md](claude.md)     |
| Codex    | [codex.md](codex.md)       |
| Cursor   | [cursor.md](cursor.md)     |
| opencode | [opencode.md](opencode.md) |
| agents   | [agents.md](agents.md)     |

## Native vs fallback by runtime

The package truth is `ycc/settings/packages.json`; the summary below matches
that model. Native package IDs are `<package>@ycc`. `ycc-rules@ycc` is
Cursor-only. `installer-fallback` is an internal modeling key for
installer-only artifacts — it is not an installable package ID.

The live baselines every runtime keeps until (and mostly after) the flip —
these are the current, runnable commands, documented fully in `docs/install/`:

```bash
./install.sh install --target <claude|cursor|codex|opencode|agents>
./install.sh sync --target <t> --intent <intents>
```

| Runtime  | Native in v6 (hidden until the listing flip)                                                                                                                   | Fallback today (live `install.sh`)                                                                                                                                                                                                                         | Not installable                                                                                                                    |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Claude   | `ycc@ycc` (listed, shipping today), `ycc-hooks@ycc`, `ycc-mcp@ycc`, `ycc-all@ycc` (meta, depends on the others; hidden)                                        | `install.sh --target claude`: plugin registration plus file-copy rules, `CLAUDE.md` instructions, settings, and statusline — no Claude `ycc-rules` exists                                                                                                  | Claude `ycc-agents` (agents-only package) deferred to v7.0.0; qualified references would be a breaking namespace change            |
| Codex    | `ycc@ycc` (skills + shared), `ycc-mcp@ycc` (both hidden; current catalog is `ycc@local-ycc-plugins`)                                                           | `install.sh --target codex`: agents TOML, `AGENTS.md` instructions, config settings (Codex plugins cannot carry these)                                                                                                                                     | Codex `ycc-hooks` excluded: no-go until verified (YAN-1149); hooks stay out of the Codex bundle                                    |
| Cursor   | `ycc@ycc` (skills, agents, commands, shared), `ycc-rules@ycc`, `ycc-mcp@ycc`, `ycc-hooks@ycc` (`sessionStart` only); all hidden                                | `install.sh --target cursor`: base bundle (skills, agents, rules) with opt-in settings and MCP merges; **no hooks** — the `hooks` intent is a no-op and `WorktreeCreate` is not implemented for Cursor (the fallback `cli-config.json` registers no hooks) | — (all four modeled Cursor packages stay unlisted with no root marketplace until the flip)                                         |
| opencode | `@yandy-r/ycc-opencode` (one npm V2 plugin that would register skills, agents, commands, shared, MCP, instructions — modeled from the v2.0.29 spike mechanism) | `install.sh --target opencode`: file copy of skills, agents, commands, shared, `opencode.json` settings, `AGENTS.md` instructions — **primary and unchanged**                                                                                              | — (the npm package is experimental and opt-in; the file copy is never replaced as the default)                                     |
| agents   | none — file copy only                                                                                                                                          | `install.sh --target agents`: skills + `ycc-shared` into `~/.agents/`                                                                                                                                                                                      | The `npx skills` path cannot replace the file copy (spike: shared helpers not delivered; bare-repo discovery finds the wrong tree) |

### Duplicates and what migration must delete

- **Claude:** a native plugin and the installer-merged settings hooks both run;
  settings + plugin copies do not dedupe. Native hooks rollout waits for
  installer-owned command-level dedupe.
- **Codex:** the current catalog ID is `ycc@local-ycc-plugins` (marketplace
  `local-ycc-plugins`, source `./plugins/ycc`). It stays active until the v6
  flip; the planned listing is `ycc@ycc` from `.agents/plugins/marketplace.json`
  with a `local` source at `./.codex-plugin/ycc`.
- **Cursor:** `~/.cursor/skills/<name>` copies and plugin skills do not share a
  dedupe key, so both stay. Migration must remove confirmed installer-owned
  copies while preserving user-owned files. No ownership-aware migration is
  implemented today; live bundle removal deletes by name, not ownership. See
  [cursor.md](cursor.md) for the hazard and manual inventory/backup procedure.
- **opencode / agents:** file copies are the whole story today; see
  [opencode.md](opencode.md) and [agents.md](agents.md).

## Planned installer surface (not runnable today)

`install.sh --package <name>` and `install.sh migrate --target <t>` are
**planned but not implemented**. They are documented in the per-runtime drafts
as future behavior only; no command shown for them can be run in the current
tree.

## Evidence

Version claims below are data points from spike harnesses, not minimum
supported versions, except where explicitly established (Claude hooks need
Claude Code 2.1.300+; Cursor manifests declare the tested floor 3.24.12).

- Package model: `docs/internal/adr/0001-package-model-and-versioning.md`
- Spikes: `docs/internal/spikes/{claude-namespace,claude-hooks,codex-marketplace,cursor-plugin,opencode-config-hook,npx-skills,codex-public-fork-install}.md`
- Native package layouts: `docs/internal/{claude-native-packages,cursor-native-packages}.md`
