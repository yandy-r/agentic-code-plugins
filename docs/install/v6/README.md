# ycc v6 Install Drafts

> **DRAFT — unwired for v6.** These pages describe the native-package install
> surface targeted at v6.0.0. The hidden native packages under `packages/`
> remain **unlisted in production catalogs**: Claude `ycc@ycc` stays the only
> listed, shipping entry. The experimental opencode npm package is generated
> and its tag-triggered publishing workflow is implemented; neither fact
> establishes that a version has actually been published to npm.
> `install.sh migrate` is implemented as a dry-run-first command for Claude,
> Codex, and Cursor; `install.sh --package` remains planned, not implemented.
> The live install commands in `docs/install/` are unchanged and remain the
> supported install route. The repository was renamed to
> `yandy-r/ystack`.

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

| Runtime  | Native in v6 (hidden until the listing flip)                                                                                                                  | Fallback today (live `install.sh`)                                                                                                                                                                                                                         | Not installable                                                                                                                    |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Claude   | `ycc@ycc` (listed, shipping today), `ycc-hooks@ycc`, `ycc-mcp@ycc`, `ycc-all@ycc` (meta, depends on the others; hidden)                                       | `install.sh --target claude`: plugin registration plus file-copy rules, `CLAUDE.md` instructions, settings, and statusline — no Claude `ycc-rules` exists                                                                                                  | Claude `ycc-agents` (agents-only package) deferred to v7.0.0; qualified references would be a breaking namespace change            |
| Codex    | `ycc@ycc` (skills + shared), `ycc-mcp@ycc` (both hidden; current catalog is `ycc@local-ycc-plugins`)                                                          | `install.sh --target codex`: agents TOML, `AGENTS.md` instructions, config settings (Codex plugins cannot carry these)                                                                                                                                     | Codex `ycc-hooks` excluded: no-go until verified (YAN-1149); hooks stay out of the Codex bundle                                    |
| Cursor   | `ycc@ycc` (skills, agents, commands, shared), `ycc-rules@ycc`, `ycc-mcp@ycc`, `ycc-hooks@ycc` (`sessionStart` only); all hidden                               | `install.sh --target cursor`: base bundle (skills, agents, rules) with opt-in settings and MCP merges; **no hooks** — the `hooks` intent is a no-op and `WorktreeCreate` is not implemented for Cursor (the fallback `cli-config.json` registers no hooks) | — (all four modeled Cursor packages stay unlisted with no root marketplace until the flip)                                         |
| opencode | `@yandy-r/ycc-opencode` (generated npm V2 plugin registering skills, agents, namespaced commands, shared helpers, MCP, instructions; experimental and opt-in) | `install.sh --target opencode`: file copy of skills, agents, commands, shared, `opencode.json` settings, `AGENTS.md` instructions — **primary and unchanged**                                                                                              | — (the npm package is unlisted and opt-in; registry publication is separate from generation and the implemented publish workflow)  |
| agents   | none — file copy only                                                                                                                                         | `install.sh --target agents`: skills + `ycc-shared` into `~/.agents/`                                                                                                                                                                                      | The `npx skills` path cannot replace the file copy (spike: shared helpers not delivered; bare-repo discovery finds the wrong tree) |

### Duplicates and what migration removes

- **Claude:** a native plugin and installer-merged settings hooks both run;
  settings + plugin copies do not dedupe. Migration prunes only proven
  installer-owned hook commands when `ycc-hooks@ycc` is explicitly enabled,
  preserving user commands in the same event. It does not infer enablement
  from `ycc-all@ycc`. Managed MCP removal similarly requires explicit
  `ycc-mcp@ycc` enablement; only global config files and owned links are in
  scope.
- **Codex:** the current catalog ID is `ycc@local-ycc-plugins` (marketplace
  `local-ycc-plugins`, source `./plugins/ycc`). It stays active until an
  eligible native `ycc` catalog is available (YAN-1140). Production apply
  fails closed before cleanup or any CLI call while that gate is unmet;
  dry-run explains the gate and retains the legacy install. A staged native
  catalog can be selected with `--marketplace-source <dir>` (Codex only),
  subject to the same catalog and payload checks. Native installation and
  installed/enabled verification must succeed before retiring legacy entries.
  Migration never removes anything under `~/.codex/agents/`.
- **Cursor:** file copies and plugin skills do not share a dedupe key.
  Migration removes only byte-identical canonical copies or exactly owned
  symlinks across installed skills, agents, rules, and shared helpers. Edited
  and foreign entries remain with conflict reports; recorded names alone
  never authorize deletion. It prints the interactive `/add-plugin` step,
  not an automatic install or a claim of runtime verification.
- **opencode:** no migration is supported; the file copy stays primary. The
  generated npm alternative is opt-in; same-ID file-copy definitions can
  override package content, while namespaced package commands coexist with
  bare file-copy commands. See [opencode.md](opencode.md) before opting in.
- **agents:** no migration is supported; file copy only. See
  [agents.md](agents.md).

## Migration CLI

Preview first; `migrate` defaults to dry-run and writes no config, state,
build output, or CLI state. Only `--apply` makes changes:

```bash
./install.sh migrate --target claude
./install.sh migrate --target codex
./install.sh migrate --target cursor
./install.sh migrate --target claude --apply
./install.sh migrate --target codex --apply
./install.sh migrate --target cursor --apply
```

`--target all` resolves to exactly Claude, Codex, and Cursor; opencode and
agents are excluded from `all`, and naming either target explicitly is
rejected. Migration preserves user edits/data and uncertain entries, is safe
to run repeatedly, and rejects `--force`. See each runtime guide for gates.
For Codex, apply checks installed/enabled CLI state before retiring legacy;
that metadata check is not runtime session, MCP execution, or hook-dispatch
verification.

`install.sh --package <name>` (package-graph closure expansion) is still
**planned and not implemented**; it is not a runnable command today.

## Evidence

Version claims below are data points from spike harnesses, not minimum
supported versions, except where explicitly established (Claude hooks need
Claude Code 2.1.300+; Cursor manifests declare the tested floor 3.24.12;
the generated opencode npm manifest declares `engines.opencode: >=2.0.30`).

- Package model: `docs/internal/adr/0001-package-model-and-versioning.md`
- Spikes: `docs/internal/spikes/{claude-namespace,claude-hooks,codex-marketplace,cursor-plugin,opencode-config-hook,npx-skills,codex-public-fork-install}.md`
- Native package layouts: `docs/internal/{claude-native-packages,cursor-native-packages}.md`
- opencode npm implementation: `scripts/generate_opencode_package.py`,
  `packages/opencode/ycc-opencode/{package.json,index.js,registration.json}`,
  `.github/workflows/release.yml`, and `scripts/opencode_npm_release.py`
