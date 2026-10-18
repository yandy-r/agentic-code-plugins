# Claude Install Guide (v6 native packages)

Claude Code installs `ycc` as native plugins from the `ycc` marketplace in this
repository (`yandy-r/ystack`). For the checkout-based `install.sh` route and
the pieces plugins cannot carry (rules, instructions, settings, statusline),
see [Claude Install](../claude.md).

## Install

```bash
claude plugin marketplace add yandy-r/ystack

# Everything: ycc + ycc-mcp + ycc-hooks through the ycc-all dependencies
claude plugin install ycc-all@ycc

# Or pick the parts
claude plugin install ycc@ycc
claude plugin install ycc-mcp@ycc
claude plugin install ycc-hooks@ycc
```

`ycc-hooks@ycc` needs Claude Code **2.1.300** or later; older clients keep the
installer-managed hooks. Run `/reload-plugins` or start a new session after
installing.

From a checkout, `./install.sh install --target claude` registers the same
marketplace and installs `ycc@ycc` (`claude plugin marketplace add <repo>
--scope user`, then `claude plugin install ycc@ycc --scope user`); settings,
rules, MCP, hooks, and mods stay on `install.sh` steps as documented in the
live guide.

## v6 Native Package Model

`ycc/settings/packages.json` is the package truth (loaded through
`scripts/package_model.py`); ADR 0001
([package model and versioning](../../internal/adr/0001-package-model-and-versioning.md))
is the decision record. Package IDs use the component name with `ycc` as the
marketplace:

| ID              | Package                          | Status                                                                                                   |
| --------------- | -------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `ycc@ycc`       | 49 skills, 55 agents, `_shared`  | Listed; skills and agents stay in `ycc` for all of v6.                                                   |
| `ycc-mcp@ycc`   | Native MCP-only plugin           | Listed.                                                                                                  |
| `ycc-hooks@ycc` | Native `hooks/hooks.json` plugin | Listed; requires Claude Code **2.1.300**.                                                                |
| `ycc-all@ycc`   | Meta plugin (no components)      | Listed; depends on `ycc`, `ycc-mcp`, and `ycc-hooks`.                                                    |
| `ycc-agents`    | Agents-only plugin               | **Deferred to v7.0.0** — qualified `ycc-agents:` references are a breaking namespace change (see below). |

Each package has its own distinct manifest `name`. No package reuses the `ycc`
manifest name: the namespace spike found that a shared name silently splits
runtime resolution between skills (first-installed wins) and agents
(last-installed wins).

Generated payloads live under `packages/claude/` (`ycc-mcp`, `ycc-hooks`,
`ycc-all`); see
[Claude native add-on packages](../../internal/claude-native-packages.md).

The `ycc-hooks` package relocates only the `WorktreeCreate` registration
committed in `ycc/settings/settings.json`. Its `hooks/hooks.json` does **not**
register `SessionStart` or activate herdr;
`scripts/generate_claude_packages.py` rejects other registered hook events.

## Config Shape

Claude Code writes the following to `~/.claude/settings.json` after the
installs above (you can also enable them there directly):

```json
{
  "enabledPlugins": {
    "ycc@ycc": true,
    "ycc-mcp@ycc": true,
    "ycc-hooks@ycc": true
  },
  "extraKnownMarketplaces": {
    "ycc": {
      "source": { "source": "github", "repo": "yandy-r/ystack", "ref": "main" },
      "autoUpdate": true
    }
  }
}
```

Installing only the meta plugin expands the same set through the manifest
dependency list:

```json
{ "enabledPlugins": { "ycc-all@ycc": true } }
```

The generated `ycc-all` manifest declares bare-name dependencies `ycc`,
`ycc-mcp`, `ycc-hooks` (no version ranges). Bare names resolve only inside one
relative-path marketplace, so every `ycc-all` dependency must stay in the same
`ycc` catalog.

## Tested Baselines And Version Boundaries

Spike test versions are data points, not claimed minimums:

- **Namespace / cross-plugin dispatch (YAN-1121):** Claude Code **2.1.143**
  (candidate floor) and **2.1.300** (latest at test time). Distinct manifest
  names with qualified `ycc-agents:` references: Go on both; shared manifest
  name: No-Go on both.
- **Plugin-hook fixtures (YAN-1122):** a recording `SessionStart` fixture
  fires from a plugin on both 2.1.143 and 2.1.300; the `WorktreeCreate`
  fixture fires **only on 2.1.300** (silently absent on 2.1.143). Hence the
  documented 2.1.300 minimum for `ycc-hooks@ycc`, which registers only
  `WorktreeCreate`. No version between the two pins was tested, and the
  fixture's `SessionStart` probe did not execute the real herdr script.
