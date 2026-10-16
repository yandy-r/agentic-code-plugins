# Claude Install Guide (v6 native packages)

> **DRAFT — unwired for v6: hidden native packages are not installable from
> production catalogs today.** Everything under `docs/install/v6/` is planned
> behavior, not current install instructions. For the guide that works now,
> use [Claude Install](../claude.md).

## Current Install (unchanged today)

Today Claude Code installs exactly one listed package, `ycc@ycc`, from this
checkout or the published repository:

```bash
./install.sh install --target claude
```

The `base` step runs `claude plugin marketplace add <repo> --scope user` and
`claude plugin install ycc@ycc --scope user`. Settings, rules, MCP, hooks, and
mods stay on `install.sh` steps exactly as documented in the live guide. The
v6 work below adds packages around that flow; it does not change it before
the listing flip.

## v6 Native Package Model

`ycc/settings/packages.json` is the package truth (loaded through
`scripts/package_model.py`); ADR 0001
([package model and versioning](../../internal/adr/0001-package-model-and-versioning.md))
is the decision record. Package IDs use the component name with `ycc` as the
marketplace:

| ID              | Package                          | v6.0.0 status                                                                                             |
| --------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `ycc@ycc`       | 49 skills, 55 agents, `_shared`  | Ships and stays listed; skills and agents stay in `ycc` for all of v6.                                    |
| `ycc-mcp@ycc`   | Native MCP-only plugin           | Planned in v6; unspiked; hidden until the listing flip.                                                   |
| `ycc-hooks@ycc` | Native `hooks/hooks.json` plugin | Ships hidden; documented minimum Claude Code **2.1.300**; native rollout waits for installer hook dedupe. |
| `ycc-all@ycc`   | Meta plugin (no components)      | Planned; blocked by the dependency-installation proof gate below.                                         |
| `ycc-agents`    | Agents-only plugin               | **Deferred to v7.0.0** — qualified `ycc-agents:` references are a breaking namespace change (see below).  |

Each package has its own distinct manifest `name`. No package reuses the `ycc`
manifest name: the namespace spike found that a shared name silently splits
runtime resolution between skills (first-installed wins) and agents
(last-installed wins).

Generated hidden payloads live under `packages/claude/` (`ycc-mcp`,
`ycc-hooks`, `ycc-all`); see
[Hidden Claude native add-ons](../../internal/claude-native-packages.md).
`listed: false` in `packages.json` is generator input, not a runtime field;
it does not suppress generation.

The generated `ycc-hooks` package relocates only the `WorktreeCreate`
registration committed in `ycc/settings/settings.json`. Its
`hooks/hooks.json` does **not** register `SessionStart` or activate herdr;
`scripts/generate_claude_packages.py` rejects other registered hook events.

## Planned Post-Listing Config (not runnable today)

The snippets below show the shape Claude Code writes to
`~/.claude/settings.json` **after** the v6 listing flip. They are examples
only — these IDs are not installable from the production marketplace today,
and nothing here is a command to run:

```json
{
  "enabledPlugins": {
    "ycc@ycc": true,
    "ycc-mcp@ycc": true,
    "ycc-hooks@ycc": true
  },
  "extraKnownMarketplaces": {
    "ycc": {
      "source": { "source": "github", "repo": "yandy-r/claude-plugins", "ref": "main" },
      "autoUpdate": true
    }
  }
}
```

Installing only the meta plugin is expected to expand the same set through
the manifest dependency list:

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
- **Dependency installation:** the hidden-package smoke harness installed
  `ycc-all` and observed automatic installation of `ycc`, `ycc-mcp`, and
  `ycc-hooks` on Claude Code **2.1.301**, from a local directory-source
  marketplace, with no Claude session or MCP execution. Dependency support on
  the 2.1.143 candidate baseline, any minimum dependency-capable version, and
  remote/public-fork installation are **not established**.

### `ycc-all` dependency proof gate

`ycc-all@ycc` must not be listed until dependency installation is proven on
the **2.1.143 candidate baseline and on the latest client**, and the
supported minimum is documented from those results. The 2.1.301 directory-source
proof alone does not satisfy the gate. This guide therefore documents
`ycc-all` as planned only — never as an install command.

## Native Vs Fallback

- **Native (plugin) layer:** skills, agents, `_shared`, MCP connections, and
  (at ≥2.1.300) hooks ship as marketplace plugins with the IDs above.
- **Fallback (`install.sh`) layer:** Claude **rules**, `CLAUDE.md`
  instructions, settings, and the statusline have no plugin-manifest component
  and stay on `install.sh`. There is no Claude `ycc-rules` package;
  `installer-fallback` in `packages.json` is an internal modeling key, never
  an installable ID.

`install.sh migrate` and `install.sh --package` (closure expansion through
the package graph) are **planned and not implemented**. They are never
runnable commands; do not document or run them as if they exist.

## Duplicates And Coexistence

- **Hooks double-run.** A plugin hook and a settings-registered hook for the
  same event **both execute** — the spike's recording fixtures verified 1 + 1
  counts for `SessionStart` on both pinned versions and for `WorktreeCreate`
  on 2.1.300, including when the two copies run the literal same script. The
  runtime does no dedupe, so enabling the current generated `ycc-hooks@ycc`
  while the installer's settings hook remains would duplicate
  `WorktreeCreate` runs. The `SessionStart` double-run result concerns spike
  fixtures only: the actual package has no `SessionStart` registration and
  does not produce duplicate herdr reports.
- **Migration constraint.** Safe migration must remove only installer-owned
  settings hook entries and preserve any user-owned hooks in the same event
  array. The current merge engine (`scripts/merge_managed_config.py`) models
  `hooks` as `map-entries` and cannot do command-level removal today; that
  merge-engine work gates the native hooks rollout.
- **Plugin + file copy.** A native plugin and an install.sh file copy can both
  be installed; the same dedupe requirement applies before native rollout.
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
- [Hidden Claude native add-ons (YAN-1130)](../../internal/claude-native-packages.md)
- Package truth: `ycc/settings/packages.json` (`scripts/package_model.py`)
- Live guide: [Claude Install](../claude.md); draft index: [v6 README](README.md)
