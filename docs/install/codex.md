# Codex Install Guide

This guide covers Codex plugin installs, Codex custom agents, and Codex Desktop.

## Quick Start

From the repository root:

```bash
./install.sh install --target codex
```

The default `base` step generates and validates the Codex bundle, links the
plugin tree into `~/.codex/plugins/ycc/`, syncs custom agents into
`~/.codex/agents/`, registers the bundle in
`~/.agents/plugins/marketplace.json`, and installs + enables it with
`codex plugin add ycc@local-ycc-plugins` (Codex 0.160+). Codex snapshots the
plugin into `~/.codex/plugins/cache/local-ycc-plugins/ycc/<version>/`, so rerun
the base step after regenerating the bundle.

The marketplace entry's path is `./.agents/plugins/ycc`: Codex resolves local
sources against the marketplace root (the directory holding
`.agents/plugins/marketplace.json`, here `$HOME`), not against the JSON file.
Older entries written as `./plugins/ycc` resolve to a missing `~/plugins/ycc`
and show "Failed to load plugin details"; rerunning the base step rewrites
them.

Restart Codex after the install.

## Add Settings And Rules

For the full local Codex setup:

```bash
./install.sh sync --target codex --intent base,settings,mcp,plugins,rules
```

The step-flag `install` form is equivalent:

```bash
./install.sh install --target codex --settings --rules
```

Step behavior:

| Step       | Effect                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `base`     | In local mode, generates and validates the Codex bundle, links `~/.codex/plugins/ycc/` and `~/.agents/plugins/ycc` to `.codex-plugin/ycc/`, installs custom agents from `.codex-plugin/agents/` into `~/.codex/agents/` (your own agents stay), and registers the marketplace path `./.agents/plugins/ycc`. Repo mode registers the git-subdir source and does not create those local links. See [Local Vs Repo Mode](#local-vs-repo-mode). |
| `skills`   | Generates the skills and installs each into `~/.codex/skills/<name>` (helpers in `~/.codex/skills/_shared`), with plugin paths re-pointed. No plugin link, cache or marketplace entry.                                                                                                                                                                                                                                                      |
| `agents`   | Generates the custom agents and installs each into `~/.codex/agents/<name>.toml`, leaving your own agents alone.                                                                                                                                                                                                                                                                                                                            |
| `settings` | Merges managed keys from `.codex-plugin/config/config.toml` into `~/.codex/config.toml`. Plugin enablement lives in the same file, so the `plugins` intent also maps here.                                                                                                                                                                                                                                                                  |
| `mcp`      | Merges `[mcp_servers.*]` from `.codex-plugin/config/config.toml` into `<project>/.codex/config.toml` (or `~/.codex/config.toml` with `--global`).                                                                                                                                                                                                                                                                                           |
| `rules`    | Symlinks `.codex-plugin/config/default.rules` and `AGENTS.md` into `~/.codex/`; Codex reads `AGENTS.md`, not `CLAUDE.md`.                                                                                                                                                                                                                                                                                                                   |

Settings merge without rewriting the rest of TOML: comments, local trusted
projects, account-specific connectors, tokens, and unknown tables stay intact.
Managed defaults are `gpt-6-astra` at Medium effort for the main agent and
`gpt-5.6-sol` at High effort for spawned agents (`[agents]` defaults). `--rules`
symlinks the global rules so edits stay live.

## Global Rules

Codex loads global instructions from `~/.codex/AGENTS.md` (or an
`AGENTS.override.md` under `CODEX_HOME`); see the
[official AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
The installer uses the default home path, links the complete tool-neutral body
as `AGENTS.md`, and does not alter overrides. `default.rules` is separate command
approval policy. `CLAUDE.md` is not a native global filename: no new link is made.
Existing legacy links stay in place until `remove --intent rules`, which removes
only links owned by this checkout, never real files or foreign links.

## Local Vs Repo Mode

Local mode is the default and is best for contributors:

```bash
./install.sh install --target codex --mode local
```

In local mode, the installer symlinks:

```text
~/.codex/plugins/ycc/ -> <repo>/.codex-plugin/ycc/
~/.agents/plugins/ycc -> <repo>/.codex-plugin/ycc/
```

`codex plugin add` then copies the plugin into Codex's versioned cache. Codex
builds without the plugin CLI fall back to the legacy hand-written cache at
`~/.codex/plugins/cache/local-ycc-plugins/ycc` (a flat copy with a
`skills/.codex-plugin/plugin.json` compatibility manifest); the installer
removes that flat copy once the CLI is available.

After editing source files under `ycc/`, regenerate the Codex bundle before
reloading Codex:

```bash
./scripts/sync.sh --only codex
```

Repo mode writes a git-subdir marketplace entry — Codex clones
`https://github.com/yandy-r/claude-plugins.git` at `main` and pulls the bundle
from the `./.codex-plugin/ycc` subdirectory:

```bash
./install.sh install --target codex --mode repo
```

Use repo mode for non-developer installs that should track the published
repository.

## Selective Steps

Use `--only` to run exactly the listed steps:

```bash
./install.sh install --target codex --only base
./install.sh install --target codex --only settings
./install.sh install --target codex --only rules
./install.sh install --target codex --only settings,rules
./install.sh install --target codex --only mcp                   # <project>/.codex/config.toml
./install.sh install --target codex --only mcp --global          # ~/.codex/config.toml
./install.sh remove --target codex --only mcp --global   # remove managed servers
```

Codex loads a project `.codex/config.toml` only when the project is trusted in
`~/.codex/config.toml`. MCP servers moved from the `settings` step to the `mcp`
step; pass `--global` to keep writing the user config. See
[Project Vs Global Scope](README.md#project-vs-global-scope) and
[Removing Installed Config](README.md#removing-installed-config).

If `~/.codex/plugins/ycc/` already exists as a real directory from an older
install flow, remove it before rerunning the local-mode base step:

```bash
rm -rf ~/.codex/plugins/ycc
./install.sh install --target codex --only base
```

If you clear `~/.codex/plugins/cache/`, rerun the base step so
`codex plugin add` re-creates the snapshot:

```bash
./install.sh install --target codex --only base
```

## Codex Desktop

Codex Desktop uses the same installed plugin and custom-agent locations when it
reads the standard Codex config directories:

| Surface            | Location                                                  |
| ------------------ | --------------------------------------------------------- |
| Plugin tree        | `~/.codex/plugins/ycc/`                                   |
| Marketplace source | `~/.agents/plugins/ycc`                                   |
| Enabled cache      | `~/.codex/plugins/cache/local-ycc-plugins/ycc/<version>/` |
| Custom agents      | `~/.codex/agents/`                                        |
| Config             | `~/.codex/config.toml`                                    |
| Marketplace        | `~/.agents/plugins/marketplace.json`                      |

Recommended desktop install:

```bash
./install.sh install --target codex --mode repo --settings --rules
```

Then restart Codex Desktop and install `ycc` through the desktop app's plugin UI
or `/plugins` surface.

For contributor/local desktop testing, use local mode instead:

```bash
./install.sh install --target codex --settings --rules
```

After local source edits, run `./scripts/sync.sh --only codex`, then restart or
reload Codex Desktop.

If Codex Desktop does not show `ycc`, confirm it is using the same `~/.codex/`
and `~/.agents/plugins/marketplace.json` locations as the Codex CLI/TUI.

## Codex Notes

- Codex support is native. Skills are packaged as a Codex plugin and agents are
  emitted as Codex custom-agent TOMLs.
- Codex does not install this repository's custom slash-command layer. Use the
  bundled skills directly and Codex built-ins such as `/plan` and `/review`.
- Generated Codex skill bodies assume the managed path
  `~/.codex/plugins/ycc/`. The installer creates that path as a symlink in local
  mode.