- **Dependency installation:** the native-package smoke harness installed
  `ycc-all` and observed automatic installation of `ycc`, `ycc-mcp`, and
  `ycc-hooks` on Claude Code **2.1.301**, from a local directory-source
  marketplace, with no Claude session or MCP execution. The v6.0.0 maintainer
  verification (tracked in YAN-1141) additionally covered a published install
  on a clean host: `claude plugin install ycc-all@ycc` installed the three
  packages. Dependency
  support on the 2.1.143 candidate baseline and any lower dependency-capable
  version are **not established**. On those clients, install `ycc@ycc` and
  `ycc-mcp@ycc` individually; `ycc-hooks@ycc` needs Claude Code 2.1.300 or later,
  so clients below that keep the installer-managed hooks.

## Native Vs Fallback

- **Native (plugin) layer:** skills, agents, `_shared`, MCP connections, and
  (at ≥2.1.300) hooks ship as marketplace plugins with the IDs above.
- **Fallback (`install.sh`) layer:** Claude **rules**, `CLAUDE.md`
  instructions, settings, and the statusline have no plugin-manifest component
  and stay on `install.sh`. There is no Claude `ycc-rules` package;
  `installer-fallback` in `packages.json` is an internal modeling key, never
  an installable ID.

## Migration CLI

Preview the global Claude migration, then explicitly apply it:

```bash
./install.sh migrate --target claude
./install.sh migrate --target claude --apply
```

The default dry-run writes no config, state, build output, or CLI state and
uses the same state-based cleanup plan as apply. Symlinked configuration
files are retained with a notice, preserving dotfiles links.
Migration does not install packages — install them first (see above). Hook cleanup requires
`ycc-hooks@ycc` to be explicitly enabled, and MCP cleanup requires
`ycc-mcp@ycc` to be explicitly enabled. `ycc-all@ycc` enablement alone is not
evidence that either dependency is installed and enabled.

Apply prunes only proven installer-owned hook commands in
`~/.claude/settings.json`, preserving user-owned commands even within the
same event group. Managed global MCP entries are removed only with ownership
proof; project MCP files are not touched. Link cleanup removes only symlinks
that still point at this checkout's managed source, never real files or
foreign links. Edited values and uncertain ownership are retained and
reported, repeated migration is safe, and `--force` is rejected.

Without the explicit enablement the dry-run prints `Claude hooks retained:
ycc-hooks@ycc is not explicitly enabled` and `Claude MCP retained:
ycc-mcp@ycc is not explicitly enabled`, and leaves those entries alone. The
usual order is: install `ycc-hooks@ycc` / `ycc-mcp@ycc`, run
`./install.sh migrate --target claude --apply`, then rerun it to confirm it is
stable.

This cleanup is not a Claude session, MCP execution, or hook-dispatch check.
`install.sh install --package <ids> --target claude` is a checkout-based
file/config delivery route (it accepts `ycc`, `ycc-mcp`, and `ycc-hooks`, not
`ycc-all`); it does not replace the marketplace installs above.

## Duplicates And Coexistence

- **Hooks double-run.** A plugin hook and a settings-registered hook for the
  same event **both execute** — the spike's recording fixtures verified 1 + 1
  counts for `SessionStart` on both pinned versions and for `WorktreeCreate`
  on 2.1.300, including when the two copies run the literal same script. The
  runtime does no dedupe, so enabling `ycc-hooks@ycc` while the installer's
  settings hook remains would duplicate `WorktreeCreate` runs; run
  `./install.sh migrate --target claude --apply` after enabling it. The `SessionStart` double-run result concerns spike
  fixtures only: the actual package has no `SessionStart` registration and
  does not produce duplicate herdr reports.
- **Migration constraint (implemented).** Migration removes only
  installer-owned settings hook commands with legacy managed-state or source
  hash proof, preserving any user hooks in the same event array. This uses
  command-level pruning in `scripts/merge_managed_config.py`, not whole-event
  removal; uncertainty is reported rather than forced.
- **Plugin + file copy.** A native plugin and an install.sh file copy can both
  be installed; there is no dedupe key between them, so use `migrate` when
  moving an installer-managed setup onto the native packages.
- **Standalone slices.** Installing `--only skills` (or the `commands` alias)
  alongside `base` lists every skill twice (`ycc:<name>` and `<name>`); the
  installer warns.

## Deferred: `ycc-agents` Split (v7)

Splitting agents out of `ycc` requires qualified `ycc-agents:<agent>`
references in dispatches and `skills:` frontmatter — a breaking namespace
change. The spike proved the mechanics work on both pinned versions, but v6
keeps agents inside `ycc`. Nothing in this guide installs or references the
deferred `ycc-agents` package as an installable ID.

## Evidence Index

- [ADR 0001: package model and versioning](../../internal/adr/0001-package-model-and-versioning.md)
- [Claude namespace spike (YAN-1121)](../../internal/spikes/claude-namespace.md)
- [Claude hooks spike (YAN-1122)](../../internal/spikes/claude-hooks.md)
- [Claude native add-on packages (YAN-1130)](../../internal/claude-native-packages.md)
- Package truth: `ycc/settings/packages.json` (`scripts/package_model.py`)
- Live guide: [Claude Install](../claude.md); v6 index: [v6 README](README.md)
